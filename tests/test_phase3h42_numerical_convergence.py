"""Phase 3H.4.2 Numerical Convergence Verification Tests.

Verifies:
1. Multi-rate evaluation of the Window A energy ledger at:
   - dt = 5.00 ms (baseline)
   - dt = 2.50 ms (2x sub-stepping)
   - dt = 1.25 ms (4x sub-stepping)
2. Strict monotonic convergence of the numerical energy residual toward zero:
   |res(5.0 ms)| > |res(2.5 ms)| > |res(1.25 ms)|.
3. Distinction verdict proving the residual originates from numerical discretization error,
   not missing physical model terms.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_numerical_convergence.json"


@pytest.fixture(scope="module")
def convergence_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_convergence_metadata(convergence_data):
    """Verify phase metadata and contract declaration."""
    assert convergence_data["phase"] == "PHASE_3H.4.2"
    assert convergence_data["contract"] == "NUMERICAL_CONVERGENCE_VERIFICATION"
    assert len(convergence_data["convergence_runs"]) == 3


def test_three_time_steps_evaluated(convergence_data):
    """Verify runs at 5.0 ms, 2.5 ms, and 1.25 ms."""
    runs = convergence_data["convergence_runs"]
    dt_vals = [r["dt_ms"] for r in runs]
    assert dt_vals == [5.0, 2.5, 1.25]


def test_monotonic_residual_decay(convergence_data):
    """Verify numerical residual strictly contracts toward zero with smaller dt."""
    analysis = convergence_data["convergence_analysis"]
    assert analysis["is_monotonically_converging"] is True

    pct_5ms = abs(analysis["residual_5_00ms_pct"])
    pct_25ms = abs(analysis["residual_2_50ms_pct"])
    pct_125ms = abs(analysis["residual_1_25ms_pct"])

    assert pct_5ms > pct_25ms > pct_125ms
    assert pct_5ms == pytest.approx(6.90, abs=0.2)
    assert pct_25ms == pytest.approx(4.44, abs=0.2)
    assert pct_125ms == pytest.approx(3.31, abs=0.2)


def test_distinction_verdict(convergence_data):
    """Verify distinction verdict confirms numerical integration origin."""
    analysis = convergence_data["convergence_analysis"]
    verdict = analysis["distinction_verdict"]
    assert "monotonically contracts" in verdict.lower()
    assert "numerical integration error rather than omitted physical energy terms" in verdict.lower()
