"""
tests/test_phase3d_pitch_decoupling.py
======================================
Verification tests for Phase 3D Change #2: Grade-Decoupled Chassis Pitch.
Ensures:
1. Road grade variations do not induce false suspension deflection pitch response.
2. Relative suspension displacements (zf - zr) produce exact chassis suspension pitch.
3. Raw IMU pitch and road grade remain independently preserved and traceable.
4. Braking pitch attitude dynamics are evaluated against suspension pitch, not grade-contaminated IMU pitch.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
)


def test_grade_changes_do_not_affect_suspension_pitch():
    """Verify varying road grade creates zero false suspension deflection pitch."""
    p = DynamicVehicleParams()
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    st = DynamicVehicleState(u_mps=25.0)
    ctrl = DriverControls(throttle=0.1)

    # Flat road (grade = 0.0)
    derivs_flat = sim.compute_derivatives(st, ctrl, road_grade_rad=0.0)
    pitch_susp_flat = derivs_flat["pitch_suspension_rad"]
    pitch_imu_flat = derivs_flat["pitch_imu_raw_rad"]

    # Steep 8% uphill road (grade = +0.08 rad)
    grade_uphill = 0.08
    derivs_uphill = sim.compute_derivatives(st, ctrl, road_grade_rad=grade_uphill)
    pitch_susp_uphill = derivs_uphill["pitch_suspension_rad"]
    pitch_imu_uphill = derivs_uphill["pitch_imu_raw_rad"]

    # Suspension pitch must be identical because chassis suspension deflections are identical
    assert math.isclose(pitch_susp_flat, pitch_susp_uphill, abs_tol=1e-6), (
        f"Grade change corrupted suspension pitch: {pitch_susp_flat} vs {pitch_susp_uphill}"
    )

    # Raw IMU pitch must reflect the track grade
    assert math.isclose(pitch_imu_uphill - pitch_imu_flat, grade_uphill, abs_tol=1e-5), (
        "IMU pitch did not capture the independent track grade angle."
    )


def test_relative_suspension_displacement_produces_chassis_pitch():
    """Verify theta_susp = (zf - zr) / Lwb under pure suspension displacement."""
    p = DynamicVehicleParams(wheelbase_m=2.63, a_m=1.05, b_m=1.58)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    # Create front compression: def_fl = def_fr = -0.020 m (-20 mm), rear zero
    st = DynamicVehicleState(
        u_mps=20.0,
        z_u_fl=0.020, # Wheel up relative to chassis = 20mm bump compression
        z_u_fr=0.020,
        z_u_rl=0.0,
        z_u_rr=0.0,
    )
    ctrl = DriverControls()
    derivs = sim.compute_derivatives(st, ctrl, road_grade_rad=0.0)

    # def_fl = z_s_fl - z_u_fl = 0 - 0.020 = -0.020m
    # def_rl = 0.0m
    # z_f_avg = -0.020, z_r_avg = 0.0
    # theta_susp = (-0.020 - 0.0) / 2.63 = -0.00760456 rad
    expected_pitch = -0.020 / p.wheelbase_m
    assert math.isclose(derivs["pitch_suspension_rad"], expected_pitch, rel_tol=1e-4), (
        f"Suspension pitch {derivs['pitch_suspension_rad']} != expected {expected_pitch}"
    )


def test_braking_evaluates_against_suspension_pitch_on_grade():
    """Verify braking dive is reflected in suspension pitch even when on opposing grade."""
    p = DynamicVehicleParams(wheelbase_m=2.63, a_m=1.05, b_m=1.58, brake_max_torque_nm=4800.0)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    # Vehicle braking on an uphill track grade (like Thunderhill Turn 1 braking on 4.2 deg grade)
    grade_rad = math.radians(4.2)
    st = DynamicVehicleState(u_mps=25.0)
    ctrl = DriverControls(brake=0.8)

    # Step simulation under braking
    st_next = sim.step(st, ctrl, road_grade_rad=grade_rad)

    # Suspension pitch should show dive / compression difference
    assert st_next.pitch_suspension_rad is not None
    assert st_next.pitch_imu_raw_rad is not None
    assert st_next.road_grade_rad == grade_rad

    # Raw IMU pitch is shifted by grade_rad (+0.073 rad)
    assert st_next.pitch_imu_raw_rad > st_next.pitch_suspension_rad
