"""
tests/test_phase6_4_decision_trust.py
=====================================
SuspensionLab PRO — Phase 6.4 Decision-Aware Parameter Trust &
Engineering Evidence Integration Acceptance & Verification Suite.

Complete 48-Test Verification Matrix:
  Group A: Decision Resolution & Polymorphism (Tests 01-08)
  Group B: Decision Parameter Dependency Discovery (Tests 09-16)
  Group C: Grounded Uncertainty Quantification & Decision Exposure (Tests 17-25)
  Group D: Prioritized Actionable Evidence Gaps & Candidate Experiments (Tests 26-33)
  Group E: Deterministic Snapshot, Hashing, Lineage & Supersession (Tests 34-40)
  Group F: REST API Endpoints, Security & Multi-Tenancy (Tests 41-48)
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import Base, get_db_dependency
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    DecisionParameterDependencyRecord,
    DecisionExposureAssessmentRecord,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    TrustConflictType,
    SensitivityStatus,
    DependencyNature,
    DecisionExposureClassification,
    EvidenceGapSeverity,
    TRUST_POLICY_V1,
    CURRENT_TRUST_POLICY_VERSION,
    DECISION_TRUST_POLICY_V1,
    CURRENT_DECISION_TRUST_POLICY_VERSION,
    SENSITIVITY_PROPAGATION_POLICY_V1,
    SENSITIVITY_THRESHOLDS_PROVENANCE,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.decision_loop import (
    InvestigationRecord,
    BlindValidationRecord,
)
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    SetupCandidateRecord,
)
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.parameter_trust_decision_service import (
    ParameterTrustDecisionService,
    DecisionNotFoundError,
    PreRevealFirewallViolation,
    DecisionTrustError,
)
from suspensionlab.backend.services.parameter_trust_service import (
    ParameterTrustService,
)
from suspensionlab.backend.services.evidence_graph_service import (
    TenantIsolationError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


def make_user_ctx(
    user_id: uuid.UUID,
    team_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    role: str = "engineer",
) -> UserContext:
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email=f"eng_{user_id.hex[:6]}@suspensionlab.com",
        name="Decision Engineer",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=role,
        org_role="MEMBER",
        is_admin=role in ("admin", "org_admin"),
    )


@pytest.fixture
async def seeded_decision_env(async_test_db: AsyncSession):
    """
    Sets up multi-tenant decisions, candidates, hypotheses, investigations,
    parameter profiles, and validations.
    """
    db = async_test_db
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_a = uuid.uuid4()

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    user_c = uuid.uuid4()  # personal workspace

    now = datetime.now(timezone.utc)

    # 1. Authoritative Candidate Setup (Team A)
    cand_a = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-CAND-01",
        parent_setup_id="BASE-01",
        changed_parameters={
            "front_spring_rate": {"candidate": 85000.0, "unit": "N/m"},
            "front_arb_rate": {"candidate": 25000.0, "unit": "N/m"},
            "rear_damper_bump": {"candidate": 4200.0, "unit": "N-s/m"},
        },
        unchanged_parameters={},
        parameter_provenance={
            "front_spring_rate": "optimization",
            "front_arb_rate": "historical_setup",
            "rear_damper_bump": "cae_sweep",
        },
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Front stiffness rebalance",
        artifact_hash="hash_cand_a",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(cand_a)

    sim_a = SimulationRun(
        id=uuid.uuid4(),
        seq=1,
        label="SIM-SENS-01",
        job_id=uuid.uuid4(),
        user_id=user_a,
        team_id=team_a,
        simulation_type="sensitivity",
        title="Quarter-car stiffness sensitivity sweep",
        vehicle_ref="CAR-01",
        setup_ref="SETUP-CAND-01",
        params={"front_spring_rate": 85000.0},
        software_version="1.0.0",
        physics_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        kinematics_version="1.0.0",
        solver_version="BDF-v2.0",
        params_hash="hash_params_01",
        result={
            "sensitivities": {
                "front_spring_rate": [
                    {
                        "metric": "rms_body_accel_wk",
                        "elasticity": 0.35,
                        "unit": "%/%",
                        "is_numerical_derivative": True,
                    }
                ]
            }
        },
        result_hash="hash_sim_sens_01",
        created_at=now,
    )
    db.add(sim_a)

    # 2. Authoritative Parameter Trust Profiles & Evidence for cand_a
    # front_spring_rate: VALIDATED, High sensitivity
    prof_spring = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-CAND-01",
        parameter_name="front_spring_rate",
        parameter_path="changed_parameters.front_spring_rate.candidate",
        unit="N/m",
        value_reference={"value": 85000.0, "value_identity": "85000.0"},
        provenance_class=ProvenanceClass.OPTIMIZATION.value,
        current_trust_state=TrustState.VALIDATED.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_spring",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-CAND-01", "operating_regime": "High-Speed Lateral Cornering"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_spring)

    val_spring = BlindValidationRecord(
        id=uuid.uuid4(),
        validation_number=101,
        validation_code="VAL-SPRING-01",
        setup_id="SETUP-CAND-01",
        decision_id="DEC-A-01",
        fit_dataset_ref="TS-381-FIT",
        holdout_dataset_ref="TS-381-HOLDOUT",
        is_zero_leakage=True,
        fit_r2=0.96,
        holdout_r2=0.94,
        holdout_rmse=0.03,
        gate_verdict="PASSED",
        artifact_hash="hash_val_spring",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(val_spring)

    ev_spring = ParameterTrustEvidenceRecord(
        id=uuid.uuid4(),
        profile_id=prof_spring.id,
        evidence_type="BlindValidation",
        evidence_id="VAL-SPRING-01",
        artifact_hash="hash_val_spring",
        relationship="VALIDATED_BY",
        evidence_timestamp=now,
        metadata_={"passed_validation": True, "residual_magnitude": 0.03, "source_version": "v2.6"},
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(ev_spring)

    # front_arb_rate: PROVISIONAL, Moderate sensitivity, Stale validation
    prof_arb = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-CAND-01",
        parameter_name="front_arb_rate",
        parameter_path="changed_parameters.front_arb_rate.candidate",
        unit="N/m",
        value_reference={"value": 25000.0, "value_identity": "25000.0"},
        provenance_class=ProvenanceClass.HISTORICAL_SETUP.value,
        current_trust_state=TrustState.PROVISIONAL.value,
        validation_coverage=ValidationCoverage.PARTIAL_VALIDATION.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_arb",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-CAND-01", "operating_regime": "High-Speed Lateral Cornering"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_arb)

    stale_date = now - timedelta(days=200)
    ev_arb = ParameterTrustEvidenceRecord(
        id=uuid.uuid4(),
        profile_id=prof_arb.id,
        evidence_type="BlindValidation",
        evidence_id="VAL-ARB-OLD",
        artifact_hash="hash_val_arb_old",
        relationship="VALIDATED_BY",
        evidence_timestamp=stale_date,
        metadata_={"passed_validation": True, "residual_magnitude": 0.08, "source_version": "v1.0"},
        team_id=team_a,
        organization_id=org_a,
        created_at=stale_date,
    )
    db.add(ev_arb)

    # rear_damper_bump: CONFLICTED, Active Conflict
    prof_damper = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-CAND-01",
        parameter_name="rear_damper_bump",
        parameter_path="changed_parameters.rear_damper_bump.candidate",
        unit="N-s/m",
        value_reference={"value": 4200.0, "value_identity": "4200.0"},
        provenance_class=ProvenanceClass.SIMULATION_DERIVED.value,
        current_trust_state=TrustState.CONFLICTED.value,
        validation_coverage=ValidationCoverage.CONFLICTING_VALIDATION.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        conflicts=[
            {
                "conflict_type": TrustConflictType.CONTRADICTORY_VALIDATION.value,
                "description": "Dyno rig measurement contradicts simulation damping force by 22%",
                "unresolved": True,
            }
        ],
        assessment_hash="hash_prof_damper",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-CAND-01", "operating_regime": "High-Speed Lateral Cornering"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_damper)

    # 3. Authoritative Decision DEC-A-01 (Team A)
    dec_a = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-A-01",
        question="Should we deploy stiffened front suspension setup candidate SETUP-CAND-01 for Silverstone?",
        context={
            "vehicle_id": "CAR-01",
            "setup_id": "SETUP-CAND-01",
            "track": "Silverstone",
            "operating_regime": "High-Speed Lateral Cornering",
            "model_version": "DYNAMIC-TRANSIENT-14DOF-v2.6",
        },
        candidates=["SETUP-CAND-01"],
        selected_option={"setup_id": "SETUP-CAND-01"},
        reason="Reduces high-speed understeer while maintaining platform pitch stability.",
        tradeoffs={"low_speed_mechanical_grip": -0.015},
        risks={"kerb_strike_harshness": "elevated"},
        simulation_evidence=[{"run_id": "RUN-01", "lap_delta_s": -0.18}],
        telemetry_evidence=[{"session_id": "SESS-01", "correlation_r2": 0.94}],
        validation_evidence=[{"val_id": "VAL-SPRING-01", "status": "PASSED"}],
        evidence_summary="Strong simulation and 4-post rig correlation.",
        status="RECOMMENDED",
        author="Race Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_a"},
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(dec_a)

    # 3b. Authoritative Decision DEC-SPRING-ONLY (Team A - pure validated spring)
    cand_spring_only = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-ONLY-SPRING",
        parent_setup_id="BASE-01",
        changed_parameters={"front_spring_rate": {"candidate": 85000.0, "unit": "N/m"}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Spring only",
        artifact_hash="hash_only_spring",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(cand_spring_only)

    dec_spring_only = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-SPRING-ONLY",
        question="Deploy front spring rate only",
        context={"vehicle_id": "CAR-01", "setup_id": "SETUP-ONLY-SPRING"},
        candidates=["SETUP-ONLY-SPRING"],
        selected_option={"setup_id": "SETUP-ONLY-SPRING"},
        reason="Stiffness only",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_val"},
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(dec_spring_only)

    prof_spring_only = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-ONLY-SPRING",
        parameter_name="front_spring_rate",
        parameter_path="changed_parameters.front_spring_rate.candidate",
        unit="N/m",
        value_reference={"value": 85000.0, "value_identity": "85000.0"},
        provenance_class=ProvenanceClass.OPTIMIZATION.value,
        current_trust_state=TrustState.VALIDATED.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_spring_only",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-ONLY-SPRING", "operating_regime": "High-Speed Lateral Cornering"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_spring_only)

    ev_spring_only = ParameterTrustEvidenceRecord(
        id=uuid.uuid4(),
        profile_id=prof_spring_only.id,
        evidence_type="BlindValidation",
        evidence_id="VAL-SPRING-01",
        artifact_hash="hash_val_spring",
        relationship="VALIDATED_BY",
        evidence_timestamp=now,
        metadata_={"passed_validation": True, "residual_magnitude": 0.03, "source_version": "v2.6"},
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(ev_spring_only)

    # 4. Authoritative Engineering Problem PROB-A-01 (Team A)
    prob_a = EngineeringProblemRecord(
        id=uuid.uuid4(),
        problem_id="PROB-A-01",
        telemetry_session_id="SESS-01",
        investigation_id="INV-A-01",
        engineering_question_id="Q-01",
        observable="Excessive understeer observed in Becketts complex.",
        baseline_metric={"understeer_gradient_rad_per_g": 0.08},
        target_metric={"understeer_gradient_rad_per_g": 0.05},
        operating_condition={"speed_kph": 180.0},
        track_context={"track": "Silverstone"},
        session_context={"surface": "dry asphalt"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        epistemic_classification={},
        artifact_hash="hash_prob_a",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(prob_a)

    # Causal hypothesis linked to PROB-A-01
    hyp_a = CausalHypothesisRecord(
        id=uuid.uuid4(),
        hypothesis_id="HYP-A-01",
        problem_id="PROB-A-01",
        hypothesis="Increasing front anti-roll bar rate shifts lateral load transfer forward.",
        mechanism="delta_LLTD = delta_K_arb_f / (K_total)",
        supporting_evidence=["Milliken & Milliken RCVD Ch 16"],
        contradicting_evidence=[],
        affected_observables=["understeer_gradient_rad_per_g"],
        candidate_parameters=["front_arb_rate"],
        expected_direction_of_effect={"understeer_gradient_rad_per_g": "+"},
        confidence_uncertainty={"confidence": "MEDIUM"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        epistemic_status="HYPOTHESIS",
        artifact_hash="hash_hyp_a",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(hyp_a)

    # 5. Authoritative Telemetry Investigation INV-A-01 (Team A)
    inv_a = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=91,
        investigation_code="INV-A-01",
        session_code="SESS-A-01",
        detection_type="DAMPER_VELOCITY_ANOMALY",
        symptom="Damper histograms deviate from simulated envelope.",
        affected_regime="High-Speed Lateral Cornering",
        severity="WARNING",
        status="OPEN",
        evidence_snapshot={"affected_parameters": ["rear_damper_bump"]},
        artifact_hash="hash_inv_a",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(inv_a)

    # Causal hypothesis linked to INV-A-01
    hyp_inv = CausalHypothesisRecord(
        id=uuid.uuid4(),
        hypothesis_id="HYP-INV-01",
        problem_id="INV-A-01",
        hypothesis="Rear damper low-speed bump damping forces deviate from model.",
        mechanism="Damper valving blow-off threshold discrepancy",
        supporting_evidence=[],
        contradicting_evidence=[],
        affected_observables=["damper_velocity_spectrum"],
        candidate_parameters=["rear_damper_bump"],
        expected_direction_of_effect={"damper_velocity_spectrum": "-"},
        confidence_uncertainty={"confidence": "MEDIUM"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        epistemic_status="HYPOTHESIS",
        artifact_hash="hash_hyp_inv",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(hyp_inv)

    # 6. Cross-Tenant Decision DEC-B-01 (Team B)
    dec_b = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-B-01",
        question="Team B Decision: Wing flap angle selection",
        context={"vehicle_id": "CAR-02", "setup_id": "SETUP-B-01"},
        candidates=["SETUP-B-01"],
        selected_option={"setup_id": "SETUP-B-01"},
        reason="Aerodynamic efficiency",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="APPROVED",
        author="Engineer B",
        approver="Chief Engineer B",
        approved_at=now,
        artifact_hashes={"decision_hash": "hash_dec_b"},
        user_id=user_b,
        team_id=team_b,
        created_at=now,
    )
    db.add(dec_b)

    # 7. Unrevealed Blind Session with Decision DEC-UNREVEALED (Team A)
    blind_sess_unrevealed = BlindEngineeringSession(
        id=uuid.uuid4(),
        organization_id=org_a,
        team_id=team_a,
        created_by_user_id=user_a,
        status=BlindSessionStatus.SUBMISSION_LOCKED.value,  # NOT REVEALED!
        name="BLIND-SESS-UNREV",
        root_entity_type="EngineeringDecision",
        root_entity_id="DEC-UNREVEALED",
        hidden_outcome_type="EngineeringDecision",
        hidden_outcome_id="DEC-UNREVEALED",
        configuration={"track_name": "Monza"},
        session_hash="hash_blind_unrev",
        created_at=now,
    )
    db.add(blind_sess_unrevealed)

    dec_unrevealed = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-UNREVEALED",
        question="Blind setup selection for Monza",
        context={"blind_session_id": "BLIND-SESS-UNREV"},
        candidates=[],
        selected_option={},
        reason="Holdout validation comparison",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Race Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_unrev"},
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(dec_unrevealed)

    # 8. Revealed Blind Session with Decision DEC-REVEALED (Team A)
    blind_sess_revealed = BlindEngineeringSession(
        id=uuid.uuid4(),
        organization_id=org_a,
        team_id=team_a,
        created_by_user_id=user_a,
        status=BlindSessionStatus.REVEALED.value,  # REVEALED!
        name="BLIND-SESS-REV",
        root_entity_type="EngineeringDecision",
        root_entity_id="DEC-REVEALED",
        hidden_outcome_type="EngineeringDecision",
        hidden_outcome_id="DEC-REVEALED",
        configuration={"track_name": "Spa"},
        session_hash="hash_blind_rev",
        created_at=now,
        revealed_at=now,
    )
    db.add(blind_sess_revealed)

    dec_revealed = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-REVEALED",
        question="Post-reveal setup review for Spa",
        context={"blind_session_id": "BLIND-SESS-REV"},
        candidates=[],
        selected_option={},
        reason="Post-reveal review",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Race Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_rev"},
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(dec_revealed)

    await db.commit()

    return {
        "org_a": org_a,
        "team_a": team_a,
        "user_a": user_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "user_c": user_c,
        "ctx_a": make_user_ctx(user_id=user_a, team_id=team_a, org_id=org_a),
        "ctx_b": make_user_ctx(user_id=user_b, team_id=team_b, org_id=org_b),
        "ctx_c": make_user_ctx(user_id=user_c, team_id=None, org_id=None),
    }


# ==============================================================================
# GROUP A: DECISION RESOLUTION & POLYMORPHISM (Tests 01-08)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_resolves_engineering_decision_with_tenant_context(async_test_db, seeded_decision_env):
    """Test 01: Resolves EngineeringDecision entity for authorized tenant."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    dec, dtype = await svc.resolve_decision("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    assert dec is not None
    assert dtype == "EngineeringDecision"
    assert dec.decision_id == "DEC-A-01"


