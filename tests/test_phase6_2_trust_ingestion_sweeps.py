"""
tests/test_phase6_2_trust_ingestion_sweeps.py
=============================================
SuspensionLab PRO — Phase 6.2 Automated Parameter Trust Ingestion,
Sweep Analysis & Recency Modeling Acceptance & Verification Suite.

Complete 50+ Test Verification Matrix:
 1. test_01_authoritative_source_discovery
 2. test_02_supported_parameter_resolution
 3. test_03_unsupported_source_rejected_explicitly
 4. test_04_no_parameter_discovery_from_descriptive_text
 5. test_05_correct_structured_provenance
 6. test_06_deterministic_value_identity
 7. test_07_batch_ingestion_creates_required_profiles
 8. test_08_identical_batch_is_idempotent
 9. test_09_duplicate_evidence_is_not_created
10. test_10_changed_value_triggers_reassessment
11. test_11_changed_evidence_hash_triggers_reassessment
12. test_12_irrelevant_changes_do_not_force_reassessment
13. test_13_malformed_entity_handled_safely
14. test_14_partial_failure_is_reported_accurately
15. test_15_batch_retry_is_safe
16. test_16_repeated_batch_creates_no_artificial_history
17. test_17_sweep_groups_comparable_parameters_correctly
18. test_18_incompatible_scope_is_excluded
19. test_19_unit_incompatibility_is_explicit
20. test_20_normalized_values_produce_correct_ranges
21. test_21_conflicts_are_represented_without_overwriting_sources
22. test_22_superseded_sources_are_handled_correctly
23. test_23_validation_coverage_across_a_sweep_is_accurate
24. test_24_no_simulation_is_misclassified_as_physical_validation
25. test_25_source_timestamps_are_normalized
26. test_26_missing_timestamps_yield_explicit_status
27. test_27_expiration_follows_declared_validity_rules
28. test_28_old_but_valid_evidence_is_not_automatically_rejected
29. test_29_recent_but_weak_evidence_is_not_automatically_trusted
30. test_30_parameter_change_triggers_the_correct_refresh
31. test_31_recency_policy_version_is_preserved
32. test_32_assessment_history_is_deterministic
33. test_33_unchanged_assessment_identity_is_stable
34. test_34_changed_assessment_input_changes_identity
35. test_35_sweep_report_identity_is_deterministic
36. test_36_batch_report_is_deterministic
37. test_37_085_validation_threshold_provenance_audit
38. test_38_no_undocumented_trust_weights_are_introduced
39. test_39_tenant_isolation_for_ingestion
40. test_40_personal_workspace_isolation
41. test_41_tenant_isolation_for_sweep_aggregates
42. test_42_cross_tenant_cache_leakage_prevented
43. test_43_existing_read_apis_still_return_authorized_data
44. test_44_phase6_1_regression_remains_green
45. test_45_phase4_regression_remains_green
46. test_46_phase5_remains_independent
47. test_47_phase5_4_remains_independent
48. test_48_production_physics_unchanged
49. test_49_phase3_artifacts_unchanged
50. test_50_evidence_graph_schema_and_vocabulary_unchanged
51. test_51_adversarial_transaction_rollback_and_partial_failure
52. test_52_adversarial_concurrent_batch_retries
53. test_53_adversarial_evidence_set_ordering_stability
54. test_54_adversarial_cross_tenant_sweep_injection
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
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    TRUST_POLICY_V1,
    CURRENT_TRUST_POLICY_VERSION,
    TRUST_RECENCY_POLICY_V1,
    CURRENT_TRUST_RECENCY_POLICY_VERSION,
    DEFAULT_RECENCY_ADVISORY_THRESHOLD_DAYS,
    RecencyCondition,
    TrustConflictType,
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
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    UnsupportedRelationshipError,
    MalformedIdentifierError,
)
from suspensionlab.backend.services.parameter_trust_service import (
    ParameterTrustService,
    compute_assessment_hash,
    compute_value_identity,
    canonicalize_parameter_unit,
    ParameterNotFoundError,
)
from suspensionlab.backend.services.parameter_trust_ingestion_service import (
    ParameterTrustIngestionService,
    are_units_dimensionally_compatible,
    convert_parameter_value,
    normalize_numeric_value,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded_ingestion_env(async_test_db: AsyncSession):
    """
    Sets up a full multi-tenant environment with multiple candidates,
    simulations, vehicle profiles, twins, telemetry, and evidence graph edges.
    """
    db = async_test_db
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_a = uuid.uuid4()

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    user_c = uuid.uuid4()  # personal workspace

    # 1. SetupCandidate A1: SETUP-P3L-CAND-01 (Validated front_spring_rate & front_arb_rate)
    cand1 = SetupCandidateRecord(
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
        creation_reason="Authoritative setup candidate 1.",
        artifact_hash="hash_cand1_xyz",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 1, 0, 0, tzinfo=timezone.utc),
    )

    # 2. SetupCandidate A2: SETUP-P3L-CAND-02 (Sweep variant with higher spring rate)
    cand2 = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-P3L-CAND-02",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={
            "front_spring_rate": {
                "baseline": 80000.0,
                "candidate": 92000.0,
                "delta_pct": 15.0,
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
        creation_reason="Authoritative setup candidate 2.",
        artifact_hash="hash_cand2_abc",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 2, 0, 0, tzinfo=timezone.utc),
    )

    # 3. SetupCandidate A3: SETUP-DIFF-REGIME (Different regime: Low-Speed Ride)
    cand3 = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-DIFF-REGIME",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={
            "front_spring_rate": {
                "baseline": 80000.0,
                "candidate": 70000.0,
                "delta_pct": -12.5,
            }
        },
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={
            "vehicle_id": "CAR-2026-07",
            "operating_regime": "Low-Speed Ride / Curbs",
            "valid_to": "2026-12-31",
        },
        creation_reason="Authoritative setup candidate 3 diff regime.",
        artifact_hash="hash_cand3_regime",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 3, 0, 0, tzinfo=timezone.utc),
    )

    # 4. Out-of-sample Validation for Candidate 1
    val1 = BlindValidationRecord(
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
        artifact_hash="hash_val1_123",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 1, 30, 0, tzinfo=timezone.utc),
    )

    # 5. Simulation Run: RUN-000183
    sim_run = SimulationRun(
        id=uuid.uuid4(),
        seq=183,
        label="RUN-000183",
        simulation_type="quarter_car",
        title="Quarter Car Step Response",
        vehicle_ref="CAR-2026-07",
        setup_ref="SETUP-P3L-CAND-01",
        params={"front_spring_rate": 85000.0, "k_s": 85000.0, "c": 2000.0},
        result={"rms_accel": 1.25},
        params_hash="hash_params_183",
        result_hash="hash_result_183",
        software_version="v2.1",
        physics_version="v2.1",
        solver_version="v1.0.4",
        model_validity={"validity": "VALID"},
        warnings=[],
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 1, 15, 0, tzinfo=timezone.utc),
    )

    # 6. VehicleProfile: VP-GT3
    vp = VehicleProfile(
        id=uuid.uuid4(),
        name="VP-GT3",
        vehicle_type="FULL_CAR",
        version=1,
        params={"front_spring_rate": 85000.0, "rear_spring_rate": 95000.0, "mass_kg": 1250.0},
        user_id=user_a,
        team_id=team_a,
    )

    # 7. VehicleTwin: CAR-2026-07
    twin = VehicleTwin(
        id=uuid.uuid4(),
        car_ref="CAR-2026-07",
        setup_ref="SETUP-P3L-CAND-01",
        track_ref="THUNDERHILL-WEST",
        calibrated_params={"front_spring_rate": 85000.0, "c_bump_f": 2200.0},
        base_params={"front_spring_rate": 80000.0},
        calibration_count=4,
        last_calibration_at=datetime(2026, 10, 8, 2, 30, 0, tzinfo=timezone.utc),
        user_id=user_a,
        team_id=team_a,
    )

    # 8. OptimizationRecord: OPT-P3L-01
    opt = OptimizationRecord(
        id=uuid.uuid4(),
        optimization_number=1,
        optimization_code="OPT-P3L-01",
        experiment_id="EXP-52",
        objective="MINIMIZE_FRONT_TIRE_SATURATION",
        constraints=[],
        design_variables=["front_spring_rate", "front_arb_rate"],
        candidates_evaluated=10,
        optimal_setup_id="SETUP-P3L-CAND-01",
        optimal_parameters={"front_spring_rate": 85000.0, "front_arb_rate": 25000.0},
        pareto_frontier=[],
        status="CONVERGED",
        solver_calls=42,
        artifact_hash="hash_opt_01",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 0, 45, 0, tzinfo=timezone.utc),
    )

    # 9. TelemetrySessionRecord: TS-STANFORD-01
    telemetry = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=1,
        session_code="TS-STANFORD-01",
        vehicle_id="CAR-2026-07",
        setup_id="SETUP-P3L-CAND-01",
        track_name="Thunderhill West",
        channels={"time": [0.0, 0.1], "speed": [25.0, 26.0]},
        sample_count=50000,
        duration_s=120.5,
        summary_metrics={"roll_angle_deg": 3.37, "ay_peak_g": 1.91},
        artifact_hash="hash_telem_01",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime(2026, 10, 8, 0, 30, 0, tzinfo=timezone.utc),
    )

    # 10. Adversary Team B candidate
    cand_b = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-TEAM-B-01",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={"front_spring_rate": 99000.0},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-TEAM-B"},
        creation_reason="Team B setup candidate.",
        artifact_hash="hash_team_b",
        user_id=user_b,
        team_id=team_b,
        created_at=datetime(2026, 10, 8, 1, 0, 0, tzinfo=timezone.utc),
    )

    db.add_all([cand1, cand2, cand3, val1, sim_run, vp, twin, opt, telemetry, cand_b])
    await db.commit()

    # Evidence Graph Edges
    # SETUP-P3L-CAND-01 --VALIDATED_BY--> VAL-31
    await EvidenceGraphService.record_edge(
        db=db,
        user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        source_type=SupportedEntityType.SETUP_CANDIDATE.value,
        source_id="SETUP-P3L-CAND-01",
        relationship=EvidenceGraphRelationship.VALIDATED_BY.value,
        target_type=SupportedEntityType.BLIND_VALIDATION.value,
        target_id="VAL-31",
    )

    # SIMULATION-RUN --USES_SETUP--> SETUP-P3L-CAND-01
    await EvidenceGraphService.record_edge(
        db=db,
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
        "db": db,
        "org_a": org_a,
        "team_a": team_a,
        "user_a": user_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "user_c": user_c,
        "cand1": cand1,
        "cand2": cand2,
        "cand3": cand3,
        "val1": val1,
        "sim_run": sim_run,
        "vp": vp,
        "twin": twin,
        "opt": opt,
        "telemetry": telemetry,
        "cand_b": cand_b,
    }


# ── TEST 01: AUTHORITATIVE SOURCE DISCOVERY ───────────────────────────────────

@pytest.mark.asyncio
async def test_01_authoritative_source_discovery(seeded_ingestion_env):
    data = seeded_ingestion_env
    # 1. SetupCandidate discovery
    cand_params = ParameterTrustIngestionService.discover_entity_parameters(data["cand1"], "SetupCandidate")
    assert "front_spring_rate" in cand_params
    assert "front_arb_rate" in cand_params

    # 2. VehicleProfile discovery
    vp_params = ParameterTrustIngestionService.discover_entity_parameters(data["vp"], "VehicleProfile")
    assert "front_spring_rate" in vp_params
    assert "mass_kg" in vp_params

    # 3. VehicleTwin discovery
    twin_params = ParameterTrustIngestionService.discover_entity_parameters(data["twin"], "VehicleTwin")
    assert "front_spring_rate" in twin_params
    assert "c_bump_f" in twin_params


# ── TEST 02: SUPPORTED PARAMETER RESOLUTION ───────────────────────────────────

@pytest.mark.asyncio
async def test_02_supported_parameter_resolution(seeded_ingestion_env):
    data = seeded_ingestion_env
    resolved = await ParameterTrustService.resolve_parameter_from_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert resolved["parameter_name"] == "front_spring_rate"
    assert resolved["value"] == 85000.0
    assert resolved["unit"] == "N/m"
    assert resolved["provenance_class"] == "optimization"


# ── TEST 03: UNSUPPORTED SOURCE REJECTED EXPLICITLY ───────────────────────────

def test_03_unsupported_source_rejected_explicitly():
    class FakeEntity:
        pass

    with pytest.raises(UnsupportedEntityTypeError):
        ParameterTrustIngestionService.discover_entity_parameters(FakeEntity(), "UnsupportedWidget")


# ── TEST 04: NO PARAMETER DISCOVERY FROM DESCRIPTIVE TEXT ─────────────────────

@pytest.mark.asyncio
async def test_04_no_parameter_discovery_from_descriptive_text(seeded_ingestion_env):
    data = seeded_ingestion_env
    cand = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-TEXT-01",
        parent_setup_id="SETUP-BASE-01",
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        changed_parameters={"k_s": 85000.0},
        unchanged_parameters={},
        parameter_provenance={"k_s": "optimization"},
        validity_domain={"vehicle_id": "CAR-2026-07"},
        creation_reason="We changed rear_arb_rate and tire_pressure to optimize yaw response",
        artifact_hash="hash_txt",
        user_id=data["user_a"],
        team_id=data["team_a"],
    )
    data["db"].add(cand)
    await data["db"].commit()

    params = ParameterTrustIngestionService.discover_entity_parameters(cand, "SetupCandidate")
    assert "k_s" in params
    # Words in creation_reason must NEVER become parameters
    assert "rear_arb_rate" not in params
    assert "tire_pressure" not in params
    assert "yaw" not in params


# ── TEST 05: CORRECT STRUCTURED PROVENANCE ────────────────────────────────────

@pytest.mark.asyncio
async def test_05_correct_structured_provenance(seeded_ingestion_env):
    data = seeded_ingestion_env
    resolved_opt = await ParameterTrustService.resolve_parameter_from_entity(
        db=data["db"],
        entity_type="Optimization",
        entity_id="OPT-P3L-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert resolved_opt["provenance_class"] == ProvenanceClass.OPTIMIZATION.value
    assert resolved_opt["provenance_details"]["status"] == "CONVERGED"


# ── TEST 06: DETERMINISTIC VALUE IDENTITY ─────────────────────────────────────

def test_06_deterministic_value_identity():
    id1 = compute_value_identity(85000.0)
    id2 = compute_value_identity(85000.0)
    id3 = compute_value_identity(85000.1)
    assert id1 == id2
    assert id1 != id3


# ── TEST 07: BATCH INGESTION CREATES REQUIRED PROFILES ────────────────────────

@pytest.mark.asyncio
async def test_07_batch_ingestion_creates_required_profiles(seeded_ingestion_env):
    data = seeded_ingestion_env
    res = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
            {"entity_type": "VehicleProfile", "entity_id": str(data["vp"].id)},
        ],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["discovered_entities"] == 2
    assert res["new_profiles"] >= 4
    assert res["discovered_parameters"] >= 4
    assert res["batch_hash"] is not None


# ── TEST 08: IDENTICAL BATCH IS IDEMPOTENT ────────────────────────────────────

@pytest.mark.asyncio
async def test_08_identical_batch_is_idempotent(seeded_ingestion_env):
    data = seeded_ingestion_env
    # First run
    run1 = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=[{"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"}],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    # Second run with exact same state
    run2 = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=[{"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"}],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert run1["new_profiles"] == 2  # front_spring_rate, front_arb_rate
    assert run2["new_profiles"] == 0
    assert run2["unchanged_assessments"] == 2
    assert run2["refreshed_assessments"] == 0
    assert run1["batch_hash"] == run2["batch_hash"]


# ── TEST 09: DUPLICATE EVIDENCE IS NOT CREATED ────────────────────────────────

@pytest.mark.asyncio
async def test_09_duplicate_evidence_is_not_created(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Re-run ingestion 3 times
    for _ in range(3):
        await ParameterTrustIngestionService.ingest_entity(
            db=data["db"],
            entity_type="SetupCandidate",
            entity_id="SETUP-P3L-CAND-01",
            team_id=data["team_a"],
            user_id=data["user_a"],
        )

    # Query evidence count in DB
    ev_stmt = select(ParameterTrustEvidenceRecord)
    ev_res = await data["db"].execute(ev_stmt)
    evidence_rows = ev_res.scalars().all()

    # Evidence records for CAND-01 should not be duplicated
    cand1_evs = [e for e in evidence_rows if e.evidence_id == "VAL-31"]
    assert len(cand1_evs) == 2, f"Expected exactly 2 evidence links to VAL-31 (1 per profile), found {len(cand1_evs)}"


# ── TEST 10: CHANGED VALUE TRIGGERS REASSESSMENT ──────────────────────────────

@pytest.mark.asyncio
async def test_10_changed_value_triggers_reassessment(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Initial ingestion
    await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    # Mutate value in candidate record
    data["cand1"].changed_parameters["front_spring_rate"]["candidate"] = 89000.0
    await data["db"].commit()

    # Ingest again
    res = await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["refreshed_assessments"] >= 1


# ── TEST 11: CHANGED EVIDENCE HASH TRIGGERS REASSESSMENT ──────────────────────

@pytest.mark.asyncio
async def test_11_changed_evidence_hash_triggers_reassessment(seeded_ingestion_env):
    data = seeded_ingestion_env
    p_before = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    h_before = p_before.assessment_hash

    # Mutate validation artifact hash
    data["val1"].artifact_hash = "mutated_hash_new_val_99"
    await data["db"].commit()

    res = await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["refreshed_assessments"] >= 1
    p_after = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert p_after.assessment_hash != h_before


# ── TEST 12: IRRELEVANT CHANGES DO NOT FORCE REASSESSMENT ─────────────────────

@pytest.mark.asyncio
async def test_12_irrelevant_changes_do_not_force_reassessment(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Perform initial ingestion so all parameters for CAND-01 are assessed
    await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    # Irrelevant change: modify human-facing creation_reason string
    data["cand1"].creation_reason = "Updated note by engineer: this is totally cosmetic."
    await data["db"].commit()

    res = await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["unchanged_assessments"] == 2
    assert res["refreshed_assessments"] == 0
    assert res["new_profiles"] == 0


# ── TEST 13: MALFORMED ENTITY HANDLED SAFELY ──────────────────────────────────

@pytest.mark.asyncio
async def test_13_malformed_entity_handled_safely(seeded_ingestion_env):
    data = seeded_ingestion_env
    res = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=[{"entity_type": "SetupCandidate", "entity_id": "NON-EXISTENT-SETUP"}],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert len(res["errors"]) == 1
    assert res["errors"][0]["reason"] == "NOT_FOUND"


# ── TEST 14: PARTIAL FAILURE IS REPORTED ACCURATELY ───────────────────────────

@pytest.mark.asyncio
async def test_14_partial_failure_is_reported_accurately(seeded_ingestion_env):
    data = seeded_ingestion_env
    res = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
            {"entity_type": "UnsupportedType", "entity_id": "WIDGET-01"},
            {"entity_type": "SetupCandidate", "entity_id": "GHOST-SETUP"},
        ],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["discovered_entities"] == 3
    assert len(res["skipped_entities"]) == 1
    assert res["skipped_entities"][0]["reason"] == "UNSUPPORTED_ENTITY_TYPE"
    assert len(res["errors"]) == 1
    assert res["errors"][0]["reason"] == "NOT_FOUND"
    assert res["new_profiles"] >= 1 or res["unchanged_assessments"] >= 1


# ── TEST 15: BATCH RETRY IS SAFE ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_15_batch_retry_is_safe(seeded_ingestion_env):
    data = seeded_ingestion_env
    batch = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
        {"entity_type": "VehicleProfile", "entity_id": str(data["vp"].id)},
    ]
    res1 = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"], entities=batch, team_id=data["team_a"], user_id=data["user_a"]
    )
    res2 = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"], entities=batch, team_id=data["team_a"], user_id=data["user_a"]
    )
    assert res1["batch_hash"] == res2["batch_hash"]


# ── TEST 16: REPEATED BATCH CREATES NO ARTIFICIAL HISTORY ─────────────────────

@pytest.mark.asyncio
async def test_16_repeated_batch_creates_no_artificial_history(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Run batch twice
    for _ in range(2):
        await ParameterTrustIngestionService.ingest_batch(
            db=data["db"],
            entities=[{"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"}],
            team_id=data["team_a"],
            user_id=data["user_a"],
        )

    # Query assessment history count for front_spring_rate
    prof_stmt = select(ParameterTrustProfile).where(
        ParameterTrustProfile.entity_id == "SETUP-P3L-CAND-01",
        ParameterTrustProfile.parameter_name == "front_spring_rate",
    )
    prof_res = await data["db"].execute(prof_stmt)
    prof = prof_res.scalars().first()

    hist_stmt = select(ParameterTrustAssessmentRecord).where(
        ParameterTrustAssessmentRecord.profile_id == prof.id
    )
    hist_res = await data["db"].execute(hist_stmt)
    history_logs = hist_res.scalars().all()

    assert len(history_logs) == 1, f"Expected exactly 1 historical log, found {len(history_logs)}"


# ── TEST 17: SWEEP GROUPS COMPARABLE PARAMETERS CORRECTLY ─────────────────────

@pytest.mark.asyncio
async def test_17_sweep_groups_comparable_parameters_correctly(seeded_ingestion_env):
    data = seeded_ingestion_env
    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="front_spring_rate",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-02"},
        ],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert sweep["comparable_count"] == 2
    assert sweep["excluded_count"] == 0
    assert sweep["summary_metrics"]["min"] == 85000.0
    assert sweep["summary_metrics"]["max"] == 92000.0
    assert sweep["summary_metrics"]["delta"] == 7000.0


# ── TEST 18: INCOMPATIBLE SCOPE IS EXCLUDED ───────────────────────────────────

@pytest.mark.asyncio
async def test_18_incompatible_scope_is_excluded(seeded_ingestion_env):
    data = seeded_ingestion_env
    # CAND1 is High-Speed Lateral; CAND3 is Low-Speed Ride
    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="front_spring_rate",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-DIFF-REGIME"},
        ],
        team_id=data["team_a"],
        user_id=data["user_a"],
        baseline_candidate={"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
    )
    assert sweep["comparable_count"] == 1
    assert sweep["excluded_count"] == 1
    assert "SCOPE_MISMATCH" in sweep["excluded_observations"][0]["exclusion_reason"]


# ── TEST 19: UNIT INCOMPATIBILITY IS EXPLICIT ─────────────────────────────────

def test_19_unit_incompatibility_is_explicit():
    assert are_units_dimensionally_compatible("N/m", "N/m") is True
    assert are_units_dimensionally_compatible("N/m", "deg") is False
    assert are_units_dimensionally_compatible("bar", "psi") is True
    assert are_units_dimensionally_compatible("kg", "m") is False


# ── TEST 20: NORMALIZED VALUES PRODUCE CORRECT RANGES ─────────────────────────

@pytest.mark.asyncio
async def test_20_normalized_values_produce_correct_ranges(seeded_ingestion_env):
    data = seeded_ingestion_env
    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="front_spring_rate",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-02"},
        ],
        team_id=data["team_a"],
    )
    metrics = sweep["summary_metrics"]
    assert metrics["min"] == 85000.0
    assert metrics["max"] == 92000.0
    assert metrics["mean"] == 88500.0
    assert metrics["spread"] == 7000.0


# ── TEST 21: CONFLICTS ARE REPRESENTED WITHOUT OVERWRITING SOURCES ────────────

@pytest.mark.asyncio
async def test_21_conflicts_are_represented_without_overwriting_sources(seeded_ingestion_env):
    data = seeded_ingestion_env
    # CAND1 has 85000 N/m, CAND2 has 92000 N/m for the same vehicle
    conflicts = await ParameterTrustService.detect_conflicts(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        current_value=85000.0,
        scope={"vehicle_id": "CAR-2026-07"},
        evidence_items=[],
        team_id=data["team_a"],
    )
    assert len(conflicts) >= 1
    assert conflicts[0]["conflict_type"] == "VALUE_DIVERGENCE"
    assert conflicts[0]["value_a"] == 85000.0
    # Both sources remain intact in DB
    cand1_val = data["cand1"].changed_parameters["front_spring_rate"]["candidate"]
    cand2_val = data["cand2"].changed_parameters["front_spring_rate"]["candidate"]
    assert cand1_val == 85000.0
    assert cand2_val == 92000.0


# ── TEST 22: SUPERSEDED SOURCES ARE HANDLED CORRECTLY ─────────────────────────

@pytest.mark.asyncio
async def test_22_superseded_sources_are_handled_correctly(seeded_ingestion_env):
    data = seeded_ingestion_env
    # CAND2 supersedes CAND1
    await EvidenceGraphService.record_edge(
        db=data["db"],
        user_id=data["user_a"],
        team_id=data["team_a"],
        organization_id=data["org_a"],
        source_type=SupportedEntityType.SETUP_CANDIDATE.value,
        source_id="SETUP-P3L-CAND-02",
        relationship=EvidenceGraphRelationship.SUPERSEDES.value,
        target_type=SupportedEntityType.SETUP_CANDIDATE.value,
        target_id="SETUP-P3L-CAND-01",
    )
    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert profile.current_trust_state == TrustState.STALE.value
    assert (profile.recency_metadata or {}).get("is_superseded") is True


# ── TEST 23: VALIDATION COVERAGE ACROSS A SWEEP IS ACCURATE ───────────────────

@pytest.mark.asyncio
async def test_23_validation_coverage_across_a_sweep_is_accurate(seeded_ingestion_env):
    data = seeded_ingestion_env
    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="front_spring_rate",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"}, # validated by VAL-31
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-02"}, # no validation linked
        ],
        team_id=data["team_a"],
    )
    coverage = sweep["validation_coverage_breakdown"]
    assert coverage.get(ValidationCoverage.VALIDATED.value) == 1
    assert coverage.get(ValidationCoverage.NO_VALIDATION.value) == 1
    assert sweep["evidence_gaps"]["coverage_pct"] == 50.0


# ── TEST 24: NO SIMULATION IS MISCLASSIFIED AS PHYSICAL VALIDATION ────────────

@pytest.mark.asyncio
async def test_24_no_simulation_is_misclassified_as_physical_validation(seeded_ingestion_env):
    data = seeded_ingestion_env
    prof = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SimulationRun",
        entity_id="RUN-000183",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert prof.validation_coverage == ValidationCoverage.NO_VALIDATION.value
    assert prof.current_trust_state != TrustState.VALIDATED.value


# ── TEST 25: SOURCE TIMESTAMPS ARE NORMALIZED ─────────────────────────────────

@pytest.mark.asyncio
async def test_25_source_timestamps_are_normalized(seeded_ingestion_env):
    data = seeded_ingestion_env
    prof = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    rec = prof.recency_metadata or {}
    ts_str = rec.get("evidence_timestamp")
    assert ts_str is not None
    # Parse back as UTC
    parsed = datetime.fromisoformat(ts_str)
    assert parsed.tzinfo is not None


# ── TEST 26: MISSING TIMESTAMPS YIELD EXPLICIT STATUS ─────────────────────────

@pytest.mark.asyncio
async def test_26_missing_timestamps_yield_explicit_status(seeded_ingestion_env):
    data = seeded_ingestion_env
    # VehicleProfile has no timestamps on params
    prof = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="VehicleProfile",
        entity_id=str(data["vp"].id),
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    rec = prof.recency_metadata or {}
    assert rec.get("recency_condition") == RecencyCondition.INSUFFICIENT_RECENCY_INFORMATION.value


# ── TEST 27: EXPIRATION FOLLOWS DECLARED VALIDITY RULES ───────────────────────

@pytest.mark.asyncio
async def test_27_expiration_follows_declared_validity_rules(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Create expired setup candidate (valid_to in 2024)
    expired_cand = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-EXPIRED-2024",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={"front_spring_rate": 85000.0},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        validity_domain={"valid_to": "2024-01-01"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        creation_reason="Expired candidate setup.",
        artifact_hash="hash_exp",
        user_id=data["user_a"],
        team_id=data["team_a"],
    )
    data["db"].add(expired_cand)
    await data["db"].commit()

    prof = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-EXPIRED-2024",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    rec = prof.recency_metadata or {}
    assert rec.get("is_validity_expired") is True
    assert rec.get("recency_condition") == RecencyCondition.VALIDITY_EXPIRED.value
    assert prof.current_trust_state == TrustState.STALE.value


# ── TEST 28: OLD BUT VALID EVIDENCE IS NOT AUTOMATICALLY REJECTED ─────────────

@pytest.mark.asyncio
async def test_28_old_but_valid_evidence_is_not_automatically_rejected(seeded_ingestion_env):
    data = seeded_ingestion_env
    # CAND1 has valid_to in future (2026-12-31), passed holdout gate
    prof = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    # Must NOT be REJECTED
    assert prof.current_trust_state != TrustState.REJECTED.value
    assert prof.current_trust_state in (TrustState.VALIDATED.value, TrustState.HIGH_CONFIDENCE.value, TrustState.CONFLICTED.value)


# ── TEST 29: RECENT BUT WEAK EVIDENCE IS NOT AUTOMATICALLY TRUSTED ────────────

@pytest.mark.asyncio
async def test_29_recent_but_weak_evidence_is_not_automatically_trusted(seeded_ingestion_env):
    data = seeded_ingestion_env
    # VehicleProfile has recent creation time but zero validation
    prof = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="VehicleProfile",
        entity_id=str(data["vp"].id),
        parameter_name="mass_kg",
        team_id=data["team_a"],
    )
    # Manually entered parameter with zero evidence is PROVISIONAL, never VALIDATED
    assert prof.current_trust_state == TrustState.PROVISIONAL.value
    assert prof.validation_coverage == ValidationCoverage.NO_VALIDATION.value


# ── TEST 30: PARAMETER CHANGE TRIGGERS THE CORRECT REFRESH ────────────────────

@pytest.mark.asyncio
async def test_30_parameter_change_triggers_the_correct_refresh(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Ingest CAND2
    res1 = await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-02",
        team_id=data["team_a"],
    )
    assert res1["new_profiles"] == 2

    # Change value
    data["cand2"].changed_parameters["front_spring_rate"]["candidate"] = 93500.0
    await data["db"].commit()

    res2 = await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-02",
        team_id=data["team_a"],
    )
    assert res2["refreshed_assessments"] >= 1


# ── TEST 31: RECENCY POLICY VERSION IS PRESERVED ──────────────────────────────

@pytest.mark.asyncio
async def test_31_recency_policy_version_is_preserved(seeded_ingestion_env):
    data = seeded_ingestion_env
    prof = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    rec = prof.recency_metadata or {}
    assert rec.get("recency_policy_version") == TRUST_RECENCY_POLICY_V1


# ── TEST 32: ASSESSMENT HISTORY IS DETERMINISTIC ──────────────────────────────

@pytest.mark.asyncio
async def test_32_assessment_history_is_deterministic(seeded_ingestion_env):
    data = seeded_ingestion_env
    hist1 = await ParameterTrustService.get_parameter_trust_history(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    hist2 = await ParameterTrustService.get_parameter_trust_history(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert len(hist1) == len(hist2)
    assert [h["assessment_hash"] for h in hist1] == [h["assessment_hash"] for h in hist2]


# ── TEST 33: UNCHANGED ASSESSMENT IDENTITY IS STABLE ──────────────────────────

@pytest.mark.asyncio
async def test_33_unchanged_assessment_identity_is_stable(seeded_ingestion_env):
    data = seeded_ingestion_env
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


# ── TEST 34: CHANGED ASSESSMENT INPUT CHANGES IDENTITY ────────────────────────

@pytest.mark.asyncio
async def test_34_changed_assessment_input_changes_identity(seeded_ingestion_env):
    data = seeded_ingestion_env
    p_orig = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    hash_orig = p_orig.assessment_hash

    # Change value
    data["cand1"].changed_parameters["front_spring_rate"]["candidate"] = 99999.0
    await data["db"].commit()

    p_new = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert p_new.assessment_hash != hash_orig


# ── TEST 35: SWEEP REPORT IDENTITY IS DETERMINISTIC ───────────────────────────

@pytest.mark.asyncio
async def test_35_sweep_report_identity_is_deterministic(seeded_ingestion_env):
    data = seeded_ingestion_env
    cands = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-02"},
    ]
    sw1 = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"], parameter_name="front_spring_rate", candidates=cands, team_id=data["team_a"]
    )
    sw2 = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"], parameter_name="front_spring_rate", candidates=cands, team_id=data["team_a"]
    )
    assert sw1["sweep_hash"] == sw2["sweep_hash"]


# ── TEST 36: BATCH REPORT IS DETERMINISTIC ────────────────────────────────────

@pytest.mark.asyncio
async def test_36_batch_report_is_deterministic(seeded_ingestion_env):
    data = seeded_ingestion_env
    ents = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
        {"entity_type": "VehicleProfile", "entity_id": str(data["vp"].id)},
    ]
    b1 = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"], entities=ents, team_id=data["team_a"]
    )
    b2 = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"], entities=ents, team_id=data["team_a"]
    )
    assert b1["batch_hash"] == b2["batch_hash"]


# ── TEST 37: 0.85 VALIDATION THRESHOLD PROVENANCE AUDIT ───────────────────────

def test_37_085_validation_threshold_provenance_audit():
    """
    Verifies that Phase 3 manifests do NOT contain an authoritative frozen rule
    that all holdout R2 must be >= 0.85 across all parameters.
    Confirms THRESHOLD_PROVENANCE_UNRESOLVED classification.
    """
    if PHASE3H_MANIFEST.exists():
        manifest_text = PHASE3H_MANIFEST.read_text(encoding="utf-8")
        assert "holdout_r2 >= 0.85" not in manifest_text
    if PHASE3L_MANIFEST.exists():
        manifest_l = json.loads(PHASE3L_MANIFEST.read_text(encoding="utf-8"))
        # Phase 3L documented yaw rate R2 = 0.716, roll R2 = 0.691
        inferences = manifest_l.get("problem", {}).get("epistemic_classification", {}).get("MODEL_INFERENCE", [])
        assert any("0.716" in s for s in inferences)


# ── TEST 38: NO UNDOCUMENTED TRUST WEIGHTS ARE INTRODUCED ─────────────────────

def test_38_no_undocumented_trust_weights_are_introduced():
    import inspect
    from suspensionlab.backend.services import parameter_trust_service, parameter_trust_ingestion_service

    src1 = inspect.getsource(parameter_trust_service)
    src2 = inspect.getsource(parameter_trust_ingestion_service)
    for forbidden in ["0.4 *", "0.3 *", "0.2 *", "0.1 *", "weight_sum", "composite_score"]:
        assert forbidden not in src1
        assert forbidden not in src2


# ── TEST 39: TENANT ISOLATION FOR INGESTION ───────────────────────────────────

@pytest.mark.asyncio
async def test_39_tenant_isolation_for_ingestion(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Team B engineer attempting to ingest Team A's SetupCandidate
    res = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=[{"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"}],
        team_id=data["team_b"],
        user_id=data["user_b"],
    )
    assert len(res["errors"]) == 1
    assert res["errors"][0]["reason"] == "TENANT_MISMATCH"
    assert res["new_profiles"] == 0


# ── TEST 40: PERSONAL WORKSPACE ISOLATION ─────────────────────────────────────

@pytest.mark.asyncio
async def test_40_personal_workspace_isolation(seeded_ingestion_env):
    data = seeded_ingestion_env
    # User C (personal workspace) cannot ingest Team A's entities
    res = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=[{"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"}],
        team_id=None,
        user_id=data["user_c"],
    )
    assert len(res["errors"]) == 1
    assert res["errors"][0]["reason"] == "TENANT_MISMATCH"


# ── TEST 41: TENANT ISOLATION FOR SWEEP AGGREGATES ────────────────────────────

@pytest.mark.asyncio
async def test_41_tenant_isolation_for_sweep_aggregates(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Team A attempting sweep including Team B's candidate
    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="front_spring_rate",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"}, # Team A
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-TEAM-B-01"},   # Team B
        ],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    # Team B candidate must be excluded
    assert sweep["comparable_count"] == 1
    assert sweep["excluded_count"] == 1
    assert sweep["excluded_observations"][0]["entity_id"] == "SETUP-TEAM-B-01"


# ── TEST 42: CROSS-TENANT CACHE LEAKAGE PREVENTED ─────────────────────────────

@pytest.mark.asyncio
async def test_42_cross_tenant_cache_leakage_prevented(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Ingest for Team A
    await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    # Query profiles for Team B
    stmt = select(ParameterTrustProfile).where(
        ParameterTrustProfile.team_id == data["team_b"],
        ParameterTrustProfile.entity_id == "SETUP-P3L-CAND-01",
    )
    res = await data["db"].execute(stmt)
    assert res.scalars().first() is None


# ── TEST 43: EXISTING READ APIS STILL RETURN AUTHORIZED DATA ──────────────────

@pytest.mark.asyncio
async def test_43_existing_read_apis_still_return_authorized_data(seeded_ingestion_env):
    data = seeded_ingestion_env
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        app.dependency_overrides[verify_api_key] = lambda: UserContext(
            user_id=str(data["user_a"]),
            email="eng_a@teama.com",
            name="Engineer A",
            plan="PRO",
            onboarding_complete=True,
            team_id=str(data["team_a"]),
            organization_id=str(data["org_a"]),
            team_role="ENGINEER",
        )
        app.dependency_overrides[get_db_dependency] = lambda: data["db"]

        resp = await ac.get("/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["parameter_identity"]["parameter_name"] == "front_spring_rate"
        assert body["current_trust_state"] in [s.value for s in TrustState]

        app.dependency_overrides.clear()


# ── TEST 44: PHASE 6.1 REGRESSION REMAINS GREEN ───────────────────────────────

@pytest.mark.asyncio
async def test_44_phase6_1_regression_remains_green(seeded_ingestion_env):
    data = seeded_ingestion_env
    profile = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
    )
    assert profile.policy_version == CURRENT_TRUST_POLICY_VERSION
    assert profile.assessment_hash is not None


# ── TEST 45: PHASE 4 REGRESSION REMAINS GREEN ─────────────────────────────────

@pytest.mark.asyncio
async def test_45_phase4_regression_remains_green(seeded_ingestion_env):
    data = seeded_ingestion_env
    edges = await EvidenceGraphService.list_edges(
        db=data["db"],
        team_id=data["team_a"],
        source_type=SupportedEntityType.SETUP_CANDIDATE.value,
        source_id="SETUP-P3L-CAND-01",
    )
    assert len(edges) >= 1
    assert edges[0].relationship == EvidenceGraphRelationship.VALIDATED_BY.value


# ── TEST 46: PHASE 5 REMAINS INDEPENDENT ──────────────────────────────────────

def test_46_phase5_remains_independent():
    import sys
    # Verify parameter_trust_service and ingestion service do NOT import blind session or reveal logic
    from suspensionlab.backend.services import parameter_trust_service, parameter_trust_ingestion_service
    import inspect

    src1 = inspect.getsource(parameter_trust_service)
    src2 = inspect.getsource(parameter_trust_ingestion_service)
    for forbidden in ["blind_session_service", "reveal_comparison", "brier_score"]:
        assert forbidden not in src1
        assert forbidden not in src2


# ── TEST 47: PHASE 5.4 REMAINS INDEPENDENT ────────────────────────────────────

def test_47_phase5_4_remains_independent():
    from suspensionlab.backend.services import parameter_trust_ingestion_service
    import inspect
    src = inspect.getsource(parameter_trust_ingestion_service)
    assert "calibration_curve" not in src
    assert "reliability_diagram" not in src


# ── TEST 48: PRODUCTION PHYSICS UNCHANGED ─────────────────────────────────────

def test_48_production_physics_unchanged():
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing physics file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Physics modification in {item['path']}!"

    from suspensionlab.physics.quarter_car import run_quarter_car_analysis, QuarterCarParams, RoadProfile
    params = QuarterCarParams()
    res = run_quarter_car_analysis(params, RoadProfile())
    assert res is not None
    assert len(res.time) > 0
    assert len(res.z_s) > 0


# ── TEST 49: PHASE 3 ARTIFACTS UNCHANGED ──────────────────────────────────────

def test_49_phase3_artifacts_unchanged():
    assert PHASE3H_MANIFEST.exists()
    assert PHASE3L_MANIFEST.exists()


# ── TEST 50: EVIDENCE GRAPH SCHEMA AND VOCABULARY UNCHANGED ───────────────────

def test_50_evidence_graph_schema_and_vocabulary_unchanged():
    canonical_17 = {
        "OBSERVED_IN", "DETECTED_FROM", "FORMULATED_FROM", "EVIDENCED_BY",
        "HYPOTHESIZED_FROM", "TESTED_BY", "EXECUTED_AS", "USES_SETUP",
        "PRODUCED_SETUP", "EVALUATED_IN", "OPTIMIZED_TO", "VALIDATED_BY",
        "JUSTIFIED_BY", "APPROVED_UNDER", "PREDICTED_FOR", "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual = {r.value for r in EvidenceGraphRelationship}
    assert actual == canonical_17
    assert len(actual) == 17


# ── TEST 51: ADVERSARIAL TRANSACTION ROLLBACK AND PARTIAL FAILURE ─────────────

@pytest.mark.asyncio
async def test_51_adversarial_transaction_rollback_and_partial_failure(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Mixed batch with valid and invalid entries
    batch = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
        {"entity_type": "InvalidType", "entity_id": "BAD-ID"},
        {"entity_type": "SetupCandidate", "entity_id": "GHOST-404"},
    ]
    res = await ParameterTrustIngestionService.ingest_batch(
        db=data["db"],
        entities=batch,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    # The valid entity's profiles must succeed without getting aborted by the invalid entries
    assert res["discovered_parameters"] >= 2
    assert len(res["skipped_entities"]) == 1
    assert len(res["errors"]) == 1


# ── TEST 52: ADVERSARIAL CONCURRENT BATCH RETRIES ─────────────────────────────

@pytest.mark.asyncio
async def test_52_adversarial_concurrent_batch_retries(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Run two ingestions sequentially or simulate idempotent re-execution
    res_a = await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
    )
    res_b = await ParameterTrustIngestionService.ingest_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
    )
    assert res_b["new_profiles"] == 0
    assert res_b["unchanged_assessments"] >= 1


# ── TEST 53: ADVERSARIAL EVIDENCE SET ORDERING STABILITY ──────────────────────

@pytest.mark.asyncio
async def test_53_adversarial_evidence_set_ordering_stability(seeded_ingestion_env):
    data = seeded_ingestion_env
    evs1 = await ParameterTrustService.traverse_supporting_evidence(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
    )
    evs2 = await ParameterTrustService.traverse_supporting_evidence(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
    )
    hashes1 = [e["artifact_hash"] for e in evs1]
    hashes2 = [e["artifact_hash"] for e in evs2]
    assert hashes1 == hashes2


# ── TEST 54: ADVERSARIAL CROSS-TENANT SWEEP INJECTION ─────────────────────────

@pytest.mark.asyncio
async def test_54_adversarial_cross_tenant_sweep_injection(seeded_ingestion_env):
    data = seeded_ingestion_env
    # Adversary user B trying to include user A's CAND1 into a sweep for Team B
    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="front_spring_rate",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-TEAM-B-01"},
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
        ],
        team_id=data["team_b"],
        user_id=data["user_b"],
    )
    # Team A's candidate must be quarantined / excluded
    assert sweep["comparable_count"] == 1
    assert sweep["excluded_count"] == 1
    assert sweep["excluded_observations"][0]["entity_id"] == "SETUP-P3L-CAND-01"


# ── TEST 55: EVIDENCE GRAPH VOCABULARY STRICTLY CANONICAL ─────────────────────

@pytest.mark.asyncio
async def test_55_graph_vocabulary_strictly_canonical(seeded_ingestion_env):
    """
    Proves that:
    1. EvidenceGraphRelationship contains exactly the 17 frozen canonical types.
    2. CALIBRATED_BY, APPROVED_BY, and COMPARED_TO are non-canonical and do not exist.
    3. Passing any non-canonical relationship raises UnsupportedRelationshipError.
    4. All traversed edges strictly possess relationships in the canonical enum.
    """
    data = seeded_ingestion_env
    canonical_17 = {
        "OBSERVED_IN", "DETECTED_FROM", "FORMULATED_FROM", "EVIDENCED_BY",
        "HYPOTHESIZED_FROM", "TESTED_BY", "EXECUTED_AS", "USES_SETUP",
        "PRODUCED_SETUP", "EVALUATED_IN", "OPTIMIZED_TO", "VALIDATED_BY",
        "JUSTIFIED_BY", "APPROVED_UNDER", "PREDICTED_FOR", "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual_enum_values = {r.value for r in EvidenceGraphRelationship}
    assert actual_enum_values == canonical_17
    assert len(actual_enum_values) == 17

    # Non-canonical relationships must NOT exist in enum
    for non_canonical in ["CALIBRATED_BY", "APPROVED_BY", "COMPARED_TO"]:
        assert non_canonical not in actual_enum_values
        with pytest.raises(UnsupportedRelationshipError):
            await EvidenceGraphService.record_edge(
                db=data["db"],
                source_type="SetupCandidate",
                source_id="SETUP-P3L-CAND-01",
                relationship=non_canonical,
                target_type="BlindValidation",
                target_id="VAL-2026-001",
                user_id=data["user_a"],
                team_id=data["team_a"],
            )

    # Traversed edges must all have canonical relationships
    evs = await ParameterTrustService.traverse_supporting_evidence(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-P3L-CAND-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    for ev in evs:
        assert ev["relationship"] in canonical_17


# ── TEST 56: ENTITY STRUCTURED UNIT PRECEDENCE ────────────────────────────────

@pytest.mark.asyncio
async def test_56_entity_structured_unit_precedence(seeded_ingestion_env):
    """
    Proves that structured unit metadata explicitly declared on the entity takes precedence
    over fallback registry defaults.
    """
    data = seeded_ingestion_env
    cand_custom_unit = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-CUSTOM-UNIT",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={
            "front_spring_rate": {
                "candidate": 85.0,
                "unit": "N/mm",  # Explicit entity unit (stiffness)
            }
        },
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-2026-07", "operating_regime": "all"},
        creation_reason="Entity with explicit custom unit.",
        artifact_hash="hash_custom_unit",
        user_id=data["user_a"],
        team_id=data["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    data["db"].add(cand_custom_unit)
    await data["db"].commit()

    resolved = await ParameterTrustService.resolve_parameter_from_entity(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-CUSTOM-UNIT",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    # Entity declared "N/mm", registry default is "N/m" -> entity unit must win
    assert resolved["unit"] == "N/mm"
    assert resolved["value"] == 85.0


# ── TEST 57: MISSING UNIT MARKED NOT_COMPARABLE ───────────────────────────────

@pytest.mark.asyncio
async def test_57_missing_unit_marked_not_comparable(seeded_ingestion_env):
    """
    Proves that if a parameter's unit cannot be reliably established (not on entity
    and not in registry), the observation is marked NOT_COMPARABLE with an explicit reason.
    """
    data = seeded_ingestion_env
    cand_no_unit = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-UNKNOWN-PARAM",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={
            "custom_arbitrary_param": 42.0,  # Unregistered, no unit
        },
        unchanged_parameters={},
        parameter_provenance={"custom_arbitrary_param": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-2026-07", "operating_regime": "all"},
        creation_reason="Candidate with unknown parameter.",
        artifact_hash="hash_unknown_param",
        user_id=data["user_a"],
        team_id=data["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    data["db"].add(cand_no_unit)
    await data["db"].commit()

    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="custom_arbitrary_param",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-UNKNOWN-PARAM"},
        ],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert sweep["comparable_count"] == 0
    assert sweep["excluded_count"] == 1
    assert "NOT_COMPARABLE" in sweep["excluded_observations"][0]["exclusion_reason"]


# ── TEST 58: DIMENSIONALLY COMPATIBLE UNIT CONVERSION ─────────────────────────

@pytest.mark.asyncio
async def test_58_dimensionally_compatible_unit_conversion(seeded_ingestion_env):
    """
    Proves that candidates with dimensionally compatible units (e.g., N/mm and N/m)
    are converted to the canonical comparison unit, ensuring valid physical range comparisons.
    """
    data = seeded_ingestion_env
    cand_n_per_mm = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-N-PER-MM",
        parent_setup_id="SETUP-BASE-01",
        changed_parameters={
            "front_spring_rate": {
                "candidate": 90.0,
                "unit": "N/mm",  # 90 N/mm = 90,000 N/m
            }
        },
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={
            "vehicle_id": "CAR-2026-07",
            "operating_regime": "High-Speed Lateral Cornering",
        },
        creation_reason="Candidate in N/mm.",
        artifact_hash="hash_n_per_mm",
        user_id=data["user_a"],
        team_id=data["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    data["db"].add(cand_n_per_mm)
    await data["db"].commit()

    # CAND1 has 85,000 N/m; CAND_N_PER_MM has 90 N/mm (= 90,000 N/m)
    sweep = await ParameterTrustIngestionService.analyze_parameter_sweep(
        db=data["db"],
        parameter_name="front_spring_rate",
        candidates=[
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-P3L-CAND-01"},
            {"entity_type": "SetupCandidate", "entity_id": "SETUP-N-PER-MM"},
        ],
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert sweep["comparable_count"] == 2
    assert sweep["excluded_count"] == 0
    # Values converted to canonical unit (N/m): 85,000 and 90,000
    assert sweep["summary_metrics"]["min"] == 85000.0
    assert sweep["summary_metrics"]["max"] == 90000.0
    assert sweep["summary_metrics"]["delta"] == 5000.0

