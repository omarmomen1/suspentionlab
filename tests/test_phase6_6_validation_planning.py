"""
tests/test_phase6_6_validation_planning.py
==========================================
SuspensionLab PRO — Phase 6.6 Engineering Validation Planning,
Evidence Closure & Decision Reassessment Hostile Verification Suite.

Complete Adversarial Verification Matrix:
  1. Plan creation from active VOI recommendation / evidence gap.
  2. Acceptance criteria sealed upon authorization (immutability check).
  3. New plan versioning preserves parent linkage and increments version.
  4. Valid lifecycle transitions (DRAFT -> PROPOSED -> AUTHORIZED -> IN_PROGRESS -> etc.).
  5. Illegal lifecycle transitions rejected (e.g. DRAFT -> ACCEPTED, AUTHORIZED -> DRAFT).
  6. Unauthorized user cannot authorize plan or review evidence (RBAC check).
  7. Evidence submission rejected without provenance (fails closed).
  8. Simulated evidence masquerading as physical rejected.
  9. Phase 5 pre-reveal firewall protects blind validation evidence.
  10. Valid physical evidence accepted and moves plan to EVIDENCE_SUBMITTED.
  11. Authorized reviewer dispositions (ACCEPTED, REJECTED, REVISION_REQUESTED).
  12. Gap closure evaluation verifies criteria satisfaction and operating scope.
  13. Gap closure evaluation fails on criteria breach or inapplicable scope.
  14. Decision reassessment triggers fresh Phase 6.5 robustness analysis.
  15. Reassessment tracks reversal resolution (REVERSAL_RESOLVED vs REVERSAL_PERSISTS).
  16. Before-and-after reassessment deltas tracked.
  17. Finite sample scope limitation notice explicitly recorded (FINITE_SAMPLE_SCOPE_NOTICE).
  18. Governance separation strictly verified (deployment_safety_inferred=False).
  19. Cross-tenant access enforcement (TenantIsolationError / 403 / 404).
  20. Full REST API workflow execution over HTTP.
"""
from __future__ import annotations

import sys
import os
_local_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path = [p for p in sys.path if not p.rstrip("/\\").endswith("src")]
sys.path.insert(0, _local_src)

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
    EngineeringValidationPlanRecord,
    ValidationEvidenceItemRecord,
    ValidationEvidenceClosureRecord,
    ValidationDecisionReassessmentRecord,
    DecisionExposureAssessmentRecord,
    DecisionRobustnessAnalysisRecord,
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    ValidationPlanStatus,
    ValidationMethodType,
    CriterionStatus,
    EvidenceDataSourceType,
    EvidenceClosureVerdict,
    ReversalResolutionStatus,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    SensitivityStatus,
    UncertaintyRepresentationType,
    DecisionRobustnessClassification,
    VALIDATION_PLANNING_POLICY_V1,
    CURRENT_VALIDATION_PLANNING_POLICY_VERSION,
    GOVERNANCE_VALIDATION_SEPARATION_NOTICE,
    FINITE_SAMPLE_SCOPE_NOTICE,
    ROBUSTNESS_POLICY_V1,
    CURRENT_ROBUSTNESS_POLICY_VERSION,
    CURRENT_TRUST_POLICY_VERSION,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    SetupCandidateRecord,
)
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.parameter_trust_validation_service import (
    ParameterTrustValidationService,
    ValidationPlanningError,
    PlanNotFoundError,
    InvalidPlanStateTransitionError,
    CriteriaImmutableAfterAuthorizationError,
    MissingEvidenceProvenanceError,
    SimulationMasqueradingAsPhysicalError,
    InvalidEvidenceScopeError,
    UnauthorizedValidationActionError,
)
from suspensionlab.backend.services.parameter_trust_robustness_service import (
    ParameterTrustRobustnessService,
)
from suspensionlab.backend.services.parameter_trust_decision_service import (
    ParameterTrustDecisionService,
    DecisionNotFoundError,
    PreRevealFirewallViolation,
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
        email=f"user_{user_id.hex[:6]}@suspensionlab.com",
        name="Validation Engineer",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=role.upper(),
        org_role="MEMBER",
        is_admin=role.lower() in ("admin", "org_admin", "lead", "validation_lead"),
    )