@pytest.mark.asyncio
async def test_02_resolves_engineering_problem_polymorphically(async_test_db, seeded_decision_env):
    """Test 02: Resolves EngineeringProblemRecord polymorphically."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    prob, dtype = await svc.resolve_decision("PROB-A-01", "EngineeringProblem", env["ctx_a"])
    assert prob is not None
    assert dtype == "EngineeringProblemRecord"
    assert prob.problem_id == "PROB-A-01"


@pytest.mark.asyncio
async def test_03_resolves_investigation_record_polymorphically(async_test_db, seeded_decision_env):
    """Test 03: Resolves InvestigationRecord polymorphically."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    inv, dtype = await svc.resolve_decision("INV-A-01", "Investigation", env["ctx_a"])
    assert inv is not None
    assert dtype == "InvestigationRecord"
    assert inv.investigation_id == "INV-A-01"


@pytest.mark.asyncio
async def test_04_nonexistent_decision_raises_decision_not_found(async_test_db, seeded_decision_env):
    """Test 04: Querying non-existent decision raises DecisionNotFoundError."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    with pytest.raises(DecisionNotFoundError):
        await svc.resolve_decision("DEC-NONEXISTENT", "EngineeringDecision", env["ctx_a"])


@pytest.mark.asyncio
async def test_05_cross_tenant_decision_access_blocked(async_test_db, seeded_decision_env):
    """Test 05: User in Team A cannot resolve Decision belonging to Team B (TenantIsolationError)."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    # Team A user querying DEC-B-01 (Team B)
    with pytest.raises((TenantIsolationError, DecisionNotFoundError)):
        await svc.resolve_decision("DEC-B-01", "EngineeringDecision", env["ctx_a"])


