"""Phase 3H.4.2 System Residual Allocation & Forensic Explanation Tests.

Verifies:
1. Target Phase 3H.4.1 residual (2,787.17 J, 19.10%) is explicitly quantified.
2. Complete numerical decomposition into 5 allocated physical and bookkeeping components:
   - Road grade work inversion (+1,997.95 J)
   - Wheel rotational KE over-approximation (+366.76 J)
   - Euler left-rectangle quadrature error (+447.89 J)
   - Suspension damper dissipation (+44.86 J)
   - Kinematic Coriolis and RK4 coupling (-70.29 J)
3. Exact numerical summation to 2,787.17 J (discrepancy < 1e-6 J).
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_residual_allocation.json"


@pytest.fixture(scope="module")
def allocation_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_residual_allocation_metadata(allocation_data):
    """Verify metadata and target residual value."""
    assert allocation_data["phase"] == "PHASE_3H.4.2"
    assert allocation_data["contract"] == "SYSTEM_RESIDUAL_EXPLANATION_AND_ALLOCATION"
    assert allocation_data["target_residual_to_explain_j"] == pytest.approx(2787.17, abs=0.01)
    assert allocation_data["target_residual_relative_pct"] == pytest.approx(19.10, abs=0.02)


def test_five_components_present(allocation_data):
    """Verify all 5 allocated components are defined and quantified."""
    comps = allocation_data["component_breakdown"]
    expected_keys = [
        "1_road_grade_work_inversion",
        "2_wheel_rotational_ke_approximation",
        "3_euler_left_rectangle_quadrature_error",
        "4_suspension_damper_dissipation",
        "5_kinematic_coriolis_and_rk4_coupling",
    ]
    for key in expected_keys:
        assert key in comps, f"Missing component: {key}"
        assert "amount_j" in comps[key]
        assert "percentage_of_residual" in comps[key]
        assert "explanation" in comps[key]
        assert len(comps[key]["explanation"]) > 20


def test_component_quantities(allocation_data):
    """Verify physical values of allocated components."""
    comps = allocation_data["component_breakdown"]
    
    # Grade inversion is the primary contributor (~71.7%)
    grade_j = comps["1_road_grade_work_inversion"]["amount_j"]
    assert grade_j == pytest.approx(1997.95, abs=0.1)
    assert comps["1_road_grade_work_inversion"]["percentage_of_residual"] == pytest.approx(71.68, abs=0.5)

    # Wheel KE error (~12.1%)
    wheel_ke_j = comps["2_wheel_rotational_ke_approximation"]["amount_j"]
    assert wheel_ke_j == pytest.approx(335.95, abs=2.0)

    # Euler quadrature error (~16.1%)
    euler_j = comps["3_euler_left_rectangle_quadrature_error"]["amount_j"]
    assert euler_j == pytest.approx(447.89, abs=2.0)

    # Damper dissipation (~1.6%)
    damper_j = comps["4_suspension_damper_dissipation"]["amount_j"]
    assert damper_j == pytest.approx(44.86, abs=1.0)


def test_exact_numerical_closure(allocation_data):
    """Verify components numerically sum to 2,787.17 J with exact closure."""
    sum_comp = allocation_data["sum_of_allocated_components_j"]
    target = allocation_data["target_residual_to_explain_j"]
    disc = allocation_data["residual_allocation_closure_discrepancy_j"]

    assert sum_comp == pytest.approx(target, abs=1e-6)
    assert disc < 1e-6, f"Residual allocation discrepancy {disc} J exceeds 1e-6 J"
    assert allocation_data["allocation_verdict"] == "EXACT_NUMERICAL_ALLOCATION_ACHIEVED"
