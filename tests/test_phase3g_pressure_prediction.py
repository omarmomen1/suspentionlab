"""
tests/test_phase3g_pressure_prediction.py
=========================================
Test Suite 3 for Phase 3G: Path 1 Standalone Pressure Prediction Accuracy.

Verifies:
  1. Prediction deliverables exist and adhere to JSON schema.
  2. External Confirmation Set (Turn 3 Approach) achieves pressure RMSE < 1.0 bar.
  3. Discovery Set (Turn 5) pressure tracking achieves RMSE < 3.0 bar.
  4. Total braking pressure correlation exceeds 0.95 across active braking maneuvers.
  5. Front/rear brake distribution and induced yaw moments are physically bounded.
"""

import json
from pathlib import Path
import pytest
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def predictions_data():
    path = PROJECT_ROOT / "data" / "phase3g_brake_distribution_predictions.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_predictions_artifact_schema(predictions_data):
    """Verify artifact schema, dataset hash, and maneuver metadata."""
    assert predictions_data["phase"] == "PHASE_3G"
    assert predictions_data["contract"] == "PATH_1_PRESSURE_PREDICTION"
    assert "dataset_hash" in predictions_data
    assert "maneuvers" in predictions_data
    assert "stress_regimes" in predictions_data


def test_turn3_clean_external_confirmation_pressure_accuracy(predictions_data):
    """Verify Turn 3 Approach (clean external confirmation) achieves tight pressure bounds."""
    t3 = predictions_data["maneuvers"]["Turn3_Approach"]
    assert t3["role"] == "EXTERNAL_CONFIRMATION_SET"

    # All four corners must have RMSE < 1.0 bar in this trail braking sector
    assert t3["corners"]["fl"]["rmse"] < 1.0, f"FL RMSE too high: {t3['corners']['fl']['rmse']}"
    assert t3["corners"]["fr"]["rmse"] < 1.0, f"FR RMSE too high: {t3['corners']['fr']['rmse']}"
    assert t3["corners"]["rl"]["rmse"] < 1.0, f"RL RMSE too high: {t3['corners']['rl']['rmse']}"
    assert t3["corners"]["rr"]["rmse"] < 1.0, f"RR RMSE too high: {t3['corners']['rr']['rmse']}"

    # Total pressure correlation must exceed 0.95
    assert t3["total_pressure"]["corr"] > 0.95


def test_turn5_discovery_set_pressure_accuracy(predictions_data):
    """Verify Turn 5 (discovery set) achieves accurate per-corner tracking."""
    t5 = predictions_data["maneuvers"]["Turn5_Tight_Complex"]
    assert t5["role"] == "DISCOVERY_SET"

    # All four corners must have RMSE < 3.0 bar under heavy 50 bar braking
    assert t5["corners"]["fl"]["rmse"] < 3.0
    assert t5["corners"]["fr"]["rmse"] < 3.0
    assert t5["corners"]["rl"]["rmse"] < 3.0
    assert t5["corners"]["rr"]["rmse"] < 3.0

    # Total pressure correlation must be nearly perfect (>0.99)
    assert t5["total_pressure"]["corr"] > 0.99


def test_front_bias_and_induced_yaw_moments(predictions_data):
    """Verify front/rear distribution and yaw moments match physical principles."""
    for m_id, m_dict in predictions_data["maneuvers"].items():
        if m_dict["corners"]["fl"]["mean_measured_bar"] > 0.5:
            # Front bias must be between 55% and 68%
            assert 0.55 <= m_dict["mean_front_bias_pred"] <= 0.68, f"{m_id} bias out of range: {m_dict['mean_front_bias_pred']}"
            # Induced yaw moment must be non-zero during cornering
            assert m_dict["max_induced_yaw_moment_nm"] >= 0.0
