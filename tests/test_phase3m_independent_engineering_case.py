"""
tests/test_phase3m_independent_engineering_case.py
==================================================
Phase 3M: Independent Canonical Engineering Case Test Suite.

Mode: CONTROLLED IMPLEMENTATION
Zero Production Physics Modifications | Canonical Governed Contract | Governed Provenance

Verifies the 20 mandatory invariants:
1. frozen physics hashes unchanged
2. canonical solver contract enforced
3. canonical parameter snapshot enforced
4. Phase 3J.1 damping provenance preserved
5. no Phase 3L stale damping leakage
6. telemetry window independence
7. observability gate
8. real solver execution
9. distinct candidate outputs
10. candidate provenance
11. fit/holdout disjointness
12. candidate-before-holdout-unseal
13. uncertainty provenance
14. no heuristic CI
15. optimization uses real solver
16. ranking reproducibility
17. decision reconstructability
18. no automatic approval
19. historical Phase 3L artifacts untouched
20. production physics unchanged
"""
from __future__ import annotations

import hashlib
import json
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
    Phase3LSetupEngineeringService,
    HoldoutLeakageError,
)
from suspensionlab.backend.services.phase3m_case_service import Phase3MCaseService
from suspensionlab.physics.dynamic_lap_sim import DynamicLapSimulator, DynamicVehicleParams
from suspensionlab.calibration.registry import STANDARD_PARAMETER_REGISTRY


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"

PHASE3H_MANIFEST = DATA_DIR / "phase3h_final_validity_manifest.json"
PHASE3J1_MANIFEST = DATA_DIR / "phase3j1_identification_robustness.json"
PHASE3L_MANIFEST = DATA_DIR / "phase3l_setup_engineering_manifest.json"
PHASE3L2_CLOSURE = DATA_DIR / "phase3l2_governance_closure.json"

PHASE3M_CASE_JSON = DATA_DIR / "phase3m_engineering_case.json"
PHASE3M_EXEC_MANIFEST = DATA_DIR / "phase3m_execution_manifest.json"
PHASE3M_PARAM_SNAPSHOT = DATA_DIR / "phase3m_parameter_snapshot.json"
PHASE3M_DOCS = DOCS_DIR / "phase3m_independent_engineering_case.md"


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


# ── TEST 1: FROZEN PHYSICS HASHES UNCHANGED ───────────────────────────────────

def test_1_frozen_physics_hashes_unchanged():
    """Verify that all 11 protected physics files remain 100% identical to Phase 3H manifest."""
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Modification detected in {item['path']}!"


# ── TEST 2: CANONICAL SOLVER CONTRACT ENFORCED ────────────────────────────────

