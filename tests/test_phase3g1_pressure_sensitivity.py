"""
tests/test_phase3g1_pressure_sensitivity.py
===========================================
Test Suite 4 for Phase 3G.1: Pressure Perturbation Sensitivity Analysis.

Verifies:
  1. Systematic sensitivity gradients:
       dVx / dP ~= -0.365 (m/s)/bar
       dOmega / dP ~= -1.17 (rad/s)/bar
       d|r| / dP <= 0.05 (rad/s)/bar
  2. Monotonicity of velocity and wheel speed responses across sweeps.
  3. Direct physical evidence that a 2 bar pressure discrepancy accounts
     for ~0.73 m/s velocity shift.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SENSITIVITY_JSON = PROJECT_ROOT / "data" / "phase3g1_pressure_sensitivity.json"
VALIDATION_STATUS_MD = PROJECT_ROOT / "docs" / "phase3g1_validation_status.md"


@pytest.fixture
def sensitivity_data():
    assert SENSITIVITY_JSON.exists(), "phase3g1_pressure_sensitivity.json must exist"
    with open(SENSITIVITY_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_sensitivity_artifacts_exist():
    """Verify JSON and Markdown validation status artifacts exist."""
    assert SENSITIVITY_JSON.is_file()
    assert VALIDATION_STATUS_MD.is_file()
    assert VALIDATION_STATUS_MD.stat().st_size > 500


def test_nominal_sensitivity_gradients(sensitivity_data):
    """Verify nominal sensitivity gradients match physical dynamics."""
    nom = sensitivity_data["nominal_sensitivity"]
    
    # dVx / dP should be approximately -0.365 (m/s)/bar
    assert -0.45 <= nom["dvx_dp_mean_mps_per_bar"] <= -0.25

    # dOmega / dP should be approximately -1.17 (rad/s)/bar
    assert -1.40 <= nom["domega_dp_mean_radps_per_bar"] <= -0.90

    # Yaw rate sensitivity should be modest (< 0.05 (rad/s)/bar)
    assert 0.0 <= nom["dyaw_dp_mean_radps_per_bar"] <= 0.05


def test_perturbation_sweeps_monotonicity(sensitivity_data):
    """Verify velocity and wheel speed changes are strictly monotonic with pressure."""
    sweeps = sensitivity_data["perturbation_sweeps"]
    levels = [-5.0, -2.0, -1.0, 1.0, 2.0, 5.0]

    # As delta pressure increases, delta Vx should monotonically decrease (more braking -> lower speed)
    delta_vx_values = [sweeps[str(lvl)]["mean_delta_vx_mps"] for lvl in levels]
    for i in range(len(delta_vx_values) - 1):
        assert delta_vx_values[i] > delta_vx_values[i + 1], "Delta Vx must strictly decrease as dP increases"

    # As delta pressure increases, delta Omega should monotonically decrease
    delta_omega_values = [sweeps[str(lvl)]["mean_delta_omega_avg_radps"] for lvl in levels]
    for i in range(len(delta_omega_values) - 1):
        assert delta_omega_values[i] > delta_omega_values[i + 1], "Delta Omega must strictly decrease as dP increases"


def test_two_bar_error_explains_observed_vx_delta(sensitivity_data):
    """Verify that a 2 bar pressure error accounts for ~0.73 m/s velocity shift."""
    p2 = sensitivity_data["perturbation_sweeps"]["2.0"]
    delta_vx = abs(p2["mean_delta_vx_mps"])
    assert 0.60 <= delta_vx <= 0.85
