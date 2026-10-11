"""
tests/test_dynamic_lap_sim_and_signed_banking.py
================================================
Tests for Dynamic Lap Simulator architecture, 14-DOF state vector, and signed banking physics.
"""

import pytest
import numpy as np

from suspensionlab.physics.lap_sim import (
    LapSimVehicle,
    TrackSegment,
    build_track_from_arrays,
    solve_lap,
    QuasiSteadyLapSimulator,
    QuasiSteadyLapResult,
)
from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleState,
    DriverControls,
)


def test_quasi_steady_lap_aliases():
    assert QuasiSteadyLapSimulator is LapSimVehicle
    assert QuasiSteadyLapResult is not None


def test_dynamic_lap_simulator_step():
    sim = DynamicLapSimulator(dt_fixed_s=0.001)
    state0 = DynamicVehicleState(u_mps=30.0, battery_soc=0.70)
    controls = DriverControls(throttle=1.0, steering_deg=5.0, ers_boost_request_kw=250.0)

    state1 = sim.step(state0, controls)
    assert state1.time_s == pytest.approx(0.001)
    assert state1.distance_m > 0.0
    assert state1.battery_soc < state0.battery_soc  # ERS deployed immediately
    assert len(state1.to_state_vector()) >= 18

    # Accelerate across transient tire relaxation window (100 ms)
    state_accel = state0
    for _ in range(100):
        state_accel = sim.step(state_accel, controls)
    assert state_accel.u_mps > state0.u_mps  # accelerating after tractive force build-up


def test_signed_banking_favorable_vs_adverse():
    # Construct vehicle
    veh = LapSimVehicle()
    
    # Track 1: Left turn with favorable banking (bank > 0)
    seg_favorable = [
        TrackSegment(distance=0.0, curvature=0.01, elevation=0.0, bank_angle=0.10, sector=1),
        TrackSegment(distance=100.0, curvature=0.01, elevation=0.0, bank_angle=0.10, sector=1),
    ]
    res_favorable = solve_lap(veh, seg_favorable, build_ggv=False)
    
    # Track 2: Left turn with adverse off-camber banking (bank < 0)
    seg_adverse = [
        TrackSegment(distance=0.0, curvature=0.01, elevation=0.0, bank_angle=-0.10, sector=1),
        TrackSegment(distance=100.0, curvature=0.01, elevation=0.0, bank_angle=-0.10, sector=1),
    ]
    res_adverse = solve_lap(veh, seg_adverse, build_ggv=False)
    
    # Favorable banking allows higher apex speed and faster lap time than off-camber
    assert res_favorable.max_speed_kmh > res_adverse.max_speed_kmh
    assert res_favorable.lap_time_s < res_adverse.lap_time_s


def test_wheel_loads_active_set_equilibrium_conservation():
    veh = LapSimVehicle()
    # High speed cornering (v=70 m/s, ay=25 m/s^2) that induces severe load transfer / wheel lift
    loads = veh.wheel_loads(v=70.0, ax=0.0, ay=25.0)
    # All 4 wheels must have non-negative normal load
    for fz in loads:
        assert fz >= 0.0

    # Total load must equal total vehicle weight + aero downforce
    W_expected = veh.mass_props.total_mass * 9.81 + veh.aero.downforce_front(70.0) + veh.aero.downforce_rear(70.0)
    assert sum(loads) == pytest.approx(W_expected, rel=1e-3)


def test_track_validator_geometry_continuity_and_closure():
    from suspensionlab.physics.lap_sim import TrackValidator
    # Smooth continuous 90-degree turn segment
    segments = [
        TrackSegment(distance=0.0, curvature=0.01, elevation=10.0, bank_angle=0.05, heading=0.0),
        TrackSegment(distance=50.0, curvature=0.01, elevation=10.5, bank_angle=0.05, heading=0.50),
        TrackSegment(distance=100.0, curvature=0.01, elevation=11.0, bank_angle=0.05, heading=1.00),
    ]
    report = TrackValidator.validate(segments, is_closed_circuit=False)
    assert report.is_geometrically_valid is True
    assert report.total_length_m == 100.0
    assert report.max_elevation_gradient < 0.10


def test_telemetry_nan_preservation_and_100hz_normalization():
    from suspensionlab.physics.telemetry_parser import parse_telemetry_csv, normalize_to_100hz
    csv_raw = (
        "time,speed,lat_g\n"
        "0.00,25.0,0.10\n"
        "0.02,26.0,INVALID_STR\n"
        "0.04,27.0,0.30\n"
        "0.06,28.0,0.40\n"
    )
    parsed = parse_telemetry_csv(csv_raw)
    assert len(parsed["time"]) == len(parsed["lat_g"]) == 4
    assert np.isnan(parsed["lat_g"][1])  # NaN preserved without shifting rows

    norm_100hz = normalize_to_100hz(parsed)
    assert "time" in norm_100hz
    dt_arr = np.diff(norm_100hz["time"])
    np.testing.assert_allclose(dt_arr, 0.01, atol=1e-5)

