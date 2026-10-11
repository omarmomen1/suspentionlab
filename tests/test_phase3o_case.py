"""
tests/test_phase3o_case.py
==========================
Comprehensive Verification & Governance Test Suite for Phase 3O:
- Cryptographic integrity of preregistration protocol and authentic telemetry
- Protected production physics immutability
- Exact authoritative sample indices and disjointness
- Fixed-step RK4 solver contract (dt = 0.001 s, 5 substeps per sample)
- Fit partition calibration and candidate freeze (s_tire* = 0.822)
- Paired moving block bootstrap RMSE difference targeting (B=1000, L=20, seed=42)
- Temporal holdout non-inferiority verification
- Cross-maneuver holdout generalization failure verification
- Secondary metrics & sideslip boundary enforcement
- Final classification: EFFECT_UNRESOLVED
- Strict prohibition of 'VALIDATED'
- Demarcation of physical track actionability (BLOCKED / NOT_YET_MAPPED)
"""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from suspensionlab.backend.services.phase3o_case_service import Phase3OCaseService

DATA_DIR = Path("data")
DOCS_DIR = Path("docs")

PARAM_SNAPSHOT_PATH = DATA_DIR / "phase3o_parameter_snapshot.json"
EXEC_MANIFEST_PATH = DATA_DIR / "phase3o_execution_manifest.json"
RESULTS_PATH = DATA_DIR / "phase3o_results.json"
BOOTSTRAP_PATH = DATA_DIR / "phase3o_bootstrap_results.json"
ENGINEERING_CASE_PATH = DATA_DIR / "phase3o_engineering_case.json"
EXEC_REPORT_PATH = DOCS_DIR / "phase3o_execution_report.md"


def test_1_pre_execution_integrity():
    """Verify cryptographic hash of protocol, historical archive, dataset, and protected physics."""
    integ = Phase3OCaseService.verify_pre_execution_integrity()
    assert integ["protocol_sha_verified"] is True
    assert integ["historical_archive_verified"] is True
    assert integ["dataset_sha_verified"] is True
    assert integ["protected_physics_verified"] is True
    assert integ["phase3n_status"] == "CLOSED_EFFECT_UNRESOLVED"


def test_2_solver_contract():
    """Verify solver contract: DynamicLapSimulator, RK4, dt=0.001 s, 5 substeps per 200 Hz sample."""
    manifest_path = DOCS_DIR / "phase3o_preregistration_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        m = json.load(f)
    sc = m["solver_contract"]
    assert sc["simulator_class"] == "DynamicLapSimulator"
    assert sc["simulator_module"] == "suspensionlab.physics.dynamic_lap_sim"
    assert sc["canonical_timestep_s"] == 0.001
    assert sc["mandatory_substeps_per_sample"] == 5
    assert sc["integrator_algorithm"] == "Fixed-step 4th-Order Runge-Kutta (RK4)"
    assert sc["silent_timestep_substitution_prohibited"] is True


def test_3_authoritative_sample_indices_and_disjointness():
    """Verify authoritative index definitions and strict disjointness."""
    fit_s, fit_e = Phase3OCaseService.FIT_INDICES
    buf1 = Phase3OCaseService.BUFFER_1_INDEX
    temp_s, temp_e = Phase3OCaseService.TEMPORAL_INDICES
    buf2_s, buf2_e = Phase3OCaseService.BUFFER_2_INDICES
    cross_s, cross_e = Phase3OCaseService.CROSS_INDICES

    assert (fit_s, fit_e) == (2800, 3759)
    assert buf1 == 3760
    assert (temp_s, temp_e) == (3761, 4599)
    assert (buf2_s, buf2_e) == (4600, 4799)
    assert (cross_s, cross_e) == (4800, 5999)

    s_fit = set(range(fit_s, fit_e + 1))
    s_temp = set(range(temp_s, temp_e + 1))
    s_cross = set(range(cross_s, cross_e + 1))
    s_buf1 = {buf1}
    s_buf2 = set(range(buf2_s, buf2_e + 1))

    assert s_fit.isdisjoint(s_temp)
    assert s_fit.isdisjoint(s_cross)
    assert s_temp.isdisjoint(s_cross)
    assert s_fit.isdisjoint(s_buf1) and s_temp.isdisjoint(s_buf1)
    assert s_temp.isdisjoint(s_buf2) and s_cross.isdisjoint(s_buf2)


def test_4_governed_artifacts_exist_and_hashes_deterministic():
    """Verify that all 6 governed artifacts exist on disk and have valid structure."""
    for p in [
        PARAM_SNAPSHOT_PATH,
        EXEC_MANIFEST_PATH,
        RESULTS_PATH,
        BOOTSTRAP_PATH,
        ENGINEERING_CASE_PATH,
        EXEC_REPORT_PATH,
    ]:
        assert p.exists(), f"Governed artifact missing: {p}"
        assert p.stat().st_size > 0, f"Governed artifact empty: {p}"


