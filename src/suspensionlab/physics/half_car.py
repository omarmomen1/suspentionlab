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
from typing import Literal

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import eigvals

from suspensionlab.physics.quarter_car import RoadProfile, _road_profile_fn


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
    damper_curve_v_f: list[float] | None = None
    damper_curve_f_f: list[float] | None = None
    damper_curve_v_r: list[float] | None = None
    damper_curve_f_r: list[float] | None = None
    
    def __post_init__(self) -> None:
        for name, val in self.__dict__.items():
            if val is not None and isinstance(val, (int, float)) and val < 0:
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
    rms_pitch_accel: float = 0.0
    rms_susp_travel_f: float = 0.0
    rms_susp_travel_r: float = 0.0
    rms_tire_load_f: float = 0.0
    rms_tire_load_r: float = 0.0


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
    # So ddz_ur gets: +k_sr/m_ur * z_s  -b*k_sr/m_ur * theta  (pitch coupling is NEGATIVE)
    A[7, 0] = k_sr / m_ur
    A[7, 1] = c_r / m_ur
    A[7, 2] = -b * k_sr / m_ur   # CORRECTED: was +b, must be -b (nose-up pitch reduces rear force)
    A[7, 3] = -b * c_r / m_ur   # CORRECTED: was +b, must be -b
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

    v_susp_f = dz_uf - dz_sf
    if p.damper_curve_v_f is not None and p.damper_curve_f_f is not None and len(p.damper_curve_v_f) > 1:
        F_damper_f = np.interp(v_susp_f, p.damper_curve_v_f, p.damper_curve_f_f)
    else:
        F_damper_f = p.c_f * v_susp_f
        
    v_susp_r = dz_ur - dz_sr
    if p.damper_curve_v_r is not None and p.damper_curve_f_r is not None and len(p.damper_curve_v_r) > 1:
        F_damper_r = np.interp(v_susp_r, p.damper_curve_v_r, p.damper_curve_f_r)
    else:
        F_damper_r = p.c_r * v_susp_r
        
    F_sf = p.k_sf * (z_uf - z_sf) + F_damper_f
    F_sr = p.k_sr * (z_ur - z_sr) + F_damper_r
    
    return F_sf, F_sr, z_sf, z_sr

def _half_car_ode(t, x, p: HalfCarParams, zr_fn, dzr_fn, t_delay: float):

    z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur = x
    
    # Front wheel hits bump at t
    z_rf = float(zr_fn(np.array([t]))[0])
    dz_rf = float(dzr_fn(np.array([t]))[0])
    
    # Rear wheel hits bump at t - t_delay
    t_rear = t - t_delay
    z_rr = float(zr_fn(np.array([t_rear]))[0]) if t_rear >= 0 else 0.0
    dz_rr = float(dzr_fn(np.array([t_rear]))[0]) if t_rear >= 0 else 0.0

    F_sf, F_sr, _, _ = _compute_forces(p, z_s, dz_s, theta, dtheta, z_uf, dz_uf, z_ur, dz_ur)

    # Accelerations
    ddz_s = (F_sf + F_sr) / p.m_s
    ddtheta = (-p.a * F_sf + p.b * F_sr) / p.I_y
    
    ddz_uf = (-F_sf - p.k_tf * (z_uf - z_rf) - p.c_tf * (dz_uf - dz_rf)) / p.m_uf
    ddz_ur = (-F_sr - p.k_tr * (z_ur - z_rr) - p.c_tr * (dz_ur - dz_rr)) / p.m_ur

    return [dz_s, ddz_s, dtheta, ddtheta, dz_uf, ddz_uf, dz_ur, ddz_ur]


# ─────────────────────────────────────────────────────────────────────────────
# Time Domain Simulation
# ─────────────────────────────────────────────────────────────────────────────

def simulate_time_response(
    p: HalfCarParams,
    profile: RoadProfile,
    t_eval_dt: float = 0.002,
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
        method="BDF",          # BDF required: same tire stiffness ratio as quarter-car (stiff problem)
        t_eval=t_eval,
        args=(p, zr_fn, dzr_fn, t_delay),
        rtol=1e-6,
        atol=1e-9,
        max_step=max(0.01, profile.duration / 1000.0),
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
    }

def compute_metrics(time_data: dict, p: HalfCarParams) -> dict:
    rms_heave = float(np.sqrt(np.mean(time_data["ddz_s"] ** 2)))
    rms_pitch = float(np.sqrt(np.mean(time_data["ddtheta"] ** 2)))
    rms_susp_f = float(np.sqrt(np.mean(time_data["susp_travel_f"] ** 2)))
    rms_susp_r = float(np.sqrt(np.mean(time_data["susp_travel_r"] ** 2)))
    rms_tire_f = float(np.sqrt(np.mean(time_data["tire_load_f"] ** 2)))
    rms_tire_r = float(np.sqrt(np.mean(time_data["tire_load_r"] ** 2)))
    
    return {
        "rms_heave_accel": rms_heave,
        "rms_pitch_accel": rms_pitch,
        "rms_susp_travel_f": rms_susp_f,
        "rms_susp_travel_r": rms_susp_r,
        "rms_tire_load_f": rms_tire_f,
        "rms_tire_load_r": rms_tire_r,
    }

def run_half_car_analysis(
    p: HalfCarParams,
    profile: RoadProfile,
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
        rms_pitch_accel=metrics["rms_pitch_accel"],
        rms_susp_travel_f=metrics["rms_susp_travel_f"],
        rms_susp_travel_r=metrics["rms_susp_travel_r"],
        rms_tire_load_f=metrics["rms_tire_load_f"],
        rms_tire_load_r=metrics["rms_tire_load_r"],
    )
    return result