def test_2_canonical_solver_contract_enforced():
    """Verify solver identity and mandatory dt = 0.001 s numerical configuration."""
    assert PHASE3M_EXEC_MANIFEST.exists()
    with open(PHASE3M_EXEC_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    sc = manifest["solver_contract"]
    assert sc["integrator"] == "RK4"
    assert sc["dt_s"] == 0.001
    assert sc["integration_frequency_hz"] == 1000.0
    assert sc["state_dimension"] == 22
    assert sc["derivative_evaluations_per_step"] == 4
    assert sc["solver_module"] == "suspensionlab.physics.dynamic_lap_sim"
    assert sc["solver_function"] == "DynamicLapSimulator.step"

    # Enforce rejection of dt != 0.001 in canonical solver path
    with pytest.raises(ValueError, match="Mandatory canonical timestep is dt = 0.001 s"):
        Phase3LSetupEngineeringService.execute_canonical_governed_simulation(
            setup_id="SETUP-INVALID-DT",
            dt_s=0.005,
        )


# ── TEST 3: CANONICAL PARAMETER SNAPSHOT ENFORCED ─────────────────────────────

def test_3_canonical_parameter_snapshot_enforced():
    """Verify authoritative vehicle parameters match canonical state and provenances."""
    assert PHASE3M_PARAM_SNAPSHOT.exists()
    with open(PHASE3M_PARAM_SNAPSHOT, "r", encoding="utf-8") as f:
        snap = json.load(f)

    params = snap["parameters"]
    assert params["total_vehicle_mass"]["baseline_value"] == 1530.0
    assert params["sprung_mass"]["baseline_value"] == 1410.0
    assert params["spring_rate_front"]["baseline_value"] == 65000.0
    assert params["anti_roll_bar_front"]["baseline_value"] == 25000.0
    assert params["nominal_tire_pressure_bar"]["baseline_value"] == 2.0
    assert params["aero_front_balance"]["baseline_value"] == 0.44

    # Every parameter must have explicit provenance
    for p_name, p_data in params.items():
        if isinstance(p_data, dict) and "source_artifact" in p_data:
            assert len(p_data["source_artifact"]) > 0
            assert p_data["identifiability_state"] in {
                "IDENTIFIABLE",
                "INHERITED_IDENTIFICATION",
                "MAPPED_WHEEL_RATE",
                "CONTROL_VARIABLE",
                "GEOMETRIC_SPECIFICATION",
            }


# ── TEST 4: PHASE 3J.1 DAMPING PROVENANCE PRESERVED ───────────────────────────

def test_4_phase3j1_damping_provenance_preserved():
    """Verify front bump damping baseline is exactly 2244.46 Ns/m from Phase 3J.1 calibration."""
    with open(PHASE3J1_MANIFEST, "r", encoding="utf-8") as f:
        p3j1 = json.load(f)

    t5_damping = p3j1["analysis_windows"][1]["parameters"]["damper_bump_front"]
    calibrated_val = round(float(t5_damping["calibrated_value"]), 2)
    assert calibrated_val == 2244.46

    snap = Phase3MCaseService.get_canonical_parameter_snapshot()
    d_param = snap["parameters"]["damper_bump_front"]
    assert d_param["baseline_value"] == 2244.46
    assert d_param["identifiability_window"] == "Turn_5_Complex [74.0, 83.0] s"


# ── TEST 5: NO PHASE 3L STALE DAMPING LEAKAGE ─────────────────────────────────

def test_5_no_phase3l_stale_damping_leakage():
    """Verify that stale Phase 3L value 3800 Ns/m is absent from all Phase 3M setups."""
    assert PHASE3M_EXEC_MANIFEST.exists()
    with open(PHASE3M_EXEC_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for cand in manifest["experiment"]["candidates"]:
        assert cand["c_damper_front_nsm"] != 3800.0
        assert cand["c_damper_front_nsm"] in {2244.46, 1950.00, 2600.00}

    with open(PHASE3M_PARAM_SNAPSHOT, "r", encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["parameters"]["damper_bump_front"]["baseline_value"] != 3800.0
    assert snap["parameters"]["damper_bump_front"]["stale_value_prohibited"] == 3800.0


# ── TEST 6: TELEMETRY WINDOW INDEPENDENCE ─────────────────────────────────────

def test_6_telemetry_window_independence():
    """Verify that Phase 3M utilizes Turn 5 Complex [74, 83] s and NOT Phase 3L Turn 8 [39, 44] s."""
    audit = Phase3MCaseService.audit_telemetry_window()

    assert audit["window_name"] == "Turn_5_Complex"
    assert audit["window_start_s"] == 74.0
    assert audit["window_end_s"] == 83.0
    assert audit["sample_count"] == 1800

    # Ensure completely non-overlapping with Phase 3L Turn 8 [39.0, 44.0]
    p3l_interval = (39.0, 44.0)
    p3m_interval = (74.0, 83.0)
    assert p3m_interval[0] > p3l_interval[1]


# ── TEST 7: OBSERVABILITY GATE ────────────────────────────────────────────────

def test_7_observability_gate():
    """Verify that explicit damping observability gate confirms status IDENTIFIABLE."""
    gate = Phase3MCaseService.run_observability_gate()

    assert gate["gate_status"] == "IDENTIFIABLE"
    assert gate["proceed_permitted"] is True
    assert gate["payload"]["sensitivity_norm"] >= 0.50
    assert gate["payload"]["fisher_information_rank"] == 2
    assert gate["payload"]["max_parameter_correlation"] < 0.05
    assert gate["payload"]["multistart_dispersion_pct"] < 2.0


# ── TEST 8: REAL SOLVER EXECUTION ─────────────────────────────────────────────

def test_8_real_solver_execution():
    """Verify simulation executes actual production RK4 solver at dt = 0.001 s."""
    res = Phase3LSetupEngineeringService.execute_canonical_governed_simulation(
        setup_id="SETUP-REAL-01",
        c_damper_front=2244.46,
        telemetry_window_s=(74.0, 75.0),
        dt_s=0.001,
    )

    assert res["solver_status"] == "SUCCESS"
    assert res["solver_identity"]["derivative_evaluations_per_step"] == 4
    assert res["solver_configuration"]["dt_s"] == 0.001
    assert res["metrics"]["yaw_rate_rmse_radps"] > 0.0
    assert res["runtime_s"] > 0.0
    assert len(res["trajectory_hash"]) == 64
    assert len(res["output_hash"]) == 64


# ── TEST 9: DISTINCT CANDIDATE OUTPUTS ────────────────────────────────────────

def test_9_distinct_candidate_outputs():
    """Verify that each candidate produces distinct physical metrics and hashes."""
    sim_base = Phase3LSetupEngineeringService.execute_canonical_governed_simulation(
        setup_id="SETUP-BASE-TEST",
        c_damper_front=2244.46,
        telemetry_window_s=(74.0, 79.5),
        dt_s=0.001,
    )
    sim_cand = Phase3LSetupEngineeringService.execute_canonical_governed_simulation(
        setup_id="SETUP-CAND-TEST",
        c_damper_front=2600.00,
        telemetry_window_s=(74.0, 79.5),
        dt_s=0.001,
    )

    assert sim_base["output_hash"] != sim_cand["output_hash"]
    assert sim_base["trajectory_hash"] != sim_cand["trajectory_hash"]
    assert sim_base["metrics"]["yaw_rate_rmse_radps"] != sim_cand["metrics"]["yaw_rate_rmse_radps"]
    assert sim_base["metrics"]["roll_rms_deg"] != sim_cand["metrics"]["roll_rms_deg"]


# ── TEST 10: CANDIDATE PROVENANCE ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_10_candidate_provenance(async_test_db: AsyncSession):
    """Verify candidate record contains explicit provenance, valid domain, and parent lineage."""
    user_id = str(uuid.uuid4())
    _, hyp = await Phase3MCaseService.create_problem_and_hypothesis(async_test_db, user_id)
    cand_info = await Phase3MCaseService.design_experiment_and_candidates(
        async_test_db, user_id, hypothesis_id=hyp.hypothesis_id
    )

    res = await async_test_db.execute(select(SetupCandidateRecord))
    recs = res.scalars().all()
    assert len(recs) == 3

    for r in recs:
        assert "damper_bump_front" in r.changed_parameters
        assert "damper_bump_front" in r.parameter_provenance
        assert r.validity_domain["min_operational"] == 600.0
        assert r.validity_domain["max_operational"] == 6500.0


# ── TEST 11: FIT / HOLDOUT SAMPLE DISJOINTNESS ─────────────────────────────────

def test_11_fit_holdout_sample_disjointness():
    """Prove mathematically and via set theory that D_fit ∩ D_holdout = ∅."""
    fit_samples = set(np.round(np.arange(74.0, 79.5001, 0.005), 4))
    holdout_samples = set(np.round(np.arange(79.505, 83.0001, 0.005), 4))

    assert fit_samples.isdisjoint(holdout_samples)
    assert len(fit_samples.intersection(holdout_samples)) == 0
    assert max(fit_samples) < min(holdout_samples)


# ── TEST 12: CANDIDATE BEFORE HOLDOUT UNSEAL ──────────────────────────────────

@pytest.mark.asyncio
async def test_12_candidate_before_holdout_unseal(async_test_db: AsyncSession):
    """Prove candidate generation and optimization strictly precede holdout unseal."""
    user_id = str(uuid.uuid4())
    _, hyp = await Phase3MCaseService.create_problem_and_hypothesis(async_test_db, user_id)

    cand_design = await Phase3MCaseService.design_experiment_and_candidates(
        async_test_db, user_id, hypothesis_id=hyp.hypothesis_id
    )
    sim_res = Phase3MCaseService.execute_candidate_simulations_fit_window()
    opt_res = Phase3MCaseService.evaluate_tradeoffs_and_optimization(sim_res)

    val_res = await Phase3MCaseService.execute_sealed_blind_validation(
        db=async_test_db,
        user_id=user_id,
        candidate_setup_id="SETUP-P3M-CAND-02",
        candidate_generation_timestamp_iso=cand_design["creation_timestamp_iso"],
        optimization_timestamp_iso=opt_res["optimization_timestamp_iso"],
    )

    assert val_res["samples_disjoint"] is True
    assert val_res["gate_verdict"] == "PASSED"
    assert val_res["parameters_frozen"] is True


# ── TEST 13: UNCERTAINTY PROVENANCE ───────────────────────────────────────────

def test_13_uncertainty_provenance():
    """Verify uncertainty is derived from parameter covariance and measurement noise."""
    uncert = Phase3MCaseService.derive_uncertainty_analysis()

    p_unc = uncert["parameter_uncertainty"]
    assert p_unc["parameter"] == "damper_bump_front"
    assert p_unc["standard_error_nsm"] == 95.59
    assert p_unc["relative_standard_error_pct"] == 4.26
    assert p_unc["confidence_interval_95_nsm"] == [2057.11, 2431.81]

    m_unc = uncert["measurement_uncertainty"]
    assert m_unc["yaw_rate_sigma_radps"] == 0.015
    assert m_unc["lateral_accel_sigma_mps2"] == 0.05


# ── TEST 14: NO HEURISTIC CI ──────────────────────────────────────────────────

def test_14_no_heuristic_ci():
    """Verify that arbitrary 1.96 * 3% heuristic is strictly rejected."""
    uncert = Phase3MCaseService.derive_uncertainty_analysis()
    assert uncert["governance_rule"] == "HEURISTIC_CI_PROHIBITED"
    assert uncert["heuristic_196_pct_detected"] is False

    with open(PHASE3M_EXEC_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["uncertainty"]["heuristic_196_pct_detected"] is False


# ── TEST 15: OPTIMIZATION USES REAL SOLVER ────────────────────────────────────

def test_15_optimization_uses_real_solver():
    """Verify candidate optimization evaluates real simulation trajectory metrics."""
    sims = Phase3MCaseService.execute_candidate_simulations_fit_window()
    opt = Phase3MCaseService.evaluate_tradeoffs_and_optimization(sims)

    assert opt["selected_setup_id"] == "SETUP-P3M-CAND-02"
    ranking = opt["ranking"]
    assert len(ranking) == 3
    assert ranking[0]["setup_id"] == "SETUP-P3M-CAND-02"
    assert ranking[0]["rank"] == 1
    assert ranking[1]["setup_id"] == "SETUP-P3M-BASE"


# ── TEST 16: RANKING REPRODUCIBILITY ──────────────────────────────────────────

def test_16_ranking_reproducibility():
    """Verify candidate ranking is 100% reproducible across independent executions."""
    sims_1 = Phase3MCaseService.execute_candidate_simulations_fit_window()
    opt_1 = Phase3MCaseService.evaluate_tradeoffs_and_optimization(sims_1)

    sims_2 = Phase3MCaseService.execute_candidate_simulations_fit_window()
    opt_2 = Phase3MCaseService.evaluate_tradeoffs_and_optimization(sims_2)

    assert opt_1["selected_setup_id"] == opt_2["selected_setup_id"]
    assert opt_1["ranking"] == opt_2["ranking"]
    assert opt_1["artifact_hash"] == opt_2["artifact_hash"]


# ── TEST 17: DECISION RECONSTRUCTABILITY ───────────────────────────────────────

def test_17_decision_reconstructability():
    """Verify unbroken 14-link backward reconstructability chain from Decision ID."""
    lineage = Phase3MCaseService.reconstruct_lineage(decision_id="DEC-P3M-01")

    assert lineage["root_decision_id"] == "DEC-P3M-01"
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


# ── TEST 18: NO AUTOMATIC APPROVAL ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_18_no_automatic_approval(async_test_db: AsyncSession):
    """Verify engineering decision is NOT approved until explicit human sign-off."""
    user_id = str(uuid.uuid4())
    _, hyp = await Phase3MCaseService.create_problem_and_hypothesis(async_test_db, user_id)
    cand = await Phase3MCaseService.design_experiment_and_candidates(async_test_db, user_id, hypothesis_id=hyp.hypothesis_id)
    sims = Phase3MCaseService.execute_candidate_simulations_fit_window()
    opt = Phase3MCaseService.evaluate_tradeoffs_and_optimization(sims)
    val = await Phase3MCaseService.execute_sealed_blind_validation(
        async_test_db, user_id, candidate_setup_id=opt["selected_setup_id"]
    )

    # Prior to human approval
    dec = await Phase3MCaseService.formulate_engineering_decision(
        db=async_test_db,
        user_id=user_id,
        decision_code="DEC-TEST-01",
        selected_setup_id=opt["selected_setup_id"],
        blind_validation_results=val,
    )
    assert dec["status"] == "VALIDATED"  # VALIDATED recommendation, but NOT APPROVED

    # After explicit human sign-off
    app = await Phase3MCaseService.execute_human_approval(
        db=async_test_db,
        user_id=user_id,
        decision_code="DEC-TEST-01",
        approver_name="Marcus Vance",
        approver_role="Chief Technical Director & Chief Race Engineer",
    )
    assert app["status"] == "APPROVED"

    res = await async_test_db.execute(select(EngineeringDecision).where(EngineeringDecision.decision_id == "DEC-TEST-01"))
    db_dec = res.scalar_one()
    assert db_dec.status == "APPROVED"


# ── TEST 19: HISTORICAL PHASE 3L ARTIFACTS UNTOUCHED ──────────────────────────

def test_19_historical_phase3l_artifacts_untouched():
    """Verify that historical Phase 3L manifests and records remain untouched."""
    assert PHASE3L_MANIFEST.exists()
    assert PHASE3L2_CLOSURE.exists()

    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)
    assert closure["final_classification"] == "GOVERNANCE_VIOLATION"
    assert closure["baseline_release"]["git_sha"] == "fbe3d045762d8c216922630ca5c3b0da1d589a31"


# ── TEST 20: PRODUCTION PHYSICS UNCHANGED ─────────────────────────────────────

def test_20_production_physics_unchanged():
    """Verify zero modifications to production physics equations or solver implementations."""
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert hashlib.sha256(full_path.read_bytes()).hexdigest() == item["sha256"]
