"""Phase 3H.2.2 Pre-Registered Validation Thresholds Tests.

Verifies:
1. Formal pre-registration of validation thresholds across all relevant physical observables.
2. Boundaries defined for longitudinal braking confirmation and complex handling validation.
3. Energy balance closure tolerance explicitly set to <= 0.10%.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
THRESHOLDS_JSON = DATA_DIR / "phase3h22_preregistered_thresholds.json"


@pytest.fixture(scope="module")
def thresh_data():
    assert THRESHOLDS_JSON.exists(), f"Missing file: {THRESHOLDS_JSON}"
    with open(THRESHOLDS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_regime_thresholds_defined(thresh_data):
    """Verify thresholds are pre-registered across all key physical observables."""
    regimes = thresh_data["thresholds_by_regime"]
    assert "longitudinal_braking_confirmation" in regimes
    assert "complex_handling_validation" in regimes
    assert "internal_energy_balance_closure" in regimes

    long_b = regimes["longitudinal_braking_confirmation"]
    assert long_b["vx_rmse_max_mps"] == 1.00
    assert long_b["wheel_speed_rmse_max_radps"] == 3.00

    comp_h = regimes["complex_handling_validation"]
    assert comp_h["vx_rmse_max_mps"] == 4.50
    assert comp_h["wheel_speed_rmse_max_radps"] == 15.00
    assert comp_h["torque_residual_mean_max_nm"] == 40.0


def test_energy_closure_tolerance(thresh_data):
    """Verify numerical energy closure tolerance is strictly bounded."""
    closure = thresh_data["thresholds_by_regime"]["internal_energy_balance_closure"]
    assert closure["max_relative_closure_error_pct"] == 0.10
