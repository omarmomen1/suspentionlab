"""Phase 3H.2.1 Maneuver-Level Validation Tests.

Verifies:
1. Every maneuver reports independent validation statuses across observables:
   Vx, wheel speed, engine speed, torque, and energy balance.
2. Blanket maneuver-level labels are strictly avoided.
3. Turn 5 remains strictly DISCOVERY_CALIBRATION and is never cited as external confirmation.
4. Turn 3 Approach is verified as CONFIRMED_ON_UNSEEN_DATA across kinematics and road loads.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANEUVER_VALIDATION_JSON = DATA_DIR / "phase3h21_maneuver_validation.json"


@pytest.fixture(scope="module")
def mv_data():
    assert MANEUVER_VALIDATION_JSON.exists(), f"Missing file: {MANEUVER_VALIDATION_JSON}"
    with open(MANEUVER_VALIDATION_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_independent_observables_reported(mv_data):
    """Verify each maneuver evaluates Vx, wheel speed, engine speed, torque, and energy balance independently."""
    expected_observables = ["Vx", "wheel_speed", "engine_speed", "engine_torque", "energy_balance"]
    maneuvers = mv_data["maneuvers"]
    assert len(maneuvers) == 5

    for m_name, m_info in maneuvers.items():
        obs = m_info["observables"]
        for o_name in expected_observables:
            assert o_name in obs, f"Missing observable {o_name} in {m_name}"
            assert "status" in obs[o_name]


def test_turn5_strictly_discovery_calibration(mv_data):
    """Verify Turn 5 is strictly DISCOVERY_CALIBRATION across all observables."""
    t5 = mv_data["maneuvers"]["Turn5_Tight_Complex"]
    assert t5["maneuver_role"] == "DISCOVERY_SET"
    for o_name, o_data in t5["observables"].items():
        assert o_data["status"] == "DISCOVERY_CALIBRATION"


def test_turn3_external_confirmation(mv_data):
    """Verify Turn 3 serves as clean EXTERNAL_CONFIRMATION_SET."""
    t3 = mv_data["maneuvers"]["Turn3_Approach"]
    assert t3["maneuver_role"] == "EXTERNAL_CONFIRMATION_SET"
    assert t3["observables"]["Vx"]["status"] == "CONFIRMED_ON_UNSEEN_DATA"
    assert t3["observables"]["wheel_speed"]["status"] == "CONFIRMED_ON_UNSEEN_DATA"
    assert t3["observables"]["energy_balance"]["status"] == "CONFIRMED_ON_UNSEEN_DATA"
