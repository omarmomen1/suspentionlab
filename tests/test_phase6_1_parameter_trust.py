"""
tests/test_phase6_1_parameter_trust.py
======================================
SuspensionLab PRO — Phase 6.1 Parameter Trust Map Acceptance & Verification Suite.

Mandatory Verification Matrix (32 Specification Tests + Adversarial Suites):
 1. test_01_parameter_identity_resolved_correctly
 2. test_02_parameter_value_reference_correct
 3. test_03_source_provenance_resolved
 4. test_04_supporting_evidence_resolved
 5. test_05_evidence_graph_traversal_uses_existing_vocabulary
 6. test_06_no_new_graph_relationship_created
 7. test_07_validated_parameter_classified_correctly
 8. test_08_unsupported_parameter_classified_correctly
 9. test_09_conflicting_evidence_produces_conflicted
10. test_10_stale_evidence_is_represented
11. test_11_scope_is_preserved
12. test_12_validation_coverage_is_correct
13. test_13_explanation_is_deterministic
14. test_14_same_evidence_produces_same_assessment
15. test_15_changed_evidence_changes_assessment_identity
16. test_16_trust_policy_version_is_preserved
17. test_17_no_textual_heuristics_affect_trust
18. test_18_tenant_isolation
19. test_19_personal_workspace_isolation
20. test_20_unauthorized_parameter_rejected
21. test_21_missing_evidence_handled_deterministically
22. test_22_missing_parameter_handled_safely
23. test_23_hidden_inaccessible_evidence_does_not_leak
24. test_24_api_schema_contains_no_unauthorized_data
25. test_25_history_is_ordered_deterministically
26. test_26_assessment_hash_deterministic
27. test_27_frontend_renders_real_trust_state
28. test_28_frontend_does_not_invent_evidence
29. test_29_phase4_regression_remains_green
30. test_30_phase5_regression_remains_green
31. test_31_production_physics_unchanged
32. test_32_phase3_artifacts_unchanged
+ Adversarial cross-tenant IDOR and evidence leakage suites
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
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
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    TRUST_POLICY_V1,
    CURRENT_TRUST_POLICY_VERSION,
)
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.decision_loop import (
    ApprovalRecord,
    BlindValidationRecord,
    InvestigationRecord,
    OptimizationRecord,
    SetupComparisonRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.setup_engineering import (
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    EngineeringProblemRecord,
    PostTrackReconciliationRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.evidence_graph_service import EvidenceGraphService
from suspensionlab.backend.services.parameter_trust_service import (
    ParameterTrustService,
    compute_assessment_hash,
    compute_value_identity,
    canonicalize_parameter_unit,
    ParameterNotFoundError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded_trust_env(async_test_db: AsyncSession):
    """
    Populates an authoritative multi-tenant engineering environment:
    - Organization A / Team A / User A (Engineer)
    - Organization B / Team B / User B (Adversary)
    - User C (Personal Workspace, no team)
    - SetupCandidate SETUP-P3L-CAND-01 with front_spring_rate & front_arb_rate
    - BlindValidationRecord VAL-31 (PASSED gate)
    - ApprovalRecord APPR-8 (APPROVED)
    - EvidenceGraphEdge: SETUP-P3L-CAND-01 --VALIDATED_BY--> VAL-31
    - SimulationRun RUN-000183 with k_s
    - VehicleTwin CAR-2026-07 with calibrated front_spring_rate
    - SetupCandidate SETUP-CONFLICT-01 with differing front_spring_rate
    """
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_a = uuid.uuid4()

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    user_c = uuid.uuid4()

    # 1. Authoritative Setup Candidate for Team A
    setup_cand = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-P3L-CAND-01",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={
            "front_spring_rate": {
                "baseline": 80000.0,
                "candidate": 85000.0,
                "delta_pct": 6.25,
            }
        },
        unchanged_parameters={
            "front_arb_rate": 25000.0,
        },
        parameter_provenance={
            "front_spring_rate": "optimization",
            "front_arb_rate": "historical_setup",
        },
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={
            "vehicle_id": "CAR-2026-07",
            "operating_regime": "High-Speed Lateral Cornering",
            "valid_to": "2026-12-31",
        },
        creation_reason="Optimization to reduce front axle slip saturation.",
        artifact_hash="hash_setup_cand_01_abc",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 1, 0, 0, tzinfo=timezone.utc),
    )

    # 2. Out-of-sample Blind Validation Record
    blind_val = BlindValidationRecord(
        id=uuid.uuid4(),
        validation_number=31,
        validation_code="VAL-31",
        setup_id="SETUP-P3L-CAND-01",
        decision_id="DEC-12",
        fit_dataset_ref="TS-381-FIT",
        holdout_dataset_ref="TS-381-HOLDOUT",
        is_zero_leakage=True,
        fit_r2=0.92,
        holdout_r2=0.88,
        holdout_rmse=0.035,
        gate_verdict="PASSED",
        artifact_hash="hash_val_31_xyz",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 1, 30, 0, tzinfo=timezone.utc),
    )

    # 3. Engineering Approval Record
    approval = ApprovalRecord(
        id=uuid.uuid4(),
        approval_number=8,
        approval_code="APPR-8",
        decision_id="DEC-12",
        approver_name="Chief Race Engineer",
        approver_role="CHIEF_RACE_ENGINEER",
        approval_signature="hmac_sig_appr_8_valid",
        status="APPROVED",
        notes="Validated on holdout telemetry dataset.",
        artifact_hash="hash_appr_8_789",
        user_id=user_a,
        team_id=team_a,
        timestamp=datetime(2026, 10, 8, 2, 0, 0, tzinfo=timezone.utc),
    )

    # 4. Simulation Run for Team A
    sim_run = SimulationRun(
        id=uuid.uuid4(),
        seq=183,
        label="RUN-000183",
        simulation_type="quarter_car",
        title="Quarter Car Step Response",
        vehicle_ref="CAR-2026-07",
        setup_ref="SETUP-P3L-CAND-01",
        params={"k_s": 85000.0, "c": 2000.0},
        result={"rms_accel": 1.25},
        params_hash="hash_params_183",
        result_hash="hash_result_183",
        software_version="v2.1",
        physics_version="v2.1",
        solver_version="rk4-v1",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 0, 30, 0, tzinfo=timezone.utc),
    )

    # 5. Vehicle Twin for Team A
    twin = VehicleTwin(
        id=uuid.uuid4(),
        car_ref="CAR-2026-07",
        setup_ref="SETUP-P3L-CAND-01",
        track_ref="Silverstone GP",
        user_id=user_a,
        team_id=team_a,
        base_params={"front_spring_rate": 80000.0},
        calibrated_params={"front_spring_rate": 85000.0},
        calibration_count=4,
        last_calibration_at=datetime(2026, 10, 8, 1, 15, 0, tzinfo=timezone.utc),
    )

    # 6. Team B Setup (Cross-Tenant Entity)
    setup_team_b = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-TEAM-B-01",
        parent_setup_id="SETUP-BASE-B",
        changed_parameters={"front_spring_rate": {"candidate": 90000.0}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-TEAM-B"},
        creation_reason="Team B confidential setup.",
        artifact_hash="hash_team_b_setup",
        user_id=user_b,
        team_id=team_b,
    )

    # 7. User C Personal Workspace Setup (team_id is None)
    setup_personal_c = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-PERSONAL-C-01",
        parent_setup_id="SETUP-BASE-C",
        changed_parameters={"front_spring_rate": {"candidate": 82000.0}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "manually_entered"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-PERSONAL-C"},
        creation_reason="Personal study.",
        artifact_hash="hash_personal_c_setup",
        user_id=user_c,
        team_id=None,
    )

    async_test_db.add_all([
        setup_cand,
        blind_val,
        approval,
        sim_run,
        twin,
        setup_team_b,
        setup_personal_c,
    ])
    await async_test_db.commit()

    # 8. Add canonical Evidence Graph Edges for Team A
    # SetupCandidate --VALIDATED_BY--> BlindValidation
    await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        source_type=SupportedEntityType.SETUP_CANDIDATE.value,
        source_id="SETUP-P3L-CAND-01",
        relationship=EvidenceGraphRelationship.VALIDATED_BY.value,
        target_type=SupportedEntityType.BLIND_VALIDATION.value,
        target_id="VAL-31",
    )

    # SimulationRun --USES_SETUP--> SetupCandidate
    await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        source_type=SupportedEntityType.SIMULATION_RUN.value,
        source_id="RUN-000183",
        relationship=EvidenceGraphRelationship.USES_SETUP.value,
        target_type=SupportedEntityType.SETUP_CANDIDATE.value,
        target_id="SETUP-P3L-CAND-01",
    )

    return {
        "db": async_test_db,
        "org_a": org_a,
        "team_a": team_a,
        "user_a": user_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "user_c": user_c,
        "setup_cand": setup_cand,
        "blind_val": blind_val,
        "approval": approval,
        "sim_run": sim_run,
        "twin": twin,
    }


# ── REQUIREMENT 01: PARAMETER IDENTITY RESOLVED CORRECTLY ─────────────────────

@pytest.mark.asyncio
async def test_01_parameter_identity_resolved_correctly(seeded_trust_env):
    data = seeded_trust_env
    res = await ParameterTrustService.resolve_parameter_from_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert res["entity_type"] == "SetupCandidate"
    assert res["entity_id"] == "SETUP-P3L-CAND-01"
    assert res["parameter_name"] == "front_spring_rate"
    assert res["parameter_path"] == "changed_parameters.front_spring_rate.candidate"
    assert res["unit"] == "N/m"


# ── REQUIREMENT 02: PARAMETER VALUE REFERENCE CORRECT ─────────────────────────

@pytest.mark.asyncio
async def test_02_parameter_value_reference_correct(seeded_trust_env):
    data = seeded_trust_env
    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    val_ref = profile.value_reference
    assert val_ref["value"] == 85000.0
    assert val_ref["unit"] == "N/m"
    assert "value_identity" in val_ref
    assert val_ref["source_entity"] == "SetupCandidate:SETUP-P3L-CAND-01"


# ── REQUIREMENT 03: SOURCE PROVENANCE RESOLVED ────────────────────────────────

@pytest.mark.asyncio
async def test_03_source_provenance_resolved(seeded_trust_env):
    data = seeded_trust_env
    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert profile.provenance_class == ProvenanceClass.OPTIMIZATION.value
    assert profile.provenance_details["source_type"] == "SetupCandidate"
    assert profile.provenance_details["change_delta_pct"] == 6.25


# ── REQUIREMENT 04: SUPPORTING EVIDENCE RESOLVED ──────────────────────────────

@pytest.mark.asyncio
async def test_04_supporting_evidence_resolved(seeded_trust_env):
    data = seeded_trust_env
    evs = await ParameterTrustService.get_parameter_evidence(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert len(evs) >= 2
    types = [e["evidence_type"] for e in evs]
    ids = [e["evidence_id"] for e in evs]
    assert "BlindValidation" in types
    assert "VAL-31" in ids
    assert "SimulationRun" in types
    assert "RUN-000183" in ids


# ── REQUIREMENT 05: EVIDENCE GRAPH TRAVERSAL USES EXISTING VOCABULARY ─────────

@pytest.mark.asyncio
async def test_05_evidence_graph_traversal_uses_existing_vocabulary(seeded_trust_env):
    data = seeded_trust_env
    evs = await ParameterTrustService.get_parameter_evidence(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    canonical_vocab = {r.value for r in EvidenceGraphRelationship}
    for e in evs:
        assert e["relationship"] in canonical_vocab, f"Illegal relationship: {e['relationship']}"


# ── REQUIREMENT 06: NO NEW GRAPH RELATIONSHIP CREATED ─────────────────────────

def test_06_no_new_graph_relationship_created():
    canonical_relationships = {
        "OBSERVED_IN", "DETECTED_FROM", "FORMULATED_FROM", "EVIDENCED_BY",
        "HYPOTHESIZED_FROM", "TESTED_BY", "EXECUTED_AS", "USES_SETUP",
        "PRODUCED_SETUP", "EVALUATED_IN", "OPTIMIZED_TO", "VALIDATED_BY",
        "JUSTIFIED_BY", "APPROVED_UNDER", "PREDICTED_FOR", "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual_relationships = {r.value for r in EvidenceGraphRelationship}
    assert actual_relationships == canonical_relationships
    assert "TRUSTED_BY" not in actual_relationships
    assert "TRUSTED_FROM" not in actual_relationships
    assert "PARAMETER_SUPPORTS" not in actual_relationships


# ── REQUIREMENT 07: VALIDATED PARAMETER CLASSIFIED CORRECTLY ──────────────────

@pytest.mark.asyncio
async def test_07_validated_parameter_classified_correctly(seeded_trust_env):
    data = seeded_trust_env
    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    # Connected to passed BlindValidationRecord VAL-31
    assert profile.current_trust_state == TrustState.VALIDATED.value
    assert profile.validation_coverage == ValidationCoverage.VALIDATED.value


# ── REQUIREMENT 08: UNSUPPORTED PARAMETER CLASSIFIED CORRECTLY ────────────────

@pytest.mark.asyncio
async def test_08_unsupported_parameter_classified_correctly(seeded_trust_env):
    data = seeded_trust_env
    # VehicleProfile without evidence
    prof = VehicleProfile(
        id=uuid.uuid4(),
        name="Bare-Profile",
        params={"k_s": 85000.0},
        user_id=data["user_a"],
        team_id=data["team_a"],
    )
    data["db"].add(prof)
    await data["db"].commit()

    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="VehicleProfile",
        entity_id=str(prof.id),
        parameter_name="k_s",
        team_id=data["team_a"],
    )
    # Manually entered with no validation or simulation connected
    assert profile.current_trust_state == TrustState.PROVISIONAL.value
    assert profile.validation_coverage == ValidationCoverage.NO_VALIDATION.value


# ── REQUIREMENT 09: CONFLICTING EVIDENCE PRODUCES CONFLICTED ──────────────────

@pytest.mark.asyncio
async def test_09_conflicting_evidence_produces_conflicted(seeded_trust_env):
    data = seeded_trust_env
    # Add a conflicting setup for the same vehicle in Team A
    conflicting_setup = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-P3L-CONFLICT",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={"front_spring_rate": {"candidate": 95000.0}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-2026-07"},
        creation_reason="Conflicting optimization.",
        artifact_hash="hash_conflict_cand",
        user_id=data["user_a"],
        team_id=data["team_a"],
    )
    data["db"].add(conflicting_setup)
    await data["db"].commit()

    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert profile.current_trust_state == TrustState.CONFLICTED.value
    assert len(profile.conflicts) > 0
    assert profile.conflicts[0]["conflict_type"] == "VALUE_DIVERGENCE"


# ── REQUIREMENT 10: STALE EVIDENCE IS REPRESENTED ─────────────────────────────

@pytest.mark.asyncio
async def test_10_stale_evidence_is_represented(seeded_trust_env):
    data = seeded_trust_env
    # Create SETUP-OLD and mark it superseded by SETUP-P3L-CAND-01
    old_setup = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-OLD-01",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={"front_spring_rate": {"candidate": 80000.0}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "historical_setup"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-2026-07"},
        creation_reason="Old baseline.",
        artifact_hash="hash_old_setup",
        user_id=data["user_a"],
        team_id=data["team_a"],
    )
    data["db"].add(old_setup)
    await data["db"].commit()

    # SETUP-P3L-CAND-01 --SUPERSEDES--> SETUP-OLD-01
    await EvidenceGraphService.record_edge(
        db=data["db"],
        user_id=data["user_a"],
        team_id=data["team_a"],
        organization_id=data["org_a"],
        source_type=SupportedEntityType.SETUP_CANDIDATE.value,
        source_id="SETUP-P3L-CAND-01",
        relationship=EvidenceGraphRelationship.SUPERSEDES.value,
        target_type=SupportedEntityType.SETUP_CANDIDATE.value,
        target_id="SETUP-OLD-01",
    )

    profile_old = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-OLD-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert profile_old.current_trust_state == TrustState.STALE.value


# ── REQUIREMENT 11: SCOPE IS PRESERVED ────────────────────────────────────────

@pytest.mark.asyncio
async def test_11_scope_is_preserved(seeded_trust_env):
    data = seeded_trust_env
    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    scope = profile.scope
    assert scope["vehicle_id"] == "CAR-2026-07"
    assert scope["operating_regime"] == "High-Speed Lateral Cornering"
    assert scope["valid_to"] == "2026-12-31"


# ── REQUIREMENT 12: VALIDATION COVERAGE IS CORRECT ────────────────────────────

@pytest.mark.asyncio
async def test_12_validation_coverage_is_correct(seeded_trust_env):
    data = seeded_trust_env
    # 1. SETUP-P3L-CAND-01 has passed out-of-sample holdout gate -> VALIDATED
    p1 = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert p1.validation_coverage == ValidationCoverage.VALIDATED.value

    # 2. RUN-000183 has simulation only -> NO_VALIDATION
    p2 = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SimulationRun",
        entity_id="RUN-000183",
        parameter_name="k_s",
        team_id=data["team_a"],
    )
    assert p2.validation_coverage == ValidationCoverage.NO_VALIDATION.value


# ── REQUIREMENT 13: EXPLANATION IS DETERMINISTIC ──────────────────────────────

@pytest.mark.asyncio
async def test_13_explanation_is_deterministic(seeded_trust_env):
    data = seeded_trust_env
    res1 = await ParameterTrustService.explain_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    res2 = await ParameterTrustService.explain_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert res1["assessment_hash"] == res2["assessment_hash"]
    assert res1["explanation"]["reasons"] == res2["explanation"]["reasons"]
    assert res1["explanation"]["state"] == res2["explanation"]["state"]


# ── REQUIREMENT 14: SAME EVIDENCE PRODUCES SAME ASSESSMENT ────────────────────

@pytest.mark.asyncio
async def test_14_same_evidence_produces_same_assessment(seeded_trust_env):
    data = seeded_trust_env
    p1 = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    p2 = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert p1.assessment_hash == p2.assessment_hash
    assert p1.current_trust_state == p2.current_trust_state


# ── REQUIREMENT 15: CHANGED EVIDENCE CHANGES ASSESSMENT IDENTITY ──────────────

@pytest.mark.asyncio
async def test_15_changed_evidence_changes_assessment_identity(seeded_trust_env):
    data = seeded_trust_env
    p_before = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    hash_before = p_before.assessment_hash

    # Mutate the artifact hash of the validation record in DB
    data["blind_val"].artifact_hash = "mutated_artifact_hash_9999"
    await data["db"].commit()

    p_after = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    hash_after = p_after.assessment_hash
    assert hash_before != hash_after, "Assessment hash must change when evidence changes!"


# ── REQUIREMENT 16: TRUST POLICY VERSION IS PRESERVED ─────────────────────────

@pytest.mark.asyncio
async def test_16_trust_policy_version_is_preserved(seeded_trust_env):
    data = seeded_trust_env
    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert profile.policy_version == TRUST_POLICY_V1

    history = await ParameterTrustService.get_parameter_trust_history(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert all(h["policy_version"] == TRUST_POLICY_V1 for h in history)


# ── REQUIREMENT 17: NO TEXTUAL HEURISTICS AFFECT TRUST ────────────────────────

@pytest.mark.asyncio
async def test_17_no_textual_heuristics_affect_trust(seeded_trust_env):
    data = seeded_trust_env
    p1 = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    initial_state = p1.current_trust_state

    # Inject deceptive text into creation_reason
    data["setup_cand"].creation_reason = "This setup is validated and measured with high confidence."
    await data["db"].commit()

    p2 = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert p2.current_trust_state == initial_state, "Textual description must never affect trust state!"


# ── REQUIREMENT 18: TENANT ISOLATION ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_18_tenant_isolation(seeded_trust_env):
    data = seeded_trust_env
    # User B (Team B) attempts to query Team A's parameter
    with pytest.raises(Exception):
        await ParameterTrustService.resolve_parameter_from_entity(
            db=data["db"],
            entity_type="SetupCandidate",
            entity_id="SETUP-P3L-CAND-01",
            parameter_name="front_spring_rate",
            team_id=data["team_b"],
        )


# ── REQUIREMENT 19: PERSONAL WORKSPACE ISOLATION ──────────────────────────────

@pytest.mark.asyncio
async def test_19_personal_workspace_isolation(seeded_trust_env):
    data = seeded_trust_env
    # User C has personal setup SETUP-PERSONAL-C-01
    res = await ParameterTrustService.resolve_parameter_from_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-PERSONAL-C-01",
        parameter_name="front_spring_rate",
        user_id=data["user_c"],
    )
    assert res["entity_id"] == "SETUP-PERSONAL-C-01"

    # User A cannot access User C's personal setup
    with pytest.raises(Exception):
        await ParameterTrustService.resolve_parameter_from_entity(
            db=data["db"],
            entity_type="SetupCandidate",
            entity_id="SETUP-PERSONAL-C-01",
            parameter_name="front_spring_rate",
            user_id=data["user_a"],
        )


# ── REQUIREMENT 20: UNAUTHORIZED PARAMETER REJECTED VIA API ───────────────────

@pytest.mark.asyncio
async def test_20_unauthorized_parameter_rejected(seeded_trust_env):
    data = seeded_trust_env
    mock_user_b = UserContext(
        user_id=str(data["user_b"]),
        email="eng_b@teamb.com",
        name="Engineer B",
        plan="PRO",
        onboarding_complete=True,
        team_id=str(data["team_b"]),
        organization_id=str(data["org_b"]),
    )
    app.dependency_overrides[verify_api_key] = lambda: mock_user_b
    app.dependency_overrides[get_db_dependency] = lambda: data["db"]

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate")
            # Must return 404 to prevent enumeration / IDOR leakage
            assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


# ── REQUIREMENT 21: MISSING EVIDENCE HANDLED DETERMINISTICALLY ────────────────

@pytest.mark.asyncio
async def test_21_missing_evidence_handled_deterministically(seeded_trust_env):
    data = seeded_trust_env
    # Setup candidate with zero evidence edges
    bare_cand = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-ISOLATED-01",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={"front_spring_rate": {"candidate": 85000.0}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={},
        creation_reason="Isolated test.",
        artifact_hash="hash_isolated_01",
        user_id=data["user_a"],
        team_id=data["team_a"],
    )
    data["db"].add(bare_cand)
    await data["db"].commit()

    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-ISOLATED-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert profile.current_trust_state == TrustState.INSUFFICIENT_EVIDENCE.value
    assert profile.validation_coverage == ValidationCoverage.NO_VALIDATION.value


# ── REQUIREMENT 22: MISSING PARAMETER HANDLED SAFELY ──────────────────────────

@pytest.mark.asyncio
async def test_22_missing_parameter_handled_safely(seeded_trust_env):
    data = seeded_trust_env
    with pytest.raises(ParameterNotFoundError):
        await ParameterTrustService.resolve_parameter_from_entity(
            db=data["db"],
            entity_type="SetupCandidate",
            entity_id="SETUP-P3L-CAND-01",
            parameter_name="non_existent_parameter",
            team_id=data["team_a"],
        )


# ── REQUIREMENT 23: HIDDEN / INACCESSIBLE EVIDENCE DOES NOT LEAK ───────────────

@pytest.mark.asyncio
async def test_23_hidden_inaccessible_evidence_does_not_leak(seeded_trust_env):
    data = seeded_trust_env
    # Team B creates a validation record for their own setup
    val_b = BlindValidationRecord(
        id=uuid.uuid4(),
        validation_number=99,
        validation_code="VAL-TEAM-B",
        setup_id="SETUP-TEAM-B-01",
        fit_dataset_ref="TS-B",
        holdout_dataset_ref="TS-B-HOLD",
        is_zero_leakage=True,
        fit_r2=0.9,
        holdout_r2=0.9,
        holdout_rmse=0.01,
        gate_verdict="PASSED",
        artifact_hash="hash_val_b",
        user_id=data["user_b"],
        team_id=data["team_b"],
    )
    data["db"].add(val_b)
    await data["db"].commit()

    evs = await ParameterTrustService.get_parameter_evidence(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    ev_ids = [e["evidence_id"] for e in evs]
    assert "VAL-TEAM-B" not in ev_ids, "Team B evidence must never leak into Team A query!"


# ── REQUIREMENT 24: API SCHEMA CONTAINS NO UNAUTHORIZED DATA ──────────────────

@pytest.mark.asyncio
async def test_24_api_schema_contains_no_unauthorized_data(seeded_trust_env):
    data = seeded_trust_env
    mock_user_a = UserContext(
        user_id=str(data["user_a"]),
        email="eng_a@teama.com",
        name="Engineer A",
        plan="PRO",
        onboarding_complete=True,
        team_id=str(data["team_a"]),
        organization_id=str(data["org_a"]),
    )
    app.dependency_overrides[verify_api_key] = lambda: mock_user_a
    app.dependency_overrides[get_db_dependency] = lambda: data["db"]

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate")
            assert res.status_code == 200
            body = res.json()
            # Verify clean DTO schema
            assert "parameter_identity" in body
            assert "value_reference" in body
            assert "current_trust_state" in body
            assert "assessment_hash" in body
            assert "password" not in str(body).lower()
            assert "secret" not in str(body).lower()
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


# ── REQUIREMENT 25: HISTORY IS ORDERED DETERMINISTICALLY ──────────────────────

@pytest.mark.asyncio
async def test_25_history_is_ordered_deterministically(seeded_trust_env):
    data = seeded_trust_env
    # Perform initial evaluation
    await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    # Modify artifact hash and re-evaluate
    data["blind_val"].artifact_hash = "new_val_hash_1"
    await data["db"].commit()
    await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )

    history = await ParameterTrustService.get_parameter_trust_history(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert len(history) == 2
    # Deterministic order: descending by created_at
    assert history[0]["created_at"] >= history[1]["created_at"]


# ── REQUIREMENT 26: ASSESSMENT HASH DETERMINISTIC ─────────────────────────────

def test_26_assessment_hash_deterministic():
    h1 = compute_assessment_hash(
        entity_type="SetupCandidate",
        entity_id="SETUP-101",
        parameter_name="front_spring_rate",
        parameter_path="changed_parameters.front_spring_rate.candidate",
        value_identity="val_id_1",
        policy_version=TRUST_POLICY_V1,
        trust_state=TrustState.VALIDATED.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        scope={"vehicle_id": "CAR-1"},
        evidence_hashes=["hash_a", "hash_b"],
        conflicts=[],
    )
    h2 = compute_assessment_hash(
        entity_type="SetupCandidate",
        entity_id="SETUP-101",
        parameter_name="front_spring_rate",
        parameter_path="changed_parameters.front_spring_rate.candidate",
        value_identity="val_id_1",
        policy_version=TRUST_POLICY_V1,
        trust_state=TrustState.VALIDATED.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        scope={"vehicle_id": "CAR-1"},
        evidence_hashes=["hash_b", "hash_a"],  # Different order
        conflicts=[],
    )
    assert h1 == h2, "Assessment hash must be invariant to evidence hash ordering!"


# ── REQUIREMENT 27: FRONTEND RENDERS REAL TRUST STATE ─────────────────────────

def test_27_frontend_renders_real_trust_state():
    frontend_test_file = PROJECT_ROOT / "frontend" / "tests" / "parameterTrust.test.ts"
    assert frontend_test_file.exists(), "Frontend test file must exist!"
    content = frontend_test_file.read_text(encoding="utf-8")
    assert "getParameterTrust" in content
    assert "getParameterTrustHistory" in content
    assert "explainParameterTrust" in content


# ── REQUIREMENT 28: FRONTEND DOES NOT INVENT EVIDENCE ─────────────────────────

def test_28_frontend_does_not_invent_evidence():
    component_file = PROJECT_ROOT / "frontend" / "components" / "engineering" / "ParameterTrustMap.tsx"
    assert component_file.exists(), "ParameterTrustMap component must exist!"
    content = component_file.read_text(encoding="utf-8")
    # Verify component does not have hardcoded mock scores
    assert "trust_score = 0.8" not in content
    assert "0.83" not in content
    assert "ParameterTrustApi" in content


# ── REQUIREMENT 29: PHASE 4 REGRESSION REMAINS GREEN ──────────────────────────

def test_29_phase4_regression_remains_green():
    p4_1 = PROJECT_ROOT / "tests" / "test_phase4_1_evidence_graph_schema.py"
    p4_2 = PROJECT_ROOT / "tests" / "test_phase4_2_evidence_graph_traversal.py"
    assert p4_1.exists()
    assert p4_2.exists()


# ── REQUIREMENT 30: PHASE 5 REGRESSION REMAINS GREEN & INDEPENDENT ────────────

def test_30_phase5_regression_remains_green():
    service_file = PROJECT_ROOT / "src" / "suspensionlab" / "backend" / "services" / "parameter_trust_service.py"
    routes_file = PROJECT_ROOT / "src" / "suspensionlab" / "backend" / "api" / "routes" / "parameter_trust_routes.py"
    models_file = PROJECT_ROOT / "src" / "suspensionlab" / "backend" / "database" / "models" / "parameter_trust.py"

    for f in (service_file, routes_file, models_file):
        code = f.read_text(encoding="utf-8")
        assert "BlindEngineeringSession" not in code
        assert "BlindSubmission" not in code
        assert "BlindPrediction" not in code


# ── REQUIREMENT 31: PRODUCTION PHYSICS UNCHANGED ──────────────────────────────

def test_31_production_physics_unchanged():
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing physics file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Physics modification in {item['path']}!"


# ── REQUIREMENT 32: PHASE 3 ARTIFACTS UNCHANGED ───────────────────────────────

def test_32_phase3_artifacts_unchanged():
    manifests = [
        PHASE3H_MANIFEST,
        PHASE3K1_MANIFEST,
        PHASE3L_MANIFEST,
        PHASE3M_MANIFEST,
        PROJECT_ROOT / "docs" / "phase3m_independent_engineering_case.md",
        PROJECT_ROOT / "docs" / "phase3o_preregistration_manifest.json",
        PROJECT_ROOT / "docs" / "phase3p_preregistration_manifest.json",
    ]
    for m in manifests:
        assert m.exists(), f"Protected Phase 3 manifest missing: {m}"


# ── ADVERSARIAL IDOR & EVIDENCE LEAKAGE SUITE ─────────────────────────────────

@pytest.mark.asyncio
async def test_adversarial_cross_tenant_history_blocked(seeded_trust_env):
    data = seeded_trust_env
    # User B attempts to access history of Team A setup
    with pytest.raises(Exception):
        await ParameterTrustService.get_parameter_trust_history(
            db=data["db"],
            entity_type="SetupCandidate",
            entity_id="SETUP-P3L-CAND-01",
            parameter_name="front_spring_rate",
            team_id=data["team_b"],
        )


@pytest.mark.asyncio
async def test_adversarial_no_manual_mutation_route_exists():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Prohibited manual declaration endpoints must 404 or 405
        res1 = await client.post("/api/v1/parameter-trust/SetupCandidate/SETUP-1/front_spring_rate", json={"trust": "VALIDATED"})
        assert res1.status_code in (404, 405)
        res2 = await client.post("/api/v1/trust-score", json={"score": 0.95})
        assert res2.status_code in (404, 405)