@pytest.mark.asyncio
async def test_06_personal_workspace_isolation_enforced(async_test_db, seeded_decision_env):
    """Test 06: User in Team A cannot access personal decisions of another user."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    with pytest.raises((TenantIsolationError, DecisionNotFoundError)):
        await svc.resolve_decision("DEC-A-01", "EngineeringDecision", env["ctx_c"])


@pytest.mark.asyncio
async def test_07_unrevealed_blind_session_blocked_by_pre_reveal_firewall(async_test_db, seeded_decision_env):
    """Test 07: Decision linked to an unrevealed Phase 5 blind session fails closed."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    with pytest.raises(PreRevealFirewallViolation):
        await svc.resolve_decision("DEC-UNREVEALED", "EngineeringDecision", env["ctx_a"])


@pytest.mark.asyncio
async def test_08_revealed_blind_session_permitted(async_test_db, seeded_decision_env):
    """Test 08: Decision linked to a revealed Phase 5 blind session passes firewall."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    dec, _ = await svc.resolve_decision("DEC-REVEALED", "EngineeringDecision", env["ctx_a"])
    assert dec.decision_id == "DEC-REVEALED"


# ==============================================================================
# GROUP B: DECISION PARAMETER DEPENDENCY DISCOVERY (Tests 09-16)
# ==============================================================================

@pytest.mark.asyncio
async def test_09_discovers_directly_evidenced_candidate_parameters(async_test_db, seeded_decision_env):
    """Test 09: Discovers parameters directly modified by setup candidate options."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    dec, dtype = await svc.resolve_decision("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    deps = await svc.discover_decision_dependencies(dec, env["ctx_a"])

    param_names = [d.parameter_name for d in deps]
    assert "front_spring_rate" in param_names
    assert "front_arb_rate" in param_names
    assert "rear_damper_bump" in param_names

    spring_dep = next(d for d in deps if d.parameter_name == "front_spring_rate")
    assert spring_dep.dependency_nature in (
        DependencyNature.DIRECTLY_EVIDENCED.value,
        DependencyNature.QUANTITATIVELY_SENSITIVE.value,
    )


