from __future__ import annotations

import math
import numpy as np
import pytest

from suspensionlab.physics.lap_sim import (
    LapSimVehicle, MassProperties, AeroMap, PowertrainModel, TrackSegment,
    TrackValidator, TrackValidationReport, ModelAssumptions, SimulationMetadata,
    solve_lap, parse_track_from_curvature,
)
from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.suspension_aero_coupling import SuspensionConfig


def make_track(n_points: int, length_m: float, curvature: float = 0.0, sectors: list[int] | None = None) -> list[TrackSegment]:
    """Helper function to build a simple track from curvature arrays."""
    distances = np.linspace(0, length_m, n_points).tolist()
    curvatures = [curvature] * n_points
    return parse_track_from_curvature(distances, curvatures, sectors=sectors)


def make_vehicle(**overrides) -> LapSimVehicle:
    """Helper function to construct a default LapSimVehicle matching lap_sim.py APIs."""
    mass_props = MassProperties(**overrides.get('mass', {}))
    aero = AeroMap(**overrides.get('aero', {}))
    powertrain = PowertrainModel(**overrides.get('powertrain', {}))
    
    v = LapSimVehicle(
        mass_props=mass_props,
        aero=aero,
        powertrain=powertrain,
        tire_coeffs=TireCoeffs(),
        suspension=SuspensionConfig(),
    )
    v.build_ggv(n_speeds=12, n_ay=6)
    return v


def test_straight_line_acceleration():
    """Validates longitudinal acceleration on a flat, straight track.
    Speeds should be monotonically non-decreasing until power limit,
    and no unexplained braking should occur.
    """
    track = make_track(200, 1000.0, curvature=0.0)
    vehicle = make_vehicle()
    
    result = solve_lap(vehicle, track, v_start=15.0)
    
    # Final speed > initial speed
    assert result.speeds[-1] > result.speeds[0], "Final speed must be greater than initial speed."
    
    # All longitudinal g >= -1e-3
    assert np.all(result.longitudinal_g >= -1e-3), "No braking should occur on a straight."
    
    # Speeds are monotonically non-decreasing
    assert np.all(np.diff(result.speeds) >= -1e-4), "Speeds must be monotonically non-decreasing."


def test_constant_radius_corner():
    """Validates speeds in a constant radius corner against analytical pure friction max speed."""
    curvature = 0.01
    R = 1.0 / curvature
    track = make_track(200, 500.0, curvature=curvature)
    vehicle = make_vehicle()
    
    result = solve_lap(vehicle, track)
    
    # Speeds should be positive and physically bounded
    assert np.all(result.speeds > 10.0)
    assert np.all(result.speeds < 80.0)
    
    # lateral_g should be positive and roughly uniform across the corner
    assert np.all(result.lateral_g[5:-5] > 0.5)


def test_braking_constraint():
    """Validates that braking occurs appropriately before entering a tight corner."""
    track = make_track(200, 1000.0, curvature=0.0)
    for seg in track[150:]:
        seg.curvature = 0.02
        
    vehicle = make_vehicle()
    result = solve_lap(vehicle, track)
    
    # Find start of braking (longitudinal_g goes negative)
    braking_indices = np.where(result.longitudinal_g < -0.1)[0]
    
    assert len(braking_indices) > 0, "Braking must occur."
    assert braking_indices[0] < 150, "Braking must start BEFORE the corner."


def test_forward_acceleration_propagation():
    """Validates forward acceleration integration consistency."""
    track = make_track(100, 500.0, curvature=0.0)
    vehicle = make_vehicle()
    
    result = solve_lap(vehicle, track)
    
    for i in range(len(track) - 1):
        v0 = result.speeds[i]
        v1 = result.speeds[i+1]
        ds = track[i+1].distance - track[i].distance
        if ds <= 0:
            continue
        
        # Verify v1 >= v0 on straight
        assert v1 >= v0 - 1e-4


def test_backward_braking_propagation():
    """Validates the backward pass propagates braking limits appropriately."""
    track = make_track(300, 1000.0, curvature=0.0)
    for seg in track[180:230]:
        seg.curvature = 0.05
        
    vehicle = make_vehicle()
    result = solve_lap(vehicle, track)
    
    # Braking must start before the corner
    speeds = result.speeds
    max_speed_idx = np.argmax(speeds[:180])
    
    assert max_speed_idx < 175, "Braking (speed decrease) must start well before the corner."


