"""
physics/handling_model.py
=========================
SuspensionLab PRO — Non-Linear Handling Dynamics
3-DOF Body + 4-Wheel Handling Model with Quasi-Static Load Transfer and Magic Formula Tires.

Mathematical Formulation Update
-------------------------------
The previous iterative predictor-corrector for algebraic load transfer has been removed.
Instead of embedding a discrete solver inside a continuous ODE (which breaks Jacobian estimation
and causes silent solver failures during transient maneuvers), the system has been reformulated as a
stiff ODE. By introducing physical relaxation time constants (tau ~ 0.05s) for load transfer
accelerations (a_x, a_y), we simulate the true physical delay of suspension compliance and
tire carcass relaxation. This breaks the algebraic loop (F_z <-> a <-> F_z) and allows
Scipy's BDF solver to natively compute the exact system Jacobian without requiring external
DAE solvers like SUNDIALS IDA.
"""

import numpy as np
from scipy.integrate import solve_ivp
from dataclasses import dataclass, field
from typing import Callable
from scipy.interpolate import interp1d
from suspensionlab.physics.magic_formula import calc_tire_forces, TireCoeffs

class SuspensionLUT:
    def __init__(self, lut_dict: dict):
        self.lut = lut_dict
        self.heave_z = self.lut["heave_z"]
        
        # 1D interpolation over heave
        self.interp_camber = interp1d(self.heave_z, self.lut["camber"], bounds_error=False, fill_value="extrapolate")
        self.interp_toe = interp1d(self.heave_z, self.lut["toe"], bounds_error=False, fill_value="extrapolate")
        self.interp_rc_z = interp1d(self.heave_z, self.lut["rc_z"], bounds_error=False, fill_value="extrapolate")
        
    def evaluate(self, heave: float):
        return {
            "camber": float(self.interp_camber(heave)),
            "toe": float(self.interp_toe(heave)),
            "h_rc": float(self.interp_rc_z(heave))
        }

