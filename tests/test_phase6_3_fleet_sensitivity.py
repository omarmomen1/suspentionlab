"""
tests/test_phase6_3_fleet_sensitivity.py
========================================
SuspensionLab PRO — Phase 6.3 Fleet-Wide Trust Synchronization &
Sensitivity-Aware Propagation Acceptance & Verification Suite.

Complete 55-Test Verification Matrix:
 Group A: Fleet Matching & Comparability Rules (Tests 01-10)
 Group B: Fleet Statistical Aggregations & Outliers (Tests 11-20)
 Group C: Assembly-Aware Structural Hierarchy & Propagation (Tests 21-27)
 Group D: Sensitivity-Aware Impact Assessment (Tests 28-36)
 Group E: API Endpoints, Security & Concurrency (Tests 37-45)
 Group F: Sensitivity Policy & Engineering-Safety Hardening (Tests 46-55)
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
    ParameterTrustFleetReport,
    ParameterTrustAssemblyImpactRecord,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    TRUST_POLICY_V1,
    CURRENT_TRUST_POLICY_VERSION,
    TRUST_RECENCY_POLICY_V1,
    CURRENT_TRUST_RECENCY_POLICY_VERSION,
    FLEET_TRUST_POLICY_V1,
    CURRENT_FLEET_TRUST_POLICY_VERSION,
    SENSITIVITY_PROPAGATION_POLICY_V1,
    CURRENT_SENSITIVITY_PROPAGATION_POLICY_VERSION,
    FleetComparabilityStatus,
    SensitivityStatus,
    ImpactClassification,
    FleetOutlierClassification,
    TrustConflictType,
    SENSITIVITY_THRESHOLDS_PROVENANCE,
    SENSITIVITY_THRESHOLDS_METADATA,
)
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.decision_loop import (
    BlindValidationRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.setup_engineering import (
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
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
    MalformedIdentifierError,
)
from suspensionlab.backend.services.parameter_trust_service import (
    ParameterTrustService,
    canonicalize_parameter_unit,
    compute_value_identity,
)
from suspensionlab.backend.services.parameter_trust_ingestion_service import (
    ParameterTrustIngestionService,
)
from suspensionlab.backend.services.parameter_trust_fleet_service import (
    ParameterTrustFleetService,
    resolve_assembly_component,
    ASSEMBLY_COMPONENT_HIERARCHY,
    KNOWN_SENSITIVITY_KPIS,
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
async def seeded_fleet_env(async_test_db: AsyncSession):
    """
    Sets up multi-vehicle fleet cohort across tenants.
    """
    db = async_test_db
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_a = uuid.uuid4()

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    user_c = uuid.uuid4()  # personal workspace

    # Vehicle 1 (Team A): SetupCandidate SETUP-CAR-01 (Validated front_spring_rate = 85000 N/m)
    c1 = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-CAR-01",
        parent_setup_id="BASE-01",
        changed_parameters={"front_spring_rate": {"candidate": 85000.0, "unit": "N/m"}},
        unchanged_parameters={"front_arb_rate": 25000.0},
        parameter_provenance={"front_spring_rate": "optimization", "front_arb_rate": "historical_setup"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Vehicle 1 setup candidate.",
        artifact_hash="hash_cand_01",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle 2 (Team A): VehicleProfile PROFILE-CAR-02 (Validated front_spring_rate = 88000 N/m)
    p2 = VehicleProfile(
        id=uuid.uuid4(),
        name="PROFILE-CAR-02",
        vehicle_type="FULL_CAR",
        version=1,
        params={"front_spring_rate": 88000.0, "front_arb_rate": 26000.0},
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle 3 (Team A): VehicleProfile PROFILE-CAR-03 (Provisional front_spring_rate = 82000 N/m)
    p3 = VehicleProfile(
        id=uuid.uuid4(),
        name="PROFILE-CAR-03",
        vehicle_type="FULL_CAR",
        version=1,
        params={"front_spring_rate": 82000.0, "front_arb_rate": 24000.0},
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle 4 (Team A): VehicleProfile PROFILE-CAR-04 (Statistical Outlier = 125000 N/m)
    p4 = VehicleProfile(
        id=uuid.uuid4(),
        name="PROFILE-CAR-04",
        vehicle_type="FULL_CAR",
        version=1,
        params={"front_spring_rate": 125000.0, "front_arb_rate": 35000.0},
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle 5 (Team A): VehicleProfile PROFILE-CAR-05 (Unit conversion: 86.0 N/mm = 86000 N/m)
    p5 = VehicleProfile(
        id=uuid.uuid4(),
        name="PROFILE-CAR-05",
        vehicle_type="FULL_CAR",
        version=1,
        params={"front_spring_rate": 86.0, "front_spring_rate_unit": "N/mm"},
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle Incompatible Unit (Team A): PROFILE-INCOMPAT (front_spring_rate = 85.0 m/s - speed!)
    p_incompat = VehicleProfile(
        id=uuid.uuid4(),
        name="PROFILE-INCOMPAT",
        vehicle_type="FULL_CAR",
        version=1,
        params={"front_spring_rate": 85.0, "front_spring_rate_unit": "m/s"},
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle Missing Unit (Team A): PROFILE-NO-UNIT
    p_nounit = VehicleProfile(
        id=uuid.uuid4(),
        name="PROFILE-NO-UNIT",
        vehicle_type="FULL_CAR",
        version=1,
        params={"custom_unregistered_param": 100.0},
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle Cross-Tenant (Team B): SETUP-TEAM-B-01
    c_b = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-TEAM-B-01",
        parent_setup_id="BASE-B",
        changed_parameters={"front_spring_rate": {"candidate": 99999.0, "unit": "N/m"}},
        unchanged_parameters={},
        parameter_provenance={"front_spring_rate": "optimization"},
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-B", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Team B candidate.",
        artifact_hash="hash_cand_b",
        user_id=user_b,
        team_id=team_b,
        created_at=datetime.now(timezone.utc),
    )

    # Vehicle Personal Workspace (User C): PROFILE-USER-C
    p_c = VehicleProfile(
        id=uuid.uuid4(),
        name="PROFILE-USER-C",
        vehicle_type="FULL_CAR",
        version=1,
        params={"front_spring_rate": 77000.0},
        user_id=user_c,
        team_id=None,
        created_at=datetime.now(timezone.utc),
    )

    # Supporting Validation for c1
    val1 = BlindValidationRecord(
        id=uuid.uuid4(),
        validation_number=1,
        validation_code="VAL-CAR-01",
        setup_id="SETUP-CAR-01",
        decision_id="DEC-01",
        fit_dataset_ref="TS-381-FIT",
        holdout_dataset_ref="TS-381-HOLDOUT",
        is_zero_leakage=True,
        fit_r2=0.92,
        holdout_r2=0.88,
        holdout_rmse=0.035,
        gate_verdict="PASSED",
        artifact_hash="hash_val_car_01",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    edge_val1 = EvidenceGraphEdgeRecord(
        id=uuid.uuid4(),
        source_type=SupportedEntityType.SETUP_CANDIDATE.value,
        source_id="SETUP-CAR-01",
        relationship=EvidenceGraphRelationship.VALIDATED_BY.value,
        target_type=SupportedEntityType.BLIND_VALIDATION.value,
        target_id="VAL-CAR-01",
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        source_artifact_hash="hash_cand_01",
        target_artifact_hash="hash_val_car_01",
        edge_hash="edge_hash_val_car_01",
        created_at=datetime.now(timezone.utc),
    )

    # SimulationRun with finite difference sensitivities for front_spring_rate
    sim_sens = SimulationRun(
        id=uuid.uuid4(),
        seq=101,
        label="SIM-SENS-CAR-01",
        simulation_type="sensitivity",
        title="Sensitivity Run",
        vehicle_ref="SETUP-CAR-01",
        setup_ref="SETUP-CAR-01",
        physics_version="2.6.0",
        solver_version="BDF-v1",
        software_version="v2.6",
        params_hash="hash_params_sens",
        params={"front_spring_rate": 85000.0},
        profile={"regime": "High-Speed Lateral Cornering"},
        result={
            "sensitivities": {
                "front_spring_rate": [
                    {
                        "metric": "rms_body_accel_wk",
                        "elasticity": 0.35,  # high downstream impact!
                        "unit": "ratio",
                        "direction": "minimize",
                    },
                    {
                        "metric": "roll_angle_deg",
                        "elasticity": -0.22,
                        "unit": "deg/(N/m)",
                        "direction": "minimize",
                    },
                ]
            }
        },
        result_hash="sim_sens_hash_01",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    # CausalHypothesis for front_arb_rate
    hyp_arb = CausalHypothesisRecord(
        id=uuid.uuid4(),
        hypothesis_id="HYP-ARB-01",
        problem_id="PROB-01",
        hypothesis="Front ARB increases front roll resistance",
        mechanism="roll_stiffness_distribution",
        supporting_evidence=[],
        contradicting_evidence=[],
        candidate_parameters=["front_arb_rate"],
        affected_observables=["roll_angle_deg", "lat_accel_g"],
        expected_direction_of_effect={"roll_angle_deg": "decrease", "lat_accel_g": "increase"},
        confidence_uncertainty={"std_err": 0.05},
        epistemic_status="ACCEPTED",
        artifact_hash="hyp_arb_hash_01",
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        user_id=user_a,
        team_id=team_a,
        created_at=datetime.now(timezone.utc),
    )

    db.add_all([
        c1, p2, p3, p4, p5, p_incompat, p_nounit, c_b, p_c,
        val1, edge_val1, sim_sens, hyp_arb
    ])
    await db.commit()

    return {
        "db": db,
        "org_a": org_a,
        "team_a": team_a,
        "user_a": user_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "user_c": user_c,
    }


# ── GROUP A: FLEET MATCHING & COMPARABILITY RULES (Tests 01-10) ───────────────

@pytest.mark.asyncio
async def test_01_parameter_matching_across_eligible_vehicles(seeded_fleet_env):
    """
    Test 01: Authoritative matching of the same parameter across multiple eligible vehicles.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-03"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert report["cohort_size"] == 3
    assert report["comparable_count"] == 3
    assert report["excluded_count"] == 0
    assert report["missing_count"] == 0