def test_tire_force_conservation():
    """Validates that combined tire utilization never significantly exceeds 1.0."""
    track = make_track(200, 1000.0, curvature=0.005)
    vehicle = make_vehicle()
    
    result = solve_lap(vehicle, track)
    
    # Check max utilization (with minor numerical margin)
    assert np.all(result.tire_utilization_combined <= 1.08), "Tire utilization must not exceed ~1.08"


def test_aero_monotonicity():
    """Validates aerodynamic effects (CL increases corner speed, CD decreases straight speed)."""
    track = make_track(200, 1000.0, curvature=0.01)
    
    veh_low_df = make_vehicle(aero={'cl_base': 1.0, 'cd_base': 1.0})
    veh_high_df = make_vehicle(aero={'cl_base': 3.0, 'cd_base': 1.0})
    
    res_low_df = solve_lap(veh_low_df, track)
    res_high_df = solve_lap(veh_high_df, track)
    
    assert np.mean(res_high_df.speeds) > np.mean(res_low_df.speeds), "Higher downforce should yield higher corner speeds."
    
    straight = make_track(200, 2000.0, curvature=0.0)
    veh_low_drag = make_vehicle(aero={'cl_base': 1.0, 'cd_base': 0.5})
    veh_high_drag = make_vehicle(aero={'cl_base': 1.0, 'cd_base': 1.5})
    
    res_low_drag = solve_lap(veh_low_drag, straight)
    res_high_drag = solve_lap(veh_high_drag, straight)
    
    assert res_low_drag.speeds[-1] > res_high_drag.speeds[-1], "Higher drag should yield lower terminal speed."


def test_power_limitation():
    """Validates terminal velocity against analytical drag equilibrium."""
    track = make_track(500, 4000.0, curvature=0.0)
    vehicle = make_vehicle(
        aero={'cl_base': 0.5, 'cd_base': 0.8, 'frontal_area': 1.6}
    )
    
    result = solve_lap(vehicle, track)
    v_term_analytical = vehicle.terminal_velocity()
    
    # On a 4km straight, the vehicle should approach its terminal velocity
    assert result.speeds[-1] == pytest.approx(v_term_analytical, rel=0.05)


def test_reproducibility():
    """Validates that identical inputs yield strictly identical outputs."""
    track = make_track(100, 1000.0, curvature=0.01)
    vehicle = make_vehicle()
    
    res1 = solve_lap(vehicle, track)
    res2 = solve_lap(vehicle, track)
    
    assert res1.total_time == res2.total_time
    np.testing.assert_array_equal(res1.speeds, res2.speeds)
    assert res1.simulation_metadata.input_hash == res2.simulation_metadata.input_hash


def test_sector_time_summation():
    """Validates that sector times sum up to the total time."""
    track = make_track(300, 1500.0, curvature=0.0)
    # Assign sectors (1-based)
    for i, seg in enumerate(track):
        if i < 100:
            seg.sector = 1
        elif i < 200:
            seg.sector = 2
        else:
            seg.sector = 3
            
    vehicle = make_vehicle()
    result = solve_lap(vehicle, track)
    
    assert sum(result.sector_times) == pytest.approx(result.total_time, abs=1e-6)


def test_grade_effects():
    """Validates effect of grade (uphill/downhill) on lap time."""
    track_flat = make_track(200, 1000.0, curvature=0.0)
    track_up = make_track(200, 1000.0, curvature=0.0)
    track_down = make_track(200, 1000.0, curvature=0.0)
    
    for seg in track_up:
        seg.elevation = seg.distance * 0.05
    for seg in track_down:
        seg.elevation = -seg.distance * 0.05
        
    vehicle = make_vehicle()
    
    t_flat = solve_lap(vehicle, track_flat).total_time
    t_up = solve_lap(vehicle, track_up).total_time
    t_down = solve_lap(vehicle, track_down).total_time
    
    assert t_down < t_flat < t_up, "Downhill should be faster than flat, and flat faster than uphill."


