import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any
from scipy.integrate import ode, solve_ivp
from numba import njit, cfunc, types, carray
from scipy import LowLevelCallable

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
    MR_f: float = 0.85
    MR_r: float = 0.85
    
    # Advanced nonlinear springs
    k_sf_nl: list[float] | None = None
    k_sr_nl: list[float] | None = None
    z_0_f: float = 0.0
    z_0_r: float = 0.0
    
    # Advanced progressive dampers (split comp/rebound)
    damper_curve_v_f: Any = None
    damper_curve_f_f: Any = None
    damper_curve_v_f_comp: Any = None
    damper_curve_f_f_comp: Any = None
    damper_curve_v_f_reb: Any = None
    damper_curve_f_f_reb: Any = None

    damper_curve_v_r: Any = None
    damper_curve_f_r: Any = None
    damper_curve_v_r_comp: Any = None
    damper_curve_f_r_comp: Any = None
    damper_curve_v_r_reb: Any = None
    damper_curve_f_r_reb: Any = None
    
    # Non-linear limits
    bump_stop_comp_f: float = 0.1
    bump_stop_ext_f: float = -0.1
    bump_stop_rate_f: float = 0.0
    bump_stop_exp_f: float = 50.0
    
    bump_stop_comp_r: float = 0.1
    bump_stop_ext_r: float = -0.1
    bump_stop_rate_r: float = 0.0
    bump_stop_exp_r: float = 50.0
    
    # Stribeck friction model
    coulomb_friction_f: float = 0.0
    stribeck_fs_f: float = 0.0
    stribeck_fc_f: float = 0.0
    stribeck_vs_f: float = 0.01
    stribeck_sigma_f: float = 0.0

    coulomb_friction_r: float = 0.0
    stribeck_fs_r: float = 0.0
    stribeck_fc_r: float = 0.0
    stribeck_vs_r: float = 0.01
    stribeck_sigma_r: float = 0.0
    
    def __post_init__(self):
        if self.m_s <= 0 or self.I_x <= 0 or self.I_y <= 0:
            raise ValueError("Mass and inertia must be positive.")
        if self.tw_f <= 0 or self.tw_r <= 0:
            raise ValueError("Track width must be positive.")

    def to_array(self) -> np.ndarray:
        return np.array([
            self.m_s, self.I_x, self.I_y, self.m_uf, self.m_ur,
            self.k_sf, self.k_sr, self.c_f, self.c_r, self.k_arb_f, self.k_arb_r,
            self.k_tf, self.k_tr, self.L, self.a, self.b, self.tw_f, self.tw_r,
            self.c_tf, self.c_tr,
            self.z_0_f, self.z_0_r,
            self.bump_stop_comp_f, self.bump_stop_ext_f, self.bump_stop_rate_f, self.bump_stop_exp_f,
            self.bump_stop_comp_r, self.bump_stop_ext_r, self.bump_stop_rate_r, self.bump_stop_exp_r,
            self.coulomb_friction_f, self.stribeck_fs_f, self.stribeck_fc_f, self.stribeck_vs_f, self.stribeck_sigma_f,
            self.coulomb_friction_r, self.stribeck_fs_r, self.stribeck_fc_r, self.stribeck_vs_r, self.stribeck_sigma_r,
            self.MR_f, self.MR_r,
        ], dtype=np.float64)

@dataclass
class FourCornerRoadProfile:
    time: np.ndarray
    z_rfl: np.ndarray
    z_rfr: np.ndarray
    z_rrl: np.ndarray
    z_rrr: np.ndarray

# ---------------------------------------------------------
# Numba JIT Compilation & Smoothing
# ---------------------------------------------------------



