"""Phase 3H.2 Engine Torque Provenance & Calibration Tests.

Verifies:
1. Strict epistemic classification across all engine torque models.
2. Calibration constraint compliance: calibrated strictly on Turn 5 discovery window.
3. Monotonic throttle mapping and bounded torque envelope.
4. Governed overrun drag cutoff at closed throttle.
"""

import json
from pathlib import Path
import pytest

from suspensionlab.physics.engine_torque_model import (
    SyntheticEngineTorqueModel,
    PredictiveEngineTorqueModel,
    PredictiveEngineTorqueConfig,
    ActuatorReplayEngineTorque,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TORQUE_MAP_JSON = DATA_DIR / "phase3h2_engine_torque_map.json"


@pytest.fixture(scope="module")
def torque_map_audit_data():
    assert TORQUE_MAP_JSON.exists(), f"Missing torque map file: {TORQUE_MAP_JSON}"
    with open(TORQUE_MAP_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_epistemic_classification_labels():
    """Verify each engine torque model emits its exact authorized epistemic classification."""
    synth = SyntheticEngineTorqueModel()
    assert synth.epistemic_classification == "DERIVED"

    replay = ActuatorReplayEngineTorque()
    assert replay.epistemic_classification == "BOUNDARY_REPLAY"

    pred = PredictiveEngineTorqueModel()
    assert pred.epistemic_classification == "MODEL_SUPPORTED"


def test_calibration_window_provenance(torque_map_audit_data):
    """Verify predictive model was calibrated strictly on Turn 5 and not on blind validation intervals."""
    calib = torque_map_audit_data["calibration_window"]
    assert calib["maneuver"] == "Turn 5 Tight Complex"
    assert calib["role"] == "DISCOVERY_SET"
    assert calib["time_window_s"] == [74.0, 83.0]


def test_predictive_model_monotonic_and_bounded():
    """Verify predictive model torque increases monotonically with throttle and stays within physical bounds."""
    model = PredictiveEngineTorqueModel()

    # Across various RPMs
    for rpm in [2000.0, 3500.0, 5000.0]:
        tq_0 = model.compute_torque(throttle=0.0, engine_rpm=rpm)
        tq_20 = model.compute_torque(throttle=0.20, engine_rpm=rpm)
        tq_50 = model.compute_torque(throttle=0.50, engine_rpm=rpm)
        tq_100 = model.compute_torque(throttle=1.0, engine_rpm=rpm)

        assert tq_0 <= 0.0, "Zero throttle must produce negative overrun drag"
        assert tq_20 > 0.0, "20% throttle must produce positive drive torque"
        assert tq_50 > tq_20, "Torque must increase monotonically with throttle"
        assert tq_100 >= tq_50, "WOT torque must be maximum"
        assert tq_100 <= 400.0, "WOT torque must not exceed physical engine limits (400 Nm)"


def test_predictive_model_overrun_cutoff():
    """Verify overrun drag applies only below overrun threshold."""
    config = PredictiveEngineTorqueConfig(throttle_overrun_threshold=0.03)
    model = PredictiveEngineTorqueModel(config=config)

    tq_closed = model.compute_torque(throttle=0.0, engine_rpm=3000.0)
    assert tq_closed < -20.0, "Closed throttle must engage overrun drag"

    tq_open = model.compute_torque(throttle=0.10, engine_rpm=3000.0)
    assert tq_open > 0.0, "Open throttle must transition cleanly to positive torque"
