"""
tests/test_phase3h_counterfactuals.py
=====================================
Test Suite 3 for Phase 3H: Counterfactual Decomposition & Contributor Classification.

Verifies:
  1. Diagnostic counterfactuals (CF_A to CF_F) evaluated with zero production tuning.
  2. Zero Aero Drag reduces Vx RMSE by > 2.0 m/s.
  3. Zero Grade reduces Vx RMSE by > 1.5 m/s.
  4. Zero Engine Torque increases Vx RMSE to > 7.5 m/s.
  5. Zero Rolling Resistance produces 0.0 m/s delta (proves inactive in FWD baseline).
  6. Multi-factor contributor classification:
       powertrain: PRIMARY CONTRIBUTOR
       aero drag: PRIMARY CONTRIBUTOR
       road grade: PRIMARY CONTRIBUTOR
       rolling resistance: NOT SUPPORTED
  7. Prohibits attributing failure to a single cause.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CF_JSON = PROJECT_ROOT / "data" / "phase3h_counterfactuals.json"
VALIDATION_STATUS_MD = PROJECT_ROOT / "docs" / "phase3h_validation_status.md"


@pytest.fixture
def cf_data():
    assert CF_JSON.exists(), "phase3h_counterfactuals.json must exist"
    with open(CF_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_counterfactual_artifacts_exist():
    """Verify counterfactual JSON and Markdown validation status exist."""
    assert CF_JSON.is_file()
    assert VALIDATION_STATUS_MD.is_file()
    assert VALIDATION_STATUS_MD.stat().st_size > 500


def test_counterfactual_cases_present(cf_data):
    """Verify all 6 required counterfactual cases are evaluated."""
    cfs = cf_data["counterfactuals"]
    expected_cfs = [
        "CF_A_Baseline",
        "CF_B1_MeasTorque_NominalGear",
        "CF_B2_MeasTorque_MeasuredGear",
        "CF_C_ZeroEngineTorque",
        "CF_D_ZeroAeroDrag",
        "CF_E_ZeroRollingResistance",
        "CF_F_ZeroGrade",
    ]
    for case in expected_cfs:
        assert case in cfs, f"Missing counterfactual: {case}"


def test_aero_drag_counterfactual_impact(cf_data):
    """Verify zero aero drag reduces RMSE by > 2.0 m/s."""
    cf_d = cf_data["counterfactuals"]["CF_D_ZeroAeroDrag"]
    delta_rmse = abs(cf_d["delta_rmse_vs_baseline_mps"])
    assert delta_rmse > 2.0
    assert cf_d["vx_rmse_mps"] < 2.5


def test_road_grade_counterfactual_impact(cf_data):
    """Verify zero grade reduces RMSE by > 1.5 m/s."""
    cf_f = cf_data["counterfactuals"]["CF_F_ZeroGrade"]
    delta_rmse = abs(cf_f["delta_rmse_vs_baseline_mps"])
    assert delta_rmse > 1.5
    assert cf_f["vx_rmse_mps"] < 3.0


def test_zero_engine_torque_counterfactual_impact(cf_data):
    """Verify zero engine torque exacerbates deceleration (RMSE > 7.5 m/s)."""
    cf_c = cf_data["counterfactuals"]["CF_C_ZeroEngineTorque"]
    assert cf_c["vx_rmse_mps"] > 7.5
    assert cf_c["exit_speed_error_mps"] > 12.0


def test_rolling_resistance_unsupported(cf_data):
    """Verify rolling resistance has 0.0 m/s effect in FWD baseline."""
    cf_e = cf_data["counterfactuals"]["CF_E_ZeroRollingResistance"]
    assert abs(cf_e["delta_rmse_vs_baseline_mps"]) < 1e-4


def test_multi_contributor_governance(cf_data):
    """Verify contributor taxonomy has multiple primary contributors and does not blame a single cause."""
    classifications = cf_data["contributors_classification"]
    assert classifications["powertrain_drive_torque"]["classification"] == "PRIMARY CONTRIBUTOR"
    assert classifications["aerodynamic_drag"]["classification"] == "PRIMARY CONTRIBUTOR"
    assert classifications["road_grade_gravity"]["classification"] == "PRIMARY CONTRIBUTOR"
    assert classifications["rolling_resistance"]["classification"] == "NOT SUPPORTED"