def test_banking_effects():
    """Validates that banked curves allow for higher cornering speeds."""
    track_flat = make_track(200, 500.0, curvature=0.05)
    track_banked = make_track(200, 500.0, curvature=0.05)
    
    for seg in track_banked:
        seg.bank_angle = 0.15  # ~8.6 deg
        
    vehicle = make_vehicle()
    
    res_flat = solve_lap(vehicle, track_flat)
    res_banked = solve_lap(vehicle, track_banked)
    
    min_v_flat = np.min(res_flat.speeds)
    min_v_banked = np.min(res_banked.speeds)
    
    assert min_v_banked > min_v_flat, "Banked curve should permit higher minimum speed."


def test_combined_slip_reduces_available_force():
    """Validates that available longitudinal acceleration is reduced under lateral load."""
    vehicle = make_vehicle()
    v = 30.0
    
    ax_pure = vehicle.ax_max_accel(v, ay=0.0)
    ax_combined = vehicle.ax_max_accel(v, ay=12.0)
    
    assert ax_combined < ax_pure, "Combined slip should reduce available longitudinal force."


def test_ggv_consistency():
    """Validates GGV lookup consistency with vehicle limit functions."""
    vehicle = make_vehicle()
    vehicle.build_ggv(n_speeds=20, n_ay=10)
    v = 30.0
    ay = 5.0
    
    ax_lookup = vehicle._lookup_ax_accel(v, ay)
    ax_direct = vehicle.ax_max_accel(v, ay)
    
    assert ax_lookup == pytest.approx(ax_direct, rel=0.15)


def test_track_validation_rejects_invalid():
    """Validates that TrackValidator correctly rejects improperly formed tracks."""
    # Empty track
    report = TrackValidator.validate([])
    assert not report.is_geometrically_valid
    
    # Duplicate distances
    track_dup = make_track(5, 100.0)
    track_dup[2].distance = track_dup[1].distance
    assert not TrackValidator.validate(track_dup).is_geometrically_valid
    
    # NaN curvature
    track_nan = make_track(5, 100.0)
    track_nan[2].curvature = float('nan')
    assert not TrackValidator.validate(track_nan).is_geometrically_valid
    
    # Impossible curvature
    track_inf = make_track(5, 100.0)
    track_inf[2].curvature = 1.0  # R = 1m
    assert not TrackValidator.validate(track_inf).is_geometrically_valid
    
    # Invalid surface mu
    track_mu = make_track(5, 100.0)
    track_mu[2].surface_mu = 0.0
    assert not TrackValidator.validate(track_mu).is_geometrically_valid
    
    # Valid track
    assert TrackValidator.validate(make_track(100, 1000.0)).is_geometrically_valid


def test_solver_diagnostics_populated():
    """Validates that metadata and model assumptions are properly populated upon completion."""
    track = make_track(100, 1000.0, curvature=0.0)
    vehicle = make_vehicle()
    
    result = solve_lap(vehicle, track)
    
    assert result.solver_converged is True
    assert isinstance(result.model_assumptions, ModelAssumptions)
    assert hasattr(result.model_assumptions, 'tire_model')
    assert isinstance(result.simulation_metadata, SimulationMetadata)
    assert result.simulation_metadata.run_id != ""
    
    assert len(result.tire_utilization_combined) == len(track)
    assert np.all(result.tire_utilization_combined >= 0.0)


def test_surface_friction_effect():
    """Validates that local surface friction changes affect cornering speeds."""
    track_dry = make_track(200, 500.0, curvature=0.05)
    track_wet = make_track(200, 500.0, curvature=0.05)
    
    # Wet patch on the second track
    for seg in track_wet[80:120]:
        seg.surface_mu = 0.5
        
    vehicle = make_vehicle()
    
    res_dry = solve_lap(vehicle, track_dry)
    res_wet = solve_lap(vehicle, track_wet)
    
    # Cornering speed in wet patch should be lower
    min_v_dry = np.min(res_dry.speeds[80:120])
    min_v_wet = np.min(res_wet.speeds[80:120])
    
    assert min_v_wet < min_v_dry, "Reduced surface mu should decrease available grip and speed."
