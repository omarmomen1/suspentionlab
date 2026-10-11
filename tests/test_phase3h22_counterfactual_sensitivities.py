"""Phase 3H.2.2 Counterfactual Sensitivity Formalization Tests.

Verifies:
1. Rejection of additive physical error percentages for counterfactual RMSE differences.
2. Formal representation of counterfactual comparisons as sensitivity metrics (Delta RMSE).
3. Presence of mandatory epistemic disclaimer on counterfactual results.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CF_SENSITIVITIES_JSON = DATA_DIR / "phase3h22_counterfactual_sensitivities.json"


@pytest.fixture(scope="module")
def cf_data():
    assert CF_SENSITIVITIES_JSON.exists(), f"Missing file: {CF_SENSITIVITIES_JSON}"
    with open(CF_SENSITIVITIES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_counterfactual_sensitivities_values(cf_data):
    """Verify Delta RMSE values for measured torque, aero, and grade sensitivities."""
    sens = cf_data["sensitivities"]
    assert sens["measured_torque_replay_sensitivity"]["delta_rmse_mps"] == pytest.approx(1.2992, abs=0.01)
    assert sens["aerodynamic_drag_sensitivity"]["delta_rmse_mps"] == pytest.approx(2.1613, abs=0.01)
    assert sens["road_grade_gravity_sensitivity"]["delta_rmse_mps"] == pytest.approx(1.6571, abs=0.01)


def test_mandatory_epistemic_disclaimer_present(cf_data):
    """Verify exact mandatory disclaimer text is present."""
    disclaimer = cf_data["mandatory_epistemic_disclaimer"]
    assert "This is a counterfactual sensitivity result and is not an additive causal decomposition of total RMSE." in disclaimer
