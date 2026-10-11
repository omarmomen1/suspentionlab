"""Phase 3H.4 Autonomous Gear Selection Tests.

Verifies:
1. Complete elimination of maneuver gear metadata (gear_expected).
2. DriverControls.gear is ignored in autonomous shifting mode.
3. Target gear and shift phase execution depend solely on forward simulated states and ShiftSpec.
4. Anti-hunting lockout strictly prevents gear hunting within lockout window.
"""

import json
from pathlib import Path
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
)
from suspensionlab.physics.gear_inference import GearInferenceEngine
from suspensionlab.physics.engine_torque_model import PredictiveEngineTorqueModel
from suspensionlab.physics.powertrain_lap_sim import PowertrainCorrectedLapSimulator
from suspensionlab.physics.transmission_state_machine import (
    EndogenousTransmission,
    ShiftSpec,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_GEAR = DATA_DIR / "phase3h4_autonomous_gear_selection.json"


@pytest.fixture(scope="module")
def gear_sel_data():
    assert JSON_GEAR.exists(), f"Missing deliverable: {JSON_GEAR}"
    with open(JSON_GEAR, "r", encoding="utf-8") as f:
        return json.load(f)


def test_autonomous_gear_deliverable_metadata(gear_sel_data):
    """Verify deliverable flags confirm zero maneuver metadata."""
    assert gear_sel_data["autonomous_mode"] is True
    assert gear_sel_data["gear_expected_accessed"] is False
    assert "simulated_vx" in gear_sel_data["decision_inputs"]
    assert "driver_throttle" in gear_sel_data["decision_inputs"]
    assert len(gear_sel_data["window_a_decisions"]) >= 1


def test_driver_controls_gear_is_ignored():
    """Verify that passing dummy or erroneous gear in DriverControls does not alter autonomous gear."""
    p = DynamicVehicleParams()
    p.drivetrain_layout = "FWD"

    st1 = DynamicVehicleState(u_mps=25.0, omega_fl=75.0, omega_fr=75.0)
    tx1 = EndogenousTransmission(spec=ShiftSpec(), initial_gear=3)
    sim1 = PowertrainCorrectedLapSimulator(
        params=p,
        gear_engine=GearInferenceEngine(),
        torque_model=PredictiveEngineTorqueModel(),
        powertrain_mode="PREDICTIVE",
        autonomous_shifting=True,
        transmission=tx1,
        dt_fixed_s=0.005,
    )
    # Provide dummy gear=0
    ctrl1 = DriverControls(steering_deg=0.0, throttle=1.0, gear=0)
    d1 = sim1.compute_derivatives(st1, ctrl1)

    st2 = DynamicVehicleState(u_mps=25.0, omega_fl=75.0, omega_fr=75.0)
    tx2 = EndogenousTransmission(spec=ShiftSpec(), initial_gear=3)
    sim2 = PowertrainCorrectedLapSimulator(
        params=p,
        gear_engine=GearInferenceEngine(),
        torque_model=PredictiveEngineTorqueModel(),
        powertrain_mode="PREDICTIVE",
        autonomous_shifting=True,
        transmission=tx2,
        dt_fixed_s=0.005,
    )
    # Provide contradictory gear=6
    ctrl2 = DriverControls(steering_deg=0.0, throttle=1.0, gear=6)
    d2 = sim2.compute_derivatives(st2, ctrl2)

    assert d1["gear_active"] == d2["gear_active"] == 3
    assert d1["torque_engine_crank_nm"] == pytest.approx(d2["torque_engine_crank_nm"])
    assert d1["T_drive_fl"] == pytest.approx(d2["T_drive_fl"])


def test_anti_hunting_lockout_enforcement():
    """Verify that an upshift locks out subsequent shifts for t_lockout duration."""
    spec = ShiftSpec(
        upshift_rpm_min=5000.0,
        upshift_rpm_max=6000.0,
        t_torque_cut_s=0.010,
        t_clutch_handover_s=0.020,
        t_speed_sync_s=0.010,
        t_lockout_s=0.400,
    )
    tx = EndogenousTransmission(spec=spec, initial_gear=2)

    # Trigger upshift
    tx.step(sim_vx=24.0, sim_omega_drive=75.0, throttle=1.0, brake_bar=0.0, demanded_engine_torque_nm=300.0, dt=0.005)

    # Step through shift (40 ms = 8 steps at 5 ms)
    for _ in range(8):
        tx.step(sim_vx=24.0, sim_omega_drive=75.0, throttle=1.0, brake_bar=0.0, demanded_engine_torque_nm=300.0, dt=0.005)

    assert tx.current_state.gear == 3
    assert tx.lockout_timer > 0.350

    # Even with low RPM (which would normally trigger a downshift), lockout prevents shifting
    st = tx.step(sim_vx=10.0, sim_omega_drive=10.0, throttle=0.0, brake_bar=50.0, demanded_engine_torque_nm=0.0, dt=0.005)
    assert st.gear == 3
    assert st.shift_state.value == "IN_GEAR"