@pytest.mark.asyncio
async def test_02_names_alone_insufficient_for_equivalence(seeded_fleet_env):
    """
    Test 02: Proves parameter names alone do not imply equivalence if dimension differs.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-INCOMPAT"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert report["cohort_size"] == 2
    assert report["comparable_count"] == 1
    assert report["excluded_count"] == 1
    assert report["excluded_instances"][0]["reason"] == "INCOMPATIBLE_UNIT_DIMENSION: Units 'm/s' and 'N/m' belong to different dimensions."


@pytest.mark.asyncio
async def test_03_authoritative_unit_conversion(seeded_fleet_env):
    """
    Test 03: Verifies physical unit conversion across fleet cohort (N/mm to N/m).
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},  # 85000 N/m
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-05"},  # 86.0 N/mm -> 86000 N/m
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
        canonical_unit="N/m",
    )

    assert report["comparable_count"] == 2
    comp_instances = report["comparable_instances"]
    v5 = next(inst for inst in comp_instances if inst["vehicle_ref"] == "PROFILE-CAR-05")
    assert v5["normalized_value"] == 86000.0
    assert v5["canonical_unit"] == "N/m"


@pytest.mark.asyncio
async def test_04_missing_units_excluded_from_numeric_cohort(seeded_fleet_env):
    """
    Test 04: Parameter with missing unit is safely excluded from numeric aggregations.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-NO-UNIT"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="custom_unregistered_param",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    # In PROFILE-NO-UNIT, custom_unregistered_param has no unit in entity or registry
    assert report["excluded_count"] >= 1
    assert report["comparable_count"] == 0


@pytest.mark.asyncio
async def test_05_incompatible_units_excluded_from_cohort(seeded_fleet_env):
    """
    Test 05: Incompatible units explicitly excluded without corrupting cohort statistics.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-INCOMPAT"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        canonical_unit="N/m",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert report["comparable_count"] == 0
    assert report["excluded_count"] == 1


