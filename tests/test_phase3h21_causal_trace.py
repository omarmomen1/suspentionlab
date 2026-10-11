"""Phase 3H.2.1 Engine-Speed Causal Trace & Anti-Leakage Tests.

Verifies:
1. Engine speed in Path B is classified as ALGEBRAICALLY_RECONSTRUCTED_KINEMATIC_STATE.
2. Engine speed is neither a free differential state nor influenced by measured RPM / wheel speed.
3. Prohibited measured telemetry channels produce exactly zero derivative on predicted outputs:
   d(PredictedTorque)/d(MeasuredRPM) == 0.0
   d(PredictedTorque)/d(MeasuredTorque) == 0.0
   d(VehicleDu)/d(MeasuredRPM) == 0.0
4. Physical dynamic coupling between simulated wheel speed and torque model is healthy (> 0).
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CAUSAL_TRACE_JSON = DATA_DIR / "phase3h21_causal_trace.json"


@pytest.fixture(scope="module")
def causal_data():
    assert CAUSAL_TRACE_JSON.exists(), f"Missing file: {CAUSAL_TRACE_JSON}"
    with open(CAUSAL_TRACE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_engine_speed_classification(causal_data):
    """Verify engine speed is classified as an algebraically reconstructed kinematic state."""
    classification = causal_data["classification_of_engine_speed"]
    assert classification["category"] == "ALGEBRAICALLY_RECONSTRUCTED_KINEMATIC_STATE"
    assert classification["is_true_differential_state"] is False
    assert classification["is_algebraically_reconstructed"] is True
    assert classification["is_influenced_by_measured_rpm"] is False
    assert classification["is_influenced_by_measured_wheelspeed"] is False


def test_prohibited_telemetry_zero_leakage_derivative(causal_data):
    """Verify d(PredictedOutput) / d(MeasuredTelemetry) == 0 for all prohibited channels."""
    derivs = causal_data["anti_leakage_numerical_derivatives"]
    assert derivs["d_PredictedTorque_d_MeasuredRPM"] == 0.0
    assert derivs["d_VehicleDu_d_MeasuredRPM"] == 0.0
    assert derivs["d_PredictedTorque_d_MeasuredTorque"] == 0.0
    assert derivs["d_VehicleDu_d_MeasuredTorque"] == 0.0
    assert derivs["leakage_test_passed"] is True


def test_physical_dynamic_coupling_preserved(causal_data):
    """Verify d(VehicleState) / d(PredictedPowertrain) is physically coupled (> 0)."""
    coupling = causal_data["physical_dynamic_coupling_derivative"]
    assert coupling["d_PredictedTorque_d_SimulatedWheelSpeed"] > 0.0
    assert coupling["physical_coupling_verified"] is True