@njit(fastmath=True, cache=True)
def _get_damper_fast(v_rel: float, c_lin: float, fric: float, fs: float, fc: float, vs: float, sigma: float) -> float:
    F = c_lin * v_rel
    # Dissipative smooth approximations
    # Using tanh(v_rel / 0.01) to prevent infinite Jacobian while maintaining strict energy dissipation
    vs_safe = max(vs, 1e-6)
    if fs > 0.0 or fc > 0.0:
        F += (fc + (fs - fc) * np.exp(-(v_rel / vs_safe)**2)) * np.tanh(v_rel / 0.01) + sigma * v_rel
    elif fric > 0.0:
        F += fric * np.tanh(v_rel / 0.01)
    return F

@njit(fastmath=True, cache=True)
def _get_bump_fast(z_rel: float, comp_lim: float, ext_lim: float, rate: float, ext_exp: float) -> float:
    if rate <= 0.0: 
        return 0.0
    # Bound the exponent to prevent overflow and infinite Jacobian
    if z_rel > comp_lim:
        dz = min(z_rel - comp_lim, 0.05)
        return rate * (np.exp(ext_exp * dz) - 1.0)
    elif z_rel < ext_lim:
        dz = max(z_rel - ext_lim, -0.05)
        return -rate * (np.exp(-ext_exp * dz) - 1.0)
    return 0.0

@njit(fastmath=True, cache=True)
def _get_tire_force_inner(k_t: float, z_u: float, z_r: float, c_t: float, dz_u: float, dz_r: float) -> float:
    return -k_t * (z_u - z_r) - c_t * (dz_u - dz_r)

@njit(fastmath=False, cache=True)
def _get_tire_force(k_t: float, z_u: float, z_r: float, c_t: float, dz_u: float, dz_r: float) -> float:
    force = _get_tire_force_inner(k_t, z_u, z_r, c_t, dz_u, dz_r)
    if np.isnan(force) or np.isinf(force):
        return 0.0
    return force

