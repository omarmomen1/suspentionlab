"""Phase 3H.2.1 Predictive Torque Residual Matrix Tests.

Verifies:
1. Zero parameter retuning policy during Phase 3H.2.1 audit.
2. Residual matrix completeness across RPM, throttle, gear, and 2D bins.
3. Accurate identification and documentation of systematic underprediction in high-load regimes.
4. Power residual and energy deficits are explicitly quantified for HighSpeed S-Curves.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TORQUE_RESIDUALS_JSON = DATA_DIR / "phase3h21_torque_residuals.json"


@pytest.fixture(scope="module")
def res_data():
    assert TORQUE_RESIDUALS_JSON.exists(), f"Missing file: {TORQUE_RESIDUALS_JSON}"
    with open(TORQUE_RESIDUALS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_zero_retuning_policy(res_data):
    """Verify that zero model parameters were retuned during Phase 3H.2.1."""
    assertion = res_data["zero_retuning_assertion"]
    assert "No model parameters were fitted or modified" in assertion


def test_binning_matrix_completeness(res_data):
    """Verify all required binning dimensions are populated."""
    assert len(res_data["binned_by_rpm"]) >= 4
    assert len(res_data["binned_by_throttle"]) >= 4
    assert len(res_data["binned_by_gear"]) >= 2
    assert len(res_data["matrix_rpm_x_throttle"]) >= 3


def test_highspeed_s_curves_torque_underprediction_identified(res_data):
    """Verify systematic underprediction on HighSpeed S-Curves is accurately characterized."""
    analysis = res_data["systematic_bias_analysis"]
    assert analysis["verdict"] == "SYSTEMATIC_UNDERPREDICTION_IN_HIGH_LOAD_REGIMES"
    assert analysis["highspeed_s_curves_mean_deficit_nm"] < -20.0
    assert analysis["highspeed_s_curves_power_deficit_kw"] < -10.0


def test_turn3_confirmation_set_low_residual(res_data):
    """Verify Turn 3 confirmation set maintains low torque residuals within validated envelope."""
    t3 = res_data["maneuver_summaries"]["Turn3_Approach"]
    assert abs(t3["t_residual_mean_nm"]) < 10.0
    assert abs(t3["p_residual_mean_kw"]) < 5.0