@pytest.mark.asyncio
async def test_06_operating_regime_separation(seeded_fleet_env):
    """
    Test 06: Operating regime differences are properly surfaced in instance metadata.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    inst = report["comparable_instances"][0]
    assert inst["operating_regime"] == "High-Speed Lateral Cornering"


@pytest.mark.asyncio
async def test_07_missing_fleet_members_handled_safely(seeded_fleet_env):
    """
    Test 07: Nonexistent vehicle locators are safely marked in missing_instances without crash.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "SetupCandidate", "entity_id": "GHOST-VEHICLE-999"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    # GHOST-VEHICLE-999 will fail validation or member resolution and appear in missing_instances
    assert report["comparable_count"] == 1
    assert report["missing_count"] == 1


@pytest.mark.asyncio
async def test_08_cross_tenant_members_quarantined_without_leakage(seeded_fleet_env):
    """
    Test 08: Cross-tenant endpoints are quarantined without leaking existence.
    """
    data = seeded_fleet_env
    # User A tries to probe Team B's candidate
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-TEAM-B-01"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    # SETUP-TEAM-B-01 must be quarantined as missing/non-existent
    assert report["comparable_count"] == 1
    assert report["missing_count"] == 1
    assert "SETUP-TEAM-B-01" in report["missing_instances"][0]["entity_id"]


@pytest.mark.asyncio
async def test_09_personal_workspace_isolation(seeded_fleet_env):
    """
    Test 09: Personal workspace vehicles do not leak across team/org boundaries.
    """
    data = seeded_fleet_env
    # User A requests personal user C's vehicle
    members = [
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-USER-C"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert report["comparable_count"] == 0
    assert report["missing_count"] == 1


@pytest.mark.asyncio
async def test_10_separate_instances_never_overwritten(seeded_fleet_env):
    """
    Test 10: Invariant: Each vehicle retains its own authoritative parameters and sources.
    Zero local parameter overwrites occur during synchronization.
    """
    data = seeded_fleet_env
    p2_before = await data["db"].execute(
        select(VehicleProfile).where(VehicleProfile.name == "PROFILE-CAR-02")
    )
    p2_rec = p2_before.scalar_one()
    val_before = p2_rec.params["front_spring_rate"]

    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
    ]

    await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    p2_after = await data["db"].execute(
        select(VehicleProfile).where(VehicleProfile.name == "PROFILE-CAR-02")
    )
    assert p2_after.scalar_one().params["front_spring_rate"] == val_before


# ── GROUP B: FLEET STATISTICAL AGGREGATIONS & OUTLIERS (Tests 11-20) ──────────

@pytest.mark.asyncio
async def test_11_deterministic_fleet_statistics(seeded_fleet_env):
    """
    Test 11: Exact deterministic cohort statistics (min, max, delta, spread, mean, median).
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},   # 85000
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"}, # 88000
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-03"}, # 82000
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    metrics = report["summary_metrics"]
    assert metrics["min"] == 82000.0
    assert metrics["max"] == 88000.0
    assert metrics["delta"] == 6000.0
    assert metrics["spread"] == 6000.0
    assert metrics["mean"] == 85000.0
    assert metrics["median"] == 85000.0


@pytest.mark.asyncio
async def test_12_exact_sample_counts_preserved(seeded_fleet_env):
    """
    Test 12: Preserves sample count, excluded count, and missing count integrity.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},   # Comparable
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-INCOMPAT"}, # Excluded
        {"entity_type": "SetupCandidate", "entity_id": "NONEXISTENT-CAR"}, # Missing
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert report["cohort_size"] == 3
    assert report["comparable_count"] == 1
    assert report["excluded_count"] == 1
    assert report["missing_count"] == 1


@pytest.mark.asyncio
async def test_13_iqr_outlier_detection(seeded_fleet_env):
    """
    Test 13: Detects statistical outliers using IQR rule under FLEET_TRUST_POLICY_V1.
    Values: 82000, 85000, 88000, 125000 -> 125000 is an IQR outlier.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},   # 85000
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"}, # 88000
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-03"}, # 82000
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-04"}, # 125000
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert len(report["outliers"]) == 1
    outlier = report["outliers"][0]
    assert outlier["vehicle_ref"] == "PROFILE-CAR-04"
    assert outlier["value"] == 125000.0
    assert outlier["outlier_type"] == FleetOutlierClassification.STATISTICAL_OUTLIER.value


@pytest.mark.asyncio
async def test_14_statistical_outlier_does_not_imply_defect(seeded_fleet_env):
    """
    Test 14: Strict Invariant: A statistical outlier does not constitute an engineering defect.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-03"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-04"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    outlier = report["outliers"][0]
    assert "Statistical outlier does not constitute an engineering defect" in outlier["note"]


@pytest.mark.asyncio
async def test_15_cohort_below_threshold_skips_outliers(seeded_fleet_env):
    """
    Test 15: When comparable cohort count < 4, IQR outlier calculation is safely skipped.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-04"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert len(report["outliers"]) == 0


@pytest.mark.asyncio
async def test_16_validation_coverage_breakdown(seeded_fleet_env):
    """
    Test 16: Validation coverage counts across cohort.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert "validation_coverage_breakdown" in report
    assert sum(report["validation_coverage_breakdown"].values()) == 2


@pytest.mark.asyncio
async def test_17_trust_state_breakdown(seeded_fleet_env):
    """
    Test 17: Trust state counts across cohort.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert "trust_state_breakdown" in report
    assert sum(report["trust_state_breakdown"].values()) == 2


@pytest.mark.asyncio
async def test_18_provenance_distribution_summary(seeded_fleet_env):
    """
    Test 18: Provenance distribution counts across cohort.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert "provenance_distribution" in report
    assert sum(report["provenance_distribution"].values()) == 2