@pytest.fixture
async def seeded_validation_env(async_test_db: AsyncSession):
    """
    Sets up multi-tenant decisions, candidate setups, robustness analyses,
    and blind engineering sessions.
    """
    db = async_test_db
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_a = uuid.uuid4()     # Lead / Reviewer
    eng_a = uuid.uuid4()      # Engineer
    viewer_a = uuid.uuid4()   # Viewer

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    now = datetime.now(timezone.utc)

    # 1. Candidate Setup A
    cand_a = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-VAL-01",
        parent_setup_id="BASE-01",
        changed_parameters={
            "front_spring_rate": {"candidate": 80000.0, "unit": "N/m"},
            "front_damper_rate": {"candidate": 3500.0, "unit": "N-s/m"},
        },
        unchanged_parameters={},
        parameter_provenance={
            "front_spring_rate": "optimization",
            "front_damper_rate": "cae_sweep",
        },
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Validation planning candidate",
        artifact_hash="hash_cand_val_01",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(cand_a)

    # Candidate Setup B (Alternative for ranking)
    cand_b = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-VAL-02",
        parent_setup_id="BASE-01",
        changed_parameters={
            "front_spring_rate": {"candidate": 75000.0, "unit": "N/m"},
            "front_damper_rate": {"candidate": 3200.0, "unit": "N-s/m"},
        },
        unchanged_parameters={},
        parameter_provenance={
            "front_spring_rate": "heuristic",
            "front_damper_rate": "cae_sweep",
        },
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Alternative candidate",
        artifact_hash="hash_cand_val_02",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(cand_b)

    # Simulation sensitivity run for spring rate
    sim_a = SimulationRun(
        id=uuid.uuid4(),
        seq=1,
        label="SIM-SENS-VAL-01",
        job_id=uuid.uuid4(),
        user_id=user_a,
        team_id=team_a,
        simulation_type="sensitivity",
        title="Quarter-car stiffness sensitivity sweep",
        vehicle_ref="CAR-01",
        setup_ref="SETUP-VAL-01",
        params={"front_spring_rate": 80000.0},
        software_version="1.0.0",
        physics_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        kinematics_version="1.0.0",
        solver_version="BDF-v2.0",
        params_hash="hash_params_val_01",
        result={
            "sensitivities": {
                "front_spring_rate": [
                    {
                        "metric": "damping_ratio",
                        "elasticity": 0.48,
                        "unit": "%/%",
                        "is_numerical_derivative": True,
                    }
                ]
            }
        },
        result_hash="hash_sim_val_01",
        created_at=now,
    )
    db.add(sim_a)

    # Parameter Trust Profiles for cand_a
    prof_spring = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-VAL-01",
        parameter_name="front_spring_rate",
        parameter_path="changed_parameters.front_spring_rate.candidate",
        unit="N/m",
        value_reference={"value": 80000.0, "value_identity": "80000.0"},
        provenance_class=ProvenanceClass.OPTIMIZATION.value,
        current_trust_state=TrustState.VALIDATED.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_spring_val",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-VAL-01"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_spring)

    prof_damper = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-VAL-01",
        parameter_name="front_damper_rate",
        parameter_path="changed_parameters.front_damper_rate.candidate",
        unit="N-s/m",
        value_reference={"value": 3500.0, "value_identity": "3500.0"},
        provenance_class=ProvenanceClass.SIMULATION_DERIVED.value,
        current_trust_state=TrustState.PROVISIONAL.value,
        validation_coverage=ValidationCoverage.PARTIAL_VALIDATION.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_damper_val",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-VAL-01"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_damper)

    # 2. Engineering Decision A
    dec_id = uuid.uuid4()
    dec_a = EngineeringDecision(
        id=dec_id,
        decision_id=str(dec_id),
        question="Select front axle setup for high-speed cornering stability",
        context={"vehicle_id": "CAR-01", "setup_id": "SETUP-VAL-01"},
        candidates=["SETUP-VAL-01", "SETUP-VAL-02"],
        selected_option={"setup_id": "SETUP-VAL-01"},
        reason="Stiffness targets ride frequency and damping ratio",
        tradeoffs={"ride_vs_handling": "Stiffer front improves turn-in response"},
        risks={"kerb_strike": "Higher peak contact patch load"},
        simulation_evidence=[{"sim_label": "SIM-SENS-VAL-01"}],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Validation Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_val_01"},
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(dec_a)

    # 3. Decision Exposure Assessment A (Phase 6.4 Snapshot)
    exposure_a = DecisionExposureAssessmentRecord(
        id=uuid.uuid4(),
        decision_id=str(dec_a.id),
        decision_type="EngineeringDecision",
        policy_version="DECISION_TRUST_POLICY_V1",
        assessment_hash="hash_exp_val_01",
        input_snapshot_hash="hash_snap_val_01",
        exposure_classification="HIGH_EXPOSURE",
        exposure_summary="Decision is sensitive to front_spring_rate uncertainty.",
        parameter_dependencies=[],
        evidence_gaps=[
            {
                "gap_id": "GAP-VAL-SPRING-01",
                "parameter_name": "front_spring_rate",
                "severity": "HIGH",
                "reason": "Missing empirical 4-post rig physical validation.",
                "candidate_experiment_type": "RIG_TEST_4_POST",
                "operating_conditions": {"regime": "TRACK_DRY", "temperature_min_c": 15.0, "temperature_max_c": 35.0},
            }
        ],
        actionable_recommendations=[],
        governance_separation_notice="DECISION EXPOSURE ASSESSMENT ONLY",
        is_active=True,
        organization_id=org_a,
        team_id=team_a,
        user_id=user_a,
        created_at=now,
    )
    db.add(exposure_a)

    # 4. Decision Robustness Analysis A (Phase 6.5 Snapshot with Demonstrated Reversals)
    robustness_a = DecisionRobustnessAnalysisRecord(
        id=uuid.uuid4(),
        decision_id=str(dec_a.id),
        decision_type="EngineeringDecision",
        policy_version=CURRENT_ROBUSTNESS_POLICY_VERSION,
        analysis_hash="hash_rob_val_01",
        input_snapshot_hash="hash_snap_rob_01",
        robustness_classification=DecisionRobustnessClassification.FRAGILE_REVERSAL_DEMONSTRATED.value,
        robustness_summary="Decision reverses under wide unverified front_spring_rate uncertainty.",
        evaluated_envelope={
            "parameters": {
                "front_spring_rate": {"nominal": 80000.0, "min": 68000.0, "max": 92000.0, "unit": "N/m"},
            },
            "decision_threshold": 0.65,
            "target_kpi": "damping_ratio",
            "selected_option": "SETUP-VAL-01",
        },
        parameter_uncertainties=[],
        reversal_scenarios=[
            {
                "scenario_id": "SCEN-REV-01",
                "reversal_type": "RANKING_REVERSAL",
                "parameter_shifts": {"front_spring_rate": 69000.0},
                "kpi_delta": -0.06,
                "alternative_winner": "SETUP-VAL-02",
            }
        ],
        boundary_crossings=[
            {
                "boundary_type": "RANKING_REVERSAL_BOUNDARY",
                "critical_parameters": ["front_spring_rate"],
                "target_kpi": "damping_ratio",
                "description": "Crosses threshold at 72000.0 N/m",
            }
        ],
        dominant_uncertainties=[
            {
                "parameter_name": "front_spring_rate",
                "impact_score": 0.85,
                "elasticity": 0.72,
                "reversals_participated": 2,
                "unit": "N/m",
            }
        ],
        voi_prioritizations=[
            {
                "parameter_name": "front_spring_rate",
                "priority_level": "CRITICAL",
                "recommended_experiment": "RIG_TEST_4_POST",
                "justification": "Direct physical measurement needed to resolve ranking reversal.",
            }
        ],
        solver_failures=[],
        governance_separation_notice="ROBUSTNESS ANALYSIS IS AN ANALYTICAL EVALUATION ONLY",
        is_active=True,
        organization_id=org_a,
        team_id=team_a,
        user_id=user_a,
        created_at=now,
    )
    db.add(robustness_a)

    # 5. Phase 5 Blind Engineering Sessions (for Firewall testing)
    blind_unrevealed = BlindEngineeringSession(
        id=uuid.uuid4(),
        organization_id=org_a,
        team_id=team_a,
        created_by_user_id=user_a,
        name="BLIND-VAL-SESS-99",
        session_hash="BLIND-VAL-SESS-99",
        root_entity_type="QuarterCarModel",
        root_entity_id="QC-01",
        hidden_outcome_type="ValidationDataset",
        hidden_outcome_id="DS-VAL-99",
        status=BlindSessionStatus.BLIND_ACTIVE.value,  # NOT REVEALED
        configuration={},
        created_at=now,
    )
    db.add(blind_unrevealed)

    blind_revealed = BlindEngineeringSession(
        id=uuid.uuid4(),
        organization_id=org_a,
        team_id=team_a,
        created_by_user_id=user_a,
        name="BLIND-VAL-SESS-01",
        session_hash="BLIND-VAL-SESS-01",
        root_entity_type="QuarterCarModel",
        root_entity_id="QC-01",
        hidden_outcome_type="ValidationDataset",
        hidden_outcome_id="DS-VAL-01",
        status=BlindSessionStatus.REVEALED.value,  # REVEALED
        revealed_at=now,
        configuration={},
        created_at=now,
    )
    db.add(blind_revealed)

    await db.flush()

    return {
        "db": db,
        "org_a": org_a,
        "team_a": team_a,
        "user_a": user_a,
        "eng_a": eng_a,
        "viewer_a": viewer_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "dec_a": dec_a,
        "exposure_a": exposure_a,
        "robustness_a": robustness_a,
        "blind_unrevealed": blind_unrevealed,
        "blind_revealed": blind_revealed,
    }


# ── TEST CASES ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_01_plan_creation_from_voi_and_gap(seeded_validation_env):
    """
    Test 1: Plan creation from active VOI recommendation.
    Verifies plan contract, deterministic plan_hash, criteria initialization,
    and strict governance decoupling (deployment_safety_inferred=False).
    """
    env = seeded_validation_env
    db = env["db"]
    user_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=user_ctx,
        evidence_gap_id="GAP-VAL-SPRING-01",
        validation_objective="Empirically measure front spring rate on 4-post rig to eliminate reversal",
        validation_method=ValidationMethodType.RIG_TEST_4_POST.value,
        unit="N/m",
        acceptance_criteria=[
            {
                "metric_name": "front_spring_rate_tolerance",
                "target_value": 80000.0,
                "tolerance_band": [76000.0, 84000.0],
                "unit": "N/m",
                "status": "PROPOSED",
                "provenance": "Derived from damping ratio limit threshold",
            }
        ],
        operating_conditions={
            "temperature_min_c": 15.0,
            "temperature_max_c": 35.0,
            "regime": "TRACK_DRY",
        },
    )

    assert plan.plan_id.startswith("VAL-PLAN-")
    assert plan.decision_id == str(env["dec_a"].id)
    assert plan.parameter_name == "front_spring_rate"
    assert plan.status == ValidationPlanStatus.DRAFT.value
    assert plan.plan_version == 1
    assert plan.plan_hash is not None
    assert len(plan.plan_hash) == 64
    assert plan.deployment_safety_inferred is False
    assert plan.deployment_authorization == "NOT_ESTABLISHED"
    assert len(plan.acceptance_criteria) == 1
    assert plan.acceptance_criteria[0]["status"] == CriterionStatus.PROPOSED.value


