"""
tests/test_phase3h_force_ledger.py
==================================
Test Suite 2 for Phase 3H: Full Longitudinal Force Ledger & Defect Reproduction.

Verifies:
  1. Complete longitudinal force ledger exposing every force term separately.
  2. Timestep count: 1800 samples covering t in [54.0, 63.0] s at dt=0.005 s.
  3. Exact numerical reproduction of Phase 3G.1 defect:
       Vx RMSE in [4.3, 4.6] m/s
       Exit speed error (meas - sim) in [+7.0, +7.6] m/s
  4. Aerodynamic drag (~637 N) and road grade (~ -563 N) decomposition.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEDGER_JSON = PROJECT_ROOT / "data" / "phase3h_longitudinal_ledger.json"
FORENSIC_MD = PROJECT_ROOT / "docs" / "phase3h_longitudinal_forensic_report.md"


@pytest.fixture
def ledger_data():
    assert LEDGER_JSON.exists(), "phase3h_longitudinal_ledger.json must exist"
    with open(LEDGER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_force_ledger_artifacts_exist():
    """Verify ledger JSON and forensic markdown report exist and are non-empty."""
    assert LEDGER_JSON.is_file()
    assert FORENSIC_MD.is_file()
    assert FORENSIC_MD.stat().st_size > 500


def test_force_ledger_completeness_and_structure(ledger_data):
    """Verify all 1800 timesteps expose every force term separately without combining."""
    records = ledger_data["records"]
    assert len(records) == 1800
    assert ledger_data["dt_s"] == 0.005

    required_keys = [
        "t_s",
        "engine_torque_sim_nm",
        "engine_torque_meas_nm",
        "transmission_ratio_sim",
        "transmission_ratio_meas",
        "differential_torque_nm",
        "fl_wheel_drive_torque_nm",
        "fr_wheel_drive_torque_nm",
        "rl_wheel_drive_torque_nm",
        "rr_wheel_drive_torque_nm",
        "tire_fx_fl_n",
        "tire_fx_fr_n",
        "tire_fx_rl_n",
        "tire_fx_rr_n",
        "tire_fx_total_n",
        "rolling_resistance_sim_n",
        "rolling_resistance_theory_n",
        "aerodynamic_drag_n",
        "road_grade_force_n",
        "total_longitudinal_force_n",
        "measured_ax_mps2",
        "simulated_ax_mps2",
        "integrated_vx_mps",
        "measured_vx_mps",
    ]

    for key in required_keys:
        assert key in records[0], f"Missing required column in force ledger: {key}"


def test_exact_defect_reproduction(ledger_data):
    """Verify exact reproduction of HighSpeed S-Curves velocity degradation."""
    stats = ledger_data["summary_statistics"]
    rmse = stats["baseline_vx_rmse_mps"]
    exit_err = stats["baseline_exit_error_mps"]

    assert 4.3 <= rmse <= 4.6, f"Vx RMSE out of reproduction bounds: {rmse} m/s"
    assert 7.0 <= exit_err <= 7.6, f"Exit error out of reproduction bounds: {exit_err} m/s"


def test_road_load_magnitudes(ledger_data):
    """Verify independent road load magnitudes match physical expectations."""
    stats = ledger_data["summary_statistics"]
    mean_drag = stats["mean_aerodynamic_drag_n"]
    mean_grade = stats["mean_road_grade_force_n"]

    # Aero drag at ~28 m/s should be between 550 N and 750 N
    assert 550.0 <= mean_drag <= 750.0

    # Grade force at ~3.83% uphill slope should be negative (retarding) between -650 N and -450 N
    assert -650.0 <= mean_grade <= -450.0