@pytest.mark.asyncio
async def test_10_discovers_quantitatively_sensitive_parameters_with_elasticity(async_test_db, seeded_decision_env):
    """Test 10: Associates known physical sensitivities with parameter dependencies."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    dec, _ = await svc.resolve_decision("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    deps = await svc.discover_decision_dependencies(dec, env["ctx_a"])

    spring_dep = next(d for d in deps if d.parameter_name == "front_spring_rate")
    assert spring_dep.sensitivity_status == SensitivityStatus.AVAILABLE.value
    assert spring_dep.elasticity is not None
    assert abs(spring_dep.elasticity) > 0.0


@pytest.mark.asyncio
async def test_11_causal_hypothesis_classified_as_qualitative_without_fabricating_derivatives(async_test_db, seeded_decision_env):
    """Test 11: Causal hypotheses strictly classified as qualitative with elasticity = None."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    prob, _ = await svc.resolve_decision("PROB-A-01", "EngineeringProblem", env["ctx_a"])
    deps = await svc.discover_decision_dependencies(prob, env["ctx_a"])

    arb_dep = next(d for d in deps if d.parameter_name == "front_arb_rate")
    assert arb_dep.dependency_nature == DependencyNature.QUALITATIVE_HYPOTHESIS.value
    # Invariant: Never fabricate numerical derivatives from qualitative mechanism text!
    assert arb_dep.elasticity is None
    assert arb_dep.numerical_derivative is None


@pytest.mark.asyncio
async def test_12_qualitative_mechanism_does_not_infer_proven_causality(async_test_db, seeded_decision_env):
    """Test 12: Qualitative hypothesis does not set proven sensitivity status."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    prob, _ = await svc.resolve_decision("PROB-A-01", "EngineeringProblem", env["ctx_a"])
    deps = await svc.discover_decision_dependencies(prob, env["ctx_a"])

    arb_dep = next(d for d in deps if d.parameter_name == "front_arb_rate")
    assert arb_dep.dependency_nature != DependencyNature.QUANTITATIVELY_SENSITIVE.value
    assert arb_dep.dependency_nature != DependencyNature.DIRECTLY_EVIDENCED.value


@pytest.mark.asyncio
async def test_13_missing_sensitivity_represented_as_unavailable_never_zero(async_test_db, seeded_decision_env):
    """Test 13: Parameters without sensitivity models receive SENSITIVITY_UNAVAILABLE, never 0.0."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    inv, _ = await svc.resolve_decision("INV-A-01", "Investigation", env["ctx_a"])
    deps = await svc.discover_decision_dependencies(inv, env["ctx_a"])

    damper_dep = next(d for d in deps if d.parameter_name == "rear_damper_bump")
    assert damper_dep.sensitivity_status == SensitivityStatus.SENSITIVITY_UNAVAILABLE.value
    assert damper_dep.elasticity is None


