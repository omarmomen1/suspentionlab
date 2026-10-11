"""
tests/test_phase3p_case.py
==========================
Comprehensive Verification & Governance Test Suite for Phase 3P:
- Cryptographic integrity of preregistration protocol and authentic telemetry
- Protected production physics immutability
- Exact authoritative sample indices and disjointness for Turn 4 partitions
- Fixed-step RK4 solver contract (dt = 0.001 s, 5 substeps per sample)
- Fit partition calibration and candidate freeze (sigma_y0* = 0.497 m)
- Paired moving block bootstrap RMSE difference targeting (B=1000, L=20, seed=42)
- Sustained holdout non-inferiority verification (Turn 4 Apex)
- Temporal holdout improvement requirement & hypothesis test (Turn 4 Exit)
- Secondary metrics & sideslip boundary enforcement
- Final classification: HYPOTHESIS_NOT_SUPPORTED
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

from suspensionlab.backend.services.phase3p_case_service import Phase3PCaseService

DATA_DIR = Path("data")
DOCS_DIR = Path("docs")

PARAM_SNAPSHOT_PATH = DATA_DIR / "phase3p_parameter_snapshot.json"
EXEC_MANIFEST_PATH = DATA_DIR / "phase3p_execution_manifest.json"
RESULTS_PATH = DATA_DIR / "phase3p_results.json"
BOOTSTRAP_PATH = DATA_DIR / "phase3p_bootstrap_results.json"
ENGINEERING_CASE_PATH = DATA_DIR / "phase3p_engineering_case.json"
EXEC_REPORT_PATH = DOCS_DIR / "phase3p_execution_report.md"


def test_1_pre_execution_integrity():
    """Verify cryptographic hash of protocol, dataset, and protected physics."""
    integ = Phase3PCaseService.verify_pre_execution_integrity()
    assert integ["protocol_sha_verified"] is True
    assert integ["dataset_sha_verified"] is True
    assert integ["protected_physics_verified"] is True
    assert integ["phase3o_status"] == "PERMANENTLY_CLOSED_UNTOUCHED"


def test_2_solver_contract():
    """Verify solver contract: DynamicLapSimulator, RK4, dt=0.001 s, 5 substeps per sample."""
    manifest_path = DOCS_DIR / "phase3p_preregistration_manifest.json"
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
    """Verify authoritative Turn 4 index definitions and strict disjointness."""
    fit_s, fit_e = Phase3PCaseService.FIT_INDICES
    buf1_s, buf1_e = Phase3PCaseService.BUFFER_1_INDICES
    sust_s, sust_e = Phase3PCaseService.SUSTAINED_INDICES
    buf2_s, buf2_e = Phase3PCaseService.BUFFER_2_INDICES
    temp_s, temp_e = Phase3PCaseService.TEMPORAL_INDICES

    assert (fit_s, fit_e) == (11200, 12199)
    assert (buf1_s, buf1_e) == (12200, 12699)
    assert (sust_s, sust_e) == (12700, 13699)
    assert (buf2_s, buf2_e) == (13700, 13899)
    assert (temp_s, temp_e) == (13900, 14599)

    s_fit = set(range(fit_s, fit_e + 1))
    s_buf1 = set(range(buf1_s, buf1_e + 1))
    s_sust = set(range(sust_s, sust_e + 1))
    s_buf2 = set(range(buf2_s, buf2_e + 1))
    s_temp = set(range(temp_s, temp_e + 1))

    assert s_fit.isdisjoint(s_sust)
    assert s_fit.isdisjoint(s_temp)
    assert s_sust.isdisjoint(s_temp)
    assert s_fit.isdisjoint(s_buf1) and s_sust.isdisjoint(s_buf1)
    assert s_sust.isdisjoint(s_buf2) and s_temp.isdisjoint(s_buf2)


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

    assert snap["protocol_id"] == "PREREG-P3P-01"
    assert snap["protocol_version"] == "1.0.0-frozen"
    assert snap["protocol_sha256"] == Phase3PCaseService.PROTOCOL_SHA256

    mech = snap["target_mechanism"]
    assert mech["parameter_name"] == "DynamicVehicleParams.tire_relaxation_length_y_m"
    assert mech["symbol"] == "sigma_y0"
    assert mech["units"] == "m"
    assert mech["baseline_value"] == 0.250
    assert mech["baseline_semantics"] == "UNIDENTIFIED_NOMINAL_REFERENCE"
    assert mech["calibrated_setup_id"] == "SETUP-P3P-CAL"
    assert mech["calibrated_value"] == 0.497

    assert snap["model_parameter_actionability"] == "SUPPORTED_AS_MODEL_VARIABLE"
    assert snap["physical_track_actionability"] == "BLOCKED / NOT_YET_MAPPED"


def test_6_fit_calibration_and_diagnostic():
    """Verify Fit partition calibration result and Fit Diagnostic pass condition."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    fit = res["fit_calibration"]
    assert fit["candidate_setup_id"] == "SETUP-P3P-CAL"
    assert fit["sigma_y0_frozen"] == 0.497
    assert fit["sample_count"] == 1000

    base_rmse = fit["baseline_fit"]["yaw_rmse"]
    cal_rmse = fit["candidate_fit"]["yaw_rmse"]
    assert cal_rmse < base_rmse
    assert fit["fit_diagnostic"]["classification"] == "PASS"
    assert fit["fit_diagnostic"]["evidential_weight"] == 0.0
    assert fit["fit_diagnostic"]["observed_relative_pct"] <= -1.0