@njit(fastmath=True, cache=True)
def _compute_full_car_forces_fast(x: np.ndarray, u: np.ndarray, p: np.ndarray, ddz_out: np.ndarray):
    """
    x: shape (14,)
    u: shape (4,) [z_rfl, z_rfr, z_rrl, z_rrr]
    p: shape (40,)
    ddz_out: shape (14,) - will be mutated in-place with derivatives
    """
    z_s, theta, phi, z_ufl, z_ufr, z_url, z_urr, dz_s, dtheta, dphi, dz_ufl, dz_ufr, dz_url, dz_urr = x
    z_rfl, z_rfr, z_rrl, z_rrr = u

    # Unpack params
    m_s = p[0]; I_x = p[1]; I_y = p[2]; m_uf = p[3]; m_ur = p[4]
    k_sf = p[5]; k_sr = p[6]; c_f = p[7]; c_r = p[8]
    k_arb_f = p[9]; k_arb_r = p[10]; k_tf = p[11]; k_tr = p[12]
    a = p[14]; b = p[15]; tw_f = p[16]; tw_r = p[17]
    c_tf = p[18]; c_tr = p[19]
    z_0_f = p[20]; z_0_r = p[21]
    
    bs_cf = p[22]; bs_ef = p[23]; bs_rf = p[24]; bs_exp_f = p[25]
    bs_cr = p[26]; bs_er = p[27]; bs_rr = p[28]; bs_exp_r = p[29]
    
    fr_f = p[30]; fs_f = p[31]; fc_f = p[32]; vs_f = p[33]; sig_f = p[34]
    fr_r = p[35]; fs_r = p[36]; fc_r = p[37]; vs_r = p[38]; sig_r = p[39]
    MR_f = p[40]; MR_r = p[41]

    # Kinematics
    z_sfl = z_s - a * theta + (tw_f / 2) * phi
    z_sfr = z_s - a * theta - (tw_f / 2) * phi
    z_srl = z_s + b * theta + (tw_r / 2) * phi
    z_srr = z_s + b * theta - (tw_r / 2) * phi

    dz_sfl = dz_s - a * dtheta + (tw_f / 2) * dphi
    dz_sfr = dz_s - a * dtheta - (tw_f / 2) * dphi
    dz_srl = dz_s + b * dtheta + (tw_r / 2) * dphi
    dz_srr = dz_s + b * dtheta - (tw_r / 2) * dphi

    z_rel_w_fl = z_sfl - z_ufl; v_rel_w_fl = dz_sfl - dz_ufl
    z_rel_w_fr = z_sfr - z_ufr; v_rel_w_fr = dz_sfr - dz_ufr
    z_rel_w_rl = z_srl - z_url; v_rel_w_rl = dz_srl - dz_url
    z_rel_w_rr = z_srr - z_urr; v_rel_w_rr = dz_srr - dz_urr
    
    z_rel_s_fl = z_rel_w_fl * MR_f; v_rel_s_fl = v_rel_w_fl * MR_f
    z_rel_s_fr = z_rel_w_fr * MR_f; v_rel_s_fr = v_rel_w_fr * MR_f
    z_rel_s_rl = z_rel_w_rl * MR_r; v_rel_s_rl = v_rel_w_rl * MR_r
    z_rel_s_rr = z_rel_w_rr * MR_r; v_rel_s_rr = v_rel_w_rr * MR_r
    
    # Suspension Forces
    F_d_fl = _get_damper_fast(v_rel_s_fl, c_f, fr_f, fs_f, fc_f, vs_f, sig_f)
    F_d_fr = _get_damper_fast(v_rel_s_fr, c_f, fr_f, fs_f, fc_f, vs_f, sig_f)
    F_d_rl = _get_damper_fast(v_rel_s_rl, c_r, fr_r, fs_r, fc_r, vs_r, sig_r)
    F_d_rr = _get_damper_fast(v_rel_s_rr, c_r, fr_r, fs_r, fc_r, vs_r, sig_r)

    F_s_fl = k_sf * (z_rel_s_fl - z_0_f)
    F_s_fr = k_sf * (z_rel_s_fr - z_0_f)
    F_s_rl = k_sr * (z_rel_s_rl - z_0_r)
    F_s_rr = k_sr * (z_rel_s_rr - z_0_r)
    
    F_b_fl = _get_bump_fast(z_rel_s_fl, bs_cf, bs_ef, bs_rf, bs_exp_f)
    F_b_fr = _get_bump_fast(z_rel_s_fr, bs_cf, bs_ef, bs_rf, bs_exp_f)
    F_b_rl = _get_bump_fast(z_rel_s_rl, bs_cr, bs_er, bs_rr, bs_exp_r)
    F_b_rr = _get_bump_fast(z_rel_s_rr, bs_cr, bs_er, bs_rr, bs_exp_r)
    
    # ARB forces (at the wheel)
    F_arb_fl = k_arb_f * (z_rel_w_fl - z_rel_w_fr)
    F_arb_fr = k_arb_f * (z_rel_w_fr - z_rel_w_fl)
    F_arb_rl = k_arb_r * (z_rel_w_rl - z_rel_w_rr)
    F_arb_rr = k_arb_r * (z_rel_w_rr - z_rel_w_rl)
    
    # Total suspension force at the wheel (scale by MR)
    F_susp_fl = (F_s_fl + F_d_fl + F_b_fl) * MR_f + F_arb_fl
    F_susp_fr = (F_s_fr + F_d_fr + F_b_fr) * MR_f + F_arb_fr
    F_susp_rl = (F_s_rl + F_d_rl + F_b_rl) * MR_r + F_arb_rl
    F_susp_rr = (F_s_rr + F_d_rr + F_b_rr) * MR_r + F_arb_rr
    
    # Tire Forces
    F_t_fl = _get_tire_force(k_tf, z_ufl, z_rfl, c_tf, dz_ufl, 0.0) # dz_rfl ignored for now
    F_t_fr = _get_tire_force(k_tf, z_ufr, z_rfr, c_tf, dz_ufr, 0.0)
    F_t_rl = _get_tire_force(k_tr, z_url, z_rrl, c_tr, dz_url, 0.0)
    F_t_rr = _get_tire_force(k_tr, z_urr, z_rrr, c_tr, dz_urr, 0.0)
    
    # Accelerations (in-place write)
    ddz_out[0] = dz_s
    ddz_out[1] = dtheta
    ddz_out[2] = dphi
    ddz_out[3] = dz_ufl
    ddz_out[4] = dz_ufr
    ddz_out[5] = dz_url
    ddz_out[6] = dz_urr
    
    # FIXED: Sign convention correction — Newton's 3rd Law.
    # When suspension compresses (z_sfl > z_ufl), F_susp > 0.
    # This force acts DOWNWARD on the sprung mass (-) and UPWARD on the unsprung mass (+).
    ddz_out[7] = (-F_susp_fl - F_susp_fr - F_susp_rl - F_susp_rr) / m_s
    ddz_out[8] = (a * (F_susp_fl + F_susp_fr) - b * (F_susp_rl + F_susp_rr)) / I_y
    ddz_out[9] = (-(tw_f / 2.0) * (F_susp_fl - F_susp_fr) - (tw_r / 2.0) * (F_susp_rl - F_susp_rr)) / I_x
    
    # FIXED: Unsprung masses — suspension pulls UP on wheel (+F_susp), tire pushes UP (+F_tire).
    # Note: _get_tire_force now returns negative force for positive displacement, so we ADD it here.
    ddz_out[10] = (F_susp_fl + F_t_fl) / m_uf
    ddz_out[11] = (F_susp_fr + F_t_fr) / m_uf
    ddz_out[12] = (F_susp_rl + F_t_rl) / m_ur
    ddz_out[13] = (F_susp_rr + F_t_rr) / m_ur


