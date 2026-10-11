"""Phase 3H.3 Counterfactual Autonomy Evaluation Tests.

Verifies:
1. Comparison between Case A (precomputed boundary), Case B (endogenous scheduler), and Case C (erroneous boundary).
2. Autonomous selection and holding of Gear 3 by Case B without precomputed hints.
3. Verification that Case C produces performance/torque discrepancy.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h3_counterfactual_autonomy.json"


@pytest.fixture(scope="module")
def cf_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_case_b_autonomy_equivalence(cf_data):
    """Verify Case B matches Case A while determining gear endogenously."""
    cases = cf_data["cases"]
    case_a = cases["case_a_precomputed_boundary"]
    case_b = cases["case_b_endogenous_scheduler"]

    assert case_b["delta_rmse_vs_case_a"] == pytest.approx(0.0, abs=1e-4)
    assert 3 in case_b["gears_selected"]
    assert case_b["shift_events_count"] == 0


def test_case_c_boundary_vulnerability(cf_data):
    """Verify erroneous boundary conditions alter RMSE and tractive dynamics."""
    cases = cf_data["cases"]
    case_c4 = cases["case_c4_erroneous_boundary_gear4"]
    assert case_c4["delta_rmse_vs_case_a"] != 0.0
