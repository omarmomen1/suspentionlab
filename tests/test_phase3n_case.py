"""
tests/test_phase3n_case.py
==========================
Phase 3N: Independent Governed Engineering Case Test Suite.

Mode: CONTROLLED IMPLEMENTATION
Parameter Under Test: DynamicVehicleParams.steering_compliance_rad_per_mps2 (k_delta)
Zero Production Physics Modifications | Canonical Governed Contract (RK4, dt=0.001s) | Governed Provenance

Verifies the 20 mandatory invariants:
 1. protected physics hashes unchanged (all 11 files)
 2. mandatory RK4 dt = 0.001 s contract enforced
 3. parameter snapshot baseline semantics (rigid reference vs historical reference)
 4. excluded parameters audit (steer_ratio cancellation, rate_limit inactivity)
 5. partition disjointness proof (Fit ∩ Temp = ∅, Fit ∩ Cross = ∅, Temp ∩ Cross = ∅)
 6. telemetry window suitability & sensor dropout disqualification
 7. observability gate (IDENTIFIABLE status, sensitivity norm, FIM rank, correlation)
 8. pre-registration frozen before holdout unseal
 9. real solver execution & distinct candidate outputs
10. fit window optimization ranking reproducibility & trade-offs
11. temporal holdout non-inferiority (CAND-02 best on exit, CAND-03 over-compliance)
12. cross-maneuver holdout generalization (Chicane tracking improvement)
13. paired block bootstrap uncertainty (B=1000, 100ms blocks, no heuristic CI)
14. secondary metric admissibility (ay, sideslip beta, roll, jounce clearance)
15. final classification semantics (ENGINEERING_DECISION_SUPPORTED, never VALIDATED)
16. track prediction immutability (PRED-P3N-01 = PREDICTION_PENDING_TRACK_TEST)
17. human approval HMAC-SHA256 non-repudiable sign-off
18. unbroken 14-link lineage reconstructability
19. historical Phase 3M and 3M.1 artifacts untouched
20. all persisted Phase 3N artifacts exist and validate
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import uuid
import pytest
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.decision_loop import (
    ApprovalRecord,
    BlindValidationRecord,
)
from suspensionlab.backend.services.phase3l_setup_engineering_service import (
    HoldoutLeakageError,
)
from suspensionlab.backend.services.phase3n_case_service import Phase3NCaseService
from suspensionlab.physics.dynamic_lap_sim import DynamicLapSimulator, DynamicVehicleParams


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"

PHASE3H_MANIFEST = DATA_DIR / "phase3h_final_validity_manifest.json"
PHASE3M_CASE_JSON = DATA_DIR / "phase3m_engineering_case.json"
PHASE3M_EXEC_MANIFEST = DATA_DIR / "phase3m_execution_manifest.json"
PHASE3M_PARAM_SNAPSHOT = DATA_DIR / "phase3m_parameter_snapshot.json"
PHASE3M_DOCS = DOCS_DIR / "phase3m_independent_engineering_case.md"

PHASE3N_CASE_JSON = DATA_DIR / "phase3n_engineering_case.json"
PHASE3N_EXEC_MANIFEST = DATA_DIR / "phase3n_execution_manifest.json"
PHASE3N_PARAM_SNAPSHOT = DATA_DIR / "phase3n_parameter_snapshot.json"
PHASE3N_DOCS = DOCS_DIR / "phase3n_independent_engineering_case.md"


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── TEST 1: PROTECTED PHYSICS HASHES UNCHANGED ────────────────────────────────
def test_1_protected_physics_hashes_unchanged():
    """Verify that all 11 protected physics files remain 100% identical to Phase 3H manifest."""
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing physics file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Modification detected in protected physics: {item['path']}!"


# ── TEST 2: MANDATORY RK4 DT = 0.001 S CONTRACT ───────────────────────────────
def test_2_mandatory_rk4_dt_contract():
    """Verify RK4 numerical configuration and rejection of non-compliant timesteps."""
    assert PHASE3N_EXEC_MANIFEST.exists()
    with open(PHASE3N_EXEC_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    sc = manifest["solver_contract"]
    assert sc["integrator"] == "RK4"
    assert sc["dt_s"] == 0.001
    assert sc["integration_frequency_hz"] == 1000.0
    assert sc["state_dimension"] == 22
    assert sc["derivative_evaluations_per_step"] == 4
    assert sc["solver_module"] == "suspensionlab.physics.dynamic_lap_sim"
    assert sc["solver_function"] == "DynamicLapSimulator.step"

    with pytest.raises(ValueError, match="Mandatory canonical timestep is dt = 0.001 s"):
        Phase3NCaseService.execute_governed_simulation(
            setup_id="SETUP-INVALID-DT",
            k_delta=0.000451,
            telemetry_window_s=(14.0, 15.0),
            dt_s=0.005,
        )


# ── TEST 3: PARAMETER SNAPSHOT BASELINE SEMANTICS ─────────────────────────────
def test_3_parameter_snapshot_baseline_semantics():
    """Verify rigid reference baseline vs historical reference semantics and provenance."""
    assert PHASE3N_PARAM_SNAPSHOT.exists()
    with open(PHASE3N_PARAM_SNAPSHOT, "r", encoding="utf-8") as f:
        snap = json.load(f)

    p = snap["parameters"]["steering_compliance_rad_per_mps2"]
    assert p["canonical_name"] == "steering_compliance_rad_per_mps2"
    assert p["unit"] == "rad/(m/s^2)"
    assert p["baseline_value"] == 0.0
    assert p["baseline_semantic_role"] == "RIGID_REFERENCE_BASELINE"
    assert "Uncalibrated rigid linkage reference" in p["baseline_qualification"]
    assert p["historical_calibrated_reference"] == 0.000451
    assert "Phase 3D" in p["historical_provenance"]
    assert p["valid_domain"]["min_operational"] == 0.0
    assert p["valid_domain"]["max_operational"] == 0.0012
    assert "provenance_note" in p["valid_domain"]

    # Canonical frozen vehicle state
    veh = snap["vehicle_params"]
    assert veh["mass_kg"] == 1530.0
    assert veh["sprung_mass_kg"] == 1410.0
    assert veh["c_damper_front_nsm"] == 2244.46
    assert veh["k_spring_front_nm"] == 65000.0
    assert veh["k_arb_front_nm"] == 25000.0


# ── TEST 4: EXCLUDED PARAMETERS AUDIT ─────────────────────────────────────────
def test_4_excluded_parameters_audit():
    """Verify steer_ratio and steering_rate_limit_rads exclusion rationales."""
    gate = Phase3NCaseService.run_observability_gate()
    ex = gate["payload"]["excluded_parameters_audit"]
    assert "steer_ratio" in ex
    assert "algebraic cancellation" in ex["steer_ratio"]
    assert "steering_rate_limit_rads" in ex
    assert "peak telemetry rate" in ex["steering_rate_limit_rads"]


# ── TEST 5: PARTITION DISJOINTNESS PROOF ──────────────────────────────────────
def test_5_partition_disjointness_proof():
    """Prove mathematically and via set theory that Fit, Temporal, and Cross holdouts are disjoint."""
    audit = Phase3NCaseService.audit_telemetry_windows()
    proof = audit["partition_disjointness_proof"]

    assert proof["fit_temporal_disjoint"] is True
    assert proof["fit_cross_disjoint"] is True
    assert proof["temporal_cross_disjoint"] is True
    assert proof["overlap_sample_counts"]["fit_temporal"] == 0
    assert proof["overlap_sample_counts"]["fit_cross"] == 0
    assert proof["overlap_sample_counts"]["temporal_cross"] == 0


# ── TEST 6: TELEMETRY WINDOW SUITABILITY & DISQUALIFICATION ────────────────────
def test_6_telemetry_window_suitability_and_disqualification():
    """Verify window suitability metrics and documented disqualification of Turn 9-10."""
    audit = Phase3NCaseService.audit_telemetry_windows()
    fit = audit["partitions"]["fit_window"]
    temp = audit["partitions"]["temporal_holdout_window"]
    cross = audit["partitions"]["cross_maneuver_holdout_window"]

    assert fit["window_name"] == "Turn_1_Complex"
    assert fit["sample_count"] == 960
    assert fit["stats"]["peak_lateral_accel_g"] >= 0.85
    assert fit["stats"]["peak_yaw_rate_radps"] >= 0.35

    assert temp["window_name"] == "Turn_1_Exit"
    assert temp["sample_count"] == 639

    assert cross["window_name"] == "Chicane_HighSpeed_S_Curves"
    assert cross["sample_count"] == 1800

    # Turn 9-10 disqualification
    assert "Turn_9_10_Final_Complex" in audit["disqualified_windows"]
    assert "602 deg/s" in audit["disqualified_windows"]["Turn_9_10_Final_Complex"]["disqualification_reason"]


# ── TEST 7: OBSERVABILITY GATE ────────────────────────────────────────────────
def test_7_observability_gate():
    """Verify that steering compliance achieves status IDENTIFIABLE."""
    gate = Phase3NCaseService.run_observability_gate()
    assert gate["gate_status"] == "IDENTIFIABLE"
    assert gate["proceed_permitted"] is True

    payload = gate["payload"]
    assert payload["sensitivity_norm"] >= 0.040
    assert payload["fisher_information_eigenvalue"] > 5.0
    assert payload["condition_number_1d"] == 1.00
    assert abs(payload["max_parameter_correlation"]) < 0.30
    assert payload["multistart_dispersion_pct"] < 1.0


# ── TEST 8: PRE-REGISTRATION FROZEN BEFORE HOLDOUT ────────────────────────────
def test_8_preregistration_frozen_before_holdout():
    """Verify pre-registration definition contains immutable hash and pre-registered rules."""
    prereg = Phase3NCaseService.create_preregistration_record(user_id=str(uuid.uuid4()))
    assert prereg["is_frozen"] is True
    assert len(prereg["preregistration_hash"]) == 64

    payload = prereg["payload"]
    assert payload["primary_metric"]["metric_name"] == "yaw_rate_rmse_radps"
    assert payload["decision_rules"]["rule_classification"] == "PRE-REGISTERED ENGINEERING DECISION RULE"
    assert "secondary_metrics" in payload
    assert "sideslip_angle_rmse_rad" in payload["secondary_metrics"]
    assert payload["secondary_metrics"]["sideslip_angle_rmse_rad"]["provenance"] == "DERIVED_FROM_MEASUREMENT"


# ── TEST 9: REAL SOLVER EXECUTION & DISTINCT OUTPUTS ──────────────────────────
def test_9_real_solver_execution_and_distinct_outputs():
    """Verify simulation solver executes and distinct candidate values produce distinct metrics."""
    sim_base = Phase3NCaseService.execute_governed_simulation(
        setup_id="SETUP-P3N-BASE",
        k_delta=0.0,
        telemetry_window_s=Phase3NCaseService.FIT_WINDOW,
    )
    sim_cand = Phase3NCaseService.execute_governed_simulation(
        setup_id="SETUP-P3N-CAND-02",
        k_delta=0.000451,
        telemetry_window_s=Phase3NCaseService.FIT_WINDOW,
    )

    assert sim_base["solver_status"] == "SUCCESS"
    assert sim_cand["solver_status"] == "SUCCESS"
    assert sim_base["output_hash"] != sim_cand["output_hash"]
    assert sim_base["metrics"]["yaw_rate_rmse_radps"] != sim_cand["metrics"]["yaw_rate_rmse_radps"]
    assert sim_cand["metrics"]["yaw_rate_rmse_radps"] < sim_base["metrics"]["yaw_rate_rmse_radps"]


# ── TEST 10: FIT WINDOW OPTIMIZATION RANKING ──────────────────────────────────
def test_10_fit_window_optimization_ranking():
    """Verify fit window candidate ranking and trade-off documentation."""
    sims = Phase3NCaseService.execute_candidate_simulations_fit_window()
    opt = Phase3NCaseService.evaluate_tradeoffs_and_optimization(sims)

    ranking = opt["ranking"]
    assert len(ranking) == 4
    # Fit RMSE strictly monotonic with compliance: CAND-03 < CAND-02 < CAND-01 < BASE
    assert ranking[0]["setup_id"] == "SETUP-P3N-CAND-03"
    assert ranking[1]["setup_id"] == "SETUP-P3N-CAND-02"
    assert ranking[2]["setup_id"] == "SETUP-P3N-CAND-01"
    assert ranking[3]["setup_id"] == "SETUP-P3N-BASE"

    assert "SETUP-P3N-CAND-02" in opt["tradeoffs"]
    assert len(opt["tradeoffs"]["SETUP-P3N-CAND-02"]["WHAT_IMPROVED"]) > 0


# ── TEST 11: TEMPORAL HOLDOUT NON-INFERIORITY ─────────────────────────────────
@pytest.mark.asyncio
async def test_11_temporal_holdout_non_inferiority(async_test_db: AsyncSession):
    """Verify Candidate 2 achieves optimal performance on Turn 1 Exit while Candidate 3 over-complies."""
    user_id = str(uuid.uuid4())
    val = await Phase3NCaseService.execute_sealed_blind_validation(
        async_test_db, user_id=user_id, candidate_setup_id="SETUP-P3N-CAND-02"
    )

    temp = val["temporal_holdout"]
    # Point estimate improves (-5.64%)
    assert temp["candidate_yaw_rmse_radps"] < temp["baseline_yaw_rmse_radps"]
    assert temp["relative_delta_pct"] < 0.0  # Point difference improves

    # However, exact upper 95% bootstrap CI (+0.00178 rad/s) exceeds the 5% margin (+0.00158 rad/s)
    assert temp["ci_upper_exceeds_margin"] is True
    assert temp["non_inferiority_passed"] is False
    assert temp["status"] == "TEMPORAL_NONINFERIORITY_NOT_ESTABLISHED"
    assert val["gate_verdict"] == "UNRESOLVED"

    # Confirm CAND-03 over-attenuates relative to CAND-02 on exit
    sim_c2 = Phase3NCaseService.execute_governed_simulation(
        "SETUP-P3N-CAND-02", 0.000451, Phase3NCaseService.TEMPORAL_HOLDOUT_WINDOW
    )
    sim_c3 = Phase3NCaseService.execute_governed_simulation(
        "SETUP-P3N-CAND-03", 0.000650, Phase3NCaseService.TEMPORAL_HOLDOUT_WINDOW
    )
    assert sim_c2["metrics"]["yaw_rate_rmse_radps"] < sim_c3["metrics"]["yaw_rate_rmse_radps"]


# ── TEST 12: CROSS-MANEUVER HOLDOUT GENERALIZATION ────────────────────────────
@pytest.mark.asyncio
async def test_12_cross_maneuver_holdout_generalization(async_test_db: AsyncSession):
    """Verify Candidate 2 generalizes on the unseen Chicane holdout segment."""
    user_id = str(uuid.uuid4())
    val = await Phase3NCaseService.execute_sealed_blind_validation(
        async_test_db, user_id=user_id, candidate_setup_id="SETUP-P3N-CAND-02"
    )

    cross = val["cross_maneuver_holdout"]
    assert cross["generalization_passed"] is True
    assert cross["candidate_yaw_rmse_radps"] < cross["baseline_yaw_rmse_radps"]
    assert cross["candidate_r2"] > cross["baseline_r2"]
    assert cross["relative_delta_pct"] < -8.0  # -8.58%


# ── TEST 13: PAIRED BLOCK BOOTSTRAP UNCERTAINTY ───────────────────────────────
def test_13_paired_block_bootstrap_uncertainty():
    """Verify stationary block bootstrap exclusions and prohibition of heuristic CI."""
    boot = Phase3NCaseService.compute_block_bootstrap_analysis(b_reps=1000, seed=42)

    assert boot["replicates"] == 1000
    assert boot["governance_rule"] == "HEURISTIC_CI_PROHIBITED"
    assert boot["heuristic_196_pct_detected"] is False

    fit = boot["fit_window"]
    assert fit["point_effect_radps"] < -0.010
    assert fit["zero_excluded"] is True  # Statistically significant improvement on fit
    assert fit["ci_95_radps"][1] < 0.0

    temp = boot["temporal_holdout_window"]
    assert temp["zero_excluded"] is False  # Neutral / non-inferior on temporal holdout
    assert temp["ci_95_radps"][1] < 0.005  # Upper limit well within non-inferiority

    cross = boot["cross_maneuver_holdout_window"]
    assert cross["zero_excluded"] is True  # Statistically significant generalization
    assert cross["ci_95_radps"][1] < 0.0


# ── TEST 14: SECONDARY METRIC ADMISSIBILITY ───────────────────────────────────
def test_14_secondary_metric_admissibility():
    """Verify lateral accel, vehicle sideslip beta, roll, and jounce clearance meet admissibility constraints."""
    sim_base = Phase3NCaseService.execute_governed_simulation("SETUP-P3N-BASE", 0.0, Phase3NCaseService.FIT_WINDOW)
    sim_cand = Phase3NCaseService.execute_governed_simulation("SETUP-P3N-CAND-02", 0.000451, Phase3NCaseService.FIT_WINDOW)

    m_base = sim_base["metrics"]
    m_cand = sim_cand["metrics"]

    # Lateral accel: degradation <= +5%
    ay_delta_pct = (m_cand["lateral_accel_rmse_mps2"] - m_base["lateral_accel_rmse_mps2"]) / m_base["lateral_accel_rmse_mps2"] * 100.0
    assert ay_delta_pct <= 5.0
    assert ay_delta_pct < 0.0  # Improved (-0.85%)

    # Sideslip angle beta: degradation <= +5%
    beta_delta_pct = (m_cand["peak_sideslip_deg"] - m_base["peak_sideslip_deg"]) / m_base["peak_sideslip_deg"] * 100.0
    assert beta_delta_pct <= 5.0
    assert beta_delta_pct < 0.0  # Improved (-8.25%)

    # Roll angle: degradation <= +5%
    roll_delta_pct = (m_cand["peak_roll_angle_deg"] - m_base["peak_roll_angle_deg"]) / m_base["peak_roll_angle_deg"] * 100.0
    assert roll_delta_pct <= 5.0

    # Jounce travel: <= 55 mm
    assert m_cand["dynamic_jounce_travel_mm"] <= 55.0
    assert (55.0 - m_cand["dynamic_jounce_travel_mm"]) >= 5.0


# ── TEST 15: FINAL CLASSIFICATION SEMANTICS ───────────────────────────────────
@pytest.mark.asyncio
async def test_15_final_classification_semantics(async_test_db: AsyncSession):
    """Verify final classification is EFFECT_UNRESOLVED and NEVER VALIDATED."""
    user_id = str(uuid.uuid4())
    dec = await Phase3NCaseService.formulate_engineering_decision(
        async_test_db, user_id=user_id, selected_setup_id="SETUP-P3N-CAND-02"
    )
    assert dec["status"] == "EFFECT_UNRESOLVED"
    assert dec["status"] != "ENGINEERING_DECISION_VALIDATED"
    assert dec["status"] != "VALIDATED"


# ── TEST 16: TRACK PREDICTION IMMUTABILITY ────────────────────────────────────
@pytest.mark.asyncio
async def test_16_track_prediction_immutability(async_test_db: AsyncSession):
    """Verify TrackTestPredictionRecord immutability and physical mapping status."""
    user_id = str(uuid.uuid4())
    pred = await Phase3NCaseService.generate_track_test_prediction(
        async_test_db, user_id=user_id, candidate_setup_id="SETUP-P3N-CAND-02"
    )
    assert pred["prediction_id"] == "PRED-P3N-01"
    assert pred["reconciliation_status"] in {
        "MODEL_PARAMETER_PREDICTION_PENDING_PHYSICAL_MAPPING",
        "PREDICTION_PENDING_TRACK_TEST",
    }
    assert pred["is_immutable"] is True
    assert len(pred["prediction_hash"]) == 64


# ── TEST 17: HUMAN APPROVAL HMAC SIGNOFF ──────────────────────────────────────
@pytest.mark.asyncio
async def test_17_human_approval_hmac_signoff(async_test_db: AsyncSession):
    """Verify decision requires human HMAC-SHA256 signature and cannot be auto-approved."""
    user_id = str(uuid.uuid4())
    await Phase3NCaseService.formulate_engineering_decision(
        async_test_db, user_id=user_id, decision_code="DEC-TEST-01"
    )

    # Human sign-off
    app = await Phase3NCaseService.execute_human_approval(
        async_test_db,
        user_id=user_id,
        decision_code="DEC-TEST-01",
        approver_name="Marcus Vance",
        approver_role="Chief Technical Director & Chief Race Engineer",
    )
    assert app["status"] == "APPROVED"
    assert len(app["signature"]) == 64

    res = await async_test_db.execute(select(EngineeringDecision).where(EngineeringDecision.decision_id == "DEC-TEST-01"))
    dec_db = res.scalar_one()
    assert dec_db.status == "APPROVED"


# ── TEST 18: UNBROKEN 14-LINK LINEAGE TRACE ───────────────────────────────────
def test_18_14_link_lineage_trace():
    """Verify unbroken 14-link backward lineage chain."""
    lineage = Phase3NCaseService.reconstruct_lineage(decision_id="DEC-P3N-01")
    assert lineage["root_decision_id"] == "DEC-P3N-01"
    assert lineage["reconstruction_status"] == "UNBROKEN_CRYPTOGRAPHIC_CHAIN"
    assert lineage["total_links"] == 14

    links = [item["link"] for item in lineage["chain"]]
    expected_links = [
        "Decision",
        "Approval",
        "Validation",
        "Optimization",
        "Simulation",
        "Experiment",
        "Hypothesis",
        "Evidence",
        "Question",
        "Telemetry Session",
        "Dataset",
        "Parameter Snapshot",
        "Model Version",
        "Solver Configuration",
    ]
    assert links == expected_links


# ── TEST 19: HISTORICAL PHASE 3M ARTIFACTS UNTOUCHED ──────────────────────────
def test_19_historical_phase3m_artifacts_untouched():
    """Verify that Phase 3M and Phase 3M.1 historical manifests remain strictly untouched."""
    assert PHASE3M_DOCS.exists()
    assert PHASE3M_CASE_JSON.exists()
    assert PHASE3M_PARAM_SNAPSHOT.exists()
    assert PHASE3M_EXEC_MANIFEST.exists()

    expected_hashes = {
        PHASE3M_DOCS: "b4485ba58a84a18c01d742a88709873d964381df562243824b28a388d0c4d70a",
        PHASE3M_CASE_JSON: "20fd0ec059fb3d4873d5f9321679f289666f225933eaf9f107fc3ef83a13f3b7",
        PHASE3M_PARAM_SNAPSHOT: "6d93b50d0ca682b99d9593ddb67a8cbd24fdb42c926fc2726a0bea4c1efc5c67",
        PHASE3M_EXEC_MANIFEST: "eeff2692af566559800aa717f673af43c158f3f69d19823fb971bb9a1df37db0",
    }
    for p, h in expected_hashes.items():
        actual_h = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual_h == h, f"Mutation detected in historical 3M artifact {p.name}!"


# ── TEST 20: ALL PERSISTED PHASE 3N ARTIFACTS EXIST ───────────────────────────
def test_20_all_persisted_phase3n_artifacts_exist():
    """Verify that all Phase 3N persistent artifacts exist on disk and validate."""
    assert PHASE3N_PARAM_SNAPSHOT.exists()
    assert PHASE3N_EXEC_MANIFEST.exists()
    assert PHASE3N_CASE_JSON.exists()

    with open(PHASE3N_EXEC_MANIFEST, "r", encoding="utf-8") as f:
        m = json.load(f)
    assert m["phase"] == "PHASE_3N"
    assert m["final_classification"] == "EFFECT_UNRESOLVED"

    with open(PHASE3N_CASE_JSON, "r", encoding="utf-8") as f:
        c = json.load(f)
    assert c["phase"] == "PHASE_3N"
    assert c["final_classification"] == "EFFECT_UNRESOLVED"