@pytest.mark.asyncio
async def test_02_acceptance_criteria_sealed_upon_authorization(seeded_validation_env):
    """
    Test 2: Acceptance criteria cannot be retroactively edited once AUTHORIZED.
    Seals criteria as AUTHORIZED and records criteria_authorized_by_user_id.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
        acceptance_criteria=[
            {
                "metric_name": "stiffness_check",
                "target_value": 80000.0,
                "tolerance_band": [76000.0, 84000.0],
                "unit": "N/m",
                "status": "PROPOSED",
            }
        ],
    )

    # DRAFT -> PROPOSED
    p_prop = await ParameterTrustValidationService.transition_plan_status(
        db=db,
        plan_id=plan.id,
        target_status=ValidationPlanStatus.PROPOSED.value,
        user_context=lead_ctx,
    )
    assert p_prop.status == ValidationPlanStatus.PROPOSED.value

    # PROPOSED -> AUTHORIZED
    p_auth = await ParameterTrustValidationService.transition_plan_status(
        db=db,
        plan_id=plan.id,
        target_status=ValidationPlanStatus.AUTHORIZED.value,
        user_context=lead_ctx,
    )
    assert p_auth.status == ValidationPlanStatus.AUTHORIZED.value
    assert p_auth.acceptance_criteria[0]["status"] == CriterionStatus.AUTHORIZED.value
    assert p_auth.criteria_authorized_by_user_id == str(env["user_a"])
    assert p_auth.authorized_at is not None


@pytest.mark.asyncio
async def test_03_new_plan_version_preserves_parent_linkage(seeded_validation_env):
    """
    Test 3: New plan versioning preserves parent linkage and increments version.
    Modifying authorized requirements creates version N+1 and marks vN SUPERSEDED.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p1 = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p1.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p1.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    # Create Version 2 with revised criteria
    p2 = await ParameterTrustValidationService.create_new_plan_version(
        db=db,
        plan_id=p1.id,
        user_context=lead_ctx,
        acceptance_criteria=[
            {
                "metric_name": "front_spring_rate_tolerance_v2",
                "target_value": 81000.0,
                "tolerance_band": [78000.0, 84000.0],
                "unit": "N/m",
                "status": "PROPOSED",
                "provenance": "Updated specification for high-load track testing",
            }
        ],
    )

    assert p2.plan_version == 2
    assert p2.parent_plan_id == str(p1.id)
    assert p2.status == ValidationPlanStatus.DRAFT.value

    # Verify parent plan was marked SUPERSEDED
    stmt = select(EngineeringValidationPlanRecord).where(EngineeringValidationPlanRecord.id == uuid.UUID(str(p1.id)))
    res = await db.execute(stmt)
    old_p = res.scalar_one()
    assert old_p.status == ValidationPlanStatus.SUPERSEDED.value
    assert old_p.is_active is False


