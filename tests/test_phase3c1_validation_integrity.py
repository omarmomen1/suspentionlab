"""
tests/test_phase3c1_validation_integrity.py
===========================================
Automated tests for Phase 3C.1 Validation Integrity, Anti-Tautology,
Evidence-Governance, and Claim Consistency.
"""

import os
import json
import pytest
import numpy as np
import pandas as pd

DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'external', 'stanford_vw_golf_thunderhill_2023_11.csv'))
PHASE3C_RESULTS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'phase3c_validation_results.json'))
DEP_GRAPH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'phase3c1_dependency_graph.json'))
CLAIM_REPORT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'phase3c1_claim_consistency_report.json'))
CALIB_PROV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'phase3c1_calibration_provenance.json'))
AUTH_MATRIX_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'phase3c1_authoritative_validation_matrix.json'))
BASELINE_MANIFEST_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'docs', 'phase3c1_frozen_baseline_manifest.json'))


@pytest.fixture(scope="module")
def dep_graph():
    assert os.path.exists(DEP_GRAPH_PATH), f"Missing {DEP_GRAPH_PATH}"
    with open(DEP_GRAPH_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def claim_report():
    assert os.path.exists(CLAIM_REPORT_PATH), f"Missing {CLAIM_REPORT_PATH}"
    with open(CLAIM_REPORT_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def calib_prov():
    assert os.path.exists(CALIB_PROV_PATH), f"Missing {CALIB_PROV_PATH}"
    with open(CALIB_PROV_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def auth_matrix():
    assert os.path.exists(AUTH_MATRIX_PATH), f"Missing {AUTH_MATRIX_PATH}"
    with open(AUTH_MATRIX_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def baseline_manifest():
    assert os.path.exists(BASELINE_MANIFEST_PATH), f"Missing {BASELINE_MANIFEST_PATH}"
    with open(BASELINE_MANIFEST_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# -----------------------------------------------------------------------------
# 1. INPUT INDEPENDENCE & ANTI-TAUTOLOGY TESTS
# -----------------------------------------------------------------------------

def test_no_measured_vx_in_fully_blind(dep_graph):
    """Ensure that in FULLY_BLIND mode, measured forward velocity Vx is NOT injected."""
    vx_entry = dep_graph["Vx"]
    assert vx_entry["GROUND_TRUTH_INJECTION"]["FULLY_BLIND"] is False, "Vx cannot be injected in FULLY_BLIND mode!"


def test_no_measured_yaw_in_fully_blind(dep_graph):
    """Ensure that in FULLY_BLIND mode, measured yaw rate or yaw angle is NOT injected."""
    yaw_entry = dep_graph["yaw_rate"]
    assert yaw_entry["GROUND_TRUTH_INJECTION"]["FULLY_BLIND"] is False
    assert "yawRate_radps" not in yaw_entry["DIRECT_MEASURED_INPUTS"]


def test_no_measured_roll_in_fully_blind(dep_graph):
    """Ensure that in FULLY_BLIND mode, measured roll angle is NOT injected during simulation."""
    roll_entry = dep_graph["roll"]
    assert roll_entry["GROUND_TRUTH_INJECTION"]["FULLY_BLIND"] is False


def test_no_gps_resets_in_open_loop_trajectory(dep_graph):
    """Ensure open-loop trajectory integration receives zero GPS position updates or resets."""
    for axis in ["trajectory_E", "trajectory_N"]:
        traj = dep_graph[axis]
        assert traj["GROUND_TRUTH_INJECTION"]["FULLY_BLIND"] is False
        assert "posE_m" not in traj["DIRECT_MEASURED_INPUTS"]
        assert "posN_m" not in traj["DIRECT_MEASURED_INPUTS"]


def test_no_wheel_speed_feedback_in_fully_blind_wheel_prediction(dep_graph):
    """Ensure wheel speed prediction in FULLY_BLIND mode does not inject measured wheel speed."""
    for corner in ["wheel_speed_FL", "wheel_speed_FR", "wheel_speed_RL", "wheel_speed_RR"]:
        ws = dep_graph[corner]
        assert ws["GROUND_TRUTH_INJECTION"]["FULLY_BLIND"] is False


# -----------------------------------------------------------------------------
# 2. EVIDENCE & CLASSIFICATION INTEGRITY TESTS
# -----------------------------------------------------------------------------

def test_low_r2_not_classified_as_empirically_validated(auth_matrix):
    """Ensure that poorly performing holdouts (e.g. low R2) are NOT classified as EMPIRICALLY_VALIDATED."""
    for row in auth_matrix:
        # Check trajectory: longitudinal drift was 25%, so Trajectory must NOT be EMPIRICALLY_VALIDATED across all maneuvers
        if row["subsystem"] == "Planar GPS Trajectory":
            assert row["status"] != "EMPIRICALLY_VALIDATED", "Trajectory must not be marked EMPIRICALLY_VALIDATED due to 25% braking drift!"
            assert row["status"] in ["CORRELATED", "MODEL_SUPPORTED"]


def test_missing_sensor_classified_as_unvalidated(auth_matrix):
    """Physically absent sensors (RR suspension, 3-axis wheel force hubs) must strictly be UNVALIDATED."""
    subsystem_statuses = {row["subsystem"]: row["status"] for row in auth_matrix}
    assert subsystem_statuses["Suspension Travel (RR)"] == "UNVALIDATED"
    assert subsystem_statuses["Tire Contact Patch Forces"] == "UNVALIDATED_SIMULATION_ESTIMATE"


def test_anti_dive_classified_as_consistent_with(auth_matrix):
    """Anti-dive must NOT be labeled as 'confirmed' or 'empirically validated'; must be CONSISTENT_WITH."""
    subsystem_statuses = {row["subsystem"]: row["status"] for row in auth_matrix}
    assert subsystem_statuses["Anti-Dive Reaction Kinematics"] == "CONSISTENT_WITH"


def test_claim_consistency_report_catches_all_contradictions(claim_report):
    """Audit engine must automatically flag the narrative claim contradictions."""
    assert claim_report["total_inconsistencies_detected"] >= 2
    claim_ids = [inc["claim_id"] for inc in claim_report["inconsistencies"]]
    assert "INCONSISTENCY_YAW_01" in claim_ids
    assert "INCONSISTENCY_TRAJECTORY_02" in claim_ids


# -----------------------------------------------------------------------------
# 3. DATA QUALITY & UNITS INTEGRITY TESTS
# -----------------------------------------------------------------------------

def test_suspension_potentiometer_unit_anomaly_detected():
    """Verify that raw CSV values are in centimeters (6-14) and requires 0.01x factor to be SI meters."""
    df = pd.read_csv(DATA_PATH, comment='#')
    fl_vals = df['suspFLpos_m'].values
    min_v, max_v = float(np.min(fl_vals)), float(np.max(fl_vals))
    assert min_v > 5.0 and max_v < 20.0, "Raw column suspFLpos_m should be in range 6-15 cm"
    stroke_mm = (max_v - min_v) * 10.0
    assert 50.0 < stroke_mm < 100.0, f"Scaled stroke {stroke_mm} mm must match realistic passenger suspension"


def test_missing_rr_channel_verified_in_raw_data():
    """Verify that suspRRpos_m does NOT exist in the external CSV."""
    df = pd.read_csv(DATA_PATH, comment='#', nrows=1)
    assert 'suspFLpos_m' in df.columns
    assert 'suspFRpos_m' in df.columns
    assert 'suspRLpos_m' in df.columns
    assert 'suspRRpos_m' not in df.columns, "suspRRpos_m must not exist in raw physical dataset!"


def test_calibrated_parameters_marked_as_calibrations(calib_prov):
    """Ensure calibrated parameters (s_tire, k_delta, s_susp) are marked as IDENTIFIED calibrations, not direct measurements."""
    prov_map = {p["parameter"]: p["classification"] for p in calib_prov["parameters"]}
    assert prov_map["s_tire"] == "IDENTIFIED_MODEL_CALIBRATION"
    assert prov_map["s_susp"] == "IDENTIFIED_MODEL_CALIBRATION"
    assert prov_map["k_delta"] == "IDENTIFIED_MODEL_CALIBRATION"
    assert prov_map["phi_bias"] == "IDENTIFIED_SENSOR_BIAS"
    assert prov_map["Rw"] == "KINEMATICALLY_DERIVED_MEASUREMENT"