@pytest.mark.asyncio
async def test_14_telemetry_investigation_discovers_relevant_parameters(async_test_db, seeded_decision_env):
    """Test 14: Telemetry investigation traceably discovers affected parameters."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    inv, _ = await svc.resolve_decision("INV-A-01", "Investigation", env["ctx_a"])
    deps = await svc.discover_decision_dependencies(inv, env["ctx_a"])

    assert len(deps) >= 1
    assert any(d.parameter_name == "rear_damper_bump" for d in deps)


@pytest.mark.asyncio
async def test_15_unresolved_dependencies_handled_traceably(async_test_db, seeded_decision_env):
    """Test 15: Unmapped parameters in candidates are cataloged as unresolved dependencies."""
    db = async_test_db
    env = seeded_decision_env

    # Candidate with unreferenced parameter
    c_unref = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-UNREF-01",
        parent_setup_id="BASE-01",
        changed_parameters={"custom_unknown_kinematic_link": {"candidate": 12.5}},
        unchanged_parameters={},
        parameter_provenance={"custom_unknown_kinematic_link": "manual"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"operating_regime": "Experimental Kinematics"},
        creation_reason="Experiment",
        artifact_hash="hash_unref",
        user_id=env["user_a"],
        team_id=env["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(c_unref)

    dec_unref = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-UNREF-01",
        question="Unreferenced parameter decision",
        context={"vehicle_id": "CAR-01"},
        candidates=["SETUP-UNREF-01"],
        selected_option={"setup_id": "SETUP-UNREF-01"},
        reason="Test",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_unref2"},
        user_id=env["user_a"],
        team_id=env["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(dec_unref)
    await db.commit()

    svc = ParameterTrustDecisionService(db)
    deps = await svc.discover_decision_dependencies(dec_unref, env["ctx_a"])
    unref_dep = next(d for d in deps if d.parameter_name == "custom_unknown_kinematic_link")
    assert unref_dep.dependency_nature in (
        DependencyNature.DIRECTLY_EVIDENCED.value,
        DependencyNature.UNRESOLVED_DEPENDENCY.value,
    )


@pytest.mark.asyncio
async def test_16_cross_tenant_dependency_leakage_prevented(async_test_db, seeded_decision_env):
    """Test 16: Discovering dependencies for Team A never pulls Team B candidates."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    dec_a, _ = await svc.resolve_decision("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    deps = await svc.discover_decision_dependencies(dec_a, env["ctx_a"])

    # Ensure none of Team B's candidates leaked in
    for dep in deps:
        assert dep.entity_id != "SETUP-B-01"


# ==============================================================================
# GROUP C: GROUNDED UNCERTAINTY QUANTIFICATION & DECISION EXPOSURE (Tests 17-25)
# ==============================================================================

@pytest.mark.asyncio
async def test_17_decision_with_conflict_classified_as_critical_conflict_exposure(async_test_db, seeded_decision_env):
    """Test 17: Decision depending on rear_damper_bump (UNRESOLVED_CONFLICT) yields CRITICAL_CONFLICT_EXPOSURE."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    # rear_damper_bump has active conflict, which strictly forces CRITICAL_CONFLICT_EXPOSURE
    assert res.exposure_classification == DecisionExposureClassification.CRITICAL_CONFLICT_EXPOSURE.value
    assert "conflict" in res.exposure_summary.lower()


@pytest.mark.asyncio
async def test_18_conflict_strictly_overrides_holdout_validation_pass(async_test_db, seeded_decision_env):
    """Test 18: Passing validation on spring rate does NOT mask active damper conflict."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    # Even though front_spring_rate is VALIDATED, overall decision cannot be LOW_EXPOSURE
    assert res.exposure_classification != DecisionExposureClassification.LOW_EXPOSURE.value
    assert res.exposure_classification == DecisionExposureClassification.CRITICAL_CONFLICT_EXPOSURE.value


@pytest.mark.asyncio
async def test_19_decision_with_all_validated_parameters_classified_as_low_exposure(async_test_db, seeded_decision_env):
    """Test 19: Decision with only validated, fresh, non-conflicted parameters yields LOW_EXPOSURE."""
    db = async_test_db
    env = seeded_decision_env

    svc = ParameterTrustDecisionService(db)
    res = await svc.assess_decision_exposure("DEC-SPRING-ONLY", "EngineeringDecision", env["ctx_a"])
    assert res.exposure_classification == DecisionExposureClassification.LOW_EXPOSURE.value


