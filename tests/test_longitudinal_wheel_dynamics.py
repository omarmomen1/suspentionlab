"""
tests/test_longitudinal_wheel_dynamics.py
=========================================
Rigorous verification & validation suite for Longitudinal Wheel Dynamics:
1. Zero-torque free rolling equilibrium (kappa == 0, omega == Vx / Rw)
2. Drive torque acceleration and positive slip (kappa > 0, omega > Vx / Rw)
3. Heavy braking deceleration and negative slip (kappa < 0)
4. Non-reversing dry friction brake mechanics (brake cannot spin wheels backwards)
5. Low-speed standstill regularization without NaN / Inf or zero-division
6. Open-differential / axle torque distribution consistency
7. Epistemic validity tracking (lockup, wheelspin, linear regimes)
8. Guardrail validation for non-physical wheel parameters
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.wheel_dynamics import (
    WheelRotationalState,
    calc_longitudinal_slip,
    calc_wheel_torques,
    calc_wheel_acceleration,
    integrate_wheel_rotations_step,
    evaluate_wheel_dynamics_validity,
)
from suspensionlab.physics.handling_model import (
    HandlingParams,
    simulate_maneuver,
)
from suspensionlab.physics.validity import PhysicsValidityStatus


# ─────────────────────────────────────────────────────────────────────────────
# 1. Zero-Torque Steady Roll & Slip Definition
# ─────────────────────────────────────────────────────────────────────────────

def test_zero_torque_free_rolling_equilibrium():
    """Verify that a freely rolling wheel at peripheral speed equal to body speed produces zero slip."""
    r_w = 0.33
    v_x = 25.0
    omega_sync = v_x / r_w

    slip = calc_longitudinal_slip(omega_sync, v_x, r_w)
    assert abs(slip) < 1e-6, f"Free rolling slip must be zero, got {slip}"

    state = WheelRotationalState.from_vehicle_speed(v_x, r_w)
    assert np.allclose(state.to_list(), [omega_sync] * 4)


def test_drive_slip_positive_and_bounded():
    """Verify that wheel peripheral speed exceeding body speed produces positive drive slip, bounded to 1.0."""
    r_w = 0.33
    v_x = 20.0

    # 10% overspeed
    omega_accel = (v_x * 1.10) / r_w
    slip = calc_longitudinal_slip(omega_accel, v_x, r_w)
    assert 0.09 < slip < 0.11, f"Expected ~0.10 slip, got {slip}"

    # Extreme wheelspin (e.g. 5x speed on ice) must be bounded
    omega_spin = (v_x * 5.0) / r_w
    slip_spin = calc_longitudinal_slip(omega_spin, v_x, r_w, max_slip=1.0)
    assert slip_spin == 1.0


def test_brake_slip_negative_and_lockup():
    """Verify that braking produces negative slip, reaching -1.0 at pure lockup (omega = 0)."""
    r_w = 0.33
    v_x = 30.0

    # Locked wheel (omega = 0) at 30 m/s
    slip_locked = calc_longitudinal_slip(0.0, v_x, r_w)
    assert np.isclose(slip_locked, -1.0), f"Locked wheel slip must be -1.0, got {slip_locked}"

    # 20% braking slip
    omega_braking = (v_x * 0.80) / r_w
    slip_braking = calc_longitudinal_slip(omega_braking, v_x, r_w)
    assert -0.21 < slip_braking < -0.19, f"Expected ~ -0.20 slip, got {slip_braking}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Standstill & Low-Speed Regularization
# ─────────────────────────────────────────────────────────────────────────────

def test_standstill_low_speed_regularization():
    """Verify that at standstill (|v_x| < 1e-4, |omega| < 1e-4), slip ratio does not NaN or blow up."""
    r_w = 0.33
    slip_standstill = calc_longitudinal_slip(0.0, 0.0, r_w)
    assert slip_standstill == 0.0
    assert not math.isnan(slip_standstill)
    assert not math.isinf(slip_standstill)

    # Low speed (0.1 m/s) with stationary wheel: slip attenuates smoothly without singularity
    slip_creep = calc_longitudinal_slip(0.0, 0.1, r_w, v_min=0.5)
    assert -1.0 <= slip_creep <= 0.0
    assert not math.isnan(slip_creep)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Non-Reversing Brake Physics & Torque Balance
# ─────────────────────────────────────────────────────────────────────────────

def test_brake_cannot_reverse_wheel_rotation():
    """Verify that pure braking torque cannot accelerate the wheel in reverse direction."""
    r_w = 0.33
    i_w = 1.2
    omega_fwd = 5.0  # rad/s forward rotation

    # Apply heavy braking with zero drive torque and zero road force
    d_omega = calc_wheel_acceleration(
        omega=omega_fwd,
        T_drive=0.0,
        T_brake=1000.0,
        F_x=0.0,
        r_w=r_w,
        I_w=i_w,
    )
    # Angular deceleration must be negative
    assert d_omega < 0.0, "Brake must decelerate forward rotating wheel"

    # When wheel has reached zero speed (omega = 0.0), brake must NOT produce negative acceleration!
    d_omega_zero = calc_wheel_acceleration(
        omega=0.0,
        T_drive=0.0,
        T_brake=1000.0,
        F_x=0.0,
        r_w=r_w,
        I_w=i_w,
    )
    assert d_omega_zero == 0.0, f"Static brake must hold wheel at rest, got d_omega = {d_omega_zero}"


def test_brake_bias_and_torque_distribution():
    """Verify powertrain drive and brake torque splits across axles and sides."""
    drive_t, brake_t = calc_wheel_torques(
        throttle=1.0,
        brake=0.8,
        drive_bias_f=0.0,    # RWD
        brake_bias_f=0.60,   # 60% front
        max_drive_torque=1200.0,
        max_brake_torque=2000.0,
    )

    # Drive torque: RWD -> front is 0, rear is 600 Nm each side (total 1200)
    assert drive_t[0] == 0.0
    assert drive_t[1] == 0.0
    assert drive_t[2] == 600.0
    assert drive_t[3] == 600.0

    # Total brake torque = 0.8 * 2000 = 1600 Nm
    # Front axle = 60% * 1600 = 960 Nm -> 480 Nm per wheel
    # Rear axle = 40% * 1600 = 640 Nm -> 320 Nm per wheel
    assert np.isclose(brake_t[0], 480.0)
    assert np.isclose(brake_t[1], 480.0)
    assert np.isclose(brake_t[2], 320.0)
    assert np.isclose(brake_t[3], 320.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Maneuver Dynamic Simulation with Wheel Dynamics
# ─────────────────────────────────────────────────────────────────────────────

def test_handling_simulation_acceleration_slip_response():
    """Verify that applying throttle during a maneuver causes driven rear wheels to spin up and produce positive slip."""
    p = HandlingParams(drive_bias_f=0.0, max_drive_torque=1800.0)
    res = simulate_maneuver(
        p=p,
        v_x_init=15.0,
        steering_func=lambda t: 0.0,
        throttle_func=lambda t: 0.8 if t > 0.2 else 0.0,
        brake_func=lambda t: 0.0,
        duration=2.0,
        dt=0.02,
    )

    # Vehicle should accelerate
    assert res["v_x"][-1] > res["v_x"][0]

    # Under RWD acceleration, rear longitudinal slip must be positive
    idx_accel = int(1.0 / 0.02)
    assert res["kappa_rl"][idx_accel] > 0.0
    assert res["kappa_rr"][idx_accel] > 0.0
    # Rear slip should exceed non-driven front slip
    assert res["kappa_rl"][idx_accel] > res["kappa_fl"][idx_accel]


def test_handling_simulation_braking_slip_response():
    """Verify that applying braking during a maneuver causes negative slip and decelerates the vehicle."""
    p = HandlingParams(brake_bias_f=0.60, max_brake_torque=2500.0)
    res = simulate_maneuver(
        p=p,
        v_x_init=30.0,
        steering_func=lambda t: 0.0,
        throttle_func=lambda t: 0.0,
        brake_func=lambda t: 0.7 if t > 0.2 else 0.0,
        duration=2.0,
        dt=0.02,
    )

    # Vehicle should decelerate
    assert res["v_x"][-1] < res["v_x"][0]

    # Under braking, slip must be negative
    idx_brake = int(1.0 / 0.02)
    assert res["kappa_fl"][idx_brake] < 0.0
    assert res["kappa_fr"][idx_brake] < 0.0
    assert res["kappa_rl"][idx_brake] < 0.0
    assert res["kappa_rr"][idx_brake] < 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Central Physics Validity Record & Guardrails
# ─────────────────────────────────────────────────────────────────────────────

def test_wheel_dynamics_validity_record_lockup():
    """Verify that full wheel lockup triggers an EXTRAPOLATED validity warning."""
    slips = {"fl": -0.99, "fr": -0.99, "rl": -0.30, "rr": -0.30}
    omegas = {"fl": 0.0, "fr": 0.0, "rl": 45.0, "rr": 45.0}

    rec = evaluate_wheel_dynamics_validity(slips, omegas, v_x=20.0)
    assert rec.status == PhysicsValidityStatus.EXTRAPOLATED
    assert any("lockup" in w.lower() for w in rec.warnings)


def test_handling_params_wheel_guardrails():
    """Verify that unphysical wheel inertia or radius raises ValueError."""
    with pytest.raises(ValueError, match="wheel_inertia"):
        HandlingParams(wheel_inertia=0.0)

    with pytest.raises(ValueError, match="wheel_radius"):
        HandlingParams(wheel_radius=0.01)
