"""
physics/half_car.py
===================
SuspensionLab PRO — Half Car (Pitch-Plane) Physics Module
4-DOF Linear Half Car Model

Model description
-----------------
Sprung mass: body/chassis (m_s), pitch inertia (I_y)
Unsprung masses: front (m_uf), rear (m_ur)

State-space formulation
-----------------------
State vector  x = [z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur]^T
Inputs        u = [z_rf, z_rr]^T  (road displacement at front and rear)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import eigvals

from suspensionlab.physics.quarter_car import RoadProfile, _road_profile_fn
from suspensionlab.physics.contracts import (
    ContactState,
    PhysicsDiagnostics,
    PhysicsProvenance,
    CanonicalRoadProfile,
    compute_dataset_hash,
)
from suspensionlab.physics.anti_geometry import ForceMomentLedger


# ─────────────────────────────────────────────────────────────────────────────
# Data Contracts
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HalfCarParams:
    """All physical parameters for the 4-DOF half car model."""
    m_s: float = 1200.0   # kg (total sprung mass)
    I_y: float = 1800.0   # kg*m^2 (pitch inertia)
    m_uf: float = 40.0    # kg (front unsprung mass)
    m_ur: float = 40.0    # kg (rear unsprung mass)
    k_sf: float = 30_000.0 # N/m (front wheel rate)
    k_sr: float = 35_000.0 # N/m (rear wheel rate)
    c_f: float = 2_500.0  # Ns/m (front damping)
    c_r: float = 3_000.0  # Ns/m (rear damping)
    k_tf: float = 250_000.0 # N/m (front tire stiffness)
    k_tr: float = 250_000.0 # N/m (rear tire stiffness)
    L: float = 2.6        # m (wheelbase)
    a: float = 1.2        # m (CG to front axle)
    b: float = 1.4        # m (CG to rear axle)
    speed_mps: float = 20.0 # m/s (vehicle speed for rear wheel time delay)
    c_tf: float = 0.0     # Ns/m (front tire damping)
    c_tr: float = 0.0     # Ns/m (rear tire damping)
    # Advanced nonlinear springs
    k_sf_nl: list[float] | None = None
    k_sr_nl: list[float] | None = None
    z_0_f: float = 0.0
    z_0_r: float = 0.0
    
    # Advanced progressive dampers (split comp/rebound)
    damper_curve_v_f: list[float] | None = None
    damper_curve_f_f: list[float] | None = None
    damper_curve_v_f_comp: list[float] | None = None
    damper_curve_f_f_comp: list[float] | None = None
    damper_curve_v_f_reb: list[float] | None = None
    damper_curve_f_f_reb: list[float] | None = None

    damper_curve_v_r: list[float] | None = None
    damper_curve_f_r: list[float] | None = None
    damper_curve_v_r_comp: list[float] | None = None
    damper_curve_f_r_comp: list[float] | None = None
    damper_curve_v_r_reb: list[float] | None = None
    damper_curve_f_r_reb: list[float] | None = None
    
    # Non-linear limits
    bump_stop_comp_f: float = 0.1    # m (suspension compression limit)
    bump_stop_ext_f: float = -0.1    # m (suspension extension limit)
    bump_stop_rate_f: float = 0.0    # N/m
    bump_stop_exp_f: float = 50.0
    
    bump_stop_comp_r: float = 0.1    # m
    bump_stop_ext_r: float = -0.1    # m
    bump_stop_rate_r: float = 0.0    # N/m
    bump_stop_exp_r: float = 50.0
    
    # Stribeck friction model
    coulomb_friction_f: float = 0.0  # N
    stribeck_fs_f: float = 0.0
    stribeck_fc_f: float = 0.0
    stribeck_vs_f: float = 0.01
    stribeck_sigma_f: float = 0.0

    coulomb_friction_r: float = 0.0  # N
    stribeck_fs_r: float = 0.0
    stribeck_fc_r: float = 0.0
    stribeck_vs_r: float = 0.01
    stribeck_sigma_r: float = 0.0
    enable_contact_loss: bool = True  # Enable nonlinear tire liftoff clamping (Fz >= 0)
    
    # Longitudinal acceleration and physically derived anti-geometry
    a_x: float = 0.0                      # m/s^2 (longitudinal acceleration: <0 braking, >0 drive)
    h_cg: float = 0.35                    # m (CG height above ground)
    anti_dive_f: float = 0.0              # fraction 0..1 front anti-dive
    anti_lift_r: float = 0.0              # fraction 0..1 rear anti-lift (braking)
    anti_squat_r: float = 0.0             # fraction 0..1 rear anti-squat (drive)
    anti_lift_f: float = 0.0              # fraction 0..1 front anti-lift (drive)

    def __post_init__(self) -> None:
        import math
        for name, val in self.__dict__.items():
            if name in ("bump_stop_ext_f", "bump_stop_ext_r", "enable_contact_loss", "a_x"):
                continue
            if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"Parameter '{name}' cannot be NaN or infinite.")
                if name in ("k_sf", "k_sr") and val < 1000.0:
                    raise ValueError(f"Spring rate '{name}' must be at least 1,000 N/m (got {val}).")
                if name in ("k_tf", "k_tr") and val < 10000.0:
                    raise ValueError(f"Tire vertical stiffness '{name}' must be at least 10,000 N/m (got {val}).")
                if name in ("m_s", "m_uf", "m_ur") and val < 0.1:
                    raise ValueError(f"Mass '{name}' must be strictly positive >= 0.1 kg (got {val}).")
                if name == "I_y" and val <= 0.0:
                    raise ValueError(f"Pitch inertia 'I_y' must be strictly positive (got {val}).")
                if name in ("a", "b", "L") and val <= 0.0:
                    raise ValueError(f"Geometric parameter '{name}' must be strictly positive (got {val}).")
                if val < 0:
                    raise ValueError(f"Parameter '{name}' must be non-negative, got {val}")

        # Validate wheelbase consistency instead of silently overwriting L.
        # If L != a + b the user has provided contradictory geometry.
        expected_L = self.a + self.b
        if abs(self.L - expected_L) > 1e-3:
            raise ValueError(
                f"Wheelbase L={self.L:.4f} m is inconsistent with "
                f"a + b = {self.a:.4f} + {self.b:.4f} = {expected_L:.4f} m. "
                f"Either set L = a + b, or omit L and it will be inferred."
            )


@dataclass
class HalfCarResult:
    """Complete analysis results from the half car model."""
    # Frequencies (extracted from eigenvalues)
    f_n_heave: float = 0.0
    f_n_pitch: float = 0.0
    f_n_uf: float = 0.0
    f_n_ur: float = 0.0

    # Time domain
    time: np.ndarray = field(default_factory=lambda: np.array([]))
    z_s: np.ndarray = field(default_factory=lambda: np.array([]))
    theta: np.ndarray = field(default_factory=lambda: np.array([]))
    z_uf: np.ndarray = field(default_factory=lambda: np.array([]))
    z_ur: np.ndarray = field(default_factory=lambda: np.array([]))
    z_rf: np.ndarray = field(default_factory=lambda: np.array([]))
    z_rr: np.ndarray = field(default_factory=lambda: np.array([]))
    dz_s: np.ndarray = field(default_factory=lambda: np.array([]))
    dtheta: np.ndarray = field(default_factory=lambda: np.array([]))
    ddz_s: np.ndarray = field(default_factory=lambda: np.array([]))
    ddtheta: np.ndarray = field(default_factory=lambda: np.array([]))
    susp_travel_f: np.ndarray = field(default_factory=lambda: np.array([]))
    susp_travel_r: np.ndarray = field(default_factory=lambda: np.array([]))
    tire_load_f: np.ndarray = field(default_factory=lambda: np.array([]))
    tire_load_r: np.ndarray = field(default_factory=lambda: np.array([]))
    
    # Metrics
    rms_heave_accel: float = 0.0
    rms_heave_accel_wk: float = 0.0
    rms_pitch_accel: float = 0.0
    rms_susp_travel_f: float = 0.0
    rms_susp_travel_r: float = 0.0
    rms_tire_load_f: float = 0.0
    rms_tire_load_r: float = 0.0

    # Contact & Conservation Diagnostics
    contact_states_f: List[Any] = field(default_factory=list)
    contact_states_r: List[Any] = field(default_factory=list)
    liftoff_time_f: Optional[float] = None
    liftoff_time_r: Optional[float] = None
    minimum_Fz_f: float = 0.0
    minimum_Fz_r: float = 0.0
    diagnostics: Optional[PhysicsDiagnostics] = None
    provenance: Optional[PhysicsProvenance] = None
    ledger: Optional[ForceMomentLedger] = None


# ─────────────────────────────────────────────────────────────────────────────
# State-Space Matrix Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_state_space(p: HalfCarParams) -> tuple[np.ndarray, np.ndarray]:
    """
    Build the 8x8 system matrix A and input vector B for the half car.
    State: x = [z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur]
    """
    A = np.zeros((8, 8))
    B = np.zeros((8, 2))  # Inputs: [z_rf, z_rr]
    
    # x1 = z_s, x2 = dz_s
    A[0, 1] = 1.0
    # x3 = theta, x4 = dtheta
    A[2, 3] = 1.0
    # x5 = z_uf, x6 = dz_uf
    A[4, 5] = 1.0
    # x7 = z_ur, x8 = dz_ur
    A[6, 7] = 1.0

    m_s, I_y, m_uf, m_ur = p.m_s, p.I_y, p.m_uf, p.m_ur
    k_sf, k_sr, c_f, c_r = p.k_sf, p.k_sr, p.c_f, p.c_r
    k_tf, k_tr = p.k_tf, p.k_tr
    c_tf, c_tr = p.c_tf, p.c_tr
    a, b = p.a, p.b

    # ddz_s (row 1)
    A[1, 0] = -(k_sf + k_sr) / m_s
    A[1, 1] = -(c_f + c_r) / m_s
    A[1, 2] = (a * k_sf - b * k_sr) / m_s
    A[1, 3] = (a * c_f - b * c_r) / m_s
    A[1, 4] = k_sf / m_s
    A[1, 5] = c_f / m_s
    A[1, 6] = k_sr / m_s
    A[1, 7] = c_r / m_s

    # ddtheta (row 3)
    A[3, 0] = (a * k_sf - b * k_sr) / I_y
    A[3, 1] = (a * c_f - b * c_r) / I_y
    A[3, 2] = -(a**2 * k_sf + b**2 * k_sr) / I_y
    A[3, 3] = -(a**2 * c_f + b**2 * c_r) / I_y
    A[3, 4] = -a * k_sf / I_y
    A[3, 5] = -a * c_f / I_y
    A[3, 6] = b * k_sr / I_y
    A[3, 7] = b * c_r / I_y

    # ddz_uf (row 5)
    A[5, 0] = k_sf / m_uf
    A[5, 1] = c_f / m_uf
    A[5, 2] = -a * k_sf / m_uf
    A[5, 3] = -a * c_f / m_uf
    A[5, 4] = -(k_sf + k_tf) / m_uf
    A[5, 5] = -(c_f + c_tf) / m_uf
    
    # ddz_ur (row 7)
    # F_sr acts on z_ur via spring: F_sr = k_sr*(z_sr - z_ur), z_sr = z_s + b*theta
    # So ddz_ur gets: +k_sr/m_ur * z_s  +b*k_sr/m_ur * theta  (pitch coupling is POSITIVE)
    A[7, 0] = k_sr / m_ur
    A[7, 1] = c_r / m_ur
    A[7, 2] = b * k_sr / m_ur    # CORRECTED: positive pitch coupling
    A[7, 3] = b * c_r / m_ur    # CORRECTED: positive pitch coupling
    A[7, 6] = -(k_sr + k_tr) / m_ur
    A[7, 7] = -(c_r + c_tr) / m_ur

    # B Matrix (assuming only displacement inputs, velocity inputs ignored for B matrix formulation)
    B[5, 0] = k_tf / m_uf
    B[7, 1] = k_tr / m_ur

    return A, B


def compute_modal_properties(p: HalfCarParams) -> dict:
    from scipy.linalg import eig
    A, _ = build_state_space(p)
    eigs, vecs = eig(A)
    
    # Identify modes via dominant eigenvectors
    f_n_heave = 0.0
    f_n_pitch = 0.0
    f_n_uf = 0.0
    f_n_ur = 0.0
    
    seen = set()
    for i in range(len(eigs)):
        lam = eigs[i]
        if lam.imag <= 1e-6:
            continue
            
        key = round(abs(lam), 4)  # group conjugate pairs
        if key in seen:
            continue
        seen.add(key)
            
        wn = abs(lam)
        fn = wn / (2.0 * np.pi)
        
        mode_shape = np.abs(vecs[:, i])
        # Indices: 0: zs, 1: dzs, 2: theta, 3: dtheta, 4: zuf, 5: dzuf, 6: zur, 7: dzur
        # Scale pitch (rad) by half wheelbase (m) to match heave displacement (m) units
        mode_shape[2] *= p.L / 2.0
        dom_idx = np.argmax(mode_shape[[0, 2, 4, 6]]) # check displacements
        
        if dom_idx == 0:
            f_n_heave = float(fn)
        elif dom_idx == 1:
            f_n_pitch = float(fn)
        elif dom_idx == 2:
            f_n_uf = float(fn)
        elif dom_idx == 3:
            f_n_ur = float(fn)
    
    return {
        "f_n_heave": float(f_n_heave),
        "f_n_pitch": float(f_n_pitch),
        "f_n_uf": float(f_n_uf),
        "f_n_ur": float(f_n_ur),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ODE Right-Hand Side
# ─────────────────────────────────────────────────────────────────────────────


def _compute_forces(p: HalfCarParams, z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur):
    z_sf = z_s - p.a * theta
    z_sr = z_s + p.b * theta
    dz_sf = dz_s - p.a * dtheta
    dz_sr = dz_s + p.b * dtheta

    v_rel_f = dz_uf - dz_sf
    z_rel_f = z_uf - z_sf
    z_rel_f_adj = z_rel_f - p.z_0_f
    
    v_rel_r = dz_ur - dz_sr
    z_rel_r = z_ur - z_sr
    z_rel_r_adj = z_rel_r - p.z_0_r
    
    # Dampers Front
    F_damper_f = np.zeros_like(v_rel_f)
    if p.damper_curve_v_f_comp is not None and p.damper_curve_f_f_comp is not None and p.damper_curve_v_f_reb is not None and p.damper_curve_f_f_reb is not None:
        F_comp = np.interp(v_rel_f, p.damper_curve_v_f_comp, p.damper_curve_f_f_comp)
        F_reb = np.interp(v_rel_f, p.damper_curve_v_f_reb, p.damper_curve_f_f_reb)
        F_damper_f = np.where(v_rel_f > 0, F_comp, F_reb)
    elif p.damper_curve_v_f is not None and p.damper_curve_f_f is not None and len(p.damper_curve_v_f) > 1:
        F_damper_f = np.interp(v_rel_f, p.damper_curve_v_f, p.damper_curve_f_f)
    else:
        F_damper_f = p.c_f * v_rel_f
        
    if p.stribeck_fs_f > 0 or p.stribeck_fc_f > 0:
        fric_f = (p.stribeck_fc_f + (p.stribeck_fs_f - p.stribeck_fc_f) * np.exp(-(v_rel_f / p.stribeck_vs_f)**2)) * np.tanh(v_rel_f / 0.01) + p.stribeck_sigma_f * v_rel_f
        F_damper_f += fric_f
    elif p.coulomb_friction_f > 0:
        F_damper_f += p.coulomb_friction_f * np.tanh(v_rel_f / 0.01)

    # Dampers Rear
    F_damper_r = np.zeros_like(v_rel_r)
    if p.damper_curve_v_r_comp is not None and p.damper_curve_f_r_comp is not None and p.damper_curve_v_r_reb is not None and p.damper_curve_f_r_reb is not None:
        F_comp = np.interp(v_rel_r, p.damper_curve_v_r_comp, p.damper_curve_f_r_comp)
        F_reb = np.interp(v_rel_r, p.damper_curve_v_r_reb, p.damper_curve_f_r_reb)
        F_damper_r = np.where(v_rel_r > 0, F_comp, F_reb)
    elif p.damper_curve_v_r is not None and p.damper_curve_f_r is not None and len(p.damper_curve_v_r) > 1:
        F_damper_r = np.interp(v_rel_r, p.damper_curve_v_r, p.damper_curve_f_r)
    else:
        F_damper_r = p.c_r * v_rel_r
        
    if p.stribeck_fs_r > 0 or p.stribeck_fc_r > 0:
        fric_r = (p.stribeck_fc_r + (p.stribeck_fs_r - p.stribeck_fc_r) * np.exp(-(v_rel_r / p.stribeck_vs_r)**2)) * np.tanh(v_rel_r / 0.01) + p.stribeck_sigma_r * v_rel_r
        F_damper_r += fric_r
    elif p.coulomb_friction_r > 0:
        F_damper_r += p.coulomb_friction_r * np.tanh(v_rel_r / 0.01)
        
    # Springs
    if p.k_sf_nl is not None and len(p.k_sf_nl) >= 3:
        F_sf = p.k_sf_nl[0] * z_rel_f_adj + p.k_sf_nl[1] * (z_rel_f_adj**2) + p.k_sf_nl[2] * (z_rel_f_adj**3) + F_damper_f
    else:
        F_sf = p.k_sf * z_rel_f_adj + F_damper_f
        
    if p.k_sr_nl is not None and len(p.k_sr_nl) >= 3:
        F_sr = p.k_sr_nl[0] * z_rel_r_adj + p.k_sr_nl[1] * (z_rel_r_adj**2) + p.k_sr_nl[2] * (z_rel_r_adj**3) + F_damper_r
    else:
        F_sr = p.k_sr * z_rel_r_adj + F_damper_r
    
    # Bump Stops
    if p.bump_stop_rate_f > 0:
        bump_comp_f = np.where(z_rel_f > p.bump_stop_comp_f, p.bump_stop_rate_f * (np.exp(p.bump_stop_exp_f * (z_rel_f - p.bump_stop_comp_f)) - 1.0), 0.0)
        bump_ext_f = np.where(z_rel_f < p.bump_stop_ext_f, -p.bump_stop_rate_f * (np.exp(p.bump_stop_exp_f * (p.bump_stop_ext_f - z_rel_f)) - 1.0), 0.0)
        F_sf += bump_comp_f + bump_ext_f
        
    if p.bump_stop_rate_r > 0:
        bump_comp_r = np.where(z_rel_r > p.bump_stop_comp_r, p.bump_stop_rate_r * (np.exp(p.bump_stop_exp_r * (z_rel_r - p.bump_stop_comp_r)) - 1.0), 0.0)
        bump_ext_r = np.where(z_rel_r < p.bump_stop_ext_r, -p.bump_stop_rate_r * (np.exp(p.bump_stop_exp_r * (p.bump_stop_ext_r - z_rel_r)) - 1.0), 0.0)
        F_sr += bump_comp_r + bump_ext_r
    
    return F_sf, F_sr, z_sf, z_sr

def _half_car_ode(t, x, p: HalfCarParams, zr_fn, dzr_fn, t_delay: float):

    z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur = x
    
    # Front wheel hits bump at t
    z_rf = float(zr_fn(np.array([t]))[0])
    dz_rf = float(dzr_fn(np.array([t]))[0])
    
    # Rear wheel hits bump at t - t_delay
    t_rear = t - t_delay
    z_rr = float(zr_fn(np.array([max(t_rear, 0.0)]))[0]) if t_rear >= 0 else 0.0
    dz_rr = float(dzr_fn(np.array([max(t_rear, 0.0)]))[0]) if t_rear >= 0 else 0.0

    F_sf, F_sr, _, _ = _compute_forces(p, z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur)

    # Longitudinal load transfer and kinematic anti-reaction forces
    L = max(p.a + p.b, 0.5)
    delta_Fz_long = (p.m_s * p.a_x * p.h_cg) / L  # >0 for forward accel, <0 for braking

    if p.a_x < 0.0:
        # Braking (load transfers forward: front load increases, rear decreases)
        trans_front = -delta_Fz_long  # > 0
        F_anti_f = p.anti_dive_f * trans_front   # upward on front chassis (resists dive)
        F_anti_r = -p.anti_lift_r * trans_front  # downward on rear chassis (resists lift)
    else:
        # Traction / Acceleration (load transfers rearward: rear increases, front decreases)
        trans_rear = delta_Fz_long    # >= 0
        F_anti_r = p.anti_squat_r * trans_rear   # upward on rear chassis (resists squat)
        F_anti_f = -p.anti_lift_f * trans_rear  # downward on front chassis (resists lift)

    M_pitch_inertial = -p.m_s * p.a_x * p.h_cg  # In half-car convention, +theta is nose down, so braking (a_x < 0) gives positive nose-down moment

    # Accelerations
    ddz_s = (F_sf + F_sr + F_anti_f + F_anti_r) / p.m_s
    ddtheta = (-p.a * (F_sf + F_anti_f) + p.b * (F_sr + F_anti_r) + M_pitch_inertial) / p.I_y
    
    F_tf = p.k_tf * (z_rf - z_uf) + p.c_tf * (dz_rf - dz_uf)
    F_tr = p.k_tr * (z_rr - z_ur) + p.c_tr * (dz_rr - dz_ur)
    if p.enable_contact_loss:
        # Contact-loss: clamp total tire load (static + dynamic) to >= 0
        static_front = (p.m_s * p.b / (p.a + p.b) + p.m_uf) * 9.81
        static_rear  = (p.m_s * p.a / (p.a + p.b) + p.m_ur) * 9.81
        if static_front + F_tf < 0:
            F_tf = -static_front
        if static_rear + F_tr < 0:
            F_tr = -static_rear

    ddz_uf = (-(F_sf + F_anti_f) + F_tf) / p.m_uf
    ddz_ur = (-(F_sr + F_anti_r) + F_tr) / p.m_ur

    return [dz_s, ddz_s, dtheta, ddtheta, dz_uf, ddz_uf, dz_ur, ddz_ur]


# ─────────────────────────────────────────────────────────────────────────────
# Time Domain Simulation
# ─────────────────────────────────────────────────────────────────────────────

def simulate_time_response(
    p: HalfCarParams,
    profile: RoadProfile,
    t_eval_dt: float = 0.001,
) -> dict:
    zr_fn, dzr_fn = _road_profile_fn(profile)
    t_delay = p.L / p.speed_mps if p.speed_mps > 0 else 0.0

    t_span = (0.0, profile.duration)
    t_eval = np.arange(0.0, profile.duration, t_eval_dt)
    x0 = [0.0] * 8

    sol = solve_ivp(
        fun=_half_car_ode,
        t_span=t_span,
        y0=x0,
        method="LSODA",          # Adaptive stiff/non-stiff solver
        t_eval=t_eval,
        args=(p, zr_fn, dzr_fn, t_delay),
        rtol=1e-5,
        atol=1e-7,
        max_step=0.01,
    )
    if not sol.success:
        # Fallback to BDF with robust stepping
        sol = solve_ivp(
            fun=_half_car_ode,
            t_span=t_span,
            y0=x0,
            method="BDF",
            t_eval=t_eval,
            args=(p, zr_fn, dzr_fn, t_delay),
            rtol=1e-5,
            atol=1e-7,
            max_step=0.005,
        )
    if not sol.success:
        from suspensionlab.physics.exceptions import MathConvergenceError
        raise MathConvergenceError(
            f"Half-car ODE solver failed to converge: {sol.message}. "
            "Try reducing bump amplitude, increasing damping, or shortening duration."
        )

    t = sol.t
    z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur = sol.y
    
    # Reconstruct road profile
    z_rf_arr = zr_fn(t)
    # Vectorized rear road profile with delay — avoid per-element Python loop
    t_rear = t - t_delay
    z_rr_arr = np.where(t_rear >= 0, zr_fn(np.maximum(t_rear, 0.0)), 0.0)

    # Reconstruct accelerations
    F_sf, F_sr, z_sf, z_sr = _compute_forces(p, z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur)

    ddz_s = (F_sf + F_sr) / p.m_s
    ddtheta = (-p.a * F_sf + p.b * F_sr) / p.I_y
    
    susp_travel_f = z_sf - z_uf
    susp_travel_r = z_sr - z_ur
    tire_load_f = p.k_tf * (z_uf - z_rf_arr)
    tire_load_r = p.k_tr * (z_ur - z_rr_arr)
    # Total vertical tire forces
    static_front = (p.m_s * p.b / (p.a + p.b) + p.m_uf) * 9.81
    static_rear  = (p.m_s * p.a / (p.a + p.b) + p.m_ur) * 9.81
    total_Fz_f = np.maximum(0.0, static_front + tire_load_f)
    total_Fz_r = np.maximum(0.0, static_rear + tire_load_r)

    contact_states_f = []
    contact_states_r = []
    liftoff_time_f = None
    liftoff_time_r = None

    for idx in range(len(t)):
        if total_Fz_f[idx] <= 1e-3:
            contact_states_f.append(ContactState.LIFTOFF)
            if liftoff_time_f is None:
                liftoff_time_f = float(t[idx])
        else:
            contact_states_f.append(ContactState.CONTACT)

        if total_Fz_r[idx] <= 1e-3:
            contact_states_r.append(ContactState.LIFTOFF)
            if liftoff_time_r is None:
                liftoff_time_r = float(t[idx])
        else:
            contact_states_r.append(ContactState.CONTACT)

    diagnostics = PhysicsDiagnostics(
        force_residual_max_n=float(np.max(np.abs(p.m_s * ddz_s - (F_sf + F_sr)))),
        moment_residual_max_nm=float(np.max(np.abs(p.I_y * ddtheta - (-p.a * F_sf + p.b * F_sr)))),
        contact_violations_count=int(np.sum(total_Fz_f < -1e-6) + np.sum(total_Fz_r < -1e-6)),
        contact_states=contact_states_f,
        liftoff_time_s=liftoff_time_f,
        minimum_Fz_n=float(min(np.min(total_Fz_f), np.min(total_Fz_r))),
        solver_name="LSODA",
        solver_steps_taken=len(t),
        solver_evaluations=getattr(sol, "nfev", len(t)),
        converged=sol.success,
    )

    provenance = PhysicsProvenance(
        model_version="half-car-4dof-v3.0",
        solver="LSODA",
        backend="scipy.integrate.solve_ivp",
        input_dataset_hash=compute_dataset_hash(p),
        parameter_version="canonical-2026",
    )

    return {
        "time": t,
        "z_s": z_s,
        "theta": theta,
        "z_uf": z_uf,
        "z_ur": z_ur,
        "z_rf": z_rf_arr,
        "z_rr": z_rr_arr,
        "dz_s": dz_s,
        "dtheta": dtheta,
        "ddz_s": ddz_s,
        "ddtheta": ddtheta,
        "susp_travel_f": susp_travel_f,
        "susp_travel_r": susp_travel_r,
        "tire_load_f": tire_load_f,
        "tire_load_r": tire_load_r,
        "contact_states_f": contact_states_f,
        "contact_states_r": contact_states_r,
        "liftoff_time_f": liftoff_time_f,
        "liftoff_time_r": liftoff_time_r,
        "minimum_Fz_f": float(np.min(total_Fz_f)),
        "minimum_Fz_r": float(np.min(total_Fz_r)),
        "diagnostics": diagnostics,
        "provenance": provenance,
        "ledger": ForceMomentLedger(
            m_total_kg=p.m_s,
            h_cg_m=p.h_cg,
            wheelbase_m=p.a + p.b,
            a_x_mps2=p.a_x,
            front_anti_pct=p.anti_dive_f * 100.0 if p.a_x < 0 else p.anti_lift_f * 100.0,
            rear_anti_pct=p.anti_lift_r * 100.0 if p.a_x < 0 else p.anti_squat_r * 100.0,
        ),
    }

def compute_metrics(time_data: dict, p: HalfCarParams) -> dict:
    from suspensionlab.physics.quarter_car import _apply_wk_weighting
    
    rms_heave = float(np.sqrt(np.mean(time_data["ddz_s"] ** 2)))
    
    dt = time_data["time"][1] - time_data["time"][0] if len(time_data["time"]) > 1 else 0.002
    rms_heave_wk = float(np.sqrt(np.mean(_apply_wk_weighting(time_data["ddz_s"], dt)**2)))
    
    rms_pitch = float(np.sqrt(np.mean(time_data["ddtheta"] ** 2)))
    rms_susp_f = float(np.sqrt(np.mean(time_data["susp_travel_f"] ** 2)))
    rms_susp_r = float(np.sqrt(np.mean(time_data["susp_travel_r"] ** 2)))
    rms_tire_f = float(np.sqrt(np.mean(time_data["tire_load_f"] ** 2)))
    rms_tire_r = float(np.sqrt(np.mean(time_data["tire_load_r"] ** 2)))
    
    return {
        "rms_heave_accel": rms_heave,
        "rms_heave_accel_wk": rms_heave_wk,
        "rms_pitch_accel": rms_pitch,
        "rms_susp_travel_f": rms_susp_f,
        "rms_susp_travel_r": rms_susp_r,
        "rms_tire_load_f": rms_tire_f,
        "rms_tire_load_r": rms_tire_r,
    }

def run_half_car_analysis(
    p: HalfCarParams,
    profile: Union[RoadProfile, CanonicalRoadProfile],
) -> HalfCarResult:
    modal = compute_modal_properties(p)
    time_data = simulate_time_response(p, profile)
    metrics = compute_metrics(time_data, p)

    # Downsample time domain data to ~2000 points maximum (prevent large JSON payloads)
    N_total = len(time_data["time"])
    step = max(1, N_total // 2000)

    result = HalfCarResult(
        f_n_heave=modal["f_n_heave"],
        f_n_pitch=modal["f_n_pitch"],
        f_n_uf=modal["f_n_uf"],
        f_n_ur=modal["f_n_ur"],

        time=time_data["time"][::step],
        z_s=time_data["z_s"][::step],
        theta=time_data["theta"][::step],
        z_uf=time_data["z_uf"][::step],
        z_ur=time_data["z_ur"][::step],
        z_rf=time_data["z_rf"][::step],
        z_rr=time_data["z_rr"][::step],
        dz_s=time_data["dz_s"][::step],
        dtheta=time_data["dtheta"][::step],
        ddz_s=time_data["ddz_s"][::step],
        ddtheta=time_data["ddtheta"][::step],
        susp_travel_f=time_data["susp_travel_f"][::step],
        susp_travel_r=time_data["susp_travel_r"][::step],
        tire_load_f=time_data["tire_load_f"][::step],
        tire_load_r=time_data["tire_load_r"][::step],

        rms_heave_accel=metrics["rms_heave_accel"],
        rms_heave_accel_wk=metrics["rms_heave_accel_wk"],
        rms_pitch_accel=metrics["rms_pitch_accel"],
        rms_susp_travel_f=metrics["rms_susp_travel_f"],
        rms_susp_travel_r=metrics["rms_susp_travel_r"],
        rms_tire_load_f=metrics["rms_tire_load_f"],
        rms_tire_load_r=metrics["rms_tire_load_r"],

        contact_states_f=time_data.get("contact_states_f", [])[::step],
        contact_states_r=time_data.get("contact_states_r", [])[::step],
        liftoff_time_f=time_data.get("liftoff_time_f", None),
        liftoff_time_r=time_data.get("liftoff_time_r", None),
        minimum_Fz_f=time_data.get("minimum_Fz_f", 0.0),
        minimum_Fz_r=time_data.get("minimum_Fz_r", 0.0),
        diagnostics=time_data.get("diagnostics", None),
        provenance=time_data.get("provenance", None),
    )
    return result