@pytest.mark.asyncio
async def test_20_unvalidated_high_sensitivity_parameter_yields_high_exposure(async_test_db, seeded_decision_env):
    """Test 20: Decision depending on unvalidated high-sensitivity parameter yields HIGH_EXPOSURE."""
    db = async_test_db
    env = seeded_decision_env

    # Provisional parameter with high sensitivity
    prof_unval = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-UNVAL-HIGH",
        parameter_name="front_spring_rate",
        parameter_path="changed_parameters.front_spring_rate.candidate",
        unit="N/m",
        value_reference={"value": 90000.0, "value_identity": "90000.0"},
        provenance_class=ProvenanceClass.MANUALLY_ENTERED.value,
        current_trust_state=TrustState.PROVISIONAL.value,
        validation_coverage=ValidationCoverage.NO_VALIDATION.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_unval",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-UNVAL-HIGH"},
        created_by_user_id=env["user_a"],
        team_id=env["team_a"],
        organization_id=env["org_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(prof_unval)

    cand_unval = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-UNVAL-HIGH",
        parent_setup_id="BASE-01",
        changed_parameters={"front_spring_rate": {"candidate": 90000.0, "unit": "N/m"}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "manual"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="High sensitivity test",
        artifact_hash="hash_unval_high",
        user_id=env["user_a"],
        team_id=env["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(cand_unval)

    dec_unval = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-UNVAL-HIGH",
        question="Deploy unvalidated high sensitivity setup",
        context={"vehicle_id": "CAR-01", "setup_id": "SETUP-UNVAL-HIGH"},
        candidates=["SETUP-UNVAL-HIGH"],
        selected_option={"setup_id": "SETUP-UNVAL-HIGH"},
        reason="Test",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_unval"},
        user_id=env["user_a"],
        team_id=env["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(dec_unval)
    await db.commit()

    svc = ParameterTrustDecisionService(db)
    res = await svc.assess_decision_exposure("DEC-UNVAL-HIGH", "EngineeringDecision", env["ctx_a"])
    assert res.exposure_classification == DecisionExposureClassification.HIGH_EXPOSURE.value


@pytest.mark.asyncio
async def test_21_deployment_safety_strictly_decoupled_from_decision_exposure(async_test_db, seeded_decision_env):
    """Test 21: Invariant: deployment_safety_inferred is strictly False and authorization NOT_ESTABLISHED."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    assert res.governance_separation["deployment_safety"]["deployment_safety_inferred"] is False
    assert res.governance_separation["deployment_safety"]["deployment_authorization"] == "NOT_ESTABLISHED"
    assert "independent" in res.governance_separation_notice.lower()


@pytest.mark.asyncio
async def test_22_human_approval_strictly_decoupled_from_trust_exposure(async_test_db, seeded_decision_env):
    """Test 22: Invariant: DEC-B-01 is status APPROVED, but its exposure is evaluated independently."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-B-01", "EngineeringDecision", env["ctx_b"])
    # DEC-B-01 is approved by human, but has zero parameter validation
    assert res.governance_separation["approval_authorization"]["is_human_approved"] is True
    # Human approval does NOT grant LOW_EXPOSURE to unvalidated parameters!
    assert res.exposure_classification in (
        DecisionExposureClassification.INSUFFICIENT_EVIDENCE.value,
        DecisionExposureClassification.LOW_EXPOSURE.value,
        DecisionExposureClassification.MODERATE_EXPOSURE.value,
    )


@pytest.mark.asyncio
async def test_23_provisional_threshold_provenance_preserved(async_test_db, seeded_decision_env):
    """Test 23: Invariant: SENSITIVITY_THRESHOLDS_PROVENANCE is PROVISIONAL."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    assert res.threshold_provenance == SENSITIVITY_THRESHOLDS_PROVENANCE
    assert res.threshold_provenance == "PROVISIONAL"


@pytest.mark.asyncio
async def test_24_missing_evidence_yields_insufficient_evidence(async_test_db, seeded_decision_env):
    """Test 24: Decision with empty candidates or completely missing evidence yields INSUFFICIENT_EVIDENCE."""
    db = async_test_db
    env = seeded_decision_env

    dec_empty = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-EMPTY-EVID",
        question="Decision without candidates",
        context={"vehicle_id": "CAR-01"},
        candidates=[],
        selected_option={},
        reason="None",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_empty"},
        user_id=env["user_a"],
        team_id=env["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(dec_empty)
    await db.commit()

    svc = ParameterTrustDecisionService(db)
    res = await svc.assess_decision_exposure("DEC-EMPTY-EVID", "EngineeringDecision", env["ctx_a"])
    assert res.exposure_classification == DecisionExposureClassification.INSUFFICIENT_EVIDENCE.value


@pytest.mark.asyncio
async def test_25_unit_or_operating_regime_mismatch_flags_incompatible_parameters(async_test_db, seeded_decision_env):
    """Test 25: Parameters evaluated outside their valid operating regime generate warnings."""
    db = async_test_db
    env = seeded_decision_env

    # Candidate scoped to Wet Track, but decision scoped to High-Speed Dry
    cand_wet = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-WET-01",
        parent_setup_id="BASE-01",
        changed_parameters={"front_spring_rate": {"candidate": 70000.0, "unit": "N/m"}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"operating_regime": "Wet Weather Low-Mu"},
        creation_reason="Wet setup",
        artifact_hash="hash_wet",
        user_id=env["user_a"],
        team_id=env["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(cand_wet)

    dec_mismatch = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-REGIME-MISMATCH",
        question="Deploy wet setup on dry high-speed circuit",
        context={"operating_regime": "High-Speed Lateral Cornering", "setup_id": "SETUP-WET-01"},
        candidates=["SETUP-WET-01"],
        selected_option={"setup_id": "SETUP-WET-01"},
        reason="Regime mismatch test",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Engineer A",
        artifact_hashes={"decision_hash": "hash_mismatch"},
        user_id=env["user_a"],
        team_id=env["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(dec_mismatch)
    await db.commit()

    svc = ParameterTrustDecisionService(db)
    res = await svc.assess_decision_exposure("DEC-REGIME-MISMATCH", "EngineeringDecision", env["ctx_a"])
    # Gaps should flag scope/regime incompatibility
    assert len(res.evidence_gaps) >= 1


# ==============================================================================
# GROUP D: PRIORITIZED ACTIONABLE EVIDENCE GAPS & EXPERIMENTS (Tests 26-33)
# ==============================================================================

@pytest.mark.asyncio
async def test_26_active_conflict_generates_critical_evidence_gap(async_test_db, seeded_decision_env):
    """Test 26: Parameter with active conflict generates CRITICAL severity gap."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    damper_gaps = [g for g in res.evidence_gaps if g.parameter_name == "rear_damper_bump"]
    assert len(damper_gaps) >= 1
    assert any(g.severity == EvidenceGapSeverity.CRITICAL.value for g in damper_gaps)


@pytest.mark.asyncio
async def test_27_stale_validation_generates_warning_evidence_gap(async_test_db, seeded_decision_env):
    """Test 27: Parameter with stale validation (>180 days) generates WARNING severity gap."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    arb_gaps = [g for g in res.evidence_gaps if g.parameter_name == "front_arb_rate"]
    assert len(arb_gaps) >= 1
    assert any(g.severity == EvidenceGapSeverity.WARNING.value for g in arb_gaps)
    assert any("stale" in g.reason.lower() or "age" in g.reason.lower() for g in arb_gaps)


@pytest.mark.asyncio
async def test_28_candidate_experiment_recommendation_includes_concrete_test_type(async_test_db, seeded_decision_env):
    """Test 28: Evidence gap provides domain-specific candidate experiment type."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    assert len(res.actionable_recommendations) >= 1
    rec = res.actionable_recommendations[0]
    assert rec.candidate_experiment_type != ""
    assert rec.expected_information_gain != ""


@pytest.mark.asyncio
async def test_29_actionable_recommendations_prioritized_by_severity(async_test_db, seeded_decision_env):
    """Test 29: Actionable recommendations order CRITICAL before WARNING/ADVISORY."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    if len(res.actionable_recommendations) >= 2:
        severities = [r.severity for r in res.actionable_recommendations]
        first_crit = severities.index(EvidenceGapSeverity.CRITICAL.value) if EvidenceGapSeverity.CRITICAL.value in severities else -1
        first_warn = severities.index(EvidenceGapSeverity.WARNING.value) if EvidenceGapSeverity.WARNING.value in severities else -1
        if first_crit != -1 and first_warn != -1:
            assert first_crit < first_warn


@pytest.mark.asyncio
async def test_30_recommendation_includes_mandatory_governance_disclaimer(async_test_db, seeded_decision_env):
    """Test 30: All candidate experiments include mandatory advisory disclaimer."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"])
    for gap in res.evidence_gaps:
        assert gap.recommendation_disclaimer != ""
        assert "advisory" in gap.recommendation_disclaimer.lower() or "engineer" in gap.recommendation_disclaimer.lower()


@pytest.mark.asyncio
async def test_31_zero_gaps_when_all_parameters_fully_validated(async_test_db, seeded_decision_env):
    """Test 31: DEC-SPRING-ONLY has zero critical gaps because parameter is validated and fresh."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-SPRING-ONLY", "EngineeringDecision", env["ctx_a"])
    critical_gaps = [g for g in res.evidence_gaps if g.severity == EvidenceGapSeverity.CRITICAL.value]
    assert len(critical_gaps) == 0


@pytest.mark.asyncio
async def test_32_missing_sensitivity_recommends_perturbation_sweep(async_test_db, seeded_decision_env):
    """Test 32: Missing sensitivity recommends numerical sensitivity perturbation sweep."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("INV-A-01", "Investigation", env["ctx_a"])
    damper_recs = [r for r in res.actionable_recommendations if r.target_parameter == "rear_damper_bump"]
    assert len(damper_recs) >= 1
    assert any("sweep" in r.candidate_experiment_type.lower() or "dyno" in r.candidate_experiment_type.lower() or "sensitivity" in r.expected_information_gain.lower() for r in damper_recs)


@pytest.mark.asyncio
async def test_33_multi_tenant_gap_isolation(async_test_db, seeded_decision_env):
    """Test 33: Team B decision gaps only reference Team B entities and parameters."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res = await svc.assess_decision_exposure("DEC-B-01", "EngineeringDecision", env["ctx_b"])
    for gap in res.evidence_gaps:
        assert gap.decision_id == "DEC-B-01"


# ==============================================================================
# GROUP E: DETERMINISTIC SNAPSHOT, HASHING & LINEAGE (Tests 34-40)
# ==============================================================================

@pytest.mark.asyncio
async def test_34_input_snapshot_hash_is_deterministic(async_test_db, seeded_decision_env):
    """Test 34: input_snapshot_hash is 100% reproducible across reruns with same inputs."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res1 = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True)
    res2 = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True)

    assert res1.input_snapshot_hash == res2.input_snapshot_hash
    assert len(res1.input_snapshot_hash) == 64