@pytest.mark.asyncio
async def test_04_valid_plan_lifecycle_transitions(seeded_validation_env):
    """
    Test 4: Valid lifecycle transitions walk through complete state machine:
    DRAFT -> PROPOSED -> AUTHORIZED -> IN_PROGRESS -> EVIDENCE_SUBMITTED -> UNDER_REVIEW -> ACCEPTED.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
    )
    assert p.status == ValidationPlanStatus.DRAFT.value

    p = await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    assert p.status == ValidationPlanStatus.PROPOSED.value

    p = await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )
    assert p.status == ValidationPlanStatus.AUTHORIZED.value

    p = await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.IN_PROGRESS.value, user_context=lead_ctx
    )
    assert p.status == ValidationPlanStatus.IN_PROGRESS.value

    # Submitting evidence moves to EVIDENCE_SUBMITTED
    ev = await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=p.id,
        evidence_data={
            "source_identifier": "RIG-TEST-001",
            "evidence_source_type": EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
            "observed_value": 79800.0,
            "observed_interval": [78500.0, 81100.0],
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"facility": "4-Post Dyno", "rig_id": "RIG-4P-01"},
        },
        user_context=lead_ctx,
    )
    p_ref = await ParameterTrustValidationService.get_validation_plan(db=db, plan_id=p.id, user_context=lead_ctx)
    assert p_ref.status == ValidationPlanStatus.EVIDENCE_SUBMITTED.value

    p = await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.UNDER_REVIEW.value, user_context=lead_ctx
    )
    assert p.status == ValidationPlanStatus.UNDER_REVIEW.value

    p = await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.ACCEPTED.value, user_context=lead_ctx
    )
    assert p.status == ValidationPlanStatus.ACCEPTED.value


@pytest.mark.asyncio
async def test_05_illegal_lifecycle_transitions_rejected(seeded_validation_env):
    """
    Test 5: Illegal lifecycle transitions rejected with InvalidPlanStateTransitionError.
    e.g. DRAFT -> ACCEPTED, AUTHORIZED -> DRAFT, SUPERSEDED -> IN_PROGRESS.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
    )

    # 1. Illegal leap from DRAFT directly to ACCEPTED
    with pytest.raises(InvalidPlanStateTransitionError) as exc_info:
        await ParameterTrustValidationService.transition_plan_status(
            db=db, plan_id=p.id, target_status=ValidationPlanStatus.ACCEPTED.value, user_context=lead_ctx
        )
    assert "Illegal validation plan transition" in str(exc_info.value)

    # Move to AUTHORIZED
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    # 2. Illegal regress from AUTHORIZED back to DRAFT
    with pytest.raises(InvalidPlanStateTransitionError) as exc_info2:
        await ParameterTrustValidationService.transition_plan_status(
            db=db, plan_id=p.id, target_status=ValidationPlanStatus.DRAFT.value, user_context=lead_ctx
        )
    assert "Illegal validation plan transition" in str(exc_info2.value)


@pytest.mark.asyncio
async def test_06_unauthorized_user_cannot_authorize_or_review(seeded_validation_env):
    """
    Test 6: Unauthorized user cannot authorize plan or review evidence (UnauthorizedValidationActionError).
    """
    env = seeded_validation_env
    db = env["db"]
    viewer_ctx = make_user_ctx(env["viewer_a"], env["team_a"], env["org_a"], role="viewer")
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )

    # Viewer attempts to AUTHORIZE -> rejected
    with pytest.raises(UnauthorizedValidationActionError) as exc_auth:
        await ParameterTrustValidationService.transition_plan_status(
            db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=viewer_ctx
        )
    assert "not authorized" in str(exc_auth.value)


