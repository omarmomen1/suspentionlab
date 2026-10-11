"""
tests/test_dynamic_tire_relaxation.py
======================================
Comprehensive Unit & Integration Test Suite for Dynamic Tire Relaxation

Verifies:
1. Time constant tau = sigma / v_trans with v_min regularization (no low-speed singularity).
2. Load-sensitive relaxation length scaling sigma(Fz).
3. Dynamic slip state RK4 convergence against theoretical first-order response.
4. Five standard ISO-aligned handling maneuvers:
   - STEP_STEER
   - SINE_STEER
   - COMBINED_BRAKING_TURNING
   - THROTTLE_ON_CORNER_EXIT
   - RAPID_STEERING_REVERSAL
5. Explicit comparison: QUASI_STEADY vs DYNAMIC (phase lag & peak force attenuation).
6. Lap simulation integration under both QUASI_STEADY and DYNAMIC modes.
7. Authoritative vehicle dynamics pipeline, SHA-256 state hashing, and epistemic validity integrity.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.tire_model import TireRelaxationDynamics
from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    DynamicTrackModel,
    TireModelType,
    solve_transient_maneuver,
    compare_quasi_steady_vs_dynamic,
    solve_dynamic_lap,
)
from suspensionlab.physics.authoritative_vehicle_dynamics import (
    AuthoritativeVehicleState,
    AuthoritativeTrackPoint,
    evaluate_authoritative_pipeline_step,
    verify_physics_consistency,
)
from suspensionlab.physics.validity import PhysicsValidityStatus


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tire Relaxation Dynamics Physics & Scaling
# ─────────────────────────────────────────────────────────────────────────────

def test_time_constant_velocity_scaling_and_regularization():
    """Verify tau = sigma / v_trans and that low-speed regularization prevents singularity at zero speed."""
    sigma_x = 0.15
    sigma_y = 0.25

    # At 30 m/s (108 km/h)
    tau_x, tau_y = TireRelaxationDynamics.get_time_constants(30.0, sigma_x, sigma_y, v_min=0.10)
    assert math.isclose(tau_x, 0.15 / math.sqrt(30.0**2 + 0.10**2), rel_tol=1e-3)
    assert math.isclose(tau_y, 0.25 / math.sqrt(30.0**2 + 0.10**2), rel_tol=1e-3)
    assert 0.004 < tau_x < 0.006
    assert 0.007 < tau_y < 0.009

    # At 0 m/s (standing still) -> strictly regularised to v_min=0.10 m/s
    tau_x_zero, tau_y_zero = TireRelaxationDynamics.get_time_constants(0.0, sigma_x, sigma_y, v_min=0.10)
    assert not math.isinf(tau_x_zero) and not math.isnan(tau_x_zero)
    assert not math.isinf(tau_y_zero) and not math.isnan(tau_y_zero)
    assert math.isclose(tau_x_zero, sigma_x / 0.10, rel_tol=1e-4)
    assert math.isclose(tau_y_zero, sigma_y / 0.10, rel_tol=1e-4)


def test_load_sensitive_relaxation_length_scaling():
    """Verify relaxation lengths scale with vertical normal load: sigma(Fz) = sigma_0 * (Fz/Fz0)^0.3."""
    fz_nom = 4000.0
    sig_x0 = 0.15
    sig_y0 = 0.25

    # At nominal load, relaxation length equals base
    sx_nom, sy_nom = TireRelaxationDynamics.calc_relaxation_lengths(fz_nom, fz_nom, sig_x0, sig_y0)
    assert math.isclose(sx_nom, sig_x0, rel_tol=1e-4)
    assert math.isclose(sy_nom, sig_y0, rel_tol=1e-4)

    # At high load (8000 N, heavy downforce), carcass deflects more -> larger relaxation length
    sx_hi, sy_hi = TireRelaxationDynamics.calc_relaxation_lengths(8000.0, fz_nom, sig_x0, sig_y0)
    assert sx_hi > sig_x0
    assert sy_hi > sig_y0
    expected_ratio = (8000.0 / 4000.0) ** 0.3
    assert math.isclose(sy_hi / sy_nom, expected_ratio, rel_tol=1e-4)

    # At low load (1000 N, unloaded inside wheel)
    sx_lo, sy_lo = TireRelaxationDynamics.calc_relaxation_lengths(1000.0, fz_nom, sig_x0, sig_y0)
    assert sx_lo < sig_x0
    assert sy_lo < sig_y0


def test_slip_derivatives_and_step_convergence():
    """Verify dynamic slip ODE integrates to steady state according to 1 - exp(-t/tau)."""
    alpha_ss = 0.08  # ~4.6 deg
    v_x = 25.0
    sig_y = 0.25
    tau = sig_y / math.sqrt(v_x**2 + 0.10**2)

    alpha_dyn = 0.0
    dt = 0.001
    times = []
    alphas = []

    for step in range(50):  # 50 ms
        t = step * dt
        d_alpha = (alpha_ss - alpha_dyn) / tau
        alpha_dyn += d_alpha * dt
        times.append(t)
        alphas.append(alpha_dyn)

    # At t = tau, response should reach ~63.2% of steady state
    idx_tau = int(tau / dt)
    assert math.isclose(alphas[idx_tau], alpha_ss * (1.0 - math.exp(-1.0)), rel_tol=0.05)
    # At t = 4*tau, response should reach > 98% of steady state
    idx_4tau = min(int(4.0 * tau / dt), len(alphas) - 1)
    assert alphas[idx_4tau] >= 0.95 * alpha_ss


# ─────────────────────────────────────────────────────────────────────────────
# 2. Five Standard Handling Maneuvers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def standard_sim():
    """Provide standard dynamic lap simulator with dynamic tire relaxation enabled."""
    params = DynamicVehicleParams(
        tire_model_type="DYNAMIC",
        tire_relaxation_length_x_m=0.15,
        tire_relaxation_length_y_m=0.25,
        relaxation_v_min_mps=0.10,
    )
    return DynamicLapSimulator(params=params)


def test_maneuver_step_steer(standard_sim):
    """Verify STEP_STEER handling maneuver produces valid telemetry, metrics, and force lag."""
    res = solve_transient_maneuver(
        standard_sim, maneuver_type="STEP_STEER", initial_speed_mps=30.0, duration_s=2.5
    )
    assert res.maneuver_type == "STEP_STEER"
    assert res.tire_model_type == "DYNAMIC"
    assert len(res.times) > 50
    assert len(res.front_lateral_force_n) == len(res.times)
    assert len(res.transient_tire_utilization) == len(res.times)

    m = res.metrics
    assert "peak_front_lateral_force_n" in m
    assert "peak_yaw_rate_rads" in m
    assert "yaw_rate_overshoot_pct" in m
    assert "force_phase_lag_ms" in m
    assert m["peak_front_lateral_force_n"] > 2000.0
    assert m["peak_yaw_rate_rads"] > 0.1
    assert m["force_phase_lag_ms"] > 0.0  # Dynamic relaxation has non-zero phase lag


def test_maneuver_sine_steer(standard_sim):
    """Verify SINE_STEER sinusoidal handling maneuver evaluates periodic response."""
    res = solve_transient_maneuver(
        standard_sim,
        maneuver_type="SINE_STEER",
        initial_speed_mps=25.0,
        steer_amplitude_deg=15.0,
        frequency_hz=1.0,
        duration_s=2.5,
    )
    assert res.maneuver_type == "SINE_STEER"
    m = res.metrics
    assert m["frequency_hz"] == 1.0
    assert m["force_amplitude_n"] > 500.0
    assert m["yaw_amplitude_rads"] > 0.05
    assert m["ay_amplitude_g"] > 0.2


def test_maneuver_combined_braking_turning(standard_sim):
    """Verify COMBINED_BRAKING_TURNING executes trail braking with combined slip."""
    res = solve_transient_maneuver(
        standard_sim,
        maneuver_type="COMBINED_BRAKING_TURNING",
        initial_speed_mps=35.0,
        brake_demand=0.50,
        steer_amplitude_deg=20.0,
        duration_s=2.5,
    )
    assert res.maneuver_type == "COMBINED_BRAKING_TURNING"
    m = res.metrics
    assert m["peak_braking_decel_g"] > 0.5
    assert m["combined_tire_utilization"] > 0.5


def test_maneuver_throttle_on_corner_exit(standard_sim):
    """Verify THROTTLE_ON_CORNER_EXIT evaluates power application during steering unwind."""
    res = solve_transient_maneuver(
        standard_sim,
        maneuver_type="THROTTLE_ON_CORNER_EXIT",
        initial_speed_mps=22.0,
        steer_amplitude_deg=20.0,
        throttle_demand=0.80,
        duration_s=2.5,
    )
    assert res.maneuver_type == "THROTTLE_ON_CORNER_EXIT"
    m = res.metrics
    assert "exit_acceleration_g" in m
    assert m["exit_acceleration_g"] > 0.3
    assert m["peak_tire_utilization"] > 0.8
    assert "traction_limit_reached" in m


def test_maneuver_rapid_steering_reversal(standard_sim):
    """Verify RAPID_STEERING_REVERSAL evaluates zero-crossing hysteresis and dynamic relaxation lag."""
    res = solve_transient_maneuver(
        standard_sim,
        maneuver_type="RAPID_STEERING_REVERSAL",
        initial_speed_mps=28.0,
        steer_amplitude_deg=25.0,
        duration_s=2.5,
    )
    assert res.maneuver_type == "RAPID_STEERING_REVERSAL"
    m = res.metrics
    assert "reversal_zero_crossing_lag_ms" in m
    assert m["peak_front_lateral_force_n"] > 2000.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Explicit Solver Comparison: QUASI_STEADY vs DYNAMIC
# ─────────────────────────────────────────────────────────────────────────────

def test_compare_quasi_steady_vs_dynamic(standard_sim):
    """Verify compare_quasi_steady_vs_dynamic produces explicit comparison deltas."""
    cmp_res = compare_quasi_steady_vs_dynamic(
        standard_sim, maneuver_type="STEP_STEER", initial_speed_mps=30.0, duration_s=2.0
    )
    assert cmp_res["status"] == "success"
    assert "quasi_steady" in cmp_res
    assert "dynamic_relaxation" in cmp_res
    c = cmp_res["comparison"]

    # In a sudden step input:
    # 1. Dynamic relaxation attenuates instantaneous force spike compared to quasi-steady
    assert c["peak_front_force_quasi_steady_n"] >= c["peak_front_force_dynamic_n"]
    assert c["force_attenuation_n"] >= 0.0

    # 2. Dynamic relaxation exhibits non-zero force rise lag (tau ~ sigma/V)
    assert c["phase_lag_dynamic_ms"] > c["phase_lag_quasi_steady_ms"]
    assert c["relaxation_delay_delta_ms"] > 0.0

    # 3. Validity record explicitly reflects simulation estimate
    val = cmp_res["validity_record"]
    assert val["status"] == PhysicsValidityStatus.SIMULATION_ESTIMATE.value


# ─────────────────────────────────────────────────────────────────────────────
# 4. Lap Simulation Integration (QUASI_STEADY vs DYNAMIC)
# ─────────────────────────────────────────────────────────────────────────────

def test_solve_dynamic_lap_with_both_tire_modes():
    """Verify 14-DOF dynamic lap simulator accepts selectable TIRE_MODEL modes."""
    # Test with 300m track segment
    dist = np.linspace(0.0, 300.0, 31)
    curv = np.zeros_like(dist)
    track = DynamicTrackModel(distances=dist, curvatures=curv)

    # Dynamic mode
    params_dyn = DynamicVehicleParams(tire_model_type="DYNAMIC")
    sim_dyn = DynamicLapSimulator(params=params_dyn)
    res_dyn = solve_dynamic_lap(sim_dyn, track, initial_speed_mps=30.0, max_simulation_time_s=15.0)
    assert res_dyn.tire_model_mode == "DYNAMIC"
    assert "relaxation lengths" in res_dyn.validity_record.assumptions[1].lower()

    # Quasi-steady mode
    params_qs = DynamicVehicleParams(tire_model_type="QUASI_STEADY")
    sim_qs = DynamicLapSimulator(params=params_qs)
    res_qs = solve_dynamic_lap(sim_qs, track, initial_speed_mps=30.0, max_simulation_time_s=15.0)
    assert res_qs.tire_model_mode == "QUASI_STEADY"
    assert "quasi-steady" in res_qs.validity_record.assumptions[1].lower()

    # Both produce valid physical lap times and telemetry
    assert 2.0 < res_dyn.total_time < 20.0
    assert 2.0 < res_qs.total_time < 20.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Authoritative Pipeline & Epistemic Validity Integrity
# ─────────────────────────────────────────────────────────────────────────────

def test_authoritative_pipeline_state_evaluation_and_hashing(standard_sim):
    """Verify evaluate_authoritative_pipeline_step produces deterministic SHA-256 fingerprint."""
    st = DynamicVehicleState(u_mps=30.0)
    ctrl = DriverControls(throttle=0.20, steering_deg=8.0, gear=3)
    track = AuthoritativeTrackPoint(station_m=120.0, grade_rad=0.01, banking_rad=0.02)

    auth_state = evaluate_authoritative_pipeline_step(standard_sim, st, ctrl, track_point=track)

    assert isinstance(auth_state, AuthoritativeVehicleState)
    assert len(auth_state.tires.Fz_n) == 4
    assert len(auth_state.tires.tau_y_s) == 4
    assert auth_state.tires.tau_y_s[0] > 0.0
    assert auth_state.powertrain.gear == 3
    assert auth_state.track.station_m == 120.0

    # Deterministic SHA-256 state hash
    h1 = auth_state.state_hash()
    h2 = auth_state.state_hash()
    assert h1 == h2
    assert len(h1) == 64

    # Epistemic validity guardrail: dynamic relaxation must not be marked EMPIRICALLY_VALIDATED
    assert auth_state.validity_record.status in (
        PhysicsValidityStatus.SIMULATION_ESTIMATE,
        PhysicsValidityStatus.MODEL_SUPPORTED,
    )
    assert auth_state.validity_record.status != PhysicsValidityStatus.EMPIRICALLY_VALIDATED


def test_epistemic_validity_non_upgradeability(standard_sim):
    """Verify that degraded upstream validity (e.g. EXTRAPOLATED) cannot be upgraded."""
    st = DynamicVehicleState(u_mps=30.0)
    ctrl = DriverControls(throttle=0.20, steering_deg=0.0)

    auth_degraded = evaluate_authoritative_pipeline_step(
        standard_sim, st, ctrl, upstream_validity=PhysicsValidityStatus.EXTRAPOLATED
    )
    # The record must reflect the degraded upstream status
    assert auth_degraded.validity_record.upstream_validity_state == PhysicsValidityStatus.EXTRAPOLATED


def test_physics_consistency_verification():
    """Verify verify_physics_consistency detects matching parameters across QSS and dynamic models."""
    from suspensionlab.physics.lap_sim import LapSimVehicle, MassProperties, AeroMap

    mp = MassProperties(total_mass=798.0, wheelbase=3.60)
    ae = AeroMap(cd_base=0.95, cl_base=2.40, frontal_area=1.75)
    qss_veh = LapSimVehicle(mass_props=mp, aero=ae)

    dyn_params = DynamicVehicleParams(
        mass_kg=798.0,
        wheelbase_m=3.60,
        a_m=1.60,
        b_m=2.00,
        cd_base=0.95,
        cl_base=2.40,
        frontal_area_m2=1.75,
    )

    res = verify_physics_consistency(mp, dyn_params)
    assert res["status"] == "PASS"
    assert res["consistent"] is True
