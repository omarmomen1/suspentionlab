"""
physics/handling_model.py
=========================
SuspensionLab PRO — Non-Linear Handling Dynamics
3-DOF Body + 4-Wheel Handling Model with Quasi-Static Load Transfer and Magic Formula Tires.
"""

import numpy as np
from scipy.integrate import solve_ivp
from dataclasses import dataclass, field
from typing import Callable
from suspensionlab.physics.magic_formula import calc_tire_forces, TireCoeffs

@dataclass
class HandlingParams:
    m: float = 1200.0       # Mass (kg)
    I_z: float = 2000.0     # Yaw inertia (kg*m^2) — exposed to UI for accurate yaw response
    a: float = 1.2          # CG to front axle (m)
    b: float = 1.4          # CG to rear axle (m)
    tw_f: float = 1.6       # Track width front (m)
    tw_r: float = 1.6       # Track width rear (m)
    h_cg: float = 0.4       # CG height (m)
    
    # Roll stiffness distribution (front fraction)
    roll_dist: float = 0.55 
    
    # Aerodynamics
    C_d: float = 0.3
    C_l: float = 0.1
    frontal_area: float = 2.2
    rho_air: float = 1.225

    tire_coeffs: TireCoeffs = field(default_factory=TireCoeffs)

def _handling_ode(
    t: float, 
    x: list[float], 
    p: HandlingParams, 
    steering_func: Callable[[float], float], 
    throttle_func: Callable[[float], float],
    brake_func: Callable[[float], float]
):
    """
    x = [v_x, v_y, omega_z, X, Y, Psi]
    v_x: longitudinal velocity in body frame
    v_y: lateral velocity in body frame
    omega_z: yaw rate
    X, Y: global position
    Psi: global heading
    """
    v_x, v_y, omega_z, X, Y, Psi = x
    
    # Prevent divide by zero at standstill
    # LIMITATION: Model is valid for speeds above ~2 km/h. Does not support reverse or complete stop.
    v_x = max(v_x, 0.1) 
    
    delta = steering_func(t)
    throttle = throttle_func(t) # 0 to 1
    brake = brake_func(t)       # 0 to 1

    # 1. Kinematics (Slip Angles)
    # v_x at wheels approx equal to vehicle v_x
    v_x_fl = v_x - omega_z * p.tw_f / 2
    v_x_fr = v_x + omega_z * p.tw_f / 2
    v_x_rl = v_x - omega_z * p.tw_r / 2
    v_x_rr = v_x + omega_z * p.tw_r / 2

    v_y_f = v_y + p.a * omega_z
    v_y_r = v_y - p.b * omega_z

    alpha_fl = delta - np.arctan2(v_y_f, v_x_fl)
    alpha_fr = delta - np.arctan2(v_y_f, v_x_fr)
    alpha_rl = -np.arctan2(v_y_r, v_x_rl)
    alpha_rr = -np.arctan2(v_y_r, v_x_rr)

    # Simplified drive/brake torque logic (RWD biased)
    # Convert throttle/brake to slip ratio kappa approx
    max_accel = 5.0 # m/s^2 approx
    max_decel = 10.0
    
    kappa_f = -brake * 0.1 # Simplistic slip ratio approximation
    kappa_r = (throttle * max_accel - brake * max_decel * 0.6) / 50.0

    # 2. Quasi-Static Load Transfer
    L = p.a + p.b
    W = p.m * 9.81
    
    # Aero downforce and drag
    v_mag = np.sqrt(v_x**2 + v_y**2)
    F_aero_d = 0.5 * p.rho_air * p.C_d * p.frontal_area * v_mag**2 * np.sign(v_x)
    F_aero_l = 0.5 * p.rho_air * p.C_l * p.frontal_area * v_mag**2
    
    W_total = W + F_aero_l
    
    # 2. Quasi-Static Load Transfer (2-step Predictor-Corrector to break algebraic loop)
    # Step 1: Predictor (Kinematic estimate)
    a_x_est = (throttle * max_accel) - (brake * max_decel) - (F_aero_d / p.m)
    a_y_est = v_x * omega_z  # Steady-state turn initial estimate

    # Iterative predictor-corrector for load transfer ↔ tire force algebraic loop
    # Converges when lateral and longitudinal acceleration corrections are < 1e-4 m/s²
    cos_d, sin_d = np.cos(delta), np.sin(delta)
    for _iter in range(20):  # max 20 iterations; converges in 3-5 for normal g-levels
        a_x_prev, a_y_prev = a_x_est, a_y_est
        delta_Fz_long = (p.m * a_x_est * p.h_cg) / L

        Fz_f_total = (W_total * p.b / L) - delta_Fz_long
        Fz_r_total = (W_total * p.a / L) + delta_Fz_long

        delta_Fz_lat_f = (p.m * a_y_est * p.h_cg / p.tw_f) * p.roll_dist
        delta_Fz_lat_r = (p.m * a_y_est * p.h_cg / p.tw_r) * (1 - p.roll_dist)

        Fz_fl = max(Fz_f_total / 2 - delta_Fz_lat_f, 10.0)
        Fz_fr = max(Fz_f_total / 2 + delta_Fz_lat_f, 10.0)
        Fz_rl = max(Fz_r_total / 2 - delta_Fz_lat_r, 10.0)
        Fz_rr = max(Fz_r_total / 2 + delta_Fz_lat_r, 10.0)

        # 3. Tire Forces
        Fx_fl, Fy_fl = calc_tire_forces(Fz_fl, alpha_fl, kappa_f, 0.0, p.tire_coeffs)
        Fx_fr, Fy_fr = calc_tire_forces(Fz_fr, alpha_fr, kappa_f, 0.0, p.tire_coeffs)
        Fx_rl, Fy_rl = calc_tire_forces(Fz_rl, alpha_rl, kappa_r, 0.0, p.tire_coeffs)
        Fx_rr, Fy_rr = calc_tire_forces(Fz_rr, alpha_rr, kappa_r, 0.0, p.tire_coeffs)

        # Resolve front forces to body frame (steering angle)
        Fx_fl_b = Fx_fl * cos_d - Fy_fl * sin_d
        Fy_fl_b = Fx_fl * sin_d + Fy_fl * cos_d
        Fx_fr_b = Fx_fr * cos_d - Fy_fr * sin_d
        Fy_fr_b = Fx_fr * sin_d + Fy_fr * cos_d

        # Total body forces
        Sum_Fx = Fx_fl_b + Fx_fr_b + Fx_rl + Fx_rr - F_aero_d
        Sum_Fy = Fy_fl_b + Fy_fr_b + Fy_rl + Fy_rr

        # Corrector: update accelerations from actual forces
        a_x_est = Sum_Fx / p.m
        a_y_est = Sum_Fy / p.m

        # Convergence check
        if abs(a_x_est - a_x_prev) < 1e-4 and abs(a_y_est - a_y_prev) < 1e-4:
            break
        a_x_prev, a_y_prev = a_x_est, a_y_est

    # Yaw moment:
    Sum_Mz = (p.a * (Fy_fl_b + Fy_fr_b) - p.b * (Fy_rl + Fy_rr) 
              - (p.tw_f / 2) * (Fx_fl_b - Fx_fr_b) 
              - (p.tw_r / 2) * (Fx_rl - Fx_rr))

    # 4. State Derivatives
    dv_x = (Sum_Fx / p.m) + v_y * omega_z
    dv_y = (Sum_Fy / p.m) - v_x * omega_z
    domega_z = Sum_Mz / p.I_z
    
    # Global coordinates
    cos_p, sin_p = np.cos(Psi), np.sin(Psi)
    dX = v_x * cos_p - v_y * sin_p
    dY = v_x * sin_p + v_y * cos_p
    dPsi = omega_z

    return [dv_x, dv_y, domega_z, dX, dY, dPsi]