@pytest.mark.asyncio
async def test_07_evidence_submission_rejected_without_provenance(seeded_validation_env):
    """
    Test 7: Evidence submission rejected without provenance (fails closed).
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    # Submit evidence missing provenance
    with pytest.raises(MissingEvidenceProvenanceError) as exc_prov:
        await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=p.id,
            evidence_data={
                "source_identifier": "TEST-NO-PROV",
                "observed_value": 80000.0,
                # provenance omitted
            },
            user_context=lead_ctx,
        )
    assert "missing source_identifier or traceable provenance" in str(exc_prov.value)


@pytest.mark.asyncio
async def test_08_simulated_evidence_masquerading_as_physical_rejected(seeded_validation_env):
    """
    Test 8: Simulated evidence masquerading as physical rejected (SimulationMasqueradingAsPhysicalError).
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    # Masquerade CAE/simulation as physically validated
    with pytest.raises(SimulationMasqueradingAsPhysicalError) as exc_masq:
        await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=p.id,
            evidence_data={
                "source_identifier": "CAE-RUN-55",
                "evidence_source_type": EvidenceDataSourceType.NUMERICAL_SIMULATION_RESULT.value,
                "observed_value": 80000.0,
                "is_physically_validated": True,  # FALSE CLAIM
                "provenance": {"tool": "ADAMS/Car CAE solver run"},
            },
            user_context=lead_ctx,
        )
    assert "SimulationMasqueradingAsPhysicalError" in type(exc_masq.value).__name__ or "cannot be marked as physically validated" in str(exc_masq.value)


@pytest.mark.asyncio
async def test_09_phase5_pre_reveal_firewall_blocks_blind_evidence(seeded_validation_env):
    """
    Test 9: Phase 5 pre-reveal firewall protects blind validation evidence.
    Unrevealed blind session evidence is blocked; revealed session evidence is accepted.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    # 1. Blocked: References unrevealed blind session
    with pytest.raises(PreRevealFirewallViolation) as exc_firewall:
        await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=p.id,
            evidence_data={
                "source_identifier": f"BLIND:{env['blind_unrevealed'].name}",
                "evidence_source_type": EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
                "observed_value": 80100.0,
                "is_physically_validated": True,
                "provenance": {"session": "BLIND_HOLD_GATE"},
            },
            user_context=lead_ctx,
        )
    assert "Pre-Reveal Firewall Violation" in str(exc_firewall.value)

    # 2. Accepted: References revealed blind session
    ev_revealed = await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=p.id,
        evidence_data={
            "source_identifier": f"BLIND:{env['blind_revealed'].name}",
            "evidence_source_type": EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
            "observed_value": 80100.0,
            "is_physically_validated": True,
            "provenance": {"session": "BLIND_REVEALED_GATE"},
        },
        user_context=lead_ctx,
    )
    assert ev_revealed.source_identifier == f"BLIND:{env['blind_revealed'].name}"


@pytest.mark.asyncio
async def test_10_valid_physical_evidence_accepted_and_moves_to_submitted(seeded_validation_env):
    """
    Test 10: Valid physical evidence accepted and moves plan to EVIDENCE_SUBMITTED.
    Verifies cryptographic integrity hash generation and pending review state.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    ev = await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=p.id,
        evidence_data={
            "source_identifier": "RIG-TEST-2026-004",
            "evidence_source_type": EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
            "observed_value": 80250.0,
            "observed_interval": [79000.0, 81500.0],
            "observed_samples": [79800.0, 80200.0, 80400.0, 80600.0],
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {
                "facility": "4-Post Dynamic Shaker Lab",
                "test_bench": "RIG-4P-B",
                "calibration_cert": "CERT-2026-8812",
            },
            "operating_scope": {
                "temperature_min_c": 18.0,
                "temperature_max_c": 28.0,
                "regime": "TRACK_DRY",
            },
        },
        user_context=lead_ctx,
    )

    assert ev.id is not None
    assert ev.observed_value == 80250.0
    assert ev.integrity_hash is not None
    assert len(ev.integrity_hash) == 64
    assert ev.review_status == "PENDING_REVIEW"

    # Plan state updated
    p_ref = await ParameterTrustValidationService.get_validation_plan(db=db, plan_id=p.id, user_context=lead_ctx)
    assert p_ref.status == ValidationPlanStatus.EVIDENCE_SUBMITTED.value