@dataclass
class HandlingParams:
    kinematics_lut_f: SuspensionLUT = None
    kinematics_lut_r: SuspensionLUT = None
    m: float = 1200.0       # Mass (kg) (legacy, overrides components if changed alone)
    m_s: float = 1000.0     # Sprung mass (kg)
    m_uf: float = 100.0     # Unsprung mass front (kg)
    m_ur: float = 100.0     # Unsprung mass rear (kg)
    I_z: float = 2000.0     # Yaw inertia (kg*m^2)
    a: float = 1.2          # CG to front axle (m)
    b: float = 1.4          # CG to rear axle (m)
    tw_f: float = 1.6       # Track width front (m)
    tw_r: float = 1.6       # Track width rear (m)
    h_cg_s: float = 0.45    # Sprung mass CG height (m)
    h_cg_uf: float = 0.3    # Front unsprung CG height (m)
    h_cg_ur: float = 0.3    # Rear unsprung CG height (m)
    
    # Roll stiffness distribution (front fraction)
    roll_dist: float = 0.55 
    
    # Aerodynamics
    C_d: float = 0.3
    C_l: float = 0.1
    frontal_area: float = 2.2
    rho_air: float = 1.225
    
    # Physical relaxation time for load transfer (seconds)
    tau_load_transfer: float = 0.05

    relaxation_length_x: float = 0.3 # m
    relaxation_length_y: float = 0.3 # m

    # Dual Path stiffness parameters
    K_spring_f: float = 30000.0  # N/m
    K_spring_r: float = 30000.0  # N/m
    K_arb_f: float = 20000.0     # Nm/rad
    K_arb_r: float = 10000.0     # Nm/rad

    tire_coeffs: TireCoeffs = field(default_factory=TireCoeffs)

    def __post_init__(self):
        if self.kinematics_lut_f is None or self.kinematics_lut_r is None:
            import numpy as np
            from suspensionlab.physics.api_models import safe_generate_kinematic_lut
            heave_sweep = np.linspace(-0.1, 0.1, 100)
            roll_sweep = np.linspace(-5.0, 5.0, 100)
            
            front_hp = {
                "chassis_strut_top": {"x": 0.0, "y": 0.45, "z": 0.6},
                "chassis_lower_front": {"x": 0.1, "y": 0.3, "z": 0.2},
                "chassis_lower_rear": {"x": -0.1, "y": 0.3, "z": 0.2},
                "upright_lower": {"x": 0.0, "y": 0.6, "z": 0.2},
                "upright_strut_mount": {"x": 0.0, "y": 0.55, "z": 0.4},
                "upright_tie_rod": {"x": 0.1, "y": 0.55, "z": 0.3},
                "chassis_tie_rod": {"x": 0.1, "y": 0.2, "z": 0.3},
                "wheel_center": {"x": 0.0, "y": 0.65, "z": 0.3}
            }
            lut_f = safe_generate_kinematic_lut("macpherson", front_hp, heave_sweep, roll_sweep)
            
            rear_hp = {
                "chassis_upper_front": {"x": 0.1, "y": 0.4, "z": 0.4},
                "chassis_upper_rear": {"x": -0.1, "y": 0.4, "z": 0.4},
                "chassis_lower_front": {"x": 0.1, "y": 0.3, "z": 0.2},
                "chassis_lower_rear": {"x": -0.1, "y": 0.3, "z": 0.2},
                "upright_upper": {"x": 0.0, "y": 0.6, "z": 0.45},
                "upright_lower": {"x": 0.0, "y": 0.6, "z": 0.2},
                "upright_tie_rod": {"x": 0.1, "y": 0.6, "z": 0.3},
                "chassis_tie_rod": {"x": 0.1, "y": 0.3, "z": 0.3},
                "wheel_center": {"x": 0.0, "y": 0.65, "z": 0.33}
            }
            lut_r = safe_generate_kinematic_lut("double_wishbone", rear_hp, heave_sweep, roll_sweep)
            
            if self.kinematics_lut_f is None:
                self.kinematics_lut_f = SuspensionLUT(lut_f)
            if self.kinematics_lut_r is None:
                self.kinematics_lut_r = SuspensionLUT(lut_r)

        if self.m != 1200.0 and self.m_s == 1000.0:
            ratio = self.m / 1200.0
            self.m_s *= ratio
            self.m_uf *= ratio
            self.m_ur *= ratio
        else:
            self.m = self.m_s + self.m_uf + self.m_ur

        import math
        for name, val in self.__dict__.items():
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                raise ValueError(f"Parameter '{name}' cannot be NaN or infinite.")
        if self.m <= 0.1:
            raise ValueError("Vehicle mass 'm' must be strictly > 0.1 to avoid division by zero in ODE.")
        if self.I_z <= 0.1:
            raise ValueError("Yaw moment of inertia 'I_z' must be strictly > 0.1 to avoid division by zero in ODE.")
        if self.tw_f <= 0.1 or self.tw_r <= 0.1:
            raise ValueError("Track width must be strictly > 0.1 to avoid division by zero in ODE.")
        if self.tau_load_transfer <= 0.001:
            self.tau_load_transfer = 0.001 # Prevent infinite stiffness

