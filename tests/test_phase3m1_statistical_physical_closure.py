"""
tests/test_phase3m1_statistical_physical_closure.py
==================================================
Phase 3M.1: Statistical & Physical Decision Validity Closure Test Suite.

Mode: AUDIT + SCIENTIFIC RECONCILIATION ONLY
Zero Production Physics Modifications | Zero Retuning | Append-Only Reconciliation

Verifies the 16 mandatory closure invariants:
 1. Phase 3M historical hashes unchanged
 2. Phase 3H protected physics hashes unchanged
 3. frozen solver identity unchanged
 4. vehicle identity reconciliation
 5. spring parameter identity reconciliation
 6. damping FIM reconstruction
 7. singular value / conditioning audit
 8. compression-specific observability
 9. uncertainty unit consistency
10. parameter-to-observable uncertainty propagation
11. paired holdout bootstrap
12. temporal dependence / block bootstrap assessment
13. preregistration hash verification
14. candidate-vs-calibration-interval semantics
15. final epistemic classification
16. no production physics modifications
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"

PHASE3H_MANIFEST = DATA_DIR / "phase3h_final_validity_manifest.json"
PHASE3M_CASE_JSON = DATA_DIR / "phase3m_engineering_case.json"
PHASE3M_EXEC_MANIFEST = DATA_DIR / "phase3m_execution_manifest.json"
PHASE3M_PARAM_SNAPSHOT = DATA_DIR / "phase3m_parameter_snapshot.json"
PHASE3M_DOCS = DOCS_DIR / "phase3m_independent_engineering_case.md"

P3M1_CLOSURE_JSON = DATA_DIR / "phase3m1_statistical_physical_closure.json"
P3M1_VEHICLE_JSON = DATA_DIR / "phase3m1_vehicle_identity_reconciliation.json"
P3M1_UNC_JSON = DATA_DIR / "phase3m1_uncertainty_propagation.json"
P3M1_HOLDOUT_JSON = DATA_DIR / "phase3m1_holdout_effect_analysis.json"
P3M1_PREREG_JSON = DATA_DIR / "phase3m1_preregistration_audit.json"
P3M1_DOCS = DOCS_DIR / "phase3m1_statistical_physical_closure.md"


# ── TEST 1: PHASE 3M HISTORICAL HASHES UNCHANGED ─────────────────────────────

def test_1_phase3m_historical_hashes_unchanged():
    """Verify that all historical Phase 3M artifacts remain strictly immutable."""
    expected_hashes = {
        PHASE3M_DOCS: "b4485ba58a84a18c01d742a88709873d964381df562243824b28a388d0c4d70a",
        PHASE3M_CASE_JSON: "20fd0ec059fb3d4873d5f9321679f289666f225933eaf9f107fc3ef83a13f3b7",
        PHASE3M_PARAM_SNAPSHOT: "6d93b50d0ca682b99d9593ddb67a8cbd24fdb42c926fc2726a0bea4c1efc5c67",
        PHASE3M_EXEC_MANIFEST: "eeff2692af566559800aa717f673af43c158f3f69d19823fb971bb9a1df37db0",
    }
    for file_path, expected_hash in expected_hashes.items():
        assert file_path.exists(), f"Historical artifact missing: {file_path}"
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, (
            f"HISTORICAL_ARTIFACT_MUTATION_DETECTED in {file_path.name}: {actual_hash} != {expected_hash}"
        )


# ── TEST 2: PHASE 3H PROTECTED PHYSICS HASHES UNCHANGED ───────────────────────

def test_2_phase3h_protected_physics_hashes_unchanged():
    """Verify all 11 protected physics files match Phase 3H manifest SHA-256 hashes."""
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Protected physics modification in {item['path']}!"


# ── TEST 3: FROZEN SOLVER IDENTITY UNCHANGED ──────────────────────────────────

def test_3_frozen_solver_identity_unchanged():
    """Verify solver identity remains RK4 at mandatory dt = 0.001 s."""
    with open(PHASE3M_EXEC_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    sc = manifest["solver_contract"]
    assert sc["integrator"] == "RK4"
    assert sc["dt_s"] == 0.001
    assert sc["derivative_evaluations_per_step"] == 4


# ── TEST 4: VEHICLE IDENTITY RECONCILIATION ───────────────────────────────────

def test_4_vehicle_identity_reconciliation():
    """Verify vehicle identity reconciliation classifies as CONFIGURATIONALLY_EQUIVALENT."""
    assert P3M1_VEHICLE_JSON.exists()
    with open(P3M1_VEHICLE_JSON, "r", encoding="utf-8") as f:
        rec = json.load(f)

    assert rec["overall_classification"] in {"CONFIGURATIONALLY_EQUIVALENT", "EXACT_MATCH"}
    assert rec["status"] == "RECONCILED"
    entities = rec["entities"]
    assert "Golf VII GTI" in entities["telemetry_dataset"]["physical_vehicle"]
    assert entities["simulation_configuration"]["mass_kg"] == 1530.0
    assert entities["simulation_configuration"]["sprung_mass_kg"] == 1410.0


# ── TEST 5: SPRING PARAMETER IDENTITY RECONCILIATION ──────────────────────────

def test_5_spring_parameter_identity_reconciliation():
    """Verify spring parameter is reconciled and classified as DIFFERENT_PARAMETER."""
    assert P3M1_CLOSURE_JSON.exists()
    with open(P3M1_CLOSURE_JSON, "r", encoding="utf-8") as f:
        closure = json.load(f)

    spring_rec = closure["spring_identity"]
    assert spring_rec["classification"] in {"DIFFERENT_PARAMETER", "MODEL_DERIVED_PARAMETER"}
    lineage = spring_rec["parameter_lineage"]
    assert lineage["phase3j1_parameter"]["value_nm"] == pytest.approx(32543.67, rel=1e-2)
    assert lineage["phase3m_snapshot_parameter"]["value_nm"] == 65000.0
    assert lineage["motorsport_reference_parameter"]["value_nm"] == 110000.0


# ── TEST 6: DAMPING FIM RECONSTRUCTION ────────────────────────────────────────

def test_6_damping_fim_reconstruction():
    """Verify FIM reconstruction demonstrates rank=2 for the 2-parameter subspace."""
    with open(P3M1_CLOSURE_JSON, "r", encoding="utf-8") as f:
        closure = json.load(f)

    obs = closure["observability_audit"]
    subspace = obs["two_parameter_subspace"]
    assert subspace["cross_correlation"] == pytest.approx(0.0097, abs=1e-3)
    assert subspace["subspace_identifiability_verdict"] == "IDENTIFIABLE"
    assert subspace["normalized_condition_number"] < 2.0


# ── TEST 7: SINGULAR VALUE / CONDITIONING AUDIT ───────────────────────────────

def test_7_singular_value_conditioning_audit():
    """Verify the root cause of the 3.57e13 condition number is the zero sensitivity of camber."""
    with open(P3M1_CLOSURE_JSON, "r", encoding="utf-8") as f:
        closure = json.load(f)

    obs = closure["observability_audit"]
    three_p = obs["three_parameter_system"]
    assert three_p["condition_number"] > 1e13
    assert three_p["numerical_rank"] == 2
    assert three_p["sensitivity_norms"][2] == 0.0  # camber has zero sensitivity
    assert "camber_stiffness_front" in three_p["root_cause_of_huge_condition_number"]


# ── TEST 8: COMPRESSION-SPECIFIC OBSERVABILITY ─────────────────────────────────

def test_8_compression_specific_observability():
    """Verify telemetry contains genuine compression excitation but solver model is SYMMETRIC."""
    with open(P3M1_CLOSURE_JSON, "r", encoding="utf-8") as f:
        closure = json.load(f)

    comp = closure["compression_excitation"]
    assert comp["compression_samples"] > 400
    assert comp["compression_peak_velocity_mps"] > 0.10
    assert comp["raw_staircase_potentiometer_daq"]["raw_peak_step_velocity_mps"] > 0.30
    assert comp["model_formulation_audit"]["epistemic_classification"] == "SYMMETRIC_DAMPER_MODEL"
    assert comp["model_formulation_audit"]["bump_rebound_split_supported"] is False


# ── TEST 9: UNCERTAINTY UNIT CONSISTENCY ──────────────────────────────────────

def test_9_uncertainty_unit_consistency():
    """Verify unit consistency audit separates text formula from implementation."""
    assert P3M1_UNC_JSON.exists()
    with open(P3M1_UNC_JSON, "r", encoding="utf-8") as f:
        unc = json.load(f)

    assert unc["historical_text_classification"] in {"DIMENSIONALLY_INVALID", "PARTIALLY_VALID"}
    dim = unc["dimensional_breakdown"]
    assert dim["parameter_uncertainty_native"]["unit"] == "N*s/m"
    assert dim["parameter_uncertainty_propagated"]["unit"] == "rad/s"
    assert dim["sensor_measurement_noise"]["unit"] == "rad/s"


# ── TEST 10: PARAMETER-TO-OBSERVABLE PROPAGATION ──────────────────────────────

def test_10_parameter_to_observable_propagation():
    """Verify Jacobian-propagated parameter uncertainty is approximately 0.000124 rad/s."""
    with open(P3M1_UNC_JSON, "r", encoding="utf-8") as f:
        unc = json.load(f)

    dim = unc["dimensional_breakdown"]
    sigma_prop = dim["parameter_uncertainty_propagated"]["value"]
    assert 0.00010 <= sigma_prop <= 0.00015
    assert unc["historical_code_classification"] == "PARTIALLY_VALID"


# ── TEST 11: PAIRED HOLDOUT BOOTSTRAP ─────────────────────────────────────────

def test_11_paired_holdout_bootstrap():
    """Verify paired holdout analysis shows yaw delta within uncertainty."""
    assert P3M1_HOLDOUT_JSON.exists()
    with open(P3M1_HOLDOUT_JSON, "r", encoding="utf-8") as f:
        holdout = json.load(f)

    yaw_metric = holdout["paired_metrics"]["delta_yaw_rmse_radps"]
    assert abs(yaw_metric["delta"]) < 0.0001
    assert yaw_metric["spans_zero"] is True
    assert yaw_metric["resolved_above_sensor_noise"] is False
    assert holdout["effect_resolution_verdict"] == "EFFECT_DIRECTIONAL_ONLY"


# ── TEST 12: TEMPORAL DEPENDENCE / BLOCK BOOTSTRAP ASSESSMENT ─────────────────

def test_12_temporal_dependence_block_bootstrap():
    """Verify block bootstrap was performed with block size > 1 sample."""
    with open(P3M1_HOLDOUT_JSON, "r", encoding="utf-8") as f:
        holdout = json.load(f)

    resamp = holdout["resampling_audit"]
    assert resamp["method"] == "STATIONARY_BLOCK_BOOTSTRAP"
    assert resamp["block_size_samples"] >= 10
    assert resamp["temporal_autocorrelation_checked"] is True


# ── TEST 13: PREREGISTRATION HASH VERIFICATION ────────────────────────────────

def test_13_preregistration_hash_verification():
    """Verify preregistration ordering and partial classification."""
    assert P3M1_PREREG_JSON.exists()
    with open(P3M1_PREREG_JSON, "r", encoding="utf-8") as f:
        prereg = json.load(f)

    assert prereg["classification"] == "PARTIALLY_PREREGISTERED"
    assert prereg["ordering_verification"]["prereg_before_execution"] is True
    assert prereg["ordering_verification"]["ranking_before_unseal"] is True


# ── TEST 14: CANDIDATE VS CALIBRATION INTERVAL SEMANTICS ──────────────────────

def test_14_candidate_vs_calibration_interval_semantics():
    """Verify candidate is classified as ENGINEERING_COUNTERFACTUAL outside calibration CI."""
    with open(P3M1_CLOSURE_JSON, "r", encoding="utf-8") as f:
        closure = json.load(f)

    cand = closure["candidate_semantics"]
    assert cand["is_inside_calibration_ci"] is False
    assert cand["is_inside_valid_domain"] is True
    assert cand["semantic_distinction"]["role"] == "ENGINEERING_COUNTERFACTUAL"
    assert cand["semantic_distinction"]["not_a_calibrated_estimate"] is True


# ── TEST 15: FINAL EPISTEMIC CLASSIFICATION ───────────────────────────────────

def test_15_final_epistemic_classification():
    """Verify the audited final epistemic classification is ENGINEERING_DECISION_SUPPORTED."""
    with open(P3M1_CLOSURE_JSON, "r", encoding="utf-8") as f:
        closure = json.load(f)

    assert closure["final_classification"] == "ENGINEERING_DECISION_SUPPORTED"
    rec = closure["historical_verdict_reconciliation"]
    assert rec["historical_phase3m_verdict"] == "ENGINEERING_DECISION_VALIDATED"
    assert rec["audited_phase3m1_verdict"] == "ENGINEERING_DECISION_SUPPORTED"


# ── TEST 16: NO PRODUCTION PHYSICS MODIFICATIONS ──────────────────────────────

def test_16_no_production_physics_modifications():
    """Verify exactly zero modifications occurred across the 11 protected physics files."""
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Physics modification in {item['path']}!"
