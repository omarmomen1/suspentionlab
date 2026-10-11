"""Phase 3H.3 Transmission State Vector Specification Tests.

Verifies:
1. Complete definition of 6-element transmission state vector:
   (gear, clutch_state, shift_state, shift_timer, input_shaft_speed, output_shaft_speed).
2. Endogenous predictability from simulated states (Vx, wheel speeds, throttle, brake, ShiftSpec).
3. Prohibition of measured telemetry feedback in state prediction.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h3_transmission_state.json"


@pytest.fixture(scope="module")
def tx_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_transmission_state_variables_present(tx_data):
    """Verify all 6 required transmission state variables are specified."""
    vars_dict = tx_data["state_variables"]
    required_vars = [
        "gear",
        "clutch_state",
        "shift_state",
        "shift_timer",
        "input_shaft_speed",
        "output_shaft_speed",
    ]
    for var_name in required_vars:
        assert var_name in vars_dict, f"Missing state variable: {var_name}"
        assert "governing_physical_law" in vars_dict[var_name] or "endogenous_governing_law" in vars_dict[var_name]


def test_endogenous_predictability_without_telemetry(tx_data):
    """Verify transmission states are predictable without measured telemetry feedback."""
    audit = tx_data["endogenous_predictability_audit"]
    assert audit["can_predict_from_simulated_states"] is True
    assert audit["telemetry_feedback_required"] is False
    assert len(audit["required_simulated_inputs"]) >= 4
    assert len(audit["prohibited_measured_inputs"]) >= 4
