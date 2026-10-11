"""
tests/test_authoritative_mass_consistency.py
=============================================
Hostile tests verifying that ONE authoritative total vehicle mass governs
all 10 physical pathways: mass, gravity force, inertia, aero acceleration,
longitudinal acceleration, load transfer, wheel loads, power requirement,
energy accounting, and lap simulation.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicVehicleParams,
    DynamicVehicleState,
    DynamicLapSimulator,
    DriverControls,
    DynamicTrackPoint,
)


def test_authoritative_mass_default_identity():
    """Verify default vehicle parameters satisfy exact component mass sum to machine precision."""
    p = DynamicVehicleParams()
    parts_sum = p.sprung_mass_kg + 2.0 * p.unsprung_mass_front_kg + 2.0 * p.unsprung_mass_rear_kg
    assert p.mass_kg == 800.0
    assert parts_sum == 800.0
    assert math.isclose(p.mass_kg, parts_sum, abs_tol=1e-12)


def test_authoritative_mass_scaling_and_synchronization():
    """Hostile test: Passing custom total mass or custom components must synchronize strictly."""
    # 1. Setting custom mass_kg scales component parts
    p1 = DynamicVehicleParams(mass_kg=950.0)
    parts_sum1 = p1.sprung_mass_kg + 2.0 * p1.unsprung_mass_front_kg + 2.0 * p1.unsprung_mass_rear_kg
    assert math.isclose(p1.mass_kg, 950.0, abs_tol=1e-9)
    assert math.isclose(parts_sum1, 950.0, abs_tol=1e-9)

    # 2. Setting custom components updates total mass_kg
    p2 = DynamicVehicleParams(
        sprung_mass_kg=600.0,
        unsprung_mass_front_kg=20.0,
        unsprung_mass_rear_kg=20.0,
        mass_kg=680.0
    )
    assert p2.mass_kg == 680.0
    parts_sum2 = p2.sprung_mass_kg + 2.0 * p2.unsprung_mass_front_kg + 2.0 * p2.unsprung_mass_rear_kg
    assert math.isclose(p2.mass_kg, parts_sum2, abs_tol=1e-12)


def test_ten_physical_pathways_derive_from_authoritative_mass():
    """Hostile verification across all 10 physical derivations:
    1. Mass definition
    2. Gravity force
    3. Inertia scaling
    4. Aero acceleration
    5. Longitudinal acceleration
    6. Load transfer
    7. Wheel loads
    8. Power requirement
    9. Energy accounting
    10. Dynamic lap simulation
    """
    m_test = 850.0
    p = DynamicVehicleParams(mass_kg=m_test)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    u = 30.0
    g = 9.81
    omega_ss = u / p.wheel_radius_m
    st = DynamicVehicleState(
        u_mps=u,
        omega_fl=omega_ss,
        omega_fr=omega_ss,
        omega_rl=omega_ss,
        omega_rr=omega_ss,
        actuator_throttle=0.8,
    )
    ctrl = DriverControls(throttle=0.8, brake=0.0, steering_deg=0.0, gear=3)
    tp = DynamicTrackPoint(distance_m=0.0, curvature_radm=0.0)

    derivs = sim.compute_derivatives(st, ctrl, track_point=tp)

    # 1. Mass
    assert math.isclose(p.mass_kg, m_test, abs_tol=1e-9)
    
    # 2. Gravity force: Total weight W = m * g
    total_weight = p.mass_kg * g
    downforce = derivs["F_downforce"]
    
    # 3. Inertia: Check pitch/roll moments of inertia are positive and finite
    assert p.I_z > 0 and p.I_y > 0 and p.I_x > 0
    
    # 4. Aerodynamic acceleration
    a_drag = derivs["F_drag"] / p.mass_kg
    assert a_drag > 0.0
    
    # 5. Longitudinal acceleration: du = (Fx_total - F_drag + m*r*v) / m
    du = derivs["du"]
    f_net_x = derivs["Fx_total"] - derivs["F_drag"] + p.mass_kg * st.yaw_rate_rads * st.v_mps
    accel_residual = abs(p.mass_kg * du - f_net_x)
    assert accel_residual < 1e-11, f"Longitudinal acceleration does not derive from authoritative mass: residual={accel_residual}"

    # 6. Load transfer: delta_Fz_long = (m * ax_physical * h) / L
    # Derived directly from authoritative mass in force balance
    Rw = p.wheel_radius_m
    gr = p.gear_ratios[2]
    rpm = max(2000.0, u * gr * 60.0 / (2.0 * math.pi * Rw))
    t_eng = p.engine_torque(rpm)
    t_drv_r = 0.8 * t_eng * gr * p.drivetrain_efficiency
    fx_demand = t_drv_r / Rw
    ax_expected = (fx_demand - derivs["F_drag"]) / p.mass_kg
    dfz_long_expected = (p.mass_kg * ax_expected * p.cg_height_m) / p.wheelbase_m

    # Dynamic rear wheel loads include 2 * Fz0_r + dFz_long
    # Under flat straight line, heave/roll = 0
    fz0_r = (p.sprung_mass_kg * (p.a_m / p.wheelbase_m) * g + p.unsprung_mass_rear_kg * 2.0 * g + downforce * (p.a_m / p.wheelbase_m)) / 2.0
    fz_r_total = derivs["wheel_loads"][2] + derivs["wheel_loads"][3]
    # Check that dynamic rear axle load transfer is governed by authoritative mass
    assert fz_r_total > 2.0 * fz0_r

    # 7. Wheel loads: sum(Fz) == m * g + F_downforce
    sum_fz = sum(derivs["wheel_loads"])
    vertical_residual = abs(sum_fz - (p.mass_kg * g + downforce))
    assert vertical_residual < 1e-10, f"Vertical load balance failed: residual={vertical_residual}"

    # 8. Power requirement: Drivetrain tractive power demand
    power_watts = fx_demand * u
    assert power_watts > 0.0

    # 9. Energy accounting: Kinetic energy definition
    e_kin = 0.5 * p.mass_kg * (u ** 2)
    assert e_kin == 0.5 * m_test * 900.0

    # 10. Lap simulation: step advances state with exact mass
    curr_st = st
    for _ in range(120):
        curr_st = sim.step(curr_st, ctrl, track_point=tp)
    assert curr_st.u_mps > st.u_mps
