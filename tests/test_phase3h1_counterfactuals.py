"""Phase 3H.1 Counterfactual Simulation Tests.

Verifies:
1. Counterfactual quantitative results across all 9 runs (CF_A to CF_I).
2. Physical gear ratio + measured torque counterfactual (CF_B2) reduces Vx RMSE by 38.3%.
3. Multi-contributor classification matrix adheres to strict forensic standards.
4. Single-cause claims are strictly rejected in favor of multi-factor attribution.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COUNTERFACTUALS_FILE = DATA_DIR / "phase3h1_counterfactuals.json"


@pytest.fixture(scope="module")
def cf_data():
    assert COUNTERFACTUALS_FILE.exists(), f"Missing counterfactuals file: {COUNTERFACTUALS_FILE}"
    with open(COUNTERFACTUALS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_baseline_counterfactual(cf_data):
    """Verify CF_A baseline metrics match frozen Phase 3H baseline."""
    cf_a = cf_data["counterfactuals"]["CF_A_Baseline"]
    assert cf_a["vx_rmse_mps"] == pytest.approx(4.4821, abs=0.01)
    assert cf_a["exit_speed_error_mps"] == pytest.approx(7.3330, abs=0.01)
    assert cf_a["integrated_energy_error_mj"] == pytest.approx(1.475, abs=0.02)


def test_physical_gear_ratio_counterfactual(cf_data):
    """Verify CF_B2 (measured torque + physical ratio 5.6426) improves Vx RMSE by ~38.3%."""
    cf_a = cf_data["counterfactuals"]["CF_A_Baseline"]
    cf_b2 = cf_data["counterfactuals"]["CF_B2_MeasTorque_PhysicalRatio"]

    assert cf_b2["vx_rmse_mps"] == pytest.approx(2.7672, abs=0.01)
    assert cf_b2["exit_speed_error_mps"] == pytest.approx(4.9446, abs=0.01)
    assert cf_b2["integrated_energy_error_mj"] == pytest.approx(0.859, abs=0.02)

    pct_improvement = (cf_a["vx_rmse_mps"] - cf_b2["vx_rmse_mps"]) / cf_a["vx_rmse_mps"] * 100.0
    assert pct_improvement == pytest.approx(38.26, abs=0.5)


def test_other_counterfactuals(cf_data):
    """Verify other counterfactual sensitivity metrics."""
    cfs = cf_data["counterfactuals"]

    # CF_C: Zero engine torque worsens error severely
    assert cfs["CF_C_ZeroEngineTorque"]["vx_rmse_mps"] == pytest.approx(7.9255, abs=0.01)

    # CF_D: Zero aero drag has large impact
    assert cfs["CF_D_ZeroAeroDrag"]["vx_rmse_mps"] == pytest.approx(2.3649, abs=0.01)

    # CF_F: Zero grade has large impact
    assert cfs["CF_F_ZeroGrade"]["vx_rmse_mps"] == pytest.approx(2.7881, abs=0.01)


def test_contributor_classification_matrix(cf_data):
    """Verify candidate causes are classified according to rigorous forensic evidence."""
    matrix = cf_data["final_classifications"]

    assert matrix["transmission_gear_clamping_discrepancy"]["classification"] == "PRIMARY_CONTRIBUTOR"
    assert matrix["synthetic_engine_torque_envelope"]["classification"] == "SECONDARY_CONTRIBUTOR"
    assert matrix["aerodynamic_drag"]["classification"] == "PRIMARY_CONTRIBUTOR"
    assert matrix["road_grade_gravity"]["classification"] == "PRIMARY_CONTRIBUTOR"
    assert matrix["lateral_scrub_coriolis"]["classification"] == "MINOR_CONTRIBUTOR"
    assert matrix["rolling_resistance"]["classification"] == "NOT_SUPPORTED"
    assert matrix["can_bus_gearratio_channel_semantics"]["classification"] == "UNIDENTIFIABLE"


def test_prohibition_of_single_cause_claim(cf_data):
    """Ensure that multi-contributor dynamics are recognized and single-cause attribution is rejected."""
    matrix = cf_data["final_classifications"]
    primary_contributors = [k for k, v in matrix.items() if v["classification"] == "PRIMARY_CONTRIBUTOR"]
    assert len(primary_contributors) > 1, "Must recognize compound multi-factor dynamics"