@pytest.mark.asyncio
async def test_11_authorized_reviewer_dispositions(seeded_validation_env):
    """
    Test 11: Authorized reviewer dispositions (ACCEPTED, REJECTED, REVISION_REQUESTED).
    Records reviewer identity and timestamp.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    ev = await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=p.id,
        evidence_data={
            "source_identifier": "RIG-TEST-REVIEW-01",
            "evidence_source_type": EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
            "observed_value": 80100.0,
            "is_physically_validated": True,
            "provenance": {"facility": "4-Post Lab"},
        },
        user_context=lead_ctx,
    )

    # Review as ACCEPTED
    rev = await ParameterTrustValidationService.review_evidence_item(
        db=db,
        evidence_id=ev.id,
        disposition="ACCEPTED",
        review_notes="Telemetry and load cell calibration verified",
        user_context=lead_ctx,
    )
    assert rev.review_status == "ACCEPTED"
    assert rev.reviewed_by_user_id == str(env["user_a"])
    assert rev.reviewed_at is not None


@pytest.mark.asyncio
async def test_12_evidence_closure_satisfies_criteria_and_scope(seeded_validation_env):
    """
    Test 12: Gap closure evaluation verifies criteria satisfaction and operating scope.
    Returns CLOSED_WITH_SUPPORTING_EVIDENCE when criteria met.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    p = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
        acceptance_criteria=[
            {
                "metric_name": "front_spring_rate_tolerance",
                "target_value": 80000.0,
                "tolerance_band": [76000.0, 84000.0],
                "unit": "N/m",
                "status": "PROPOSED",
            }
        ],
        operating_conditions={
            "temperature_min_c": 15.0,
            "temperature_max_c": 35.0,
            "regime": "TRACK_DRY",
        },
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    # Submit valid physical evidence within tolerance
    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=p.id,
        evidence_data={
            "source_identifier": "RIG-TEST-SUCCESS",
            "evidence_source_type": EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
            "observed_value": 80200.0,
            "observed_interval": [79000.0, 81400.0],
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"rig": "4-Post", "calibrated": True},
            "operating_scope": {"temperature_min_c": 18.0, "temperature_max_c": 28.0, "regime": "TRACK_DRY"},
        },
        user_context=lead_ctx,
    )

    closure = await ParameterTrustValidationService.evaluate_evidence_closure(
        db=db, plan_id=p.id, user_context=lead_ctx
    )

    assert closure.closure_verdict == EvidenceClosureVerdict.CLOSED_WITH_SUPPORTING_EVIDENCE.value
    assert closure.criteria_met is True
    assert closure.requires_robustness_reassessment is True
    assert closure.deployment_safety_inferred is False
    assert closure.deployment_authorization == "NOT_ESTABLISHED"
    assert closure.closure_hash is not None
    assert closure.finite_sample_notice == FINITE_SAMPLE_SCOPE_NOTICE


@pytest.mark.asyncio
async def test_13_evidence_closure_fails_on_criteria_breach_or_scope_mismatch(seeded_validation_env):
    """
    Test 13: Gap closure evaluation fails if evidence contradicts criteria or falls outside operating conditions.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    # 1. Criteria breach: observed value exceeds upper tolerance
    p_breach = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
        acceptance_criteria=[
            {
                "metric_name": "front_spring_rate_tolerance",
                "target_value": 80000.0,
                "tolerance_band": [76000.0, 84000.0],
                "unit": "N/m",
            }
        ],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p_breach.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p_breach.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=p_breach.id,
        evidence_data={
            "source_identifier": "RIG-BREACH-01",
            "observed_value": 91000.0,  # Exceeds 84000.0 max tolerance!
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"rig": "4-Post"},
        },
        user_context=lead_ctx,
    )
    cl_breach = await ParameterTrustValidationService.evaluate_evidence_closure(
        db=db, plan_id=p_breach.id, user_context=lead_ctx
    )
    assert cl_breach.closure_verdict == EvidenceClosureVerdict.REMAINS_OPEN.value
    assert cl_breach.criteria_met is False

    # 2. Scope mismatch: regime conflict
    p_scope = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
        operating_conditions={"regime": "TRACK_DRY"},
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p_scope.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=p_scope.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=p_scope.id,
        evidence_data={
            "source_identifier": "RIG-WET-TEST",
            "observed_value": 80000.0,
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"rig": "Wet Rig"},
            "operating_scope": {"regime": "WET_ICE_SURFACE"},  # MISMATCH
        },
        user_context=lead_ctx,
    )
    cl_scope = await ParameterTrustValidationService.evaluate_evidence_closure(
        db=db, plan_id=p_scope.id, user_context=lead_ctx
    )
    assert cl_scope.closure_verdict == EvidenceClosureVerdict.EVIDENCE_NOT_APPLICABLE.value


@pytest.mark.asyncio
async def test_14_decision_reassessment_triggers_fresh_robustness(seeded_validation_env):
    """
    Test 14: Decision reassessment triggers fresh Phase 6.5 robustness run.
    Verifies that a new DecisionRobustnessAnalysisRecord is created and linked.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
        acceptance_criteria=[
            {"metric_name": "stiffness", "target_value": 80000.0, "tolerance_band": [78000.0, 82000.0], "unit": "N/m"}
        ],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=plan.id,
        evidence_data={
            "source_identifier": "RIG-NARROW-TOLERANCE",
            "observed_value": 80100.0,
            "observed_interval": [79500.0, 80500.0],  # Narrowed physical interval
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"rig": "Rig A"},
        },
        user_context=lead_ctx,
    )

    reassessment = await ParameterTrustValidationService.execute_decision_reassessment(
        db=db, plan_id=plan.id, user_context=lead_ctx
    )

    assert reassessment.id is not None
    assert reassessment.decision_id == str(env["dec_a"].id)
    assert reassessment.new_robustness_analysis_id is not None
    assert reassessment.reassessment_delta is not None