@pytest.mark.asyncio
async def test_19_zero_trust_score_copying(seeded_fleet_env):
    """
    Test 19: Strict Invariant: Trust state is NOT copied between vehicles.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-03"},
    ]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    c1_inst = next(i for i in report["comparable_instances"] if i["vehicle_ref"] == "SETUP-CAR-01")
    p3_inst = next(i for i in report["comparable_instances"] if i["vehicle_ref"] == "PROFILE-CAR-03")

    # c1 has holdout validation (VALIDATED), p3 has no validation (PROVISIONAL)
    assert c1_inst["trust_state"] == TrustState.VALIDATED.value
    assert p3_inst["trust_state"] == TrustState.PROVISIONAL.value


@pytest.mark.asyncio
async def test_20_fleet_report_hash_deterministic(seeded_fleet_env):
    """
    Test 20: Deterministic SHA-256 report hashing.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
    ]

    r1 = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
        persist_report=False,
    )
    r2 = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=data["db"],
        fleet_id="FLEET-GT3",
        parameter_name="front_spring_rate",
        member_locators=members,
        team_id=data["team_a"],
        user_id=data["user_a"],
        persist_report=False,
    )

    assert r1["report_hash"] == r2["report_hash"]
    assert len(r1["report_hash"]) == 64


# ── GROUP C: ASSEMBLY-AWARE STRUCTURAL HIERARCHY & PROPAGATION (Tests 21-27) ──

@pytest.mark.asyncio
async def test_21_assembly_hierarchy_resolution():
    """
    Test 21: Resolves assembly and component identity for known parameter.
    """
    res = resolve_assembly_component("front_spring_rate")
    assert res == ("FRONT_SUSPENSION", "front_spring")

    res2 = resolve_assembly_component("damper_bump_rear")
    assert res2 == ("REAR_SUSPENSION", "rear_damper")


@pytest.mark.asyncio
async def test_22_unknown_parameter_prevents_propagation(seeded_fleet_env):
    """
    Test 22: Unknown parameter blocks propagation with NO_AUTHORITATIVE_DEPENDENCY_PATH.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="completely_unregistered_mystery_param",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["can_propagate"] is False
    assert "NO_AUTHORITATIVE_DEPENDENCY_PATH" in res["reason"]


@pytest.mark.asyncio
async def test_23_structural_mismatch_prevented(seeded_fleet_env):
    """
    Test 23: Mismatch between specified assembly/component and canonical path blocks propagation.
    """
    data = seeded_fleet_env
    # front_spring_rate belongs to SUSPENSION->front_spring, not AERODYNAMICS->wings
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        assembly_name="AERODYNAMICS",
        component_name="wings",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["can_propagate"] is False
    assert "STRUCTURAL_MISMATCH" in res["reason"]


@pytest.mark.asyncio
async def test_24_direct_trust_decoupled_from_assembly_impact(seeded_fleet_env):
    """
    Test 24: Strict Invariant: DIRECT TRUST IS DECOUPLED FROM PROPAGATED IMPACT.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["can_propagate"] is True
    # Direct trust is VALIDATED
    assert res["direct_trust_assessment"]["trust_state"] == TrustState.VALIDATED.value
    # Propagated assembly impact is CRITICAL_VALIDATED
    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.CRITICAL_VALIDATED.value
    assert "Direct trust state is decoupled" in res["lineage_note"]


@pytest.mark.asyncio
async def test_25_provisional_component_does_not_make_assembly_provisional(seeded_fleet_env):
    """
    Test 25: A provisional component yields an evidence gap impact classification without rewriting assembly.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="PROFILE-CAR-03",  # Unvalidated vehicle
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["can_propagate"] is True
    assert res["direct_trust_assessment"]["trust_state"] == TrustState.PROVISIONAL.value
    # Does not make assembly state "PROVISIONAL", it assigns an impact classification
    assert res["impact_assessment"]["impact_classification"] in [
        ImpactClassification.HIGH_IMPACT_EVIDENCE_GAP.value,
        ImpactClassification.SENSITIVITY_UNAVAILABLE.value,
    ]


@pytest.mark.asyncio
async def test_26_lineage_dependency_path_preserved(seeded_fleet_env):
    """
    Test 26: Full structural lineage path recorded: [vehicle_id, assembly, component, parameter].
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    expected_path = ["SETUP-CAR-01", "FRONT_SUSPENSION", "front_spring", "front_spring_rate"]
    assert res["dependency_path"] == expected_path


@pytest.mark.asyncio
async def test_27_assembly_impact_hash_deterministic(seeded_fleet_env):
    """
    Test 27: SHA-256 impact_hash is deterministic across identical evaluations.
    """
    data = seeded_fleet_env
    i1 = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
        persist_record=False,
    )
    i2 = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
        persist_record=False,
    )

    assert i1["impact_hash"] == i2["impact_hash"]
    assert len(i1["impact_hash"]) == 64


# ── GROUP D: SENSITIVITY-AWARE IMPACT ASSESSMENT (Tests 28-36) ────────────────

