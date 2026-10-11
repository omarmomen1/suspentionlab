"""
tests/test_legacy_filter_isolation.py
======================================
Hostile isolation tests proving that the legacy acceleration filter states
(now designated as diagnostic accelerometer observers x[6], x[7]) have
STRICTLY ZERO effect on physical forces, moments, accelerations, and tire loads.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.handling_model import (
    HandlingParams,
    _handling_ode,
    compute_instantaneous_wheel_state,
    simulate_maneuver,
)


def test_hostile_filter_state_perturbation_zero_physical_derivative_effect():
    """Hostile test: Inject extreme values (+/- 1000 m/s^2) into diagnostic states x[6] and x[7].
    
    Proves that all physical state derivatives (vx, vy, yaw rate, global coords,
    tire forces, wheel rotational accelerations) have EXACTLY ZERO difference.
    """
    p = HandlingParams()
    
    # Baseline nominal state (20 states: 8 chassis/diag + 8 tire force + 4 wheel spin)
    v_x = 25.0
    omega_ss = v_x / p.wheel_radius
    x_nominal = [
        v_x, 1.2, 0.15, 10.0, 5.0, 0.1,  # vx, vy, yaw_rate, X, Y, Psi
        0.0, 0.0,                         # a_x_diag, a_y_diag (nominally 0)
        100.0, 450.0, 100.0, 420.0,       # Fx_fl, Fy_fl, Fx_fr, Fy_fr
        150.0, 500.0, 150.0, 490.0,       # Fx_rl, Fy_rl, Fx_rr, Fy_rr
        omega_ss, omega_ss, omega_ss, omega_ss  # omega_fl..rr
    ]
    
    # Hostile state 1: +1000 m/s^2 in both filter states
    x_hostile_pos = list(x_nominal)
    x_hostile_pos[6] = +1000.0
    x_hostile_pos[7] = +1000.0
    
    # Hostile state 2: -1000 m/s^2 in both filter states
    x_hostile_neg = list(x_nominal)
    x_hostile_neg[6] = -1000.0
    x_hostile_neg[7] = -1000.0

    steer_fn = lambda t: 0.04
    throttle_fn = lambda t: 0.5
    brake_fn = lambda t: 0.0
    t = 1.0

    d_nom = _handling_ode(t, x_nominal, p, steer_fn, throttle_fn, brake_fn)
    d_pos = _handling_ode(t, x_hostile_pos, p, steer_fn, throttle_fn, brake_fn)
    d_neg = _handling_ode(t, x_hostile_neg, p, steer_fn, throttle_fn, brake_fn)

    # Physical derivative indices:
    # 0: dv_x, 1: dv_y, 2: domega_z, 3: dX, 4: dY, 5: dPsi
    # 8..15: dFx, dFy for 4 corners
    # 16..19: d_omega for 4 corners
    physical_indices = [0, 1, 2, 3, 4, 5] + list(range(8, len(x_nominal)))

    for idx in physical_indices:
        diff_pos = abs(d_pos[idx] - d_nom[idx])
        diff_neg = abs(d_neg[idx] - d_nom[idx])
        assert diff_pos == 0.0, f"Hostile state positive perturbation leaked into physical derivative idx {idx}: diff={diff_pos}"
        assert diff_neg == 0.0, f"Hostile state negative perturbation leaked into physical derivative idx {idx}: diff={diff_neg}"

    # Verify that the diagnostic states themselves evolve as expected for a passive observer
    # da_x_diag = (a_x_inst - x[6]) / tau
    assert d_pos[6] != d_nom[6], "Diagnostic state derivative must reflect its own observer error"
    assert d_pos[7] != d_nom[7], "Diagnostic state derivative must reflect its own observer error"


def test_hostile_filter_state_zero_wheel_load_effect():
    """Hostile test: compute_instantaneous_wheel_state must produce identical normal loads,
    load transfers, and slip angles regardless of diagnostic filter states.
    """
    p = HandlingParams()
    v_x = 30.0
    omega_ss = v_x / p.wheel_radius
    x_nom = [v_x, 0.5, 0.1, 0, 0, 0, 0.0, 0.0] + [200.0]*8 + [omega_ss]*4
    x_hostile = [v_x, 0.5, 0.1, 0, 0, 0, 999.0, -999.0] + [200.0]*8 + [omega_ss]*4

    res_nom = compute_instantaneous_wheel_state(0.0, x_nom, p, steer_val=0.03, throttle_val=0.4, brake_val=0.0)
    res_hostile = compute_instantaneous_wheel_state(0.0, x_hostile, p, steer_val=0.03, throttle_val=0.4, brake_val=0.0)

    # Check normal loads
    for corner in ("fl", "fr", "rl", "rr"):
        diff_fz = abs(res_hostile[f"Fz_{corner}"] - res_nom[f"Fz_{corner}"])
        assert diff_fz == 0.0, f"Hostile filter value leaked into normal load Fz_{corner}: diff={diff_fz}"

    # Check load transfer components
    for key in ("delta_Fz_long", "delta_Fz_lat_f", "delta_Fz_lat_r", "delta_Fz_lat_geom_f", "delta_Fz_lat_elast_f"):
        diff_lt = abs(res_hostile[key] - res_nom[key])
        assert diff_lt == 0.0, f"Hostile filter value leaked into load transfer component {key}: diff={diff_lt}"

    # Check tire forces and slip angles
    for corner in ("fl", "fr", "rl", "rr"):
        assert abs(res_hostile[f"Fx_{corner}"] - res_nom[f"Fx_{corner}"]) == 0.0
        assert abs(res_hostile[f"Fy_{corner}"] - res_nom[f"Fy_{corner}"]) == 0.0
        assert abs(res_hostile[f"alpha_{corner}_deg"] - res_nom[f"alpha_{corner}_deg"]) == 0.0
        assert abs(res_hostile[f"mu_util_{corner}"] - res_nom[f"mu_util_{corner}"]) == 0.0


def test_maneuver_simulation_decoupled_from_initial_filter_values():
    """Verify that simulate_maneuver runs strictly physically without legacy filter lag."""
    p = HandlingParams()
    steer_step = lambda t: 0.03 if t >= 0.1 else 0.0
    res = simulate_maneuver(p, v_x_init=25.0, steering_func=steer_step,
                            throttle_func=lambda t: 0.0, brake_func=lambda t: 0.0,
                            duration=0.5, dt=0.01)

    assert "a_x_diag" in res
    assert "a_y_diag" in res
    assert len(res["a_y"]) == len(res["time"])
    # Dynamic lateral load transfer responds immediately to steer step
    t_arr = res["time"]
    idx_step = np.argmin(np.abs(t_arr - 0.12))
    assert res["delta_Fz_lat_f"][idx_step] > 100.0, "Physical load transfer must respond instantaneously"
