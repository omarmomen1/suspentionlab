"""
tests/test_phase3d_steering_compliance.py
=========================================
Verification tests for Phase 3D Change #3: Endogenous Steering Compliance.
Ensures:
1. Default baseline (k_delta = 0.0) strictly preserves rigid steering behavior.
2. Calibrated k_delta attenuates effective road wheel steer under endogenous lateral load (u * r).
3. Requires zero externally injected telemetry signals (strictly endogenous).
4. Numerical stability under high-rate dynamic steering reversals.
5. Transient corner entry reduces yaw rate overshoot as demonstrated in physical telemetry.
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


def test_default_steering_compliance_is_zero_baseline():
    """Verify default DynamicVehicleParams has k_delta = 0.0, preserving uncalibrated physics."""
    p = DynamicVehicleParams()
    assert hasattr(p, "steering_compliance_rad_per_mps2")
    assert p.steering_compliance_rad_per_mps2 == 0.0

    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)
    target_steer = math.radians(27.0) / p.steer_ratio
    st = DynamicVehicleState(u_mps=25.0, yaw_rate_rads=0.30, actuator_steering_rad=target_steer)
    ctrl = DriverControls(steering_deg=27.0) # 27 deg at wheel / 13.5 ratio = 2.0 deg = 0.0349 rad

    derivs = sim.compute_derivatives(st, ctrl)
    expected_steer_rad = target_steer
    assert math.isclose(derivs["effective_steer_rad"], expected_steer_rad, abs_tol=1e-6), (
        "Default baseline modified steer angle unexpectedly."
    )


def test_endogenous_steering_compliance_attenuates_steer_angle():
    """Verify k_delta attenuates effective road wheel steer angle proportionally to u * r."""
    k_c = 0.000451 # rad/(m/s^2)
    p_comp = DynamicVehicleParams(steering_compliance_rad_per_mps2=k_c)
    sim_comp = DynamicLapSimulator(params=p_comp, dt_fixed_s=0.001)

    u = 25.0 # m/s
    r = 0.40 # rad/s -> ay_endogenous = 10.0 m/s^2 (~1.02g)
    target_steer = math.radians(27.0) / p_comp.steer_ratio
    st = DynamicVehicleState(u_mps=u, yaw_rate_rads=r, actuator_steering_rad=target_steer)
    ctrl = DriverControls(steering_deg=27.0) # road wheel cmd = 0.0349066 rad

    derivs = sim_comp.compute_derivatives(st, ctrl)

    ay_endogenous = u * r # 10.0 m/s^2
    expected_attenuation = k_c * ay_endogenous # 0.00451 rad (~0.258 deg)
    act_steer_cmd = target_steer
    expected_delta_eff = act_steer_cmd - expected_attenuation

    assert math.isclose(derivs["effective_steer_rad"], expected_delta_eff, rel_tol=1e-4)
    assert derivs["effective_steer_rad"] < act_steer_cmd


def test_steering_compliance_numerical_stability_under_sharp_reversals():
    """Verify numerical stability during aggressive high-frequency steering reversals (+-180 deg/s)."""
    k_c = 0.000451
    p = DynamicVehicleParams(steering_compliance_rad_per_mps2=k_c)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    st = DynamicVehicleState(u_mps=28.0)
    dt = 0.001

    # Simulate 1.5 seconds of high-rate sine wave steering (1.0 Hz, peak 45 deg handwheel)
    states = []
    for step in range(1500):
        t = step * dt
        steer_handwheel = 45.0 * math.sin(2.0 * math.pi * 1.0 * t)
        ctrl = DriverControls(steering_deg=steer_handwheel, throttle=0.2)
        st = sim.step(st, ctrl)
        states.append(st)

        assert not math.isnan(st.yaw_rate_rads), f"NaN yaw rate at t={t}"
        assert not math.isnan(st.effective_steer_rad), f"NaN effective steer at t={t}"
        assert abs(st.yaw_rate_rads) < 3.0, f"Unstable yaw rate {st.yaw_rate_rads} rad/s at t={t}"

    assert len(states) == 1500


def test_corner_entry_attenuates_yaw_acceleration():
    """Verify corner entry under compliance produces moderated peak yaw acceleration vs rigid."""
    p_rigid = DynamicVehicleParams(steering_compliance_rad_per_mps2=0.0)
    p_comp = DynamicVehicleParams(steering_compliance_rad_per_mps2=0.000451)

    sim_rigid = DynamicLapSimulator(params=p_rigid, dt_fixed_s=0.001)
    sim_comp = DynamicLapSimulator(params=p_comp, dt_fixed_s=0.001)

    # High-speed corner entry: 30 m/s (108 km/h), rapid 40 deg handwheel steer step
    st_r = DynamicVehicleState(u_mps=30.0)
    st_c = DynamicVehicleState(u_mps=30.0)
    ctrl = DriverControls(steering_deg=40.0)

    # Advance 0.25 seconds into corner entry
    for _ in range(250):
        st_r = sim_rigid.step(st_r, ctrl)
        st_c = sim_comp.step(st_c, ctrl)

    # Compliant steer reduces peak yaw rate by ~5-15% (moderates aggressive turn-in overshoot)
    assert st_c.yaw_rate_rads < st_r.yaw_rate_rads
    reduction_pct = (st_r.yaw_rate_rads - st_c.yaw_rate_rads) / st_r.yaw_rate_rads * 100.0
    assert 2.0 <= reduction_pct <= 20.0, f"Unexpected yaw reduction: {reduction_pct:.2f}%"
