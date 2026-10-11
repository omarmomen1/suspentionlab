"""Phase 3H.2.1 Road-Load Separation Tests.

Verifies:
1. Decomposes the 4.1169 m/s CF_L error into powertrain and road load components.
2. Quantifies the powertrain prediction discrepancy as ~31.6% (1.30 m/s).
3. Quantifies persistent road load deficits (aero drag + road grade + lateral scrub) as ~68.4% (2.82 m/s).
4. Verifies aerodynamic drag and road grade forces and energy retardations are rigorously quantified.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ROAD_LOAD_JSON = DATA_DIR / "phase3h21_road_load_separation.json"


@pytest.fixture(scope="module")
def rl_data():
    assert ROAD_LOAD_JSON.exists(), f"Missing file: {ROAD_LOAD_JSON}"
    with open(ROAD_LOAD_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_powertrain_vs_road_load_decomposition(rl_data):
    """Verify exact numerical decomposition between powertrain and road load error."""
    decomp = rl_data["error_attribution_decomposition"]
    p_err = decomp["powertrain_prediction_residual"]["rmse_contribution_mps"]
    rl_err = decomp["persistent_non_powertrain_error_mps"]
    total_baseline = rl_data["predictive_powertrain_baseline_rmse_mps"]

    assert p_err == pytest.approx(1.2992, abs=0.01)
    assert rl_err == pytest.approx(2.8177, abs=0.01)
    assert (p_err + rl_err) == pytest.approx(total_baseline, abs=0.01)

    pct_powertrain = decomp["powertrain_prediction_residual"]["percentage_of_total_error"]
    assert pct_powertrain == pytest.approx(31.56, abs=0.5)


def test_road_load_magnitudes_quantified(rl_data):
    """Verify aerodynamic drag and road grade gravitational forces and energy are quantified."""
    decomp = rl_data["error_attribution_decomposition"]
    aero = decomp["aerodynamic_drag_road_load"]
    grade = decomp["road_grade_gravity_road_load"]

    assert aero["mean_retarding_force_n"] > 600.0
    assert aero["retarding_energy_kj"] > 140.0
    assert grade["mean_retarding_force_n"] > 500.0
    assert grade["retarding_energy_kj"] > 120.0