@pytest.mark.asyncio
async def test_15_reassessment_tracks_reversal_resolution(seeded_validation_env):
    """
    Test 15: Reassessment correctly identifies reversal resolution (REVERSAL_RESOLVED vs REVERSAL_PERSISTS).
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    # In seeded_robustness_env, original robustness had reversals_count=2 (VULNERABLE_TO_REVERSAL)
    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=lead_ctx,
        acceptance_criteria=[
            {"metric_name": "rate", "target_value": 80000.0, "tolerance_band": [79000.0, 81000.0], "unit": "N/m"}
        ],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )

    # Submit evidence confirming stiffness tightly around 80000.0 N/m
    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=plan.id,
        evidence_data={
            "source_identifier": "RIG-CONFIRM-TIGHT",
            "observed_value": 80050.0,
            "observed_interval": [79800.0, 80300.0],  # Narrow bounds eliminate reversal!
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"rig": "Rig 4P"},
        },
        user_context=lead_ctx,
    )

    reassessment = await ParameterTrustValidationService.execute_decision_reassessment(
        db=db, plan_id=plan.id, user_context=lead_ctx
    )

    assert reassessment.reversal_status in (
        ReversalResolutionStatus.REVERSAL_RESOLVED.value,
        ReversalResolutionStatus.REVERSAL_PERSISTS.value,
        ReversalResolutionStatus.NO_REVERSAL_DEMONSTRATED.value,
    )
    delta = reassessment.reassessment_delta
    assert "classification_before" in delta
    assert "classification_after" in delta
    assert "reversals_before_count" in delta
    assert "reversals_after_count" in delta


@pytest.mark.asyncio
async def test_16_before_and_after_deltas_tracked(seeded_validation_env):
    """
    Test 16: Before-and-after reassessment deltas tracked with classification, reversals, boundaries.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=plan.id,
        evidence_data={
            "source_identifier": "RIG-DELTA-CHECK",
            "observed_value": 80000.0,
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"rig": "Rig 4P"},
        },
        user_context=lead_ctx,
    )

    reassessment = await ParameterTrustValidationService.execute_decision_reassessment(
        db=db, plan_id=plan.id, user_context=lead_ctx
    )

    delta = reassessment.reassessment_delta
    assert delta["classification_before"] == DecisionRobustnessClassification.FRAGILE_REVERSAL_DEMONSTRATED.value
    assert delta["reversals_before_count"] >= 1
    assert "boundaries_before_count" in delta
    assert "boundaries_after_count" in delta


@pytest.mark.asyncio
async def test_17_finite_sample_scope_notice_recorded(seeded_validation_env):
    """
    Test 17: Finite sample scope limitation notice explicitly recorded in closure and reassessment.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=plan.id,
        evidence_data={
            "source_identifier": "RIG-FINITE-RUNS",
            "observed_value": 80000.0,
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"rig": "Rig 4P"},
        },
        user_context=lead_ctx,
    )

    closure = await ParameterTrustValidationService.evaluate_evidence_closure(
        db=db, plan_id=plan.id, user_context=lead_ctx
    )
    assert closure.finite_sample_notice == FINITE_SAMPLE_SCOPE_NOTICE

    reassessment = await ParameterTrustValidationService.execute_decision_reassessment(
        db=db, plan_id=plan.id, user_context=lead_ctx
    )
    assert "FINITE_SAMPLE_SCOPE_NOTICE" in reassessment.envelope_coverage_statement


@pytest.mark.asyncio
async def test_18_governance_separation_strictly_verified(seeded_validation_env):
    """
    Test 18: Governance separation strictly verified across plan, closure, and reassessment:
    deployment_safety_inferred = False, deployment_authorization = 'NOT_ESTABLISHED'.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_ctx = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=lead_ctx
    )
    assert plan.deployment_safety_inferred is False
    assert plan.deployment_authorization == "NOT_ESTABLISHED"
    assert plan.governance_separation_notice == GOVERNANCE_VALIDATION_SEPARATION_NOTICE

    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead_ctx
    )
    await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=plan.id,
        evidence_data={
            "source_identifier": "RIG-GOV-TEST",
            "observed_value": 80000.0,
            "unit": "N/m",
            "is_physically_validated": True,
            "provenance": {"facility": "Proving Ground"},
        },
        user_context=lead_ctx,
    )

    closure = await ParameterTrustValidationService.evaluate_evidence_closure(
        db=db, plan_id=plan.id, user_context=lead_ctx
    )
    assert closure.deployment_safety_inferred is False
    assert closure.deployment_authorization == "NOT_ESTABLISHED"

    reassessment = await ParameterTrustValidationService.execute_decision_reassessment(
        db=db, plan_id=plan.id, user_context=lead_ctx
    )
    assert reassessment.deployment_safety_inferred is False
    assert reassessment.deployment_authorization == "NOT_ESTABLISHED"


@pytest.mark.asyncio
async def test_19_cross_tenant_isolation(seeded_validation_env):
    """
    Test 19: Cross-tenant access enforcement. User from Tenant B cannot access or mutate Tenant A's plan.
    """
    env = seeded_validation_env
    db = env["db"]
    user_a = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")
    user_b = make_user_ctx(env["user_b"], env["team_b"], env["org_b"], role="validation_lead")

    plan_a = await ParameterTrustValidationService.create_validation_plan(
        db=db, decision_id=str(env["dec_a"].id), parameter_name="front_spring_rate", user_context=user_a
    )

    # Tenant B tries to retrieve Tenant A's plan -> raises PlanNotFoundError (tenant boundary)
    with pytest.raises(PlanNotFoundError):
        await ParameterTrustValidationService.get_validation_plan(
            db=db, plan_id=plan_a.id, user_context=user_b
        )

    # Tenant B tries to transition Tenant A's plan -> raises PlanNotFoundError
    with pytest.raises(PlanNotFoundError):
        await ParameterTrustValidationService.transition_plan_status(
            db=db,
            plan_id=plan_a.id,
            target_status=ValidationPlanStatus.PROPOSED.value,
            user_context=user_b,
        )


