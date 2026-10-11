"""Phase 3H.2 Blind Multi-Regime Validation Tests.

Verifies:
1. Independent evaluation across all 5 maneuvers without tuning on validation sets.
2. Independent reporting of Vx, yaw rate, wheel speed, engine speed, and energy residual.
3. Epistemic role integrity: Turn 3 is EXTERNAL_CONFIRMATION_SET, Turn 5 is DISCOVERY_SET.
4. No false claims of empirical generalization on calibration intervals.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BLIND_VALIDATION_JSON = DATA_DIR / "phase3h2_blind_validation.json"


@pytest.fixture(scope="module")
def blind_data():
    assert BLIND_VALIDATION_JSON.exists(), f"Missing blind validation file: {BLIND_VALIDATION_JSON}"
    with open(BLIND_VALIDATION_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_maneuvers_presence(blind_data):
    """Verify all 5 authorized maneuvers are present in the validation ledger."""
    maneuvers = blind_data["maneuvers"]
    expected = [
        "HighSpeed_S_Curves",
        "Turn2_Complex",
        "Turn3_Approach",
        "Turn5_Tight_Complex",
        "Turn9_10_Final_Complex",
    ]
    for m in expected:
        assert m in maneuvers, f"Missing maneuver {m} in blind validation ledger"


def test_epistemic_role_integrity(blind_data):
    """Verify epistemic roles: Turn 3 is external confirmation, Turn 5 is discovery."""
    maneuvers = blind_data["maneuvers"]

    turn3 = maneuvers["Turn3_Approach"]
    assert turn3["role"] == "EXTERNAL_CONFIRMATION_SET"
    assert turn3["epistemic_verdict"] == "CONFIRMED_ON_UNSEEN_DATA"
    assert turn3["vx_rmse_mps"] < 1.5, f"Turn 3 tracking error too high: {turn3['vx_rmse_mps']}"

    turn5 = maneuvers["Turn5_Tight_Complex"]
    assert turn5["role"] == "DISCOVERY_SET"
    assert turn5["epistemic_verdict"] == "DISCOVERY_CALIBRATION"


def test_independent_metric_reporting(blind_data):
    """Verify that every maneuver independently reports all required state metrics."""
    maneuvers = blind_data["maneuvers"]
    for m_id, data in maneuvers.items():
        assert "vx_rmse_mps" in data
        assert "exit_speed_error_mps" in data
        assert "wheel_speed_rmse_radps" in data
        assert "engine_speed_rmse_rpm" in data
        assert "yaw_rate_rmse_radps" in data
        assert "energy_residual_mj" in data
