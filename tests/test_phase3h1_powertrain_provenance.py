"""Phase 3H.1 Powertrain Provenance Tests.

Verifies:
1. Synthetic engine torque relationship (T_engine ~ 360 Nm * throttle).
2. Combustion torque error envelope (CAN vs synthetic).
3. Driven axle torque deficit (36.9% under-delivery).
4. Tractive force deficit and resulting velocity drop.
5. Powertrain trace file integrity and structure.
"""

import json
from pathlib import Path
import pytest
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POWERTRAIN_TRACE_FILE = DATA_DIR / "phase3h1_powertrain_trace.json"
GEAR_AUDIT_FILE = DATA_DIR / "phase3h1_gear_ratio_audit.json"


@pytest.fixture(scope="module")
def powertrain_trace_data():
    assert POWERTRAIN_TRACE_FILE.exists(), f"Missing trace file: {POWERTRAIN_TRACE_FILE}"
    with open(POWERTRAIN_TRACE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def gear_audit_data():
    assert GEAR_AUDIT_FILE.exists(), f"Missing audit file: {GEAR_AUDIT_FILE}"
    with open(GEAR_AUDIT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_powertrain_trace_structure(powertrain_trace_data):
    """Verify trace contains expected 1800 samples and all required kinematic and dynamic channels."""
    assert powertrain_trace_data["sample_count"] == 1800
    assert len(powertrain_trace_data["records_timeline"]) == 1800

    first_rec = powertrain_trace_data["records_timeline"][0]
    expected_channels = [
        "t_s", "throttle_fraction", "engine_rpm_meas", "engine_rpm_sim",
        "transmission_ratio_meas_ratio", "transmission_ratio_sim",
        "engine_torque_meas_nm", "engine_torque_sim_nm",
        "axle_torque_meas_nm", "axle_torque_sim_nm",
        "wheel_torque_fl_sim_nm", "wheel_torque_fr_sim_nm",
        "drivetrain_efficiency"
    ]
    for ch in expected_channels:
        assert ch in first_rec, f"Missing channel {ch} in record"


def test_synthetic_engine_torque_envelope(powertrain_trace_data):
    """Verify synthetic engine torque relationship generates ~73.1 Nm average vs 86.28 Nm measured (15.3% error)."""
    analysis = powertrain_trace_data["torque_model_analysis"]
    mean_can = analysis["mean_measured_engine_torque_nm"]
    mean_sim = analysis["mean_synthetic_engine_torque_nm"]
    err_pct = analysis["engine_torque_error_pct"]

    assert 84.0 <= mean_can <= 88.0, f"Expected CAN mean torque ~86.28 Nm, got {mean_can}"
    assert 71.0 <= mean_sim <= 75.0, f"Expected synthetic mean torque ~73.1 Nm, got {mean_sim}"
    assert 14.0 <= err_pct <= 20.0, f"Expected ~15-18% combustion torque error, got {err_pct:.2f}%"


def test_driven_axle_torque_deficit(powertrain_trace_data):
    """Verify driven axle torque is under-delivered by 36.9% (161.9 Nm deficit) due to compound gear+engine discrepancy."""
    analysis = powertrain_trace_data["torque_model_analysis"]
    deficit_nm = abs(analysis["axle_torque_discrepancy_mean_nm"])
    deficit_pct = abs(analysis["axle_torque_discrepancy_pct"])

    assert 155.0 <= deficit_nm <= 175.0, f"Expected ~161.9 Nm axle deficit, got {deficit_nm}"
    assert 35.0 <= deficit_pct <= 40.0, f"Expected ~36.9% axle deficit, got {deficit_pct:.2f}%"


def test_tractive_force_deficit_and_velocity_drop(powertrain_trace_data, gear_audit_data):
    """Verify tractive force deficit is ~510-540 N, explaining ~3.0-3.2 m/s deceleration deficit over 9.0s."""
    analysis = powertrain_trace_data["torque_model_analysis"]
    deficit_nm = abs(analysis["axle_torque_discrepancy_mean_nm"])
    r_eff = gear_audit_data["signals_summary"]["mean_dynamic_rolling_radius_m"]

    tractive_force_deficit_n = deficit_nm / r_eff
    assert 490.0 <= tractive_force_deficit_n <= 560.0, f"Expected ~510-540 N tractive deficit, got {tractive_force_deficit_n}"

    # Over 9 seconds for ~1530 kg effective inertia
    time_window_s = 9.0
    approx_mass_kg = 1530.0
    predicted_delta_v = tractive_force_deficit_n * time_window_s / approx_mass_kg

    assert 2.8 <= predicted_delta_v <= 3.5, f"Expected ~3.0-3.2 m/s velocity drop, got {predicted_delta_v}"
