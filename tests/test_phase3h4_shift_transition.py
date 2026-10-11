"""Phase 3H.4 Shift Transition Validation Tests.

Verifies:
1. Window A (12.60 - 12.80 s) authentic 2 -> 3 upshift reproduction.
2. Exact gear sequence match [2, 3].
3. Shift trigger timing within 50 ms of measured ECU command.
4. Kinematically consistent RPM drop across the 2 -> 3 transition.
5. Simulated vehicle speed Vx RMSE <= 0.50 m/s through the transition.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h4_shift_transition_validation.json"


@pytest.fixture(scope="module")
def transition_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_window_a_gear_sequence(transition_data):
    """Verify Window A reproduces the authentic 2 -> 3 gear sequence."""
    win_a = transition_data["window_a_2_to_3_upshift"]
    assert win_a["gears_observed"] == [2, 3], f"Unexpected gear sequence: {win_a['gears_observed']}"
    assert len(win_a["shifts"]) == 1
    shift = win_a["shifts"][0]
    assert shift["type"] == "UPSHIFT"
    assert shift["old_gear"] == 2
    assert shift["target_gear"] == 3


def test_window_a_shift_timing(transition_data):
    """Verify Window A shift initiates within 50 ms of authentic ECU command."""
    win_a = transition_data["window_a_2_to_3_upshift"]
    shift = win_a["shifts"][0]
    meas_shift_t = 12.640  # Authentic ECU shift time
    delta_t = abs(shift["t_s"] - meas_shift_t)
    assert delta_t <= 0.050, f"Shift timing delta {delta_t:.3f} s exceeds 50 ms limit"


def test_window_a_vx_fidelity(transition_data):
    """Verify Window A Vx trajectory RMSE <= 0.50 m/s."""
    win_a = transition_data["window_a_2_to_3_upshift"]
    assert win_a["vx_rmse_mps"] <= 0.50, f"Vx RMSE {win_a['vx_rmse_mps']:.4f} exceeds 0.50 m/s"
    assert win_a["vx_rmse_mps"] == pytest.approx(0.1608, abs=0.02)


def test_window_a_rpm_kinematic_drop(transition_data):
    """Verify engine RPM drop is kinematically consistent with 2 -> 3 gear ratios."""
    win_a = transition_data["window_a_2_to_3_upshift"]
    evals = win_a["epistemic_evaluations"]["rpm_trajectory_window_a"]
    pre_rpm = evals["pre_shift_rpm"]
    post_rpm = evals["post_shift_rpm"]
    # Ratio 2 (8.528) to Ratio 3 (5.6427) represents a drop of ~1.511
    expected_post_rpm = pre_rpm * (5.6427 / 8.528)
    assert post_rpm == pytest.approx(expected_post_rpm, rel=0.05)
    assert evals["classification"] == "MODEL_SUPPORTED"
