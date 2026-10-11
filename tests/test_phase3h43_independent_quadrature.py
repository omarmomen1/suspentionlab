"""Phase 3H.4.3 Independent Quadrature Audit Tests.

Verifies:
1. Multi-rate evaluation across 3 distinct quadrature schemes:
   - Method A: Production Forward Euler left-rectangle sum
   - Method B: Trapezoidal rule post-processing
   - Method C: High-order Simpson composite quadrature
2. Monotonic convergence across all 3 methods.
3. Quantified quadrature sensitivity and curvature contraction:
   difference between Simpson and Trapezoid shrinks from 92.9 J down to 5.6 J.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h43_independent_quadrature.json"


@pytest.fixture(scope="module")
def quadrature_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_quadrature_metadata(quadrature_data):
    """Verify phase metadata and contract declaration."""
    assert quadrature_data["phase"] == "PHASE_3H.4.3"
    assert quadrature_data["contract"] == "INDEPENDENT_QUADRATURE_AUDIT"
    methods = quadrature_data["quadrature_methods"]
    assert len(methods) == 3
    assert any("Production" in m for m in methods)
    assert any("Trapezoidal" in m for m in methods)
    assert any("Simpson" in m for m in methods)


def test_quadrature_comparison_table_structure(quadrature_data):
    """Verify table contains all 5 rates."""
    table = quadrature_data["comparison_table"]
    assert len(table) == 5
    dt_vals = [row["dt_ms"] for row in table]
    assert dt_vals == [5.0, 2.5, 1.25, 0.625, 0.3125]


def test_all_methods_monotonically_converge(quadrature_data):
    """Verify all 3 methods contract monotonically as dt decreases."""
    table = quadrature_data["comparison_table"]
    res_A = [abs(row["method_A_prod_residual_j"]) for row in table]
    res_B = [abs(row["method_B_trap_residual_j"]) for row in table]
    res_C = [abs(row["method_C_simp_residual_j"]) for row in table]

    for i in range(len(table) - 1):
        assert res_A[i] > res_A[i + 1], f"Method A non-monotonic at row {i}"
        assert res_B[i] > res_B[i + 1], f"Method B non-monotonic at row {i}"
        assert res_C[i] > res_C[i + 1], f"Method C non-monotonic at row {i}"


def test_simpson_vs_trapezoid_difference_contraction(quadrature_data):
    """Verify high-order Simpson and Trapezoidal methods converge to identical values."""
    table = quadrature_data["comparison_table"]
    diffs = [abs(row["simp_vs_trap_diff_j"]) for row in table]

    for i in range(len(diffs) - 1):
        assert diffs[i] > diffs[i + 1], f"Quadrature difference did not contract at row {i}"

    assert diffs[0] == pytest.approx(92.90, abs=2.0)
    assert diffs[-1] == pytest.approx(5.65, abs=0.5)
