"""
tests/test_phase3p_preregistration.py
=====================================
SuspensionLab PRO — Phase 3P Pre-Registration Governance & Protocol Test Suite.

Enforces protocol commitments, cryptographic physics hashes, dataset provenance,
exact sample boundaries, pairwise disjointness, statistical estimator requirements,
and decision tree invariants BEFORE Phase 3P execution.

DOES NOT EXECUTE PHASE 3P OPTIMIZATION OR EVALUATE HOLDOUT PARTITIONS.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from suspensionlab.backend.services.phase3p_case_service import Phase3PCaseService


PROJECT_ROOT = Path("d:/project")
DATASET_PATH = PROJECT_ROOT / "data/external/stanford_vw_golf_thunderhill_2023_11.csv"
DATASET_EXPECTED_SHA = "489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3"

BLOCKERS_PATH = PROJECT_ROOT / "docs/phase3p_preregistration_blockers.md"
MANIFEST_PATH = PROJECT_ROOT / "docs/phase3p_preregistration_manifest.json"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dataset Integrity & Partition Boundaries
# ─────────────────────────────────────────────────────────────────────────────

def test_1_dataset_sha_uncompromised():
    """Verify that the authentic telemetry dataset matches certified SHA-256 digest."""
    assert DATASET_PATH.exists(), f"Dataset missing at {DATASET_PATH}"
    actual_sha = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest().lower()
    assert actual_sha == DATASET_EXPECTED_SHA.lower(), (
        f"Dataset hash violation: {actual_sha} != {DATASET_EXPECTED_SHA}"
    )


def test_2_exact_partition_boundaries_and_sample_counts():
    """Verify exact sample counts and zero-indexed sample boundaries for all 5 partitions."""
    meta = Phase3PCaseService.PARTITIONS_METADATA

    fit = meta["fit_partition"]
    buf1 = meta["buffer_1"]
    apex = meta["sustained_holdout_partition"]
    buf2 = meta["buffer_2"]
    exit_p = meta["temporal_holdout_partition"]

    # Boundaries and counts
    assert fit["start_sample_index"] == 11200 and fit["end_sample_index"] == 12199
    assert fit["sample_count"] == 1000

    assert buf1["start_sample_index"] == 12200 and buf1["end_sample_index"] == 12699
    assert buf1["sample_count"] == 500

    assert apex["start_sample_index"] == 12700 and apex["end_sample_index"] == 13699
    assert apex["sample_count"] == 1000

    assert buf2["start_sample_index"] == 13700 and buf2["end_sample_index"] == 13899
    assert buf2["sample_count"] == 200

    assert exit_p["start_sample_index"] == 13900 and exit_p["end_sample_index"] == 14599
    assert exit_p["sample_count"] == 700


def test_3_pairwise_disjointness_across_all_partitions():
    """Verify that all five partitions are strictly pairwise disjoint."""
    assert Phase3PCaseService.verify_partition_disjointness() is True, (
        "Data leakage: Overlap detected among telemetry partitions!"
    )


def test_4_derived_time_intervals_half_open():
    """Verify that time intervals are derived from sample indices using half-open semantics."""
    df = pd.read_csv(DATASET_PATH, comment="#")

    t_fit_start = df.loc[11200, "t_s"]
    t_fit_end = df.loc[12199, "t_s"]
    t_buf1_start = df.loc[12200, "t_s"]
    t_buf1_end = df.loc[12699, "t_s"]
    t_apex_start = df.loc[12700, "t_s"]
    t_apex_end = df.loc[13699, "t_s"]
    t_buf2_start = df.loc[13700, "t_s"]
    t_buf2_end = df.loc[13899, "t_s"]
    t_exit_start = df.loc[13900, "t_s"]
    t_exit_end = df.loc[14599, "t_s"]

    # Verify time ranges [56.001, 61.001), [61.001, 63.501), [63.501, 68.501), etc.
    assert 56.000 <= t_fit_start <= 56.005
    assert 60.995 <= t_fit_end < 61.005
    assert 61.000 <= t_buf1_start <= 61.005
    assert 63.495 <= t_buf1_end < 63.505
    assert 63.500 <= t_apex_start <= 63.505
    assert 68.495 <= t_apex_end < 68.505
    assert 68.500 <= t_buf2_start <= 68.505
    assert 69.495 <= t_buf2_end < 69.505
    assert 69.500 <= t_exit_start <= 69.505
    assert 72.995 <= t_exit_end < 73.005


# ─────────────────────────────────────────────────────────────────────────────
# 2. Exposure Classifications & Blindness Firewall
# ─────────────────────────────────────────────────────────────────────────────

def test_5_exposure_classifications_truthfulness():
    """Verify that fit partition is explicitly not labeled blind and holdouts are Category A."""
    meta = Phase3PCaseService.PARTITIONS_METADATA

    fit = meta["fit_partition"]
    assert fit["exposure_classification"] == "PREVIOUSLY_ACCESSED_NON_TIRE_ANALYSIS"
    assert fit["tire_evaluation_status"] == "NEW_FOR_TIRE_PARAMETER_EVALUATION"
    assert fit["is_blind"] is False, "Violation: Fit window must NOT be claimed as blind!"

    apex = meta["sustained_holdout_partition"]
    assert apex["exposure_classification"] == "CATEGORY_A_NEVER_ACCESSED"
    assert apex["is_blind"] is True

    exit_p = meta["temporal_holdout_partition"]
    assert exit_p["exposure_classification"] == "CATEGORY_A_NEVER_ACCESSED"
    assert exit_p["is_blind"] is True

    buf1 = meta["buffer_1"]
    assert buf1["exposure_classification"] == "EXCLUDED_BUFFER"
    assert buf1["access_policy"] == "EXCLUDED_FROM_EVALUATION"

    buf2 = meta["buffer_2"]
    assert buf2["exposure_classification"] == "EXCLUDED_BUFFER"
    assert buf2["access_policy"] == "EXCLUDED_FROM_EVALUATION"


def test_6_holdout_firewall_access_policies():
    """Verify holdout firewall policies ensure holdouts cannot enter candidate generation."""
    meta = Phase3PCaseService.PARTITIONS_METADATA
    assert meta["fit_partition"]["access_policy"] == "PERMITTED_DURING_CALIBRATION"
    assert meta["sustained_holdout_partition"]["access_policy"] == "SEALED_UNTIL_CANDIDATE_FROZEN"
    assert meta["temporal_holdout_partition"]["access_policy"] == "SEALED_UNTIL_CANDIDATE_FROZEN"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Decision Rules & Statistical Invariants
# ─────────────────────────────────────────────────────────────────────────────

def test_7_temporal_decision_requires_resolved_improvement():
    """Verify temporal test strictly requires CI upper < 0 AND delta_rmse < 0."""
    # Case 1: Resolved improvement passes
    passed, verdict = Phase3PCaseService.evaluate_temporal_decision(delta_rmse=-0.002, ci_upper=-0.0005)
    assert passed is True
    assert verdict == "TEMPORAL_IMPROVEMENT_ESTABLISHED"

    # Case 2: Merely non-inferior (CI upper > 0 even if point estimate < 0) fails
    passed, verdict = Phase3PCaseService.evaluate_temporal_decision(delta_rmse=-0.001, ci_upper=+0.0002)
    assert passed is False
    assert verdict == "HYPOTHESIS_NOT_SUPPORTED"

    # Case 3: Point estimate positive fails
    passed, verdict = Phase3PCaseService.evaluate_temporal_decision(delta_rmse=+0.001, ci_upper=+0.002)
    assert passed is False
    assert verdict == "HYPOTHESIS_NOT_SUPPORTED"


def test_8_temporal_non_inferiority_cannot_substitute_for_improvement():
    """Verify that a candidate satisfying only non-inferiority (e.g. CI upper <= +5%) fails improvement."""
    base_rmse = 0.030
    margin_5pct = 0.05 * base_rmse  # 0.0015
    # Point estimate is +0.0005 (within +5% margin, but not improving)
    passed, verdict = Phase3PCaseService.evaluate_temporal_decision(delta_rmse=0.0005, ci_upper=0.0010)
    assert passed is False
    assert verdict == "HYPOTHESIS_NOT_SUPPORTED"


def test_9_sustained_apex_requires_non_inferiority_only():
    """Verify sustained apex requires CI_upper <= +5% baseline RMSE and improvement is NOT required."""
    base_rmse = 0.040
    margin_5pct = 0.05 * base_rmse  # 0.0020

    # Case 1: Point estimate slight degradation (+0.0005), CI upper +0.0015 <= margin -> PASSES
    passed, verdict = Phase3PCaseService.evaluate_sustained_decision(
        delta_rmse=0.0005, ci_upper=0.0015, base_rmse=base_rmse
    )
    assert passed is True
    assert verdict == "SUSTAINED_NON_INFERIORITY_ESTABLISHED"

    # Case 2: CI upper exceeds margin (+0.0025 > 0.0020) -> FAILS
    passed, verdict = Phase3PCaseService.evaluate_sustained_decision(
        delta_rmse=0.0015, ci_upper=0.0025, base_rmse=base_rmse
    )
    assert passed is False
    assert verdict == "EFFECT_UNRESOLVED"


def test_10_fit_diagnostic_zero_decision_weight():
    """Verify 1% fit diagnostic is recorded as PASS/WEAK/FAILED but carries zero decision weight."""
    assert Phase3PCaseService.evaluate_fit_diagnostic(-2.5) == "PASS"
    assert Phase3PCaseService.evaluate_fit_diagnostic(-0.5) == "WEAK"
    assert Phase3PCaseService.evaluate_fit_diagnostic(+1.0) == "FAILED"

    # Regardless of fit diagnostic, if optimizer converged, holdouts improve/non-inferior, verdict is supported
    verdict_with_pass = Phase3PCaseService.evaluate_final_verdict(
        optimizer_converged=True,
        temporal_improved=True,
        sustained_non_inferior=True,
        secondary_constraints_passed=True,
        integrity_passed=True,
    )
    assert verdict_with_pass == "MODEL_PARAMETER_DECISION_SUPPORTED"

    # Optimizer divergence halts fail-closed
    verdict_diverged = Phase3PCaseService.evaluate_final_verdict(
        optimizer_converged=False,
        temporal_improved=True,
        sustained_non_inferior=True,
        secondary_constraints_passed=True,
        integrity_passed=True,
    )
    assert verdict_diverged == "ABORT_OPTIMIZER_DIVERGENCE"


def test_11_bootstrap_contract_invariants():
    """Verify bootstrap contract specifies paired moving-block bootstrap (B=1000, L=20, seed=42)."""
    boot = Phase3PCaseService.BOOTSTRAP_CONFIG
    assert boot["algorithm"] == "PAIRED_MOVING_BLOCK_BOOTSTRAP"
    assert boot["replicates_B"] == 1000
    assert boot["block_length_samples"] == 20
    assert boot["block_duration_ms"] == 100.0
    assert boot["random_seed"] == 42
    assert boot["confidence_level"] == 0.95
    assert "Delta_RMSE^(b)" in boot["target_statistic"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Secondary Metric Provenance & Physical Boundaries
# ─────────────────────────────────────────────────────────────────────────────

def test_12_secondary_metric_provenance_enforced():
    """Verify secondary metric provenance classifications prevent overclaiming."""
    sec = Phase3PCaseService.SECONDARY_METRICS_SPEC

    assert sec["yaw_rate"]["provenance"] == "MEASURED vs SIMULATED"
    assert sec["lateral_acceleration"]["provenance"] == "MEASURED vs DERIVED_FROM_SIMULATION"
    assert sec["roll_angle"]["provenance"] == "MEASURED vs SIMULATED"

    # Sideslip cannot be labeled measured
    assert sec["sideslip_angle"]["provenance"] == "SIMULATED SECONDARY STABILITY INDICATOR"
    assert sec["sideslip_angle"]["is_direct_transducer"] is False
    assert sec["sideslip_angle"]["threshold_rad"] == 0.100

    # Jounce cannot be labeled measured
    assert sec["dynamic_jounce"]["provenance"] == "MODEL-DERIVED KINEMATIC SCREEN"
    assert sec["dynamic_jounce"]["is_direct_transducer"] is False
    assert sec["dynamic_jounce"]["threshold_mm"] == 55.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Governance, Prohibited Terminology & Immutability
# ─────────────────────────────────────────────────────────────────────────────

def test_13_prohibited_terminology_enforcement():
    """Verify that 'VALIDATED' is strictly prohibited from all verdicts and outputs."""
    assert "VALIDATED" in Phase3PCaseService.PROHIBITED_TERMINOLOGY
    assert Phase3PCaseService.check_prohibited_terminology('{"verdict": "VALIDATED"}') is True
    assert Phase3PCaseService.check_prohibited_terminology('status: VALIDATED') is True
    assert Phase3PCaseService.check_prohibited_terminology('STATUS = VALIDATED') is True

    # Permitted positive verdict
    assert "MODEL_PARAMETER_DECISION_SUPPORTED" in Phase3PCaseService.ALLOWED_FINAL_OUTCOMES


def test_14_production_physics_hashes_unaltered():
    """Verify that all 5 protected production physics files match their certified SHA-256 digests."""
    hash_results = Phase3PCaseService.verify_protected_physics_hashes()
    for filename, is_match in hash_results.items():
        assert is_match is True, f"CRITICAL: Protected physics file {filename} has been modified!"


def test_15_phase3o_historical_artifacts_untouched():
    """Verify that Phase 3O pre-registration manifest and results remain strictly untouched."""
    p3o_manifest = PROJECT_ROOT / "docs/phase3o_preregistration_manifest.json"
    assert p3o_manifest.exists()
    p3o_sha = hashlib.sha256(p3o_manifest.read_bytes()).hexdigest().lower()
    expected_p3o_sha = "74cef9b8a1de6ca329e74afc7416554863142acbc0e96b7b8ffbe0a19e296831"
    assert p3o_sha == expected_p3o_sha, f"CRITICAL: Phase 3O manifest modified: {p3o_sha} != {expected_p3o_sha}"


def test_16_solver_contract_invariants():
    """Verify fixed-step RK4 solver contract at dt=0.001 s with 5 substeps per 200 Hz sample."""
    solver = Phase3PCaseService.SOLVER_CONTRACT
    assert solver["integrator_algorithm"] == "Fixed-step 4th-Order Runge-Kutta (RK4)"
    assert solver["canonical_timestep_s"] == 0.001
    assert solver["telemetry_sampling_dt_s"] == 0.005
    assert solver["mandatory_substeps_per_sample"] == 5
    assert solver["silent_timestep_substitution_prohibited"] is True


def test_17_candidate_generation_constants_authoritative():
    """Verify exact candidate generation numerical constants match ratified Option 1."""
    cfg = Phase3PCaseService.AUTHORITATIVE_CANDIDATE_GENERATION_CONFIG

    assert cfg["target_parameter"] == "DynamicVehicleParams.tire_relaxation_length_y_m"
    assert cfg["symbol"] == "sigma_y0"
    assert cfg["baseline_value"] == 0.250
    assert cfg["baseline_semantics"] == "UNIDENTIFIED_NOMINAL_REFERENCE"
    assert cfg["search_bounds"] == [0.100, 0.500]
    assert cfg["optimizer_implementation"] == "scipy.optimize.minimize_scalar"
    assert cfg["optimizer_method"] == "bounded"
    assert cfg["tolerance_xatol"] == 0.005
    assert cfg["max_iterations"] == 25
    assert cfg["numerical_rounding_precision"] == 3
    assert cfg["candidate_setup_id"] == "SETUP-P3P-CAL"
    assert cfg["baseline_setup_id"] == "SETUP-P3P-BASE"

    # pDy2 must be excluded from Phase 3P execution
    alt = cfg["alternative_mechanism_status"]
    assert alt["symbol"] == "pDy2"
    assert alt["status"] == "NEXT_CANDIDATE / ALTERNATIVE_MECHANISM"
    assert alt["phase3p_execution"] == "EXCLUDED"

    # Blocker report must record Option 1 resolution
    assert BLOCKERS_PATH.exists()
    blocker_text = BLOCKERS_PATH.read_text(encoding="utf-8")
    assert "RESOLVED" in blocker_text
    assert "Option 1" in blocker_text
    assert "0.250" in blocker_text
    assert "[0.100, 0.500]" in blocker_text


def test_18_manifest_protocol_freeze_and_schema():
    """Verify cryptographic SHA-256 integrity, canonical serialization, and protocol schema."""
    assert MANIFEST_PATH.exists(), f"Preregistration manifest missing at {MANIFEST_PATH}"

    actual_hash_bytes = hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    actual_hash_text = hashlib.sha256(MANIFEST_PATH.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    assert actual_hash_bytes == actual_hash_text, "Manifest line ending divergence!"
    assert actual_hash_bytes == Phase3PCaseService.PROTOCOL_SHA256, (
        f"Manifest protocol SHA-256 mutation detected: {actual_hash_bytes} != {Phase3PCaseService.PROTOCOL_SHA256}"
    )

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data["protocol_id"] == Phase3PCaseService.PROTOCOL_ID
    assert data["protocol_version"] == Phase3PCaseService.PROTOCOL_VERSION

    # Invariants: must NOT contain execution outcomes
    assert "candidate_fit" not in data
    assert "temporal_holdout" not in data or "candidate_rmse" not in data.get("temporal_holdout", {})
    assert "p_value" not in data
    assert "final_classification" not in data
    assert "calibrated_sigma_y0" not in data
    assert "bootstrap_output" not in data
    assert "execution_results" not in data