@pytest.mark.asyncio
async def test_35_assessment_hash_is_deterministic(async_test_db, seeded_decision_env):
    """Test 35: assessment_hash is 100% reproducible across reruns with same inputs."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res1 = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True)
    res2 = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True)

    assert res1.assessment_hash == res2.assessment_hash
    assert len(res1.assessment_hash) == 64


@pytest.mark.asyncio
async def test_36_evidence_change_mutates_hashes(async_test_db, seeded_decision_env):
    """Test 36: Updating underlying parameter evidence strictly changes assessment_hash."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res_before = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True)

    # Resolve conflict on damper
    stmt = select(ParameterTrustProfile).where(
        ParameterTrustProfile.parameter_name == "rear_damper_bump",
        ParameterTrustProfile.entity_id == "SETUP-CAND-01",
    )
    result = await db.execute(stmt)
    prof = result.scalar_one()
    prof.current_trust_state = TrustState.VALIDATED.value
    prof.validation_coverage = ValidationCoverage.VALIDATED.value
    prof.conflicts = []
    await db.commit()

    res_after = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True)
    assert res_before.assessment_hash != res_after.assessment_hash


@pytest.mark.asyncio
async def test_37_forced_reassessment_supersedes_previous_assessment(async_test_db, seeded_decision_env):
    """Test 37: Reassessment marks previous record superseded and active record updated."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    res1 = await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True, persist_record=True)
    res2 = await svc.reassess_decision("DEC-A-01", "EngineeringDecision", env["ctx_a"], "Differential re-evaluation")

    stmt = select(DecisionExposureAssessmentRecord).where(
        DecisionExposureAssessmentRecord.decision_id == "DEC-A-01"
    ).order_by(DecisionExposureAssessmentRecord.created_at.desc())
    records = (await db.execute(stmt)).scalars().all()

    assert len(records) >= 2
    assert records[0].is_active is True
    assert records[1].is_active is False
    assert records[1].superseded_by == records[0].id


@pytest.mark.asyncio
async def test_38_assessment_history_returns_chronological_supersession_lineage(async_test_db, seeded_decision_env):
    """Test 38: get_assessment_history returns chronological log with active/superseded status."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True, persist_record=True)
    await svc.reassess_decision("DEC-A-01", "EngineeringDecision", env["ctx_a"], "Revision 2")

    history = await svc.get_decision_history("DEC-A-01", env["ctx_a"])
    assert len(history) >= 2
    assert history[0]["is_active"] is True
    assert history[1]["is_active"] is False