def simulate_maneuver(
    p: HandlingParams,
    v_x_init: float,
    steering_func: Callable[[float], float],
    throttle_func: Callable[[float], float],
    brake_func: Callable[[float], float],
    duration: float = 10.0,
    dt: float = 0.01
) -> dict:
    
    t_eval = np.arange(0, duration, dt)
    x0 = [v_x_init, 0.0, 0.0, 0.0, 0.0, 0.0]
    
    sol = solve_ivp(
        fun=_handling_ode,
        t_span=(0.0, duration),
        y0=x0,
        args=(p, steering_func, throttle_func, brake_func),
        method='RK45',
        t_eval=t_eval,
        rtol=1e-4,
        atol=1e-6,
        max_step=0.05
    )
    
    # Post-process for telemetry
    v_x, v_y, omega_z, X, Y, Psi = sol.y
    a_x = np.gradient(v_x, dt) - v_y * omega_z
    a_y = np.gradient(v_y, dt) + v_x * omega_z
    
    return {
        "time": t_eval,
        "v_x": v_x,
        "v_y": v_y,
        "yaw_rate": omega_z,
        "X": X,
        "Y": Y,
        "Psi": Psi,
        "a_x": a_x,
        "a_y": a_y,
        "slip_angle": np.arctan2(v_y, np.maximum(v_x, 0.1))
    }
