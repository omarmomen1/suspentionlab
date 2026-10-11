"""
tests/test_phase3g1_regime_audit.py
===================================
Test Suite 1 for Phase 3G.1: Decoupled Pressure vs Response & Regime Governance.

Verifies:
  1. Decoupled evaluation of standalone pressure prediction (Path A) vs
     vehicle dynamic response (Path B).
  2. Turn 3 Approach is classified strictly as CONFIRMED_ON_UNSEEN_DATA.
  3. Turn 5 Tight Complex is classified strictly as SUPPORTED_BUT_INCONCLUSIVE
     (discovery/calibration set; cannot be external confirmation).
  4. Turn 9-10 is classified as CONFIRMED_ON_UNSEEN_DATA.
  5. Turn 2 is classified as MODEL_SUPPORTED.
  6. HighSpeed S-Curves is classified as NOT_GENERALIZED.
  7. No global single confirmation tag is applied.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGIME_AUDIT_JSON = PROJECT_ROOT / "data" / "phase3g1_regime_audit.json"
REGIME_AUDIT_MD = PROJECT_ROOT / "docs" / "phase3g1_regime_audit.md"


@pytest.fixture
def audit_data():
    assert REGIME_AUDIT_JSON.exists(), "phase3g1_regime_audit.json must exist"
    with open(REGIME_AUDIT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_regime_audit_artifacts_exist():
    """Verify both JSON data and Markdown documentation artifacts exist."""
    assert REGIME_AUDIT_JSON.is_file()
    assert REGIME_AUDIT_MD.is_file()
    assert REGIME_AUDIT_MD.stat().st_size > 500


def test_decoupled_path_a_and_path_b_structure(audit_data):
    """Verify Path A (pressure) and Path B (dynamics) are evaluated independently."""
    assert "regimes" in audit_data
    regimes = audit_data["regimes"]
    expected_regimes = [
        "Turn3_Approach",
        "Turn2_Complex",
        "Turn9_10_Final_Complex",
        "HighSpeed_S_Curves",
        "Turn5_Tight_Complex",
    ]
    for r in expected_regimes:
        assert r in regimes, f"Missing regime: {r}"
        reg_entry = regimes[r]
        assert "path_a_pressure_metrics" in reg_entry
        assert "path_b_vehicle_metrics" in reg_entry
        assert "regime_classification" in reg_entry
        assert "role" in reg_entry

        # Path A must have individual corners and total
        p_metrics = reg_entry["path_a_pressure_metrics"]
        assert all(k in p_metrics for k in ["fl", "fr", "rl", "rr", "total"])

        # Path B must have longitudinal and yaw metrics
        dyn_metrics = reg_entry["path_b_vehicle_metrics"]
        assert "vx" in dyn_metrics
        assert "yaw_rate" in dyn_metrics


def test_turn3_external_confirmation_classification(audit_data):
    """Verify Turn 3 Approach qualifies as clean external confirmation."""
    t3 = audit_data["regimes"]["Turn3_Approach"]
    assert t3["role"] == "EXTERNAL_CONFIRMATION_SET"
    assert t3["regime_classification"] == "CONFIRMED_ON_UNSEEN_DATA"
    
    # Path A pressure metrics
    total_p = t3["path_a_pressure_metrics"]["total"]
    assert total_p["rmse"] < 2.0  # ~1.31 bar
    assert total_p["corr"] > 0.90  # ~0.962

    # Path B dynamics metrics
    vx = t3["path_b_vehicle_metrics"]["vx"]
    assert vx["rmse"] < 1.0  # ~0.587 m/s
    assert abs(vx["final_err"]) < 1.0  # ~ -0.76 m/s


def test_turn5_calibration_contamination_classification(audit_data):
    """Verify Turn 5 is flagged as discovery/calibration and NOT external confirmation."""
    t5 = audit_data["regimes"]["Turn5_Tight_Complex"]
    assert t5["role"] == "DISCOVERY_SET"
    assert t5["regime_classification"] == "SUPPORTED_BUT_INCONCLUSIVE"
    assert "CONFIRMED_ON_UNSEEN_DATA" not in t5["regime_classification"]


def test_turn9_10_and_turn2_classifications(audit_data):
    """Verify classifications for Turn 9-10 chicane and Turn 2 sweeper."""
    t910 = audit_data["regimes"]["Turn9_10_Final_Complex"]
    assert t910["regime_classification"] == "CONFIRMED_ON_UNSEEN_DATA"
    assert t910["path_b_vehicle_metrics"]["vx"]["rmse"] < 2.5

    t2 = audit_data["regimes"]["Turn2_Complex"]
    assert t2["regime_classification"] == "MODEL_SUPPORTED"


def test_highspeed_s_curves_classification(audit_data):
    """Verify HighSpeed S-Curves is classified as NOT_GENERALIZED."""
    hs = audit_data["regimes"]["HighSpeed_S_Curves"]
    assert hs["regime_classification"] == "NOT_GENERALIZED"
    assert hs["path_b_vehicle_metrics"]["vx"]["rmse"] > 4.0


def test_no_single_global_confirmation_label(audit_data):
    """Verify that multiple distinct epistemic labels exist across the regimes."""
    classifications = {
        r["regime_classification"] for r in audit_data["regimes"].values()
    }
    assert len(classifications) >= 3, "Regimes must not collapse to a single global tag"
    assert "CONFIRMED_ON_UNSEEN_DATA" in classifications
    assert "SUPPORTED_BUT_INCONCLUSIVE" in classifications
    assert "NOT_GENERALIZED" in classifications
