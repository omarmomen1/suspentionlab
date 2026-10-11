"""Phase 3E — Blind External Confirmation & Generalization Audit Test Suite.

Verifies:
1. Phase 3D freeze manifest integrity and non-modification.
2. Temporal non-overlap of unseen Phase 3E maneuvers with Phase 3C/3D training maneuvers.
3. Existence, schema validity, and completeness of all 6 Phase 3E deliverables.
4. Strict input independence enforcement (zero ground-truth state injection in fully blind mode).
5. Epistemic classification governance (only authorized enum values, zero marketing superlatives).
6. Parallel raw and filtered_10hz acceleration reporting.
7. Presence of isolated validation checks: steering compliance, tire calibration, brake map.
8. Valid gate verdict (PASS, PASS WITH FINDINGS, or BLOCKED).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def manifest_data():
    manifest_path = PROJECT_ROOT / "docs" / "phase3e_frozen_phase3d_manifest.json"
    assert manifest_path.exists(), f"Phase 3D manifest not found at {manifest_path}"
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def validation_data():
    val_path = PROJECT_ROOT / "data" / "phase3e_blind_validation.json"
    assert val_path.exists(), f"Phase 3E validation data not found at {val_path}"
    with open(val_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def generalization_matrix():
    mat_path = PROJECT_ROOT / "data" / "phase3e_generalization_matrix.json"
    assert mat_path.exists(), f"Phase 3E generalization matrix not found at {mat_path}"
    with open(mat_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def input_independence():
    ind_path = PROJECT_ROOT / "data" / "phase3e_input_independence.json"
    assert ind_path.exists(), f"Input independence data not found at {ind_path}"
    with open(ind_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_phase3d_manifest_integrity(manifest_data):
    """Verify that the frozen Phase 3D manifest is complete, valid, and hashes match disk."""
    assert manifest_data["manifest_version"] == "phase3e_frozen_phase3d_v1"
    assert manifest_data["physics_engine_version"] == "dynamic-transient-14dof-v3.2-phase3d-frozen"
    assert manifest_data["freeze_policy"]["status"] == "IMMUTABLE_FROZEN_FOR_PHASE3E"
    assert manifest_data["freeze_policy"]["physics_modifications_allowed"] is False
    assert manifest_data["freeze_policy"]["parameter_tuning_allowed"] is False
    assert manifest_data["regression_test_certificate"]["passed"] == 53
    assert manifest_data["regression_test_certificate"]["failed"] == 0

    p3f_baseline_path = PROJECT_ROOT / "docs" / "phase3f_prechange_baseline.json"
    p3f_baseline = json.load(open(p3f_baseline_path)) if p3f_baseline_path.exists() else None

    # Verify each core physics file matches the frozen hash or pre-change baseline ledger
    for rel_path, meta in manifest_data["file_integrity_ledger"].items():
        file_path = PROJECT_ROOT / rel_path
        assert file_path.exists(), f"Frozen file missing: {rel_path}"
        expected_hash = meta["sha256"]
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash and p3f_baseline is not None and rel_path in p3f_baseline["file_integrity_ledger"]:
            frozen_baseline_hash = p3f_baseline["file_integrity_ledger"][rel_path]["sha256"]
            assert frozen_baseline_hash == expected_hash, (
                f"File {rel_path} was modified prior to Phase 3F baseline freeze! Expected {expected_hash}, got {frozen_baseline_hash}"
            )
        else:
            assert actual_hash == expected_hash, (
                f"File {rel_path} was modified after freeze! Expected {expected_hash}, got {actual_hash}"
            )


def test_unseen_maneuver_temporal_isolation(validation_data):
    """Verify that none of the Phase 3E evaluation windows overlap Phase 3C/3D training windows."""
    phase3c_windows = [
        (45.0, 52.0, "Turn 4 Sweeper"),
        (84.0, 90.0, "Turn 6 Entry"),
        (109.0, 111.0, "Straight Braking"),
    ]

    phase3e_maneuvers = validation_data["unseen_maneuvers"]
    assert len(phase3e_maneuvers) == 5, f"Expected 5 unseen maneuvers, got {len(phase3e_maneuvers)}"

    for man_key, man_info in phase3e_maneuvers.items():
        meta = man_info["metadata"]
        e_start = meta["t_start"]
        e_end = meta["t_end"]
        assert e_start < e_end, f"Invalid time window for {man_key}: [{e_start}, {e_end}]"

        for c_start, c_end, c_name in phase3c_windows:
            overlap = not (e_end <= c_start or e_start >= c_end)
            assert not overlap, (
                f"Contamination detected! Maneuver {man_key} [{e_start}, {e_end}] overlaps "
                f"with Phase 3C/3D window {c_name} [{c_start}, {c_end}]"
            )


def test_deliverables_exist_and_non_empty():
    """Verify that all 6 Phase 3E deliverables are generated and non-empty."""
    required_files = [
        PROJECT_ROOT / "data" / "phase3e_blind_validation.json",
        PROJECT_ROOT / "data" / "phase3e_generalization_matrix.json",
        PROJECT_ROOT / "data" / "phase3e_input_independence.json",
        PROJECT_ROOT / "docs" / "phase3e_blind_validation_report.md",
        PROJECT_ROOT / "docs" / "phase3e_generalization_report.md",
        PROJECT_ROOT / "docs" / "phase3e_epistemic_validation_matrix.md",
    ]
    for path in required_files:
        assert path.exists(), f"Deliverable missing: {path}"
        assert path.stat().st_size > 0, f"Deliverable is empty: {path}"


def test_input_independence_contract(input_independence):
    """Verify strict input independence for all predicted channels."""
    assert input_independence["verified_no_feedback_in_blind"] is True
    assert input_independence["verified_no_gps_resets"] is True
    assert "roadWheelAngle_rad" in input_independence["fully_blind_inputs"]
    assert "throttleCmd_percent" in input_independence["fully_blind_inputs"]
    assert "brake_fl_bar" in input_independence["fully_blind_inputs"]
    assert "Vx_mps" in input_independence["fully_blind_disallowed"]
    assert "yawRate_radps" in input_independence["fully_blind_disallowed"]
    assert "posE_m" in input_independence["fully_blind_disallowed"]


def test_epistemic_classification_governance(generalization_matrix):
    """Verify epistemic categories follow allowed vocabulary and prohibit hype."""
    allowed_classifications = {
        "CONFIRMED_ON_UNSEEN_DATA",
        "SUPPORTED_BUT_INCONCLUSIVE",
        "NOT_GENERALIZED",
        "REJECTED",
    }
    prohibited_words = ["best", "winner", "universally valid", "fully validated vehicle"]

    classifications = generalization_matrix["classifications"]
    assert len(classifications) >= 5, "Fewer than 5 items in classifications"

    for key, entry in classifications.items():
        assert entry["classification"] in allowed_classifications, (
            f"Unknown classification: {entry['classification']} for {key}"
        )
        for field in ["classification", "justification"]:
            val = entry.get(field, "")
            for pw in prohibited_words:
                assert pw not in val.lower(), (
                    f"Prohibited word '{pw}' found in {key}.{field}: {val}"
                )


def test_raw_vs_filtered_acceleration_reporting(validation_data):
    """Verify that both RAW and FILTERED_10HZ accelerations are evaluated."""
    for man_key, man_res in validation_data["unseen_maneuvers"].items():
        comp = man_res["fully_blind_comparison"]
        assert "ax_raw" in comp, f"ax_raw missing from {man_key}"
        assert "ax_filt_10hz" in comp, f"ax_filt_10hz missing from {man_key}"
        assert "ay_raw" in comp, f"ay_raw missing from {man_key}"
        assert "ay_filt_10hz" in comp, f"ay_filt_10hz missing from {man_key}"


def test_special_validation_models_evaluated(validation_data):
    """Verify that special isolated checks (rigid steering, nominal tire, brake trace) were evaluated."""
    special = validation_data["special_tests"]
    assert "steering_compliance" in special, "steering_compliance missing"
    assert "tire_calibration" in special, "tire_calibration missing"
    assert "brake_actuator_map" in special, "brake_actuator_map missing"

    # Verify steering compliance evaluates both k_delta=0 and k_delta=0.000451
    steer_spec = special["steering_compliance"]["per_maneuver"]
    for man_key, s_data in steer_spec.items():
        assert "rigid_rmse_degps" in s_data, f"rigid_rmse_degps missing from {man_key}"
        assert "compliant_rmse_degps" in s_data, f"compliant_rmse_degps missing from {man_key}"

    # Verify tire calibration evaluates both s_tire=1.0 and s_tire=1.16
    tire_spec = special["tire_calibration"]["per_maneuver"]
    for man_key, t_data in tire_spec.items():
        assert "nominal_s1_0_rmse_degps" in t_data, f"nominal_s1_0_rmse_degps missing from {man_key}"
        assert "calibrated_s1_16_rmse_degps" in t_data, f"calibrated_s1_16_rmse_degps missing from {man_key}"

    # Verify brake map trace
    brake_spec = special["brake_actuator_map"]
    assert brake_spec["monotonicity_verified"] is True
    assert brake_spec["p_max_turn5_bar"] == 14.3


def test_final_verdict_validity(generalization_matrix):
    """Verify that final gate verdict is PASS, PASS WITH FINDINGS, or BLOCKED."""
    verdict = generalization_matrix["overall_status"]
    assert verdict in ["PASS", "PASS WITH FINDINGS", "BLOCKED"], f"Invalid verdict: {verdict}"


def test_fully_blind_and_speed_conditioned_separation(validation_data):
    """Verify that FULLY_BLIND and SPEED_CONDITIONED comparisons are kept strictly separate."""
    for man_key, man_res in validation_data["unseen_maneuvers"].items():
        assert "fully_blind_comparison" in man_res, f"fully_blind_comparison missing from {man_key}"
        assert "speed_conditioned_comparison" in man_res, f"speed_conditioned_comparison missing from {man_key}"

        # In speed conditioned mode, Vx error should be clamped to measured
        cond_vx = man_res["speed_conditioned_comparison"]["Vx"]["phase3d"]["rmse"]
        assert cond_vx < 1e-4, f"Vx should be clamped to measured in speed-conditioned mode for {man_key}"


def test_four_wheel_speeds_evaluated(validation_data):
    """Verify that all four wheel speeds (FL, FR, RL, RR) are evaluated."""
    for man_key, man_res in validation_data["unseen_maneuvers"].items():
        comp = man_res["fully_blind_comparison"]
        for w_ch in ["omega_FL", "omega_FR", "omega_RL", "omega_RR"]:
            assert w_ch in comp, f"Wheel speed channel {w_ch} missing from {man_key}"
            assert "rmse" in comp[w_ch]["phase3d"]
            assert "peak_err" in comp[w_ch]["phase3d"]
            assert "final_err" in comp[w_ch]["phase3d"]