def _handling_ode(
    t: float, 
    x: list[float], 
    p: HandlingParams, 
    steering_func: Callable[[float], float], 
    throttle_func: Callable[[float], float],
    brake_func: Callable[[float], float]
):
    """
    x = [v_x, v_y, omega_z, X, Y, Psi, a_x_filt, a_y_filt, Fx_fl, Fy_fl, Fx_fr, Fy_fr, Fx_rl, Fy_rl, Fx_rr, Fy_rr]
    v_x, v_y: longitudinal and lateral velocity in body frame
    omega_z: yaw rate
    X, Y, Psi: global position and heading
    a_x_filt, a_y_filt: filtered accelerations for load transfer (breaks algebraic loop)
    Fx_fl ... Fy_rr: transient tire force states
    """
    v_x, v_y, omega_z, X, Y, Psi, a_x_filt, a_y_filt = x[:8]
    Fx_fl, Fy_fl, Fx_fr, Fy_fr, Fx_rl, Fy_rl, Fx_rr, Fy_rr = x[8:16]
    
    # Smooth velocity blend to prevent denominator division-by-zero.
    # IMPORTANT: We use v_x_safe ONLY in denominators — v_x must retain its
    # sign for all dynamics (braking = negative v_x, reversing, yaw equations).
    v_x_safe = np.sqrt(v_x**2 + 0.01**2)
    
    delta = steering_func(t)
    throttle = throttle_func(t) # 0 to 1
    brake = brake_func(t)       # 0 to 1

    # 1. Kinematics (Slip Angles) — use v_x (signed) for longitudinal, v_x_safe for denominators
    v_x_fl = v_x - omega_z * p.tw_f / 2
    v_x_fr = v_x + omega_z * p.tw_f / 2
    v_x_rl = v_x - omega_z * p.tw_r / 2
    v_x_rr = v_x + omega_z * p.tw_r / 2

    v_y_f = v_y + p.a * omega_z
    v_y_r = v_y - p.b * omega_z

    # Prevent zero division in slip angle (using the safe blend in denominator)
    v_x_fl_safe = v_x_fl if abs(v_x_fl) > 0.1 else (0.1 if v_x_fl >= 0 else -0.1)
    v_x_fr_safe = v_x_fr if abs(v_x_fr) > 0.1 else (0.1 if v_x_fr >= 0 else -0.1)
    v_x_rl_safe = v_x_rl if abs(v_x_rl) > 0.1 else (0.1 if v_x_rl >= 0 else -0.1)
    v_x_rr_safe = v_x_rr if abs(v_x_rr) > 0.1 else (0.1 if v_x_rr >= 0 else -0.1)

    delta_fl = delta
    delta_fr = delta
    delta_rl = 0.0
    delta_rr = 0.0

    # Delete old alpha computation because we deferred it to after delta assignment

    # Simplified drive/brake torque logic (RWD biased)
    max_accel = 5.0 
    max_decel = 10.0
    
    kappa_f = -brake * 0.1 
    kappa_r = (throttle * max_accel - brake * max_decel * 0.6) / 50.0

    # 2. Quasi-Static Load Transfer (Using filtered acceleration states)
    L = p.a + p.b
    W_s = p.m_s * 9.81
    W_uf = p.m_uf * 9.81
    W_ur = p.m_ur * 9.81
    
    # Static load
    W_f_static = W_s * p.b / L + W_uf
    W_r_static = W_s * p.a / L + W_ur
    
    # Aero downforce and drag
    v_mag = np.sqrt(v_x**2 + v_y**2)
    F_aero_d = 0.5 * p.rho_air * p.C_d * p.frontal_area * v_mag**2 * np.sign(v_x)
    F_aero_l = 0.5 * p.rho_air * p.C_l * p.frontal_area * v_mag**2
    
    # Longitudinal load transfer (Sprung + Unsprung)
    h_cg_total = (p.m_s * p.h_cg_s + p.m_uf * p.h_cg_uf + p.m_ur * p.h_cg_ur) / p.m
    delta_Fz_long = (p.m * a_x_filt * h_cg_total) / L
    
    # Total dynamic axle loads
    Fz_f_total = W_f_static - delta_Fz_long + (F_aero_l * p.b / L)
    Fz_r_total = W_r_static + delta_Fz_long + (F_aero_l * p.a / L)

    # Lateral load transfer
    # 1. Unsprung mass transfer
    delta_Fz_lat_uf = (p.m_uf * a_y_filt * p.h_cg_uf) / p.tw_f
    delta_Fz_lat_ur = (p.m_ur * a_y_filt * p.h_cg_ur) / p.tw_r
    
    # Kinematics LUT Integration (Strict Path)
    heave_f = delta_Fz_long / (2 * p.K_spring_f)
    heave_r = -delta_Fz_long / (2 * p.K_spring_r)
    
    M_roll_total = p.m_s * a_y_filt * p.h_cg_s
    K_roll_f = 0.5 * p.K_spring_f * p.tw_f**2 + p.K_arb_f
    K_roll_r = 0.5 * p.K_spring_r * p.tw_r**2 + p.K_arb_r
    
    roll_f = (M_roll_total * p.roll_dist) / K_roll_f
    roll_r = (M_roll_total * (1 - p.roll_dist)) / K_roll_r
    
    z_fl = heave_f + roll_f * (p.tw_f / 2)
    z_fr = heave_f - roll_f * (p.tw_f / 2)
    z_rl = heave_r + roll_r * (p.tw_r / 2)
    z_rr = heave_r - roll_r * (p.tw_r / 2)
    
    kin_fl = p.kinematics_lut_f.evaluate(z_fl)
    kin_fr = p.kinematics_lut_f.evaluate(z_fr)
    kin_rl = p.kinematics_lut_r.evaluate(z_rl)
    kin_rr = p.kinematics_lut_r.evaluate(z_rr)
    
    h_rc_f_dynamic = (kin_fl["h_rc"] + kin_fr["h_rc"]) / 2.0
    h_rc_r_dynamic = (kin_rl["h_rc"] + kin_rr["h_rc"]) / 2.0
    
    camber_fl = kin_fl["camber"] * (np.pi/180)
    camber_fr = -kin_fr["camber"] * (np.pi/180)
    camber_rl = kin_rl["camber"] * (np.pi/180)
    camber_rr = -kin_rr["camber"] * (np.pi/180)
    
    delta_fl += kin_fl["toe"] * (np.pi/180)
    delta_fr -= kin_fr["toe"] * (np.pi/180)
    delta_rl += kin_rl["toe"] * (np.pi/180)
    delta_rr -= kin_rr["toe"] * (np.pi/180)

    # 2. Kinematic (Geometric) transfer through roll centers
    delta_Fz_lat_kin_f = (p.m_s * (p.b / L) * a_y_filt * h_rc_f_dynamic) / p.tw_f
    delta_Fz_lat_kin_r = (p.m_s * (p.a / L) * a_y_filt * h_rc_r_dynamic) / p.tw_r
    
    # 3. Elastic (Roll) transfer
    h_rc_cg = h_rc_f_dynamic + (h_rc_r_dynamic - h_rc_f_dynamic) * (p.a / L)
    M_roll = p.m_s * a_y_filt * (p.h_cg_s - h_rc_cg)
    
    delta_Fz_lat_elast_f = (M_roll * p.roll_dist) / p.tw_f
    delta_Fz_lat_elast_r = (M_roll * (1 - p.roll_dist)) / p.tw_r
    
    delta_Fz_lat_f = delta_Fz_lat_uf + delta_Fz_lat_kin_f + delta_Fz_lat_elast_f
    delta_Fz_lat_r = delta_Fz_lat_ur + delta_Fz_lat_kin_r + delta_Fz_lat_elast_r

    Fz_fl = max(Fz_f_total / 2 - delta_Fz_lat_f, 10.0)
    Fz_fr = max(Fz_f_total / 2 + delta_Fz_lat_f, 10.0)
    Fz_rl = max(Fz_r_total / 2 - delta_Fz_lat_r, 10.0)
    Fz_rr = max(Fz_r_total / 2 + delta_Fz_lat_r, 10.0)

    # Corrected steered-axle slip angles with updated steer angles
    v_wheel_x_fl = v_x_fl_safe * np.cos(delta_fl) + v_y_f * np.sin(delta_fl)
    v_wheel_y_fl = -v_x_fl_safe * np.sin(delta_fl) + v_y_f * np.cos(delta_fl)
    alpha_fl = -np.arctan2(v_wheel_y_fl, v_wheel_x_fl)

    v_wheel_x_fr = v_x_fr_safe * np.cos(delta_fr) + v_y_f * np.sin(delta_fr)
    v_wheel_y_fr = -v_x_fr_safe * np.sin(delta_fr) + v_y_f * np.cos(delta_fr)
    alpha_fr = -np.arctan2(v_wheel_y_fr, v_wheel_x_fr)
    
    v_wheel_x_rl = v_x_rl_safe * np.cos(delta_rl) + v_y_r * np.sin(delta_rl)
    v_wheel_y_rl = -v_x_rl_safe * np.sin(delta_rl) + v_y_r * np.cos(delta_rl)
    alpha_rl = -np.arctan2(v_wheel_y_rl, v_wheel_x_rl)

    v_wheel_x_rr = v_x_rr_safe * np.cos(delta_rr) + v_y_r * np.sin(delta_rr)
    v_wheel_y_rr = -v_x_rr_safe * np.sin(delta_rr) + v_y_r * np.cos(delta_rr)
    alpha_rr = -np.arctan2(v_wheel_y_rr, v_wheel_x_rr)

    # 3. Tire Forces (Steady State)
    Fx_fl_ss, Fy_fl_ss = calc_tire_forces(Fz_fl, alpha_fl, kappa_f, camber_fl, p.tire_coeffs)
    Fx_fr_ss, Fy_fr_ss = calc_tire_forces(Fz_fr, alpha_fr, kappa_f, camber_fr, p.tire_coeffs)
    Fx_rl_ss, Fy_rl_ss = calc_tire_forces(Fz_rl, alpha_rl, kappa_r, camber_rl, p.tire_coeffs)
    Fx_rr_ss, Fy_rr_ss = calc_tire_forces(Fz_rr, alpha_rr, kappa_r, camber_rr, p.tire_coeffs)

    # Resolve forces to body frame using per-wheel delta
    cos_d_fl, sin_d_fl = np.cos(delta_fl), np.sin(delta_fl)
    Fx_fl_b = Fx_fl * cos_d_fl - Fy_fl * sin_d_fl
    Fy_fl_b = Fx_fl * sin_d_fl + Fy_fl * cos_d_fl
    
    cos_d_fr, sin_d_fr = np.cos(delta_fr), np.sin(delta_fr)
    Fx_fr_b = Fx_fr * cos_d_fr - Fy_fr * sin_d_fr
    Fy_fr_b = Fx_fr * sin_d_fr + Fy_fr * cos_d_fr
    
    cos_d_rl, sin_d_rl = np.cos(delta_rl), np.sin(delta_rl)
    Fx_rl_b = Fx_rl * cos_d_rl - Fy_rl * sin_d_rl
    Fy_rl_b = Fx_rl * sin_d_rl + Fy_rl * cos_d_rl
    
    cos_d_rr, sin_d_rr = np.cos(delta_rr), np.sin(delta_rr)
    Fx_rr_b = Fx_rr * cos_d_rr - Fy_rr * sin_d_rr
    Fy_rr_b = Fx_rr * sin_d_rr + Fy_rr * cos_d_rr

    # Total body forces
    Sum_Fx = Fx_fl_b + Fx_fr_b + Fx_rl_b + Fx_rr_b - F_aero_d
    Sum_Fy = Fy_fl_b + Fy_fr_b + Fy_rl_b + Fy_rr_b

    # Prevent backwards acceleration under braking at low speeds
    if v_x <= 0.1 and Sum_Fx < 0:
        Sum_Fx = 0.0

    # Yaw moment
    Sum_Mz = (p.a * (Fy_fl_b + Fy_fr_b) - p.b * (Fy_rl_b + Fy_rr_b) 
              - (p.tw_f / 2) * (Fx_fl_b - Fx_fr_b) 
              - (p.tw_r / 2) * (Fx_rl_b - Fx_rr_b))

    # Actual instantaneous accelerations
    a_x_inst = Sum_Fx / p.m
    a_y_inst = Sum_Fy / p.m

    # 4. State Derivatives
    dv_x = a_x_inst + v_y * omega_z
    dv_y = a_y_inst - v_x * omega_z
    domega_z = Sum_Mz / p.I_z
    
    # Global coordinates
    cos_p, sin_p = np.cos(Psi), np.sin(Psi)
    dX = v_x * cos_p - v_y * sin_p
    dY = v_x * sin_p + v_y * cos_p
    dPsi = omega_z

    # Relaxation ODEs for filtered accelerations (Stiff)
    da_x_filt = (a_x_inst - a_x_filt) / p.tau_load_transfer
    da_y_filt = (a_y_inst - a_y_filt) / p.tau_load_transfer
    
    # Relaxation ODEs for tire forces (Transport velocity ~ v_x)
    relax_v = max(v_x, 0.1)
    sig_x = max(p.relaxation_length_x, 0.01)
    sig_y = max(p.relaxation_length_y, 0.01)
    
    dFx_fl = (Fx_fl_ss - Fx_fl) * (relax_v / sig_x)
    dFy_fl = (Fy_fl_ss - Fy_fl) * (relax_v / sig_y)
    dFx_fr = (Fx_fr_ss - Fx_fr) * (relax_v / sig_x)
    dFy_fr = (Fy_fr_ss - Fy_fr) * (relax_v / sig_y)
    dFx_rl = (Fx_rl_ss - Fx_rl) * (relax_v / sig_x)
    dFy_rl = (Fy_rl_ss - Fy_rl) * (relax_v / sig_y)
    dFx_rr = (Fx_rr_ss - Fx_rr) * (relax_v / sig_x)
    dFy_rr = (Fy_rr_ss - Fy_rr) * (relax_v / sig_y)

    return [dv_x, dv_y, domega_z, dX, dY, dPsi, da_x_filt, da_y_filt, 
            dFx_fl, dFy_fl, dFx_fr, dFy_fr, dFx_rl, dFy_rl, dFx_rr, dFy_rr]

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
    # Initialize 8 rigid body states and 8 tire force states
    x0 = [v_x_init, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] + [0.0]*8
    
    # BDF is strongly recommended here because the relaxation ODEs are stiff
    sol = solve_ivp(
        fun=_handling_ode,
        t_span=(0.0, duration),
        y0=x0,
        args=(p, steering_func, throttle_func, brake_func),
        method='BDF',
        t_eval=t_eval,
        rtol=1e-5,
        atol=1e-7,
        max_step=0.05
    )
    
    if not sol.success:
        from suspensionlab.physics.exceptions import MathConvergenceError
        raise MathConvergenceError(f"Handling model failed to converge: {sol.message}")
    
    # Post-process for telemetry
    v_x, v_y, omega_z, X, Y, Psi, a_x_filt, a_y_filt = sol.y[:8]
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
