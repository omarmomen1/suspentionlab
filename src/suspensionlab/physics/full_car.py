import numpy as np
import scipy.signal as signal
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

from suspensionlab.shared.models import FullCarParamsSchema, FullCarResultSchema

@dataclass
class FullCarParams:
    m_s: float
    I_x: float
    I_y: float
    m_uf: float
    m_ur: float
    k_sf: float
    k_sr: float
    c_f: float
    c_r: float
    k_arb_f: float
    k_arb_r: float
    k_tf: float
    k_tr: float
    L: float
    a: float
    b: float
    tw_f: float
    tw_r: float
    speed_mps: float
    c_tf: float = 0.0
    c_tr: float = 0.0
    road_asymmetry: float = 0.3
    damper_curve_v_f: Any = None
    damper_curve_f_f: Any = None
    damper_curve_v_r: Any = None
    damper_curve_f_r: Any = None
    
    def __post_init__(self):
        if self.m_s <= 0 or self.I_x <= 0 or self.I_y <= 0:
            raise ValueError("Mass and inertia must be positive.")
        if self.tw_f <= 0 or self.tw_r <= 0:
            raise ValueError("Track width must be positive.")

@dataclass
class FourCornerRoadProfile:
    time: np.ndarray
    z_rfl: np.ndarray
    z_rfr: np.ndarray
    z_rrl: np.ndarray
    z_rrr: np.ndarray