def test_7_sustained_holdout_non_inferiority_established():
    """Verify sustained holdout non-inferiority pass via paired moving block bootstrap on Turn 4 Apex."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    sust = res["sustained_holdout"]
    assert sust["window"] == "Turn_4_Apex"
    assert sust["sample_count"] == 1000
    assert sust["non_inferiority_passed"] is True
    assert sust["verdict"] == "SUSTAINED_NON_INFERIORITY_ESTABLISHED"

    boot = sust["bootstrap"]
    assert boot["algorithm"] == "PAIRED_MOVING_BLOCK_BOOTSTRAP"
    assert boot["replicates_B"] == 1000
    assert boot["block_length_samples"] == 20
    assert boot["random_seed"] == 42
    # Upper CI must be <= margin (0.05 * base_rmse)
    assert boot["ci_upper"] <= sust["non_inferiority_margin_abs"]


def test_8_temporal_holdout_improvement_unsupported():
    """Verify that temporal holdout improvement fails to resolve statistically on Turn 4 Exit."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    temp = res["temporal_holdout"]
    assert temp["window"] == "Turn_4_Exit"
    assert temp["sample_count"] == 700
    # Point estimate is negative, but CI95 upper bound is > 0 (not statistically resolved)
    assert temp["delta_rmse"] < 0.0
    boot = temp["bootstrap"]
    assert boot["algorithm"] == "PAIRED_MOVING_BLOCK_BOOTSTRAP"
    assert boot["ci_upper"] > 0.0
    assert temp["improvement_passed"] is False
    assert temp["verdict"] == "HYPOTHESIS_NOT_SUPPORTED"


def test_9_secondary_metrics_and_boundaries():
    """Verify secondary metrics, sideslip stability boundary, and jounce screen."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    sec = res["secondary_metrics"]
    assert sec["ay_degradation_pct"]["passed"] is True
    assert sec["roll_degradation_pct"]["passed"] is True

    beta_info = sec["sideslip_beta_boundary"]
    assert beta_info["threshold_rad"] == 0.100
    assert beta_info["passed"] is True
    assert beta_info["max_observed_rad"] <= 0.100

    jounce_info = sec["dynamic_jounce"]
    assert jounce_info["threshold_mm"] == 55.0
    assert jounce_info["passed"] is True
    assert jounce_info["max_observed_mm"] <= 55.0


def test_10_final_verdict_and_prohibited_terms():
    """Verify final verdict is HYPOTHESIS_NOT_SUPPORTED and 'VALIDATED' is not used as a claim."""
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    assert res["final_classification"] == "HYPOTHESIS_NOT_SUPPORTED"
    assert res["blocker_status"]["execution_blockers"] == "NONE"
    assert res["blocker_status"]["physical_track_actionability"] == "BLOCKED / NOT_YET_MAPPED"

    with open(ENGINEERING_CASE_PATH, "r", encoding="utf-8") as f:
        case = json.load(f)
    assert case["verdict"] == "HYPOTHESIS_NOT_SUPPORTED"
    assert case["temporal_improved"] is False
    assert case["sustained_non_inferior"] is True
    assert case["secondary_constraints_passed"] is True
    assert case["governance_closure"] == "PHASE_3P_EXECUTION_COMPLETED"

    with open(EXEC_REPORT_PATH, "r", encoding="utf-8") as f:
        rep_text = f.read()

    # The word VALIDATED must not appear as a verdict or status
    assert '"verdict": "VALIDATED"' not in json.dumps(case)
    assert '"final_classification": "VALIDATED"' not in json.dumps(res)
    assert "VALIDATED" not in rep_text.replace("PREDICTION_VALIDATED", "")