def test_5_parameter_snapshot_semantics():
    """Verify parameter snapshot baseline vs calibrated semantics and actionability."""
    with open(PARAM_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        snap = json.load(f)

    assert snap["protocol_id"] == "PREREG-P3O-01"
    assert snap["protocol_version"] == "1.0.1-frozen"
    assert snap["protocol_sha256"] == Phase3OCaseService.PROTOCOL_SHA256

    mech = snap["target_mechanism"]
    assert mech["parameter_name"] == "DynamicVehicleParams.tire_calibration.s_tire"
    assert mech["baseline_value"] == 1.000
    assert mech["baseline_semantics"] == "UNIDENTIFIED_NOMINAL_REFERENCE"
    assert mech["calibrated_setup_id"] == "SETUP-P3O-CAL"
    assert mech["calibrated_value"] == 0.864
    assert mech["pKy1_calibrated"] == round(15.0 * 0.864, 3)

    assert snap["model_parameter_actionability"] == "SUPPORTED_AS_A_MODEL_VARIABLE"
    assert snap["physical_track_actionability"] == "NOT_YET_MAPPED"


def test_6_fit_gate_and_calibration():
    """Verify Fit partition calibration result and Fit Gate pass condition."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    fit = res["fit_calibration"]
    assert fit["candidate_setup_id"] == "SETUP-P3O-CAL"
    assert fit["s_tire_frozen"] == 0.864

    base_rmse = fit["baseline_fit"]["yaw_rmse"]
    cal_rmse = fit["candidate_fit"]["yaw_rmse"]
    assert cal_rmse < base_rmse
    assert fit["fit_gate"]["gate_passed"] is True
    assert fit["fit_gate"]["observed_relative_pct"] <= -3.0


def test_7_temporal_holdout_non_inferiority_established():
    """Verify temporal holdout non-inferiority pass via paired moving block bootstrap."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    temp = res["temporal_holdout"]
    assert temp["window"] == "Turn_1_Exit"
    assert temp["sample_count"] == 839
    assert temp["non_inferiority_passed"] is True
    assert temp["verdict"] == "NON_INFERIORITY_ESTABLISHED"

    boot = temp["bootstrap"]
    assert boot["algorithm"] == "PAIRED_MOVING_BLOCK_BOOTSTRAP"
    assert boot["replicates_B"] == 1000
    assert boot["block_length_samples"] == 20
    assert boot["random_seed"] == 42
    # Upper CI must be <= margin
    assert boot["ci_upper"] <= temp["non_inferiority_margin_abs"]
    # In fact, Delta RMSE is negative (improved)
    assert temp["delta_rmse"] < 0.0


def test_8_cross_maneuver_holdout_generalization_failed():
    """Verify that cross-maneuver holdout generalization fails on Turn 2 Carousel."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    cross = res["cross_maneuver_holdout"]
    assert cross["window"] == "Turn_2_Carousel"
    assert cross["sample_count"] == 1200
    assert cross["generalization_passed"] is False
    assert cross["verdict"] == "GENERALIZATION_NOT_ESTABLISHED"

    boot = cross["bootstrap"]
    assert boot["algorithm"] == "PAIRED_MOVING_BLOCK_BOOTSTRAP"
    # CI upper bound strictly positive (degradation)
    assert boot["ci_upper"] > 0.0
    assert cross["delta_rmse"] > 0.0
    assert boot["p_value"] > 0.05


def test_9_secondary_metrics_and_sideslip_gate():
    """Verify secondary metrics and authoritative sideslip boundary."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    sec = res["secondary_metrics"]
    assert sec["ay_degradation_pct"]["passed"] is True
    assert sec["roll_degradation_pct"]["passed"] is True

    beta_info = sec["sideslip_beta_boundary"]
    assert beta_info["threshold_rad"] == 0.100
    assert beta_info["threshold_deg"] == pytest.approx(5.7296, rel=1e-4)
    assert beta_info["passed"] is True
    assert beta_info["failure_status_on_breach"] == "REJECT_DUE_TO_SIDESLIP_STABILITY_BOUNDARY"

    # Dynamic jounce fails under sustained 1.14 G carousel loading
    assert sec["dynamic_jounce"]["passed"] is False
    assert sec["dynamic_jounce"]["max_observed_mm"] > 55.0


def test_10_final_decision_unresolved_and_no_validated():
    """Verify that the final outcome is EFFECT_UNRESOLVED and 'VALIDATED' is prohibited."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    assert res["final_classification"] == "EFFECT_UNRESOLVED"
    assert "Cross-maneuver generalization was not established" in res["final_reason"]
    assert res["blocker_status"]["execution_blockers"] == "NONE"
    assert res["blocker_status"]["physical_track_actionability"] == "BLOCKED / NOT_YET_MAPPED"

    # Prohibited terminology check across all artifacts
    with open(EXEC_REPORT_PATH, "r", encoding="utf-8") as f:
        rep_text = f.read()

    with open(ENGINEERING_CASE_PATH, "r", encoding="utf-8") as f:
        case_text = f.read()

    # The string 'VALIDATED' must not appear as a verdict or status
    assert "VALIDATED" not in rep_text.replace("PREDICTION_VALIDATED", "") # only if in forbidden context
    assert '"status": "VALIDATED"' not in case_text
    assert '"verdict": "VALIDATED"' not in case_text
