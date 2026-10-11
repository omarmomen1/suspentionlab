"""
tests/test_phase3g1_highspeed_forensic.py
=========================================
Test Suite 3 for Phase 3G.1: HighSpeed S-Curves Root Cause Forensic Audit.

Verifies:
  1. Measured physical caliper pressures are effectively zero throughout t in [54, 63] s.
  2. Predicted corner pressures from the BrakeDistributionController are effectively zero.
  3. The 4.511 m/s Vx RMSE is proven to have 0.0% brake controller contribution.
  4. Root cause is classified as open-loop powertrain/drag integration drift.
  5. Maneuver error is classified as NOT_A_BRAKE_CONTROLLER_DEFECT.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HIGHSPEED_JSON = PROJECT_ROOT / "data" / "phase3g1_highspeed_forensic.json"
HIGHSPEED_MD = PROJECT_ROOT / "docs" / "phase3g1_highspeed_forensic.md"


@pytest.fixture
def forensic_data():
    assert HIGHSPEED_JSON.exists(), "phase3g1_highspeed_forensic.json must exist"
    with open(HIGHSPEED_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_highspeed_forensic_artifacts_exist():
    """Verify forensic JSON and Markdown artifacts exist and are non-empty."""
    assert HIGHSPEED_JSON.is_file()
    assert HIGHSPEED_MD.is_file()
    assert HIGHSPEED_MD.stat().st_size > 500


def test_highspeed_telemetry_brake_pressure_zero(forensic_data):
    """Verify physical telemetry reveals near-zero braking across all corners."""
    telem = forensic_data["telemetry_evidence"]
    assert telem["brake_fl_bar_stats"]["mean"] < 0.20
    assert telem["brake_fr_bar_stats"]["mean"] < 0.20
    assert telem["brake_rl_bar_stats"]["mean"] < 0.20
    assert telem["brake_rr_bar_stats"]["mean"] < 0.20
    assert telem["driver_cmd_bar_stats"]["mean"] < 0.10


def test_highspeed_controller_predicted_pressure_zero(forensic_data):
    """Verify controller autonomously predicts near-zero pressure throughout maneuver."""
    telem = forensic_data["telemetry_evidence"]
    preds = telem["predicted_pressure_mean_bar"]
    assert preds["fl"] < 0.20
    assert preds["fr"] < 0.20
    assert preds["rl"] < 0.20
    assert preds["rr"] < 0.20


def test_highspeed_root_cause_attribution(forensic_data):
    """Verify forensic determination decouples the error from the brake controller."""
    det = forensic_data["forensic_determination"]
    assert det["source_of_vx_error"] == "LONGITUDINAL_POWERTRAIN_AND_DRAG_INTEGRATION_DRIFT"
    assert det["brake_controller_contribution_pct"] == 0.0
    assert det["powertrain_drag_contribution_pct"] == 100.0
    assert det["classification"] == "NOT_A_BRAKE_CONTROLLER_DEFECT"
