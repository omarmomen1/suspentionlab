"""
tests/test_driver_actuator_dynamics.py
=======================================
Step-response tests verifying that steering actuator rate limits and
throttle/brake actuator time constants exist in the actual ODE state evolution
and physically alter transient vehicle dynamics.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicVehicleParams,
    DynamicVehicleState,
    DynamicLapSimulator,
    DriverControls,
)


def test_steering_actuator_rate_limit_step_response():
    """Verify steering actuator obeys rate limit d(delta)/dt <= steering_rate_limit_rads."""
    rate_lim = 1.5  # 1.5 rad/s at the road wheel
    p = DynamicVehicleParams(steering_rate_limit_rads=rate_lim, steer_ratio=13.5)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    # Handwheel command of 54 degrees -> 4.0 degrees at wheel = 0.0698 rad
    str_deg = 54.0
    target_wheel_rad = math.radians(str_deg) / p.steer_ratio  # ~0.0698 rad
    ctrl = DriverControls(steering_deg=str_deg, throttle=0.0, brake=0.0)

    st = DynamicVehicleState(actuator_steering_rad=0.0, u_mps=25.0)

    # Step for 20 ms (20 steps of 1 ms)
    for _ in range(20):
        st = sim.step(st, ctrl)

    # Max change possible in 20 ms at 1.5 rad/s: 1.5 * 0.020 = 0.030 rad
    max_possible_angle = rate_lim * 0.020
    assert st.actuator_steering_rad < target_wheel_rad, "Steering angle must not jump instantaneously"
    assert st.actuator_steering_rad <= max_possible_angle + 0.002, (
        f"Actuator angle {st.actuator_steering_rad:.5f} exceeded rate-limited max {max_possible_angle:.5f}"
    )
    assert st.actuator_steering_rad > 0.020, "Actuator must actively slew toward target"


def test_throttle_actuator_lag_step_response():
    """Verify throttle actuator follows first-order lag: u_thr(t) = 1 - exp(-t / tau_thr)."""
    tau_thr = 0.040  # 40 ms time constant
    p = DynamicVehicleParams(throttle_actuator_tau_s=tau_thr)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    ctrl = DriverControls(throttle=1.0, brake=0.0, steering_deg=0.0, gear=3)
    st = DynamicVehicleState(actuator_throttle=0.0, u_mps=20.0, current_gear=3)

    # Step for exactly 40 ms (1 time constant)
    for _ in range(40):
        st = sim.step(st, ctrl)

    # Theoretical value at 1 tau is 1 - 1/e ≈ 0.6321
    expected_fraction = 1.0 - math.exp(-1.0)
    assert math.isclose(st.actuator_throttle, expected_fraction, abs_tol=0.05), (
        f"Throttle position {st.actuator_throttle:.4f} did not match 1-tau response {expected_fraction:.4f}"
    )

    # Stepping further to 200 ms (5 tau) should approach 1.0
    for _ in range(160):
        st = sim.step(st, ctrl)
    assert st.actuator_throttle > 0.98, "Throttle must asymptotically reach 100%"


def test_brake_actuator_lag_step_response():
    """Verify brake actuator follows first-order lag: u_brk(t) = 1 - exp(-t / tau_brk)."""
    tau_brk = 0.030  # 30 ms time constant
    p = DynamicVehicleParams(brake_actuator_tau_s=tau_brk)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    ctrl = DriverControls(throttle=0.0, brake=1.0, steering_deg=0.0)
    st = DynamicVehicleState(actuator_brake=0.0, u_mps=30.0)

    # Step for 30 ms (1 time constant)
    for _ in range(30):
        st = sim.step(st, ctrl)

    expected_fraction = 1.0 - math.exp(-1.0)  # ~0.6321
    assert math.isclose(st.actuator_brake, expected_fraction, abs_tol=0.05), (
        f"Brake position {st.actuator_brake:.4f} did not match 1-tau response {expected_fraction:.4f}"
    )


def test_actuator_limits_change_transient_vehicle_behavior():
    """Demonstrate that physical actuator dynamics measurably alter transient lateral acceleration."""
    # Fast vehicle (instantaneous-like steering)
    p_fast = DynamicVehicleParams(steering_rate_limit_rads=25.0)
    sim_fast = DynamicLapSimulator(params=p_fast, dt_fixed_s=0.001)

    # Rate-limited vehicle (heavy steering rack / unassisted manual rack)
    p_slow = DynamicVehicleParams(steering_rate_limit_rads=0.8)
    sim_slow = DynamicLapSimulator(params=p_slow, dt_fixed_s=0.001)

    # Abrupt step steer input: 45 degrees handwheel
    ctrl = DriverControls(steering_deg=45.0, throttle=0.0, brake=0.0)

    st_fast = DynamicVehicleState(u_mps=30.0, actuator_steering_rad=0.0)
    st_slow = DynamicVehicleState(u_mps=30.0, actuator_steering_rad=0.0)

    # Simulate for 15 ms
    for _ in range(15):
        st_fast = sim_fast.step(st_fast, ctrl)
        st_slow = sim_slow.step(st_slow, ctrl)

    d_fast = sim_fast.compute_derivatives(st_fast, ctrl)
    d_slow = sim_slow.compute_derivatives(st_slow, ctrl)

    # Fast vehicle has generated significant road wheel angle and lateral force
    # Rate-limited vehicle is still slewing and has much lower lateral acceleration
    assert st_fast.actuator_steering_rad > st_slow.actuator_steering_rad * 1.5
    assert abs(d_fast["Fy_total"]) > abs(d_slow["Fy_total"]) * 1.5, (
        "Rate-limited actuator must measurably retard lateral force buildup"
    )
    assert abs(d_fast["dv"]) > abs(d_slow["dv"]), "Transient lateral acceleration must be attenuated"
