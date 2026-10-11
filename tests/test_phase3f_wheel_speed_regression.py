"""
tests/test_phase3f_wheel_speed_regression.py
============================================
Test Suite 5 for Phase 3F: Independent Four-Wheel Speed Tracking and Regression Gate.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def wheel_speed_data():
    path = PROJECT_ROOT / "data" / "phase3f_wheel_speed_validation.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def brake_chain_data():
    path = PROJECT_ROOT / "data" / "phase3f_brake_chain.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_turn5_wheel_speed_rmse_reduction(wheel_speed_data):
    """Verify Turn 5 average wheel-speed RMSE is reduced by at least 40%."""
    t5_ws = wheel_speed_data["wheel_speed_breakdown"]["Turn5_Tight_Complex"]
    p3d_rmse = t5_ws["omega_avg"]["phase3d_rmse"]
    p3f_rmse = t5_ws["omega_avg"]["phase3f_rmse"]
    reduction_pct = (p3d_rmse - p3f_rmse) / p3d_rmse * 100.0

    assert reduction_pct >= 40.0, f"Expected >= 40% reduction, achieved {reduction_pct:.1f}%"


def test_turn3_wheel_speed_rmse_reduction(wheel_speed_data):
    """Verify Turn 3 average wheel-speed RMSE is reduced by at least 10%."""
    t3_ws = wheel_speed_data["wheel_speed_breakdown"]["Turn3_Approach"]
    p3d_rmse = t3_ws["omega_avg"]["phase3d_rmse"]
    p3f_rmse = t3_ws["omega_avg"]["phase3f_rmse"]
    reduction_pct = (p3d_rmse - p3f_rmse) / p3d_rmse * 100.0

    assert reduction_pct >= 10.0, f"Expected >= 10% reduction, achieved {reduction_pct:.1f}%"


def test_all_four_corners_tracked_independently(wheel_speed_data):
    """Verify each wheel corner (FL, FR, RL, RR) is independently tracked and validated."""
    for m_id, m_dict in wheel_speed_data["wheel_speed_breakdown"].items():
        assert "omega_fl" in m_dict
        assert "omega_fr" in m_dict
        assert "omega_rl" in m_dict
        assert "omega_rr" in m_dict
        assert "omega_avg" in m_dict


def test_zero_wheel_lockup_in_heavy_braking(brake_chain_data):
    """Verify all wheel speeds remain strictly positive during Turn 5 heavy braking."""
    traces = brake_chain_data["time_series_trace"]
    for t in traces:
        assert t["p3f_wfl_radps"] > 0.0, f"FL lockup at t={t['t_rel_s']}"
        assert t["p3f_wfr_radps"] > 0.0, f"FR lockup at t={t['t_rel_s']}"
        assert t["p3f_wrl_radps"] > 0.0, f"RL lockup at t={t['t_rel_s']}"
        assert t["p3f_wrr_radps"] > 0.0, f"RR lockup at t={t['t_rel_s']}"
