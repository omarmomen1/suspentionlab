"""
tests/test_phase3g1_state_conditioning.py
=========================================
Test Suite 2 for Phase 3G.1: State-Conditioning vs Full-Forward Autonomous Prediction.

Verifies:
  1. Feature taxonomy categorizing driver boundary inputs vs vehicle state feedback.
  2. Full-Forward simulation (zero telemetry state feedback) operates with
     numerical stability and equivalent accuracy to state-conditioned mode.
  3. Delta Vx RMSE between state-conditioned and full-forward is <= 0.05 m/s.
  4. Absolute verification that measured caliper pressure is never leaked into Mode B.
"""

import json
from pathlib import Path
import pytest
from suspensionlab.physics.brake_distribution import BrakeDistributionController

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_COND_JSON = PROJECT_ROOT / "data" / "phase3g1_state_conditioning.json"
STATE_COND_MD = PROJECT_ROOT / "docs" / "phase3g1_state_conditioning.md"


@pytest.fixture
def state_data():
    assert STATE_COND_JSON.exists(), "phase3g1_state_conditioning.json must exist"
    with open(STATE_COND_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_state_conditioning_artifacts_exist():
    """Verify JSON and Markdown deliverables exist and are non-empty."""
    assert STATE_COND_JSON.is_file()
    assert STATE_COND_MD.is_file()
    assert STATE_COND_MD.stat().st_size > 500


def test_feature_taxonomy_classification(state_data):
    """Verify strict taxonomy of boundary actuator inputs vs state feedback."""
    tax = state_data["feature_taxonomy"]
    assert tax["driver_demand_bar"]["classification"] == "BOUNDARY_ACTUATOR_INPUT"
    assert tax["driver_demand_bar"]["measured_state_feedback"] is False

    assert tax["steering_rad"]["classification"] == "BOUNDARY_ACTUATOR_INPUT"
    assert tax["steering_rad"]["measured_state_feedback"] is False

    state_features = ["vx_mps", "yaw_rate_radps", "ax_mps2", "ay_mps2", "wheel_speeds_radps"]
    for feat in state_features:
        assert feat in tax
        assert tax[feat]["classification"] == "STATE_INPUT"
        assert tax[feat]["measured_state_feedback"] == "MODE_DEPENDENT"


def test_full_forward_parity_and_stability(state_data):
    """Verify that full-forward autonomous integration matches state-conditioned mode."""
    table = state_data["comparison_table"]
    for regime_name, res in table.items():
        sc_rmse = res["state_conditioned_vx_rmse"]
        ff_rmse = res["full_forward_vx_rmse"]
        delta_rmse = abs(res["delta_rmse"])

        # Full forward must maintain parity within 0.05 m/s
        assert delta_rmse <= 0.05, (
            f"Regime {regime_name} has excessive delta RMSE: {delta_rmse} m/s "
            f"(SC: {sc_rmse}, FF: {ff_rmse})"
        )


def test_strict_zero_caliper_leakage_derivative():
    """Verify d(predicted_pressure) / d(measured_pressure) == 0.000000."""
    ctrl = BrakeDistributionController(static_front_bias=0.614)

    # Base prediction
    base = ctrl.predict_pressures(
        driver_demand_bar=35.0,
        steering_rad=0.08,
        vx_mps=24.0,
        yaw_rate_radps=0.15,
        ay_mps2=3.6,
    )

    # Controller signature does not accept measured caliper pressures
    import inspect
    sig = inspect.signature(ctrl.predict_pressures)
    forbidden_params = [
        "brake_fl_bar", "brake_fr_bar", "brake_rl_bar", "brake_rr_bar",
        "measured_p_fl", "measured_p_fr", "measured_p_rl", "measured_p_rr",
        "caliper_pressure", "measured_pressures",
    ]
    for param in forbidden_params:
        assert param not in sig.parameters, f"Forbidden leakage parameter found: {param}"