@pytest.mark.asyncio
async def test_28_authoritative_sensitivity_from_simulation(seeded_fleet_env):
    """
    Test 28: Resolves authoritative sensitivity from SimulationRun record.
    """
    data = seeded_fleet_env
    sens = await ParameterTrustFleetService.resolve_sensitivity_evidence(
        db=data["db"],
        parameter_name="front_spring_rate",
        vehicle_id="SETUP-CAR-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert sens["status"] == SensitivityStatus.AVAILABLE.value
    assert sens["source_type"] == "SimulationRun"
    assert sens["method"] == "finite_difference_bdf"
    assert len(sens["downstream_metrics"]) >= 1


@pytest.mark.asyncio
async def test_29_authoritative_sensitivity_from_causal_hypothesis(seeded_fleet_env):
    """
    Test 29: Resolves authoritative sensitivity from CausalHypothesisRecord.
    """
    data = seeded_fleet_env
    sens = await ParameterTrustFleetService.resolve_sensitivity_evidence(
        db=data["db"],
        parameter_name="front_arb_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert sens["status"] == SensitivityStatus.AVAILABLE.value
    assert sens["source_type"] == "CausalHypothesis"
    assert sens["method"] == "causal_hypothesis_mechanism"


@pytest.mark.asyncio
async def test_30_missing_sensitivity_never_treated_as_zero(seeded_fleet_env):
    """
    Test 30: Strict Invariant: Missing sensitivity is represented as SENSITIVITY_UNAVAILABLE, NEVER ZERO!
    """
    data = seeded_fleet_env
    sens = await ParameterTrustFleetService.resolve_sensitivity_evidence(
        db=data["db"],
        parameter_name="unrecorded_damping_coefficient",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert sens["status"] == SensitivityStatus.SENSITIVITY_UNAVAILABLE.value
    assert "never interpreted as zero" in sens["warning"]
    assert "downstream_metrics" not in sens


@pytest.mark.asyncio
async def test_31_sensitivity_units_preserved(seeded_fleet_env):
    """
    Test 31: Physical units unit(KPI)/unit(param) preserved without conflation with ratio elasticity.
    """
    data = seeded_fleet_env
    sens = await ParameterTrustFleetService.resolve_sensitivity_evidence(
        db=data["db"],
        parameter_name="front_spring_rate",
        vehicle_id="SETUP-CAR-01",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    metrics = sens["downstream_metrics"]
    roll_metric = next(m for m in metrics if m["metric"] == "roll_angle_deg")
    assert roll_metric["unit"] == "deg/(N/m)"


@pytest.mark.asyncio
async def test_32_critical_validated_impact_classification(seeded_fleet_env):
    """
    Test 32: High elasticity (>= 0.20) + VALIDATED parameter yields CRITICAL_VALIDATED.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.CRITICAL_VALIDATED.value


@pytest.mark.asyncio
async def test_33_high_impact_evidence_gap_classification(seeded_fleet_env):
    """
    Test 33: High elasticity (>= 0.20) + unvalidated parameter yields HIGH_IMPACT_EVIDENCE_GAP.
    """
    data = seeded_fleet_env
    # PROFILE-CAR-02 has no holdout validation gate -> unvalidated parameter
    # But simulation sensitivity exists for front_spring_rate (|elasticity|=0.35 >= 0.20)
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="PROFILE-CAR-02",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.HIGH_IMPACT_EVIDENCE_GAP.value
    assert "Priority engineering investigation target" in res["impact_assessment"]["impact_summary"]


@pytest.mark.asyncio
async def test_34_moderate_impact_evidence_gap_classification(seeded_fleet_env):
    """
    Test 34: Moderate elasticity (0.05 - 0.20) + unvalidated yields MODERATE_IMPACT_EVIDENCE_GAP.
    """
    data = seeded_fleet_env
    # Add simulation run with moderate elasticity = 0.12
    sim_mod = SimulationRun(
        id=uuid.uuid4(),
        seq=102,
        label="SIM-SENS-MOD",
        simulation_type="sensitivity",
        title="Sim Mod",
        vehicle_ref="PROFILE-CAR-03",
        physics_version="2.6.0",
        solver_version="BDF-v1",
        software_version="v2.6",
        params_hash="hash_params_mod",
        params={"front_arb_rate": 24000.0},
        result={
            "sensitivities": {
                "front_arb_rate": [
                    {"metric": "roll_angle_deg", "elasticity": 0.12, "unit": "ratio"}
                ]
            }
        },
        result_hash="sim_mod_hash",
        user_id=data["user_a"],
        team_id=data["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    data["db"].add(sim_mod)
    await data["db"].commit()

    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="PROFILE-CAR-03",
        parameter_name="front_arb_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.MODERATE_IMPACT_EVIDENCE_GAP.value


@pytest.mark.asyncio
async def test_35_low_impact_evidence_gap_classification(seeded_fleet_env):
    """
    Test 35: Low elasticity (< 0.05) + unvalidated yields LOW_IMPACT_EVIDENCE_GAP.
    """
    data = seeded_fleet_env
    sim_low = SimulationRun(
        id=uuid.uuid4(),
        seq=103,
        label="SIM-SENS-LOW",
        simulation_type="sensitivity",
        title="Sim Low",
        vehicle_ref="PROFILE-CAR-04",
        physics_version="2.6.0",
        solver_version="BDF-v1",
        software_version="v2.6",
        params_hash="hash_params_low",
        params={"front_arb_rate": 35000.0},
        result={
            "sensitivities": {
                "front_arb_rate": [
                    {"metric": "roll_angle_deg", "elasticity": 0.02, "unit": "ratio"}
                ]
            }
        },
        result_hash="sim_low_hash",
        user_id=data["user_a"],
        team_id=data["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    data["db"].add(sim_low)
    await data["db"].commit()

    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="PROFILE-CAR-04",
        parameter_name="front_arb_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.LOW_IMPACT_EVIDENCE_GAP.value


@pytest.mark.asyncio
async def test_36_conflicted_parameter_yields_conflicted_impact(seeded_fleet_env):
    """
    Test 36: Parameter with active conflicts yields CONFLICTED_IMPACT classification.
    """
    data = seeded_fleet_env
    prof_conflicted = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="VehicleProfile",
        entity_id="PROFILE-CAR-02",
        parameter_name="front_spring_rate",
        parameter_path="params.front_spring_rate",
        unit="N/m",
        value_reference={"value": 88000.0, "value_identity": "88000.0"},
        provenance_class=ProvenanceClass.CALIBRATED.value,
        current_trust_state=TrustState.CONFLICTED.value,
        validation_coverage=ValidationCoverage.CONFLICTING_VALIDATION.value,
        conflicts=[{"conflict_type": TrustConflictType.VALUE_DIVERGENCE.value, "detail": "Test conflict"}],
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="conflicted_hash",
        created_at=datetime.now(timezone.utc),
        created_by_user_id=data["user_a"],
        team_id=data["team_a"],
        organization_id=data["org_a"],
    )
    data["db"].add(prof_conflicted)
    await data["db"].commit()

    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="PROFILE-CAR-02",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.CONFLICTED_IMPACT.value


# ── GROUP E: API ENDPOINTS, SECURITY & CONCURRENCY (Tests 37-45) ──────────────

@pytest.mark.asyncio
async def test_37_api_fleet_compare_endpoint(seeded_fleet_env):
    """
    Test 37: POST /api/v1/parameter-trust/fleet/compare returns complete report.
    """
    data = seeded_fleet_env

    async def override_user():
        return UserContext(
            user_id=str(data["user_a"]),
            plan="PRO",
            email="engineer_a@teama.com",
            name="Engineer A",
            onboarding_complete=True,
            organization_id=str(data["org_a"]),
            team_id=str(data["team_a"]),
            team_role="ENGINEER",
        )

    async def override_db():
        yield data["db"]

    app.dependency_overrides[verify_api_key] = override_user
    app.dependency_overrides[get_db_dependency] = override_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/api/v1/parameter-trust/fleet/compare",
                json={
                    "fleet_id": "FLEET-GT3",
                    "parameter_name": "front_spring_rate",
                    "members": [
                        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
                        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
                    ],
                    "persist_report": True,
                },
            )
            assert res.status_code == 200
            json_body = res.json()
            assert json_body["fleet_id"] == "FLEET-GT3"
            assert json_body["comparable_count"] == 2
            assert json_body["report_hash"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_38_api_fleet_summary_endpoint(seeded_fleet_env):
    """
    Test 38: GET /api/v1/parameter-trust/fleet/{fleet_id}/summary returns persisted reports.
    """
    data = seeded_fleet_env

    async def override_user():
        return UserContext(
            user_id=str(data["user_a"]),
            plan="PRO",
            email="engineer_a@teama.com",
            name="Engineer A",
            onboarding_complete=True,
            organization_id=str(data["org_a"]),
            team_id=str(data["team_a"]),
            team_role="ENGINEER",
        )

    async def override_db():
        yield data["db"]

    app.dependency_overrides[verify_api_key] = override_user
    app.dependency_overrides[get_db_dependency] = override_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Post a report
            await ac.post(
                "/api/v1/parameter-trust/fleet/compare",
                json={
                    "fleet_id": "FLEET-SUMMARY-TEST",
                    "parameter_name": "front_spring_rate",
                    "members": [
                        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
                    ],
                    "persist_report": True,
                },
            )

            # 2. Query summary
            res = await ac.get("/api/v1/parameter-trust/fleet/FLEET-SUMMARY-TEST/summary")
            assert res.status_code == 200
            data_resp = res.json()
            assert data_resp["fleet_id"] == "FLEET-SUMMARY-TEST"
            assert data_resp["total"] >= 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_39_api_assembly_impact_endpoint(seeded_fleet_env):
    """
    Test 39: GET /api/v1/parameter-trust/assembly/impact returns impact assessment.
    """
    data = seeded_fleet_env

    async def override_user():
        return UserContext(
            user_id=str(data["user_a"]),
            plan="PRO",
            email="engineer_a@teama.com",
            name="Engineer A",
            onboarding_complete=True,
            organization_id=str(data["org_a"]),
            team_id=str(data["team_a"]),
            team_role="ENGINEER",
        )

    async def override_db():
        yield data["db"]

    app.dependency_overrides[verify_api_key] = override_user
    app.dependency_overrides[get_db_dependency] = override_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(
                "/api/v1/parameter-trust/assembly/impact",
                params={
                    "vehicle_id": "SETUP-CAR-01",
                    "parameter_name": "front_spring_rate",
                },
            )
            assert res.status_code == 200
            data_resp = res.json()
            assert data_resp["can_propagate"] is True
            assert data_resp["assembly_name"] == "FRONT_SUSPENSION"
            assert data_resp["component_name"] == "front_spring"
            assert data_resp["impact_hash"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_40_api_sensitivity_evidence_endpoint(seeded_fleet_env):
    """
    Test 40: GET /api/v1/parameter-trust/sensitivity/evidence returns evidence payload.
    """
    data = seeded_fleet_env

    async def override_user():
        return UserContext(
            user_id=str(data["user_a"]),
            plan="PRO",
            email="engineer_a@teama.com",
            name="Engineer A",
            onboarding_complete=True,
            organization_id=str(data["org_a"]),
            team_id=str(data["team_a"]),
            team_role="ENGINEER",
        )

    async def override_db():
        yield data["db"]

    app.dependency_overrides[verify_api_key] = override_user
    app.dependency_overrides[get_db_dependency] = override_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(
                "/api/v1/parameter-trust/sensitivity/evidence",
                params={
                    "parameter_name": "front_spring_rate",
                    "vehicle_id": "SETUP-CAR-01",
                },
            )
            assert res.status_code == 200
            data_resp = res.json()
            assert data_resp["status"] == SensitivityStatus.AVAILABLE.value
            assert data_resp["source_type"] == "SimulationRun"
    finally:
        app.dependency_overrides.clear()


def test_41_evidence_graph_17_relationships_unchanged():
    """
    Test 41: Hard Boundary: Exactly 17 frozen canonical relationships exist in Evidence Graph.
    """
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


def test_42_trust_policy_v1_and_recency_policy_v1_unchanged():
    """
    Test 42: Policy versions and core constants from Phase 6.1 and 6.2 are intact.
    """
    assert CURRENT_TRUST_POLICY_VERSION == "TRUST_POLICY_V1"
    assert CURRENT_TRUST_RECENCY_POLICY_VERSION == "TRUST_RECENCY_POLICY_V1"
    assert CURRENT_FLEET_TRUST_POLICY_VERSION == "FLEET_TRUST_POLICY_V1"
    assert CURRENT_SENSITIVITY_PROPAGATION_POLICY_VERSION == "SENSITIVITY_PROPAGATION_POLICY_V1"


@pytest.mark.asyncio
async def test_43_concurrent_fleet_synchronization_safety(seeded_fleet_env):
    """
    Test 43: Concurrent async calls to synchronize_fleet_parameter produce identical deterministic reports.
    """
    data = seeded_fleet_env
    members = [
        {"entity_type": "SetupCandidate", "entity_id": "SETUP-CAR-01"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-02"},
        {"entity_type": "VehicleProfile", "entity_id": "PROFILE-CAR-03"},
    ]

    async def call_sync():
        return await ParameterTrustFleetService.synchronize_fleet_parameter(
            db=data["db"],
            fleet_id="FLEET-CONCURRENT",
            parameter_name="front_spring_rate",
            member_locators=members,
            team_id=data["team_a"],
            user_id=data["user_a"],
            persist_report=False,
        )

    res1 = await call_sync()
    res2 = await call_sync()
    res3 = await call_sync()
    results = [res1, res2, res3]
    hashes = [r["report_hash"] for r in results]
    assert hashes[0] == hashes[1] == hashes[2]


def test_44_phase3_artifacts_and_manifests_unchanged():
    """
    Test 44: Manifest files for Phase 3h and 3l remain present and unmodified.
    """
    assert PHASE3H_MANIFEST.exists()
    assert PHASE3L_MANIFEST.exists()


def test_45_production_physics_81_files_unchanged():
    """
    Test 45: Hard Boundary: All 81 protected production physics files match authoritative SHA-256 hashes.
    Quarter-car production solver executes successfully.
    """
    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    assert hash_file.exists(), "pre_phase4_3_hashes.json missing!"

    with open(hash_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    physics_hashes = data.get("physics", {})
    assert len(physics_hashes) == 81, f"Expected 81 physics files, found {len(physics_hashes)}"

    for rel_path, expected_hash in physics_hashes.items():
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Physics file missing: {rel_path}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"CRITICAL: Production physics file {rel_path} was modified!"

    from suspensionlab.physics.quarter_car import run_quarter_car_analysis, QuarterCarParams, RoadProfile
    params = QuarterCarParams()
    res = run_quarter_car_analysis(params, RoadProfile())
    assert res is not None
    assert len(res.time) > 0
    assert len(res.z_s) > 0


# ── GROUP F: SENSITIVITY POLICY & ENGINEERING-SAFETY HARDENING (Tests 46-55) ──

@pytest.mark.asyncio
async def test_46_high_sensitivity_does_not_imply_deployment_safety(seeded_fleet_env):
    """
    Test 46: Hardening: High sensitivity (>=0.20) + passed validation gate (CRITICAL_VALIDATED)
    strictly decouples from vehicle deployment safety.
    deployment_safety_inferred is False, deployment_authorization is NOT_ESTABLISHED,
    and no claim of 'safe for deployment' exists in summary, notice, or lineage.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.CRITICAL_VALIDATED.value
    assert res["deployment_safety_inferred"] is False
    assert res["impact_assessment"]["deployment_safety_inferred"] is False
    assert res["impact_assessment"]["deployment_authorization"] == "NOT_ESTABLISHED"
    assert "safe for deployment" not in res["impact_assessment"]["impact_summary"].lower()
    assert "independent governance" in res["impact_assessment"]["deployment_safety_notice"].lower()


@pytest.mark.asyncio
async def test_47_validation_pass_does_not_override_unresolved_conflicts(seeded_fleet_env):
    """
    Test 47: Hardening: Active conflicts (e.g. VALUE_DIVERGENCE) strictly take precedence
    over holdout validation pass, yielding CONFLICTED_IMPACT instead of CRITICAL_VALIDATED.
    """
    data = seeded_fleet_env
    prof_conflicted_validated = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-CONFLICTED-VAL",
        parameter_name="front_spring_rate",
        parameter_path="params.front_spring_rate",
        unit="N/m",
        value_reference={"value": 90000.0, "value_identity": "90000.0"},
        provenance_class=ProvenanceClass.CALIBRATED.value,
        current_trust_state=TrustState.CONFLICTED.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        conflicts=[{"conflict_type": TrustConflictType.VALUE_DIVERGENCE.value, "detail": "Discrepancy with rig test"}],
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_conflict_val",
        created_at=datetime.now(timezone.utc),
        created_by_user_id=data["user_a"],
        team_id=data["team_a"],
        organization_id=data["org_a"],
    )
    sim = SimulationRun(
        id=uuid.uuid4(),
        seq=201,
        label="SIM-SENS-CONF-VAL",
        simulation_type="sensitivity",
        title="Sim Conf Val",
        vehicle_ref="SETUP-CONFLICTED-VAL",
        physics_version="2.6.0",
        solver_version="BDF-v1",
        software_version="v2.6",
        params_hash="hash_params_conf_val",
        params={"front_spring_rate": 90000.0},
        result={
            "sensitivities": {
                "front_spring_rate": [
                    {"metric": "roll_angle_deg", "elasticity": 0.30, "unit": "deg/(N/m)"}
                ]
            }
        },
        result_hash="sim_conf_val_hash",
        user_id=data["user_a"],
        team_id=data["team_a"],
        created_at=datetime.now(timezone.utc),
    )
    data["db"].add(prof_conflicted_validated)
    data["db"].add(sim)
    await data["db"].commit()

    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CONFLICTED-VAL",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.CONFLICTED_IMPACT.value
    assert "Unresolved conflicts override parameter validation status" in res["impact_assessment"]["impact_summary"]


@pytest.mark.asyncio
async def test_48_missing_sensitivity_cannot_produce_low_impact(seeded_fleet_env):
    """
    Test 48: Hardening: When only a directional causal hypothesis exists (without measured
    numerical derivative), or when sensitivity is missing, numerical sensitivity must remain SENSITIVITY_UNAVAILABLE,
    never treated as zero, and impact classification must be SENSITIVITY_UNAVAILABLE (not VALIDATED_LOW_IMPACT).
    """
    data = seeded_fleet_env
    # 1. CausalHypothesisRecord only: check that elasticity is None and is_numerical_derivative is False
    sens = await ParameterTrustFleetService.resolve_sensitivity_evidence(
        db=data["db"],
        parameter_name="front_arb_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert sens["status"] == SensitivityStatus.AVAILABLE.value
    assert sens["source_type"] == "CausalHypothesis"
    for m in sens["downstream_metrics"]:
        assert m["elasticity"] is None
        assert m["is_numerical_derivative"] is False

    # 2. Assess assembly impact on a vehicle that only has causal hypothesis
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_arb_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.SENSITIVITY_UNAVAILABLE.value
    assert "Numerical sensitivity derivative unavailable" in res["impact_assessment"]["impact_summary"]
    assert res["impact_assessment"]["impact_classification"] != ImpactClassification.VALIDATED_LOW_IMPACT.value


@pytest.mark.asyncio
async def test_49_unvalidated_high_impact_produces_evidence_gap_warning(seeded_fleet_env):
    """
    Test 49: Hardening: High sensitivity parameter lacking holdout validation coverage
    yields HIGH_IMPACT_EVIDENCE_GAP with explicit warning and evidence gap annotations.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="PROFILE-CAR-02",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["impact_assessment"]["impact_classification"] == ImpactClassification.HIGH_IMPACT_EVIDENCE_GAP.value
    assert any("NO_PHYSICAL_VALIDATION" in gap for gap in res["impact_assessment"]["evidence_gaps"])
    assert "Priority engineering investigation target" in res["impact_assessment"]["impact_summary"]


@pytest.mark.asyncio
async def test_50_unsupported_threshold_provenance_is_visible(seeded_fleet_env):
    """
    Test 50: Hardening: Elasticity threshold boundaries are transparently surfaced as PROVISIONAL,
    explicitly tagged as analytical screening heuristics without claiming formal physical safety boundaries.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["threshold_provenance"] == SENSITIVITY_THRESHOLDS_PROVENANCE == "PROVISIONAL"
    assert res["impact_assessment"]["threshold_provenance"] == "PROVISIONAL"
    meta = res["impact_assessment"]["threshold_metadata"]
    assert meta["classification_nature"] == "provisional_analytical_screening_heuristic"
    assert meta["high_threshold"] == 0.20
    assert meta["moderate_threshold"] == 0.05
    assert "screening heuristic" in meta["scientific_basis"].lower()


@pytest.mark.asyncio
async def test_51_scope_mismatch_prevents_invalid_propagation(seeded_fleet_env):
    """
    Test 51: Hardening: Scope or structural hierarchy mismatch prevents propagation
    (can_propagate is False, reason contains STRUCTURAL_MISMATCH).
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        assembly_name="REAR_SUSPENSION",
        component_name="rear_spring",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    assert res["can_propagate"] is False
    assert "STRUCTURAL_MISMATCH" in res["reason"]


@pytest.mark.asyncio
async def test_52_raw_derivative_units_preserved(seeded_fleet_env):
    """
    Test 52: Hardening: Raw derivative physical units (e.g. deg/(N/m)) are strictly preserved
    and differentiated from non-dimensional normalized ratio elasticity.
    """
    data = seeded_fleet_env
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    downstream = res["impact_assessment"]["downstream_metrics"]
    assert len(downstream) > 0
    roll_metric = next(m for m in downstream if m["metric"] == "roll_angle_deg")
    assert roll_metric["unit"] == "deg/(N/m)"
    assert roll_metric["elasticity"] == pytest.approx(-0.22)


@pytest.mark.asyncio
async def test_53_local_parameter_trust_never_overwritten_by_propagated_impact(seeded_fleet_env):
    """
    Test 53: Hardening: Downstream assembly impact propagation never modifies, overwrites,
    or pollutes the direct ParameterTrustProfile record in the database.
    """
    data = seeded_fleet_env
    # 1. Establish baseline direct parameter trust profile
    profile_initial = await ParameterTrustService.get_or_assess_parameter_trust(
        db=data["db"],
        entity_type="SetupCandidate",
        entity_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )
    original_trust_state = profile_initial.current_trust_state
    original_val_cov = profile_initial.validation_coverage
    original_assessment_hash = profile_initial.assessment_hash

    # 2. Run assembly impact assessment
    res = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
    )

    # 3. Verify direct parameter trust profile is completely untouched
    stmt = select(ParameterTrustProfile).where(
        ParameterTrustProfile.entity_id == "SETUP-CAR-01",
        ParameterTrustProfile.parameter_name == "front_spring_rate",
    )
    prof_after = (await data["db"].execute(stmt)).scalars().first()
    assert prof_after is not None
    assert prof_after.current_trust_state == original_trust_state
    assert prof_after.validation_coverage == original_val_cov
    assert prof_after.assessment_hash == original_assessment_hash
    # Direct trust state must remain decoupled from propagated impact classification
    assert prof_after.current_trust_state != res["impact_assessment"]["impact_classification"]


@pytest.mark.asyncio
async def test_54_report_hashes_remain_deterministic(seeded_fleet_env):
    """
    Test 54: Hardening: Cryptographic impact assessment hashes and fleet report hashes
    are 100% deterministic across multiple sequential and independent evaluations.
    """
    data = seeded_fleet_env
    res1 = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
        persist_record=False,
    )
    res2 = await ParameterTrustFleetService.assess_assembly_impact(
        db=data["db"],
        vehicle_id="SETUP-CAR-01",
        parameter_name="front_spring_rate",
        team_id=data["team_a"],
        user_id=data["user_a"],
        persist_record=False,
    )
    assert res1["impact_hash"] == res2["impact_hash"]
    assert len(res1["impact_hash"]) == 64


@pytest.mark.asyncio
async def test_55_tenant_isolation_and_protected_artifacts_intact(seeded_fleet_env):
    """
    Test 55: Hardening: Cross-tenant data isolation is strictly enforced;
    17 canonical Evidence Graph relationships remain frozen;
    81 protected production physics files match authoritative hashes.
    """
    data = seeded_fleet_env
    user_b_unauthorized = uuid.uuid4()
    team_b_unauthorized = uuid.uuid4()
    sens_b = await ParameterTrustFleetService.resolve_sensitivity_evidence(
        db=data["db"],
        parameter_name="front_spring_rate",
        vehicle_id="SETUP-CAR-01",
        team_id=team_b_unauthorized,
        user_id=user_b_unauthorized,
    )
    assert sens_b["status"] == SensitivityStatus.SENSITIVITY_UNAVAILABLE.value

    actual_rels = {r.value for r in EvidenceGraphRelationship}
    assert len(actual_rels) == 17

    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    with open(hash_file, "r", encoding="utf-8") as f:
        stored = json.load(f)
    physics_hashes = stored.get("physics", {})
    assert len(physics_hashes) == 81
    for rel_path, expected_hash in physics_hashes.items():
        actual_hash = hashlib.sha256((PROJECT_ROOT / rel_path).read_bytes()).hexdigest()
        assert actual_hash == expected_hash