@njit(fastmath=True, cache=True)
def _full_car_ode_fast(t: float, y: np.ndarray, g_time: np.ndarray, g_u: np.ndarray, p: np.ndarray, ddz_out: np.ndarray, u_temp: np.ndarray):
    """
    Evaluates the ODE derivatives.
    """
    N = len(g_time)
    if N < 2:
        for i in range(len(ddz_out)):
            ddz_out[i] = 0.0
        return
    idx = np.searchsorted(g_time, t) - 1
    if idx < 0: idx = 0
    if idx >= N - 1: idx = N - 2
    
    t0 = g_time[idx]
    t1 = g_time[idx+1]
    w = (t - t0) / (t1 - t0 + 1e-12)
    w = max(0.0, min(1.0, w))
    
    u_temp[0] = g_u[idx, 0] + w * (g_u[idx+1, 0] - g_u[idx, 0])
    u_temp[1] = g_u[idx, 1] + w * (g_u[idx+1, 1] - g_u[idx, 1])
    u_temp[2] = g_u[idx, 2] + w * (g_u[idx+1, 2] - g_u[idx, 2])
    u_temp[3] = g_u[idx, 3] + w * (g_u[idx+1, 3] - g_u[idx, 3])
    
    _compute_full_car_forces_fast(y, u_temp, p, ddz_out)



def _full_car_ode_wrapper(t, y, g_time, g_u, g_params):
    """Python wrapper for SciPy solver."""
    ydot = np.zeros(14, dtype=np.float64)
    u_temp = np.zeros(4, dtype=np.float64)
    _full_car_ode_fast(t, y, g_time, g_u, g_params, ydot, u_temp)
    return ydot

# ---------------------------------------------------------

