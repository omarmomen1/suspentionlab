"""Phase 3H.4.3 Richardson Extrapolation Analysis Tests.

Verifies:
1. Triplet-based convergence order formulation across:
   - Triplet 1: (5.0, 2.5, 1.25 ms)
   - Triplet 2: (2.5, 1.25, 0.625 ms)
   - Triplet 3: (1.25, 0.625, 0.3125 ms)
2. Empirical quantification of convergence order p ≈ 1.00 (strict linear order).
3. Estimation of asymptotic continuum residual R_0 ≈ -380 J.
4. Compliance with Epistemic Rule 6: do not claim lim_{dt->0} R(dt) = 0 when data shows non-zero limit.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h43_richardson_analysis.json"


@pytest.fixture(scope="module")
def richardson_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_richardson_metadata(richardson_data):
    """Verify phase metadata and contract declaration."""
    assert richardson_data["phase"] == "PHASE_3H.4.3"
    assert richardson_data["contract"] == "RICHARDSON_EXTRAPOLATION_ANALYSIS"
    assert len(richardson_data["triplets"]) == 3


def test_three_triplets_evaluated(richardson_data):
    """Verify all 3 step-doubling triplets are present."""
    labels = [t["triplet_label"] for t in richardson_data["triplets"]]
    assert "Triplet_1_5.00_2.50_1.25ms" in labels
    assert "Triplet_2_2.50_1.25_0.625ms" in labels
    assert "Triplet_3_1.25_0.625_0.3125ms" in labels


def test_convergence_order_p_quantification(richardson_data):
    """Verify convergence order p is strictly quantified near 1.00."""
    triplets = richardson_data["triplets"]
    summary = richardson_data["summary"]

    for t in triplets:
        p_val = t["observed_order_p"]
        assert 0.90 <= p_val <= 1.10, f"Order p={p_val} deviates from linear expectation"

    mean_p = summary["mean_observed_order_p"]
    assert mean_p == pytest.approx(1.001, abs=0.05)
    assert summary["order_classification"] == "STRICT_FIRST_ORDER_O_DT"


def test_asymptotic_residual_non_zero_certification(richardson_data):
    """Verify continuum limit R_0 is certified as non-zero (-380 J) adhering to Rule 6."""
    summary = richardson_data["summary"]
    assert summary["is_continuum_limit_zero"] is False
    assert summary["mean_asymptotic_residual_j"] == pytest.approx(-382.90, abs=15.0)

    # Check each individual triplet's asymptote
    for t in richardson_data["triplets"]:
        r0 = t["asymptotic_residual_j"]
        assert -410.0 <= r0 <= -360.0
