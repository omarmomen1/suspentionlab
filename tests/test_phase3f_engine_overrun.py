"""
tests/test_phase3f_engine_overrun.py
====================================
Test Suite 3 for Phase 3F: Governed Engine Overrun Drag Model.
"""

from pathlib import Path
import pytest
import numpy as np

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    EngineOverrunMap,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_engine_overrun_map_governed_profile():
    """Verify EngineOverrunMap complies with physical telemetry calibration."""
    ovr = EngineOverrunMap()

    # 1. Idle protection (anti-stall)
    assert ovr.compute_overrun_torque(800.0, throttle=0.0) == 0.0
    assert ovr.compute_overrun_torque(500.0, throttle=0.0) == 0.0

    # 2. Operating range negative retarding torque
    t_2000 = ovr.compute_overrun_torque(2000.0, throttle=0.0)
    t_3500 = ovr.compute_overrun_torque(3500.0, throttle=0.0)
    t_4500 = ovr.compute_overrun_torque(4500.0, throttle=0.0)

    assert -32.0 <= t_2000 <= -25.0, f"Expected ~ -28 Nm, got {t_2000}"
    assert -32.0 <= t_3500 <= -28.0, f"Expected ~ -30 Nm, got {t_3500}"
    assert pytest.approx(t_4500, rel=1e-3) == -31.4

    # 3. Throttle suppression
    assert ovr.compute_overrun_torque(3500.0, throttle=0.10) == 0.0
    assert ovr.compute_overrun_torque(3500.0, throttle=1.00) == 0.0

    # 4. Smooth blend in transition (0.01 < thr < 0.05)
    t_thr_002 = ovr.compute_overrun_torque(3500.0, throttle=0.02)
    assert t_3500 < t_thr_002 < 0.0


def test_overrun_drivetrain_torque_and_fwd_routing():
    """Verify overrun torque is routed to driven front axle with correct gear ratio multiplication."""
    ovr = EngineOverrunMap(is_enabled=True)
    p = DynamicVehicleParams(
        drivetrain_layout="FWD",
        drivetrain_efficiency=0.92,
        gear_ratios=[14.5, 9.633, 6.8, 5.1, 4.0, 3.2],
        engine_overrun_map=ovr,
    )
    sim = DynamicLapSimulator(params=p)

    # In 2nd gear at 2500 RPM wheel speed
    w_drive = 2500.0 / 9.633 * (2.0 * np.pi / 60.0)
    st = DynamicVehicleState(u_mps=15.0, omega_fl=w_drive, omega_fr=w_drive, omega_rl=w_drive, omega_rr=w_drive)
    ctrl = DriverControls(throttle=0.0, brake=0.0, gear=2)

    derivs = sim.compute_derivatives(st, ctrl)

    t_eng = derivs["T_overrun_engine"]
    assert -32.0 <= t_eng <= -28.0

    t_axle = derivs["T_overrun_axle"]
    expected_axle = t_eng * 9.633 * 0.92
    assert pytest.approx(t_axle, rel=1e-3) == expected_axle

    # Front wheel drive torques must be negative and share the overrun axle torque
    assert derivs["T_drive_fl"] < 0.0
    assert derivs["T_drive_fr"] < 0.0
    assert pytest.approx(derivs["T_drive_fl"] + derivs["T_drive_fr"], rel=1e-3) == expected_axle

    # Rear wheels must receive zero drive torque
    assert derivs["T_drive_rl"] == 0.0
    assert derivs["T_drive_rr"] == 0.0


def test_overrun_toggle_disables_retardation():
    """Verify is_enabled=False eliminates overrun torque completely."""
    ovr = EngineOverrunMap(is_enabled=False)
    p = DynamicVehicleParams(engine_overrun_map=ovr)
    sim = DynamicLapSimulator(params=p)
    st = DynamicVehicleState(u_mps=20.0, omega_fl=60.0, omega_fr=60.0)
    ctrl = DriverControls(throttle=0.0, brake=0.0, gear=2)

    derivs = sim.compute_derivatives(st, ctrl)
    assert derivs["T_overrun_engine"] == 0.0
    assert derivs["T_overrun_axle"] == 0.0
    assert derivs["T_drive_fl"] == 0.0
    assert derivs["T_drive_fr"] == 0.0