def build_full_car_state_space(params: FullCarParams) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Legacy linear matrices for eigenmode extraction only."""
    M_b = np.diag([params.m_s, params.I_y, params.I_x])
    M_u = np.diag([params.m_uf, params.m_uf, params.m_ur, params.m_ur])
    M = np.block([[M_b, np.zeros((3, 4))],
                  [np.zeros((4, 3)), M_u]])
                  
    T = np.array([
        [1.0, -params.a,  params.tw_f / 2.0],  # FL
        [1.0, -params.a, -params.tw_f / 2.0],  # FR
        [1.0,  params.b,  params.tw_r / 2.0],  # RL
        [1.0,  params.b, -params.tw_r / 2.0]   # RR
    ])
    
    K_s = np.diag([params.k_sf, params.k_sf, params.k_sr, params.k_sr])
    H = np.array([
        [1.0, -1.0,  0.0,  0.0],
        [0.0,  0.0,  1.0, -1.0]
    ])
    K_arb = np.diag([params.k_arb_f, params.k_arb_r])
    K_susp = K_s + H.T @ K_arb @ H
    K_t = np.diag([params.k_tf, params.k_tf, params.k_tr, params.k_tr])
    
    K = np.block([
        [ T.T @ K_susp @ T,     -T.T @ K_susp ],
        [-K_susp @ T,            K_susp + K_t ]
    ])
    
    C_s = np.diag([params.c_f, params.c_f, params.c_r, params.c_r])
    C_t = np.diag([params.c_tf, params.c_tf, params.c_tr, params.c_tr])
    
    C = np.block([
        [ T.T @ C_s @ T,     -T.T @ C_s ],
        [-C_s @ T,            C_s + C_t ]
    ])
    
    B_0 = np.block([[np.zeros((3, 4))], [K_t]])
    
    M_inv = np.linalg.inv(M)
    A = np.block([[np.zeros((7, 7)), np.eye(7)], [-M_inv @ K, -M_inv @ C]])
    B = np.block([[np.zeros((7, 4))], [M_inv @ B_0]])
    
    return A, B, np.eye(14), np.zeros((14, 4))

def calculate_full_car_kpis(params: FullCarParams, res: dict) -> dict:
    A, _, _, _ = build_full_car_state_space(params)
    vals, vecs = np.linalg.eig(A)
    
    idx = np.where(np.imag(vals) > 1e-3)[0]
    vals = vals[idx]
    vecs = vecs[:, idx]
    
    modes = {"heave": 0.0, "pitch": 0.0, "roll": 0.0, "uf": 0.0, "ur": 0.0}
    for i in range(len(vals)):
        freq = float(np.imag(vals[i]) / (2 * np.pi))
        mode_shape = np.abs(vecs[:7, i])
        mode_shape[1] *= params.L / 2.0
        mode_shape[2] *= (params.tw_f + params.tw_r) / 4.0
        max_idx = int(np.argmax(mode_shape))
        
        if max_idx == 0: modes["heave"] = freq
        elif max_idx == 1: modes["pitch"] = freq
        elif max_idx == 2: modes["roll"] = freq
        elif max_idx in [3, 4]: modes["uf"] = max(modes["uf"], freq)
        elif max_idx in [5, 6]: modes["ur"] = max(modes["ur"], freq)
            
    modes_list = []
    for i in range(len(vals)):
        freq = float(np.imag(vals[i]) / (2 * np.pi))
        damping_ratio = float(-np.real(vals[i]) / np.abs(vals[i])) if np.abs(vals[i]) > 0 else 0.0
        mode_shape = vecs[:7, i].tolist()
        if freq > 1e-3 and all(abs(freq - m["frequency"]) > 1e-2 for m in modes_list):
            modes_list.append({"frequency": freq, "damping_ratio": damping_ratio, "mode_shape": [{"real": float(np.real(c)), "imag": float(np.imag(c))} for c in mode_shape]})
            
    res["eigenmodes"] = modes_list
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

def run_full_car_analysis(params: FullCarParams, profile: FourCornerRoadProfile) -> FullCarResultSchema:
    U = np.column_stack([profile.z_rfl, profile.z_rfr, profile.z_rrl, profile.z_rrr])
    N = len(profile.time)
    
    if N < 2:
        raise ValueError("Road profile time array must have at least 2 points.")
    if N > 50000:
        raise ValueError(f"Road profile exceeds maximum allowed points (50000), got {N}.")
        
    if not np.all(np.diff(profile.time) > 0):
        raise ValueError("Road profile time array must be strictly monotonically increasing.")
    if len(profile.time) < 2:
        raise ValueError("Road profile must contain at least 2 time points.")
    
    # Local copies
    g_params = params.to_array()
    g_time = profile.time
    g_u = U
    
    y0 = np.zeros(14, dtype=np.float64)
    t_span = (profile.time[0], profile.time[-1])
    
    sol = solve_ivp(
        fun=_full_car_ode_wrapper,
        t_span=t_span,
        y0=y0,
        t_eval=profile.time,
        method='LSODA',
        args=(g_time, g_u, g_params),
        rtol=1e-5,
        atol=1e-7
    )
    
    if not sol.success:
        raise RuntimeError(f"ODE Solver failed: {sol.message}")
        
    time_out = sol.t
    yout = sol.y.T
    
    # Re-compute accelerations via vectorized mapping or loop
    x_dot = np.zeros_like(yout)
    u_temp = np.zeros(4, dtype=np.float64)
    for i in range(len(time_out)):
        _full_car_ode_fast(time_out[i], yout[i], g_time, g_u, g_params, x_dot[i], u_temp)

    from scipy.signal import welch
    dt = time_out[1] - time_out[0] if len(time_out) > 1 else 0.002
    fs = 1.0 / dt
    f_psd, p_psd = welch(x_dot[:, 7], fs, nperseg=min(len(x_dot[:, 7]), 1024))
    
    step = max(1, N // 2000)
    
    time_out_d = np.ascontiguousarray(time_out[::step])
    yout_d = np.ascontiguousarray(yout[::step, :])
    x_dot_d = np.ascontiguousarray(x_dot[::step, :])
    
    res_arrays = {
        "time": time_out_d,
        "z_s": yout_d[:, 0],
        "theta": yout_d[:, 1],
        "phi": yout_d[:, 2],
        "z_ufl": yout_d[:, 3],
        "z_ufr": yout_d[:, 4],
        "z_url": yout_d[:, 5],
        "z_urr": yout_d[:, 6],
        
        "dz_s": yout_d[:, 7],
        "dtheta": yout_d[:, 8],
        "dphi": yout_d[:, 9],
        
        "z_rfl": profile.z_rfl[::step],
        "z_rfr": profile.z_rfr[::step],
        "z_rrl": profile.z_rrl[::step],
        "z_rrr": profile.z_rrr[::step],
        
        "psd_freqs": f_psd,
        "psd_values": p_psd,
        
        "ddz_s": x_dot_d[:, 7],
        "ddtheta": x_dot_d[:, 8],
        "ddphi": x_dot_d[:, 9],
    }
    
    F_t_fl = params.k_tf * (profile.z_rfl[::step] - yout_d[:, 3])
    F_t_fr = params.k_tf * (profile.z_rfr[::step] - yout_d[:, 4])
    F_t_rl = params.k_tr * (profile.z_rrl[::step] - yout_d[:, 5])
    F_t_rr = params.k_tr * (profile.z_rrr[::step] - yout_d[:, 6])
    
    res_arrays["lateral_load_transfer_f"] = (F_t_fl - F_t_fr) / 2.0
    res_arrays["lateral_load_transfer_r"] = (F_t_rl - F_t_rr) / 2.0
    
    for k, v in res_arrays.items():
        if isinstance(v, np.ndarray):
            res_arrays[k] = np.ascontiguousarray(v)

    res = {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in res_arrays.items()}
    
    K_roll_f = 0.5 * params.k_sf * params.tw_f**2 + params.k_arb_f * params.tw_f**2
    K_roll_r = 0.5 * params.k_sr * params.tw_r**2 + params.k_arb_r * params.tw_r**2
    res["roll_stiffness_dist"] = float(K_roll_f / (K_roll_f + K_roll_r)) * 100.0 if (K_roll_f + K_roll_r) > 0 else 50.0
    
    res = calculate_full_car_kpis(params, res)
    return FullCarResultSchema(**res)