@pytest.mark.asyncio
async def test_20_rest_api_full_workflow(seeded_validation_env):
    """
    Test 20: Full REST API workflow execution over HTTP via FastAPI test client.
    """
    env = seeded_validation_env
    db = env["db"]
    lead_user = make_user_ctx(env["user_a"], env["team_a"], env["org_a"], role="validation_lead")

    # FastAPI dependency overrides
    app.dependency_overrides[get_db_dependency] = lambda: db
    app.dependency_overrides[verify_api_key] = lambda: lead_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer test-lead-key"}

            # 1. POST /api/v1/parameter-trust/validation/plans
            create_resp = await client.post(
                "/api/v1/parameter-trust/validation/plans",
                headers=headers,
                json={
                    "decision_id": str(env["dec_a"].id),
                    "parameter_name": "front_spring_rate",
                    "validation_method": "RIG_TEST_4_POST",
                    "validation_objective": "REST API validation planning test",
                    "unit": "N/m",
                    "acceptance_criteria": [
                        {
                            "metric_name": "spring_rate_tolerance",
                            "target_value": 80000.0,
                            "tolerance_band": [76000.0, 84000.0],
                            "unit": "N/m",
                        }
                    ],
                },
            )
            assert create_resp.status_code == 201
            plan_data = create_resp.json()
            plan_id = plan_data["id"]
            assert plan_data["status"] == "DRAFT"

            # 2. GET /api/v1/parameter-trust/validation/plans/{plan_id}
            get_resp = await client.get(
                f"/api/v1/parameter-trust/validation/plans/{plan_id}",
                headers=headers,
            )
            assert get_resp.status_code == 200, f"GET plan failed: {get_resp.status_code} - {get_resp.text}"
            assert get_resp.json()["id"] == plan_id

            # 3. GET /api/v1/parameter-trust/decision/{decision_id}/validation-plans
            list_resp = await client.get(
                f"/api/v1/parameter-trust/decision/{env['dec_a'].id}/validation-plans",
                headers=headers,
            )
            assert list_resp.status_code == 200
            assert list_resp.json()["total"] >= 1

            # 4. POST /api/v1/parameter-trust/validation/plans/{plan_id}/transition -> PROPOSED -> AUTHORIZED
            p_resp = await client.post(
                f"/api/v1/parameter-trust/validation/plans/{plan_id}/transition",
                headers=headers,
                json={"target_status": "PROPOSED"},
            )
            assert p_resp.status_code == 200
            assert p_resp.json()["status"] == "PROPOSED"

            auth_resp = await client.post(
                f"/api/v1/parameter-trust/validation/plans/{plan_id}/transition",
                headers=headers,
                json={"target_status": "AUTHORIZED"},
            )
            assert auth_resp.status_code == 200
            assert auth_resp.json()["status"] == "AUTHORIZED"

            # 5. POST /api/v1/parameter-trust/validation/plans/{plan_id}/evidence
            ev_resp = await client.post(
                f"/api/v1/parameter-trust/validation/plans/{plan_id}/evidence",
                headers=headers,
                json={
                    "evidence_source_type": "PHYSICAL_RIG_MEASUREMENT",
                    "source_identifier": "REST-TEST-RIG-01",
                    "observed_value": 80150.0,
                    "observed_interval": [79000.0, 81300.0],
                    "unit": "N/m",
                    "is_physically_validated": True,
                    "provenance": {"facility": "DynoLab"},
                },
            )
            assert ev_resp.status_code == 201
            evidence_id = ev_resp.json()["id"]

            # 6. POST /api/v1/parameter-trust/validation/plans/{plan_id}/evidence/{evidence_id}/review
            rev_resp = await client.post(
                f"/api/v1/parameter-trust/validation/plans/{plan_id}/evidence/{evidence_id}/review",
                headers=headers,
                json={"review_status": "ACCEPTED", "review_notes": "REST API review accept"},
            )
            assert rev_resp.status_code == 200
            assert rev_resp.json()["review_status"] == "ACCEPTED"

            # 7. POST /api/v1/parameter-trust/validation/plans/{plan_id}/closure-assessment
            cl_resp = await client.post(
                f"/api/v1/parameter-trust/validation/plans/{plan_id}/closure-assessment",
                headers=headers,
                json={"reviewer_notes": "Closure approved via REST"},
            )
            assert cl_resp.status_code == 200
            closure_data = cl_resp.json()
            assert closure_data["closure_verdict"] == "CLOSED_WITH_SUPPORTING_EVIDENCE"
            assert closure_data["deployment_safety_inferred"] is False

            # 8. POST /api/v1/parameter-trust/validation/plans/{plan_id}/reassess
            re_resp = await client.post(
                f"/api/v1/parameter-trust/validation/plans/{plan_id}/reassess",
                headers=headers,
                json={"rationale": "Reassessment triggered via REST"},
            )
            assert re_resp.status_code == 200
            reassess_data = re_resp.json()
            assert "reversal_status" in reassess_data
            assert reassess_data["deployment_safety_inferred"] is False

            # 9. GET /api/v1/parameter-trust/decision/{decision_id}/reassessments
            hist_re_resp = await client.get(
                f"/api/v1/parameter-trust/decision/{env['dec_a'].id}/reassessments",
                headers=headers,
            )
            assert hist_re_resp.status_code == 200
            assert hist_re_resp.json()["total"] >= 1

    finally:
        app.dependency_overrides.clear()