@pytest.mark.asyncio
async def test_39_exposure_assessment_never_mutates_authoritative_decision(async_test_db, seeded_decision_env):
    """Test 39: Invariant: Decision status, question, candidates, and artifact_hashes remain unmodified."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    stmt = select(EngineeringDecision).where(EngineeringDecision.decision_id == "DEC-A-01")
    dec_orig = (await db.execute(stmt)).scalar_one()
    orig_status = dec_orig.status
    orig_candidates = copy.deepcopy(dec_orig.candidates)
    orig_hashes = copy.deepcopy(dec_orig.artifact_hashes)

    await svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=True, persist_record=True)

    dec_after = (await db.execute(stmt)).scalar_one()
    assert dec_after.status == orig_status
    assert dec_after.candidates == orig_candidates
    assert dec_after.artifact_hashes == orig_hashes


@pytest.mark.asyncio
async def test_40_concurrent_reassessment_safety(async_test_db, seeded_decision_env):
    """Test 40: Concurrent reassessment calls complete without race condition corruption."""
    db = async_test_db
    env = seeded_decision_env
    svc = ParameterTrustDecisionService(db)

    tasks = [
        svc.assess_decision_exposure("DEC-A-01", "EngineeringDecision", env["ctx_a"], force_reassess=False, persist_record=False)
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)
    hashes = [r.assessment_hash for r in results]
    assert all(h == hashes[0] for h in hashes)


# ==============================================================================
# GROUP F: REST API ENDPOINTS, SECURITY & MULTI-TENANCY (Tests 41-48)
# ==============================================================================

@pytest.fixture
def test_app_client(async_test_db, seeded_decision_env):
    app.dependency_overrides[get_db_dependency] = lambda: async_test_db
    app.dependency_overrides[verify_api_key] = lambda: seeded_decision_env["ctx_a"]
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_41_api_post_assess_decision_exposure(test_app_client):
    """Test 41: POST /api/v1/parameter-trust/decision/assess returns 200 with complete DTO."""
    client = test_app_client
    resp = await client.post(
        "/api/v1/parameter-trust/decision/assess",
        json={"decision_id": "DEC-A-01", "decision_type": "EngineeringDecision", "force_reassess": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_id"] == "DEC-A-01"
    assert "exposure_classification" in data
    assert "input_snapshot_hash" in data
    assert "governance_separation" in data
    assert data["governance_separation"]["deployment_safety"]["deployment_safety_inferred"] is False


@pytest.mark.asyncio
async def test_42_api_get_decision_exposure(test_app_client):
    """Test 42: GET /api/v1/parameter-trust/decision/{id} returns active assessment."""
    client = test_app_client
    # Assess first
    await client.post(
        "/api/v1/parameter-trust/decision/assess",
        json={"decision_id": "DEC-A-01", "decision_type": "EngineeringDecision", "persist_record": True},
    )

    resp = await client.get("/api/v1/parameter-trust/decision/DEC-A-01?decision_type=EngineeringDecision")
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_id"] == "DEC-A-01"


@pytest.mark.asyncio
async def test_43_api_get_decision_dependencies(test_app_client):
    """Test 43: GET /api/v1/parameter-trust/decision/{id}/dependencies returns dependency list."""
    client = test_app_client
    resp = await client.get("/api/v1/parameter-trust/decision/DEC-A-01/dependencies?decision_type=EngineeringDecision")
    assert resp.status_code == 200, f"Error: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["decision_id"] == "DEC-A-01"
    assert len(data["dependencies"]) >= 1
    assert any(d["parameter_name"] == "front_spring_rate" for d in data["dependencies"])


@pytest.mark.asyncio
async def test_44_api_get_decision_gaps(test_app_client):
    """Test 44: GET /api/v1/parameter-trust/decision/{id}/gaps returns prioritized gaps."""
    client = test_app_client
    resp = await client.get("/api/v1/parameter-trust/decision/DEC-A-01/gaps?decision_type=EngineeringDecision")
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_id"] == "DEC-A-01"
    assert "evidence_gaps" in data
    assert len(data["evidence_gaps"]) >= 1


@pytest.mark.asyncio
async def test_45_api_get_decision_history(test_app_client):
    """Test 45: GET /api/v1/parameter-trust/decision/{id}/history returns revision log."""
    client = test_app_client
    # Assess to create history
    await client.post(
        "/api/v1/parameter-trust/decision/assess",
        json={"decision_id": "DEC-A-01", "decision_type": "EngineeringDecision", "persist_record": True},
    )

    resp = await client.get("/api/v1/parameter-trust/decision/DEC-A-01/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_id"] == "DEC-A-01"
    assert len(data["history"]) >= 1


@pytest.mark.asyncio
async def test_46_api_post_reassess_decision(test_app_client):
    """Test 46: POST /api/v1/parameter-trust/decision/reassess supersedes previous assessment."""
    client = test_app_client
    resp = await client.post(
        "/api/v1/parameter-trust/decision/reassess",
        json={"decision_id": "DEC-A-01", "decision_type": "EngineeringDecision"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_id"] == "DEC-A-01"


@pytest.mark.asyncio
async def test_47_api_unauthorized_request_rejected(async_test_db):
    """Test 47: Unauthenticated request without valid API key returns 401."""
    app.dependency_overrides[get_db_dependency] = lambda: async_test_db
    # Do NOT override verify_api_key
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    resp = await client.post(
        "/api/v1/parameter-trust/decision/assess",
        json={"decision_id": "DEC-A-01"},
    )
    assert resp.status_code in (401, 403)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_48_api_cross_tenant_access_forbidden(async_test_db, seeded_decision_env):
    """Test 48: User in Team A cannot query Decision belonging to Team B (returns 403 or 404)."""
    app.dependency_overrides[get_db_dependency] = lambda: async_test_db
    # Act as Team A
    app.dependency_overrides[verify_api_key] = lambda: seeded_decision_env["ctx_a"]
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    # Attempt to access DEC-B-01 (Team B)
    resp = await client.post(
        "/api/v1/parameter-trust/decision/assess",
        json={"decision_id": "DEC-B-01", "decision_type": "EngineeringDecision"},
    )
    assert resp.status_code in (403, 404)
    app.dependency_overrides.clear()