def build_full_car_state_space(params: FullCarParams) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Constructs the 14x14 state space model for a 7-DOF Full-Car using M, C, K block assembly.
    q = [z_s, theta, phi, z_ufl, z_ufr, z_url, z_urr]^T
    u = [z_rfl, z_rfr, z_rrl, z_rrr]^T
    """
    # Mass Matrix (7x7)
    M_b = np.diag([params.m_s, params.I_y, params.I_x])
    M_u = np.diag([params.m_uf, params.m_uf, params.m_ur, params.m_ur])
    M = np.block([[M_b, np.zeros((3, 4))],
                  [np.zeros((4, 3)), M_u]])
                  
    # Transformation matrix T (4x3): maps body DOFs to corner displacements
    # Corners: FL (1), FR (2), RL (3), RR (4)
    # Sign convention (consistent throughout): phi > 0 is LEFT side UP
    # z_front_body = z_s - a*theta  (nose-up pitch lowers front)
    # z_left = z_s + (tw/2)*phi, z_right = z_s - (tw/2)*phi
    # ARB H matrix uses FL-FR twist so H must use same sign.
    T = np.array([
        [1.0, -params.a,  params.tw_f / 2.0],  # FL
        [1.0, -params.a, -params.tw_f / 2.0],  # FR
        [1.0,  params.b,  params.tw_r / 2.0],  # RL
        [1.0,  params.b, -params.tw_r / 2.0]   # RR
    ])
    
    # Stiffness Matrices
    K_s = np.diag([params.k_sf, params.k_sf, params.k_sr, params.k_sr])
    
    # ARB connectivity H (2x4)
    H = np.array([
        [1.0, -1.0,  0.0,  0.0],  # Front ARB twist = FL - FR
        [0.0,  0.0,  1.0, -1.0]   # Rear ARB twist = RL - RR
    ])
    K_arb = np.diag([params.k_arb_f, params.k_arb_r])
    
    K_susp = K_s + H.T @ K_arb @ H
    K_t = np.diag([params.k_tf, params.k_tf, params.k_tr, params.k_tr])
    
    K = np.block([
        [ T.T @ K_susp @ T,     -T.T @ K_susp ],
        [-K_susp @ T,            K_susp + K_t ]
    ])
    
    # Damping Matrices
    C_s = np.diag([params.c_f, params.c_f, params.c_r, params.c_r])
    C_t = np.diag([params.c_tf, params.c_tf, params.c_tr, params.c_tr])
    
    C = np.block([
        [ T.T @ C_s @ T,     -T.T @ C_s ],
        [-C_s @ T,            C_s + C_t ]
    ])
    
    # Input Matrix B_0 (7x4) mapping road inputs to forces
    B_0 = np.block([
        [np.zeros((3, 4))],
        [K_t]
    ])
    
    # Convert to State Space: x_dot = A*x + B*u
    # x = [q, q_dot]^T
    M_inv = np.linalg.inv(M)
    
    A = np.block([
        [np.zeros((7, 7)), np.eye(7)],
        [-M_inv @ K,       -M_inv @ C]
    ])
    
    B = np.block([
        [np.zeros((7, 4))],
        [M_inv @ B_0]
    ])
    
    # Output Matrix C_mat and D_mat (Identity for all states)
    C_mat = np.eye(14)
    D_mat = np.zeros((14, 4))
    
    return A, B, C_mat, D_mat

def calculate_full_car_kpis(params: FullCarParams, res: dict) -> dict:
    """Calculate natural frequencies and RMS values."""
    A, _, _, _ = build_full_car_state_space(params)
    vals, vecs = np.linalg.eig(A)
    
    idx = np.where(np.imag(vals) > 1e-3)[0]
    vals = vals[idx]
    vecs = vecs[:, idx]
    
    modes = {"heave": 0.0, "pitch": 0.0, "roll": 0.0, "uf": 0.0, "ur": 0.0}
    for i in range(len(vals)):
        freq = float(np.imag(vals[i]) / (2 * np.pi))
        mode_shape = np.abs(vecs[:7, i])
        max_idx = int(np.argmax(mode_shape))
        
        if max_idx == 0:
            modes["heave"] = freq
        elif max_idx == 1:
            modes["pitch"] = freq
        elif max_idx == 2:
            modes["roll"] = freq
        elif max_idx in [3, 4]:
            modes["uf"] = max(modes["uf"], freq)
        elif max_idx in [5, 6]:
            modes["ur"] = max(modes["ur"], freq)
            
    res["f_n_heave"] = modes["heave"]
    res["f_n_roll"] = modes["roll"]
    res["f_n_pitch"] = modes["pitch"]
    res["f_n_uf"] = modes["uf"]
    res["f_n_ur"] = modes["ur"]
    
    res["rms_heave_accel"] = float(np.sqrt(np.mean(np.square(res["ddz_s"]))))
    res["rms_pitch_accel"] = float(np.sqrt(np.mean(np.square(res["ddtheta"]))))
    res["rms_roll_accel"] = float(np.sqrt(np.mean(np.square(res["ddphi"]))))
    
    res["rms_tire_load_fl"] = float(np.sqrt(np.mean(np.square(np.array(res["z_rfl"]) - np.array(res["z_ufl"]))))) * params.k_tf
    res["rms_tire_load_fr"] = float(np.sqrt(np.mean(np.square(np.array(res["z_rfr"]) - np.array(res["z_ufr"]))))) * params.k_tf
    res["rms_tire_load_rl"] = float(np.sqrt(np.mean(np.square(np.array(res["z_rrl"]) - np.array(res["z_url"]))))) * params.k_tr
    res["rms_tire_load_rr"] = float(np.sqrt(np.mean(np.square(np.array(res["z_rrr"]) - np.array(res["z_urr"]))))) * params.k_tr
    
    return res

def _full_car_ode(t, x, A, B, time_arr, U_arr):
    u = np.array([np.interp(t, time_arr, U_arr[:, i]) for i in range(4)])
    return A @ x + B @ u

def run_full_car_analysis(params: FullCarParams, profile: FourCornerRoadProfile) -> FullCarResultSchema:
    from scipy.integrate import solve_ivp
    A, B, C_mat, D_mat = build_full_car_state_space(params)
    sys = signal.StateSpace(A, B, C_mat, D_mat)
    
    U = np.column_stack([profile.z_rfl, profile.z_rfr, profile.z_rrl, profile.z_rrr])
    
    # Use solve_ivp with BDF for consistency with Quarter Car ODE solver
    sol = solve_ivp(
        fun=_full_car_ode,
        t_span=(profile.time[0], profile.time[-1]),
        y0=np.zeros(14),
        method="BDF",
        t_eval=profile.time,
        args=(A, B, profile.time, U),
        rtol=1e-5,
        atol=1e-8,
        max_step=max(0.01, (profile.time[-1] - profile.time[0]) / 1000.0)
    )
    
    time_out = sol.t
    yout = sol.y.T  # Shape: (N, 14)
    
    # Compute accelerations: x_dot = A*x + B*u
    x_dot = (A @ yout.T + B @ U.T).T

    # PSD Analysis (Backend) - Heave Acceleration (x_dot index 7 = ddz_s)
    # x_dot[:,7] is ddz_s (second time-derivative of z_s = heave acceleration)
    # This matches the quarter-car PSD which also uses heave acceleration.
    from scipy.signal import welch
    dt = time_out[1] - time_out[0] if len(time_out) > 1 else 0.002
    fs = 1.0 / dt
    f_psd, p_psd = welch(x_dot[:, 7], fs, nperseg=min(len(x_dot[:, 7]), 1024))
    
    # Downsample time domain data to ~2000 points maximum
    N_total = len(time_out)
    step = max(1, N_total // 2000)
    
    time_out = time_out[::step]
    yout = yout[::step, :]
    x_dot = x_dot[::step, :]
    U = U[::step, :]
    profile_z_rfl = profile.z_rfl[::step]
    profile_z_rfr = profile.z_rfr[::step]
    profile_z_rrl = profile.z_rrl[::step]
    profile_z_rrr = profile.z_rrr[::step]
    
    res = {
        "time": time_out.tolist(),
        "z_s": yout[:, 0].tolist(),
        "theta": yout[:, 1].tolist(),
        "phi": yout[:, 2].tolist(),
        "z_ufl": yout[:, 3].tolist(),
        "z_ufr": yout[:, 4].tolist(),
        "z_url": yout[:, 5].tolist(),
        "z_urr": yout[:, 6].tolist(),
        
        "dz_s": yout[:, 7].tolist(),
        "dtheta": yout[:, 8].tolist(),
        "dphi": yout[:, 9].tolist(),
        
        "z_rfl": profile_z_rfl.tolist(),
        "z_rfr": profile_z_rfr.tolist(),
        "z_rrl": profile_z_rrl.tolist(),
        "z_rrr": profile_z_rrr.tolist(),
        
        "psd_freqs": f_psd.tolist(),
        "psd_values": p_psd.tolist(),
    }
    
    res["ddz_s"] = x_dot[:, 7].tolist()
    res["ddtheta"] = x_dot[:, 8].tolist()
    res["ddphi"] = x_dot[:, 9].tolist()
    
    z_s_fl = yout[:, 0] - params.a * yout[:, 1] + (params.tw_f / 2) * yout[:, 2]
    z_s_fr = yout[:, 0] - params.a * yout[:, 1] - (params.tw_f / 2) * yout[:, 2]
    z_s_rl = yout[:, 0] + params.b * yout[:, 1] + (params.tw_r / 2) * yout[:, 2]
    z_s_rr = yout[:, 0] + params.b * yout[:, 1] - (params.tw_r / 2) * yout[:, 2]
    
    F_t_fl = params.k_tf * (profile_z_rfl - yout[:, 3])
    F_t_fr = params.k_tf * (profile_z_rfr - yout[:, 4])
    F_t_rl = params.k_tr * (profile_z_rrl - yout[:, 5])
    F_t_rr = params.k_tr * (profile_z_rrr - yout[:, 6])
    
    llt_f = (F_t_fl - F_t_fr) / 2.0
    llt_r = (F_t_rl - F_t_rr) / 2.0
    
    res["lateral_load_transfer_f"] = llt_f.tolist()
    res["lateral_load_transfer_r"] = llt_r.tolist()
    
    K_roll_f = 0.5 * params.k_sf * params.tw_f**2 + 0.5 * params.k_arb_f * params.tw_f**2
    K_roll_r = 0.5 * params.k_sr * params.tw_r**2 + 0.5 * params.k_arb_r * params.tw_r**2
    res["roll_stiffness_dist"] = float(K_roll_f / (K_roll_f + K_roll_r)) * 100.0 if (K_roll_f + K_roll_r) > 0 else 50.0
    
    res = calculate_full_car_kpis(params, res)
    return FullCarResultSchema(**res)
