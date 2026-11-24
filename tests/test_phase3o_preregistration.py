"""Phase 3O Pre-Registration Governance & Immutability Test Suite (v1.0.1-FROZEN).
Verifies the cryptographic protocol freeze, physics hashes, dataset provenance,
exact partition disjointness, and solver/statistical invariants.
DOES NOT execute the Phase 3O optimization or unseal holdout partitions.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

MANIFEST_PATH = Path("docs/phase3o_preregistration_manifest.json")
MANIFEST_V100_PATH = Path("docs/phase3o_preregistration_manifest_v1_0_0.json")
EXPECTED_PROTOCOL_HASH_V101 = "26e30aa08800f4756b7f219f736daddfd481ece9f5a2831469602e959631b88c"
EXPECTED_HISTORICAL_HASH_V100 = "1704bbf7213bc85064b6e60b2a6745589b3b01a6d3a59b2b2cd9630f99e81100"

def load_manifest() -> dict:
    assert MANIFEST_PATH.exists(), f"Pre-registration manifest missing at {MANIFEST_PATH}"
    content = MANIFEST_PATH.read_text(encoding="utf-8")
    return json.loads(content)

def test_protocol_hash_deterministic():
    """Verify cryptographic SHA-256 integrity of the v1.0.1-frozen pre-registration protocol."""
    actual_hash_bytes = hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    actual_hash_text = hashlib.sha256(MANIFEST_PATH.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    assert actual_hash_bytes == actual_hash_text, "Line ending divergence in manifest!"
    assert actual_hash_bytes == EXPECTED_PROTOCOL_HASH_V101, (
        f"Pre-registration protocol SHA-256 mutation detected: {actual_hash_bytes} != {EXPECTED_PROTOCOL_HASH_V101}"
    )

def test_historical_revision_preserved():
    """Verify that historical revision v1.0.0-frozen is preserved and recorded in lineage."""
    assert MANIFEST_V100_PATH.exists(), f"Historical v1.0.0 manifest missing at {MANIFEST_V100_PATH}"
    v100_text_hash = hashlib.sha256(MANIFEST_V100_PATH.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    assert v100_text_hash == EXPECTED_HISTORICAL_HASH_V100, (
        f"Historical v1.0.0 hash corrupted: {v100_text_hash} != {EXPECTED_HISTORICAL_HASH_V100}"
    )
    
    manifest = load_manifest()
    assert manifest["protocol_version"] == "1.0.1-frozen"
    history = manifest["revision_history"]
    assert len(history) >= 1
    assert history[0]["protocol_version"] == "1.0.0-frozen"
    assert history[0]["sha256"] == EXPECTED_HISTORICAL_HASH_V100
    assert history[0]["status"] == "SUPERSEDED_HISTORICAL_REVISION"

def test_protected_physics_hashes_unchanged():
    """Verify that all protected production physics files match their frozen SHA-256 checksums."""
    manifest = load_manifest()
    physics_manifest = manifest["protected_physics_manifest"]
    base_dir = Path("src/suspensionlab/physics")

    for filename, expected_sha in physics_manifest.items():
        file_path = base_dir / filename
        assert file_path.exists(), f"Protected physics file not found: {file_path}"
        actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest().lower()
        assert actual_sha == expected_sha.lower(), (
            f"Physics hash violation in {filename}: {actual_sha} != {expected_sha}"
        )

def test_dataset_sha_unchanged():
    """Verify that the authentic telemetry dataset matches its certified SHA-256 digest."""
    manifest = load_manifest()
    ds_info = manifest["dataset_provenance"]
    ds_path = Path(ds_info["file_path"])
    assert ds_path.exists(), f"Dataset file not found: {ds_path}"
    actual_sha = hashlib.sha256(ds_path.read_bytes()).hexdigest().lower()
    assert actual_sha == ds_info["sha256"].lower(), (
        f"Dataset hash violation: {actual_sha} != {ds_info['sha256']}"
    )

def test_authoritative_sample_indices_and_disjointness():
    """Verify authoritative sample indices, half-open interval derivation, and zero sample overlap."""
    manifest = load_manifest()
    parts = manifest["data_partitions"]
    ds_path = Path(manifest["dataset_provenance"]["file_path"])
    df = pd.read_csv(ds_path, comment="#")

    assert "authoritative partition definition" in parts["authoritative_definition"].lower()

    fit = parts["fit_partition"]
    temp = parts["temporal_holdout_partition"]
    cross = parts["cross_maneuver_holdout_partition"]
    buf = parts["buffers"]

    # Authoritative index ranges
    idx_fit = list(range(fit["start_sample_index"], fit["end_sample_index"] + 1))
    idx_temp = list(range(temp["start_sample_index"], temp["end_sample_index"] + 1))
    idx_cross = list(range(cross["start_sample_index"], cross["end_sample_index"] + 1))

    assert len(idx_fit) == fit["sample_count"] == 960
    assert len(idx_temp) == temp["sample_count"] == 839
    assert len(idx_cross) == cross["sample_count"] == 1200

    assert fit["start_sample_index"] == 2800 and fit["end_sample_index"] == 3759
    assert temp["start_sample_index"] == 3761 and temp["end_sample_index"] == 4599
    assert cross["start_sample_index"] == 4800 and cross["end_sample_index"] == 5999

    # Buffers
    assert buf["fit_temporal_buffer"]["sample_index"] == 3760
    assert buf["temporal_cross_buffer"]["start_sample_index"] == 4600
    assert buf["temporal_cross_buffer"]["end_sample_index"] == 4799

    # Half-open time boundaries derived from indices
    t_fit_start = df.loc[2800, "t_s"]
    t_fit_end = df.loc[3759, "t_s"]
    t_buf1 = df.loc[3760, "t_s"]
    t_temp_start = df.loc[3761, "t_s"]
    t_temp_end = df.loc[4599, "t_s"]
    t_buf2_start = df.loc[4600, "t_s"]
    t_buf2_end = df.loc[4799, "t_s"]
    t_cross_start = df.loc[4800, "t_s"]
    t_cross_end = df.loc[5999, "t_s"]

    assert 14.000 <= t_fit_start < 14.005
    assert t_fit_end < 18.800
    assert 18.800 <= t_buf1 < 18.805
    assert 18.805 <= t_temp_start < 18.810
    assert t_temp_end < 23.000
    assert 23.000 <= t_buf2_start < 23.005
    assert t_buf2_end < 24.000
    assert 24.000 <= t_cross_start < 24.005
    assert t_cross_end < 30.000

    # Strict pairwise disjointness
    s_fit = set(idx_fit)
    s_temp = set(idx_temp)
    s_cross = set(idx_cross)
    s_buf1 = {3760}
    s_buf2 = set(range(4600, 4800))

    assert s_fit.isdisjoint(s_temp), "Data leakage: Fit and Temporal partitions overlap!"
    assert s_fit.isdisjoint(s_cross), "Data leakage: Fit and Cross partitions overlap!"
    assert s_temp.isdisjoint(s_cross), "Data leakage: Temporal and Cross partitions overlap!"
    assert s_fit.isdisjoint(s_buf1) and s_temp.isdisjoint(s_buf1)
    assert s_temp.isdisjoint(s_buf2) and s_cross.isdisjoint(s_buf2)

def test_holdout_access_firewall_policy():
    """Verify that the pre-registration enforces a sealed holdout firewall."""
    manifest = load_manifest()
    parts = manifest["data_partitions"]
    assert parts["fit_partition"]["access_policy"] == "PERMITTED_DURING_CALIBRATION"
    assert parts["temporal_holdout_partition"]["access_policy"] == "SEALED_UNTIL_CANDIDATE_FROZEN"
    assert parts["cross_maneuver_holdout_partition"]["access_policy"] == "SEALED_UNTIL_CANDIDATE_FROZEN"
    
    cand_gen = manifest["candidate_generation_algorithm"]
    assert cand_gen["optional_sensitivity_grid"]["holdout_evaluation_permitted"] is False
    assert cand_gen["optional_sensitivity_grid"]["holdout_evaluation_rule"] == "BASELINE vs FROZEN SETUP-P3O-CAL ONLY"

def test_candidate_generation_configuration_immutable():
    """Verify candidate generation protocol invariants and exploratory demarcation."""
    manifest = load_manifest()
    cand_gen = manifest["candidate_generation_algorithm"]
    
    # Exploratory demarcation
    exp = cand_gen["exploratory_preliminary_estimate"]
    assert exp["label"] == "EXPLORATORY_FIT_ESTIMATE"
    assert exp["s_tire_approx"] == 0.880
    
    # Formal bounded optimization specification
    proto = cand_gen["formal_generation_protocol"]
    assert proto["method"] == "BOUNDED_1D_OPTIMIZATION"
    assert proto["partition"] == "FIT_PARTITION_ONLY"
    assert proto["search_bounds"] == [0.70, 1.30]
    assert proto["tolerance_xatol"] == 0.005
    assert proto["max_iterations"] == 25
    assert proto["numerical_rounding_precision"] == 3
    assert proto["failure_behavior"] == "HALT_FAIL_CLOSED_WITHOUT_UNSEALING_HOLDOUTS"

def test_solver_dt_invariant():
    """Verify execution contract: fixed-step RK4 at dt=0.001 s with 5 substeps per 200 Hz sample."""
    manifest = load_manifest()
    solver = manifest["solver_contract"]
    assert solver["integrator_algorithm"] == "Fixed-step 4th-Order Runge-Kutta (RK4)"
    assert solver["canonical_timestep_s"] == 0.001
    assert solver["telemetry_sampling_dt_s"] == 0.005
    assert solver["mandatory_substeps_per_sample"] == 5
    assert solver["silent_timestep_substitution_prohibited"] is True

def test_bootstrap_configuration_and_rmse_target():
    """Verify statistical contract: PAIRED MOVING BLOCK BOOTSTRAP targeting per-replicate Delta_RMSE."""
    manifest = load_manifest()
    rules = manifest["metrics_and_governance_rules"]
    boot = rules["temporal_non_inferiority"]["bootstrap_configuration"]
    
    # Terminology parity
    assert boot["algorithm"] == "PAIRED_MOVING_BLOCK_BOOTSTRAP"
    assert boot["replicates_B"] == 1000
    assert boot["block_length_samples"] == 20
    assert boot["block_duration_ms"] == 100.0
    assert boot["sampling_rate_hz"] == 200.0
    assert boot["random_seed"] == 42
    assert boot["confidence_level"] == 0.95

    # Target specification: Delta_RMSE per replicate (not MSE difference)
    assert boot["bootstrap_replicate_target"] == "Delta_RMSE^(b) = RMSE_candidate^(b) - RMSE_baseline^(b)"
    assert "RMSE_cand^(b) - RMSE_base^(b)" in boot["replicate_formula"]
    assert boot["confidence_interval_construction"] == "CI_95 = [percentile_2.5(Delta_RMSE^*), percentile_97.5(Delta_RMSE^*)]"

    # Governance policy
    assert rules["temporal_non_inferiority"]["policy"] == (
        "Only bootstrap-derived confidence intervals on Delta_RMSE are permitted. Zero heuristic confidence intervals are permitted."
    )
    assert rules["cross_maneuver_generalization"]["bootstrap_target"] == (
        "Delta_RMSE^(b) = RMSE_candidate^(b) - RMSE_baseline^(b) on Turn 2 Carousel"
    )

def test_complete_sideslip_gate():
    """Verify complete authoritative sideslip beta stability boundary and failure status."""
    manifest = load_manifest()
    beta_info = manifest["metrics_and_governance_rules"]["secondary_metrics"]["sideslip_angle"]
    
    assert beta_info["metric"] == "Peak absolute sideslip |beta|"
    assert beta_info["channel"] == "slipAngle_rad"
    assert beta_info["classification"] == "SECONDARY_STABILITY_INDICATOR"
    assert beta_info["is_direct_transducer"] is False
    assert beta_info["provenance"] == "slipAngle_rad = arctan2(Vy_mps, Vx_mps) derived from integrated GNSS/INS state vector"
    assert beta_info["threshold_rad"] == 0.10
    assert beta_info["threshold_deg"] == pytest.approx(5.7296, rel=1e-4)
    assert beta_info["failure_status"] == "REJECT_DUE_TO_SIDESLIP_STABILITY_BOUNDARY"
    assert beta_info["nature_of_constraint"] == "Engineering stability boundary, not a statistical confidence threshold"

def test_blocker_status_bifurcation():
    """Verify clear demarcation between execution blockers and physical track actionability."""
    manifest = load_manifest()
    blockers = manifest["blocker_status"]
    
    assert blockers["execution_blockers"] == "NONE"
    assert blockers["physical_track_actionability"] == "BLOCKED / NOT_YET_MAPPED"
    assert "no validated mapping: s_tire -> specific tire pressure" in blockers["actionability_rationale"]

def test_physical_actionability_status_not_yet_mapped():
    """Verify strict demarcation of model actionability vs physical track actionability."""
    manifest = load_manifest()
    mech = manifest["target_mechanism"]
    assert mech["model_parameter_actionability"] == "SUPPORTED_AS_A_MODEL_VARIABLE"
    assert mech["physical_track_actionability"] == "NOT_YET_MAPPED"
    assert "VALIDATED" in manifest["prohibited_terminology"]
    assert "MODEL_PARAMETER_DECISION_SUPPORTED" in manifest["allowed_final_outcomes"]
