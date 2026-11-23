import numpy as np
from scipy.integrate import solve_ivp
from dataclasses import dataclass
from .quarter_car import QuarterCarParams, RoadProfile, _road_profile_fn, QuarterCarResult

@dataclass
class ActiveQuarterCarParams(QuarterCarParams):
    c_sky: float = 4000.0   # Ns/m (Skyhook damping coefficient)
    c_min: float = 500.0    # Ns/m (Minimum base damping of MR fluid)

def _active_quarter_car_ode(t, x, p: ActiveQuarterCarParams, zr_fn, dzr_fn):
    z_s, dz_s, z_u, dz_u = x
    z_r  = float(zr_fn(np.array([t]))[0])
    dz_r = float(dzr_fn(np.array([t]))[0])

    k_w = p.k_w
    v_rel = dz_s - dz_u
    
    # Scale velocities to damper using Motion Ratio
    v_damper = v_rel * p.MR
    dz_s_damper = dz_s * p.MR
    
    # Karnopp Semi-Active Skyhook Control Logic
    # The semi-active damper can only dissipate energy (passivity constraint c_eff >= c_min >= 0).
    c_min = getattr(p, "c_min", 300.0)
    c_max = min(2.0 * p.c_sky, 8000.0)
    if dz_s_damper * v_damper > 0.0 and abs(v_damper) > 1e-6:
        c_req = (p.c_sky * dz_s_damper) / v_damper
        c_eff = min(max(c_req, c_min), c_max)
    else:
        c_eff = c_min

    F_damper = c_eff * v_damper
    
    # Scale damper force back to wheel
    F_d = F_damper * p.MR

    # Sprung acceleration
    ddz_s = (1.0 / p.m_s) * (
        - F_d
        - k_w * (z_s  - z_u)
    )

    # Dynamic tire force (upward force on unsprung mass from road)
    F_tire_dyn = p.k_t * (z_r - z_u) + p.c_t * (dz_r - dz_u)
    if getattr(p, "enable_contact_loss", True):
        static_tire_load = (p.m_s + p.m_u) * 9.81
        # Unilateral tire contact: road can only push upward, never pull downward
        F_z_total = max(0.0, static_tire_load + F_tire_dyn)
        F_tire_dyn = F_z_total - static_tire_load

    # Unsprung acceleration
    ddz_u = (1.0 / p.m_u) * (
          F_d
        + k_w * (z_s   - z_u)
        + F_tire_dyn
    )

    return [dz_s, ddz_s, dz_u, ddz_u]


def simulate_active_time_response(
    p: ActiveQuarterCarParams,
    profile: RoadProfile,
    t_eval_dt: float = 0.002,
) -> QuarterCarResult:
    
    zr_fn, dzr_fn = _road_profile_fn(profile)
    t_span = (0.0, profile.duration)
    t_eval = np.arange(0.0, profile.duration, t_eval_dt)
    x0 = [0.0, 0.0, 0.0, 0.0]

    sol = solve_ivp(
        fun=_active_quarter_car_ode,
        t_span=t_span,
        y0=x0,
        t_eval=t_eval,
        args=(p, zr_fn, dzr_fn),
        method="BDF",
        rtol=1e-5,
        atol=1e-7,
        max_step=max(0.001, profile.duration / 5000.0),
    )

    time = sol.t
    z_s = sol.y[0]
    dz_s = sol.y[1]
    z_u = sol.y[2]
    dz_u = sol.y[3]

    # Calculate accelerations and forces vectorized
    z_r_arr = np.asarray(zr_fn(time)).flatten()
    dz_r_arr = np.asarray(dzr_fn(time)).flatten()
    
    v_rel = dz_s - dz_u
    v_damper = v_rel * p.MR
    dz_s_damper = dz_s * p.MR
    
    c_min = getattr(p, "c_min", 300.0)
    c_max = min(2.0 * p.c_sky, 8000.0)
    
    # Vectorized Karnopp semi-active skyhook
    v_damper_safe = np.where(np.abs(v_damper) < 1e-6, 1e-6, v_damper)
    c_eff = np.where(
        (dz_s_damper * v_damper > 0.0) & (np.abs(v_damper) > 1e-6),
        np.clip((p.c_sky * dz_s_damper) / v_damper_safe, c_min, c_max),
        c_min
    )
    F_damper = c_eff * v_damper
    F_d = F_damper * p.MR
    
    ddz_s = (1.0 / p.m_s) * (-F_d - p.k_w * (z_s - z_u))

    static_tire_load = (p.m_s + p.m_u) * 9.81
    F_tire_dyn = p.k_t * (z_r_arr - z_u) + p.c_t * (dz_r_arr - dz_u)
    if getattr(p, "enable_contact_loss", True):
        F_z_total = np.maximum(0.0, static_tire_load + F_tire_dyn)
        F_tire_dyn = F_z_total - static_tire_load
    else:
        F_z_total = static_tire_load + F_tire_dyn

    ddz_u = (1.0 / p.m_u) * (F_d + p.k_w * (z_s - z_u) + F_tire_dyn)

    susp_travel = z_s - z_u
    tire_defl = z_u - z_r_arr
    tire_load_var = -F_tire_dyn

    # Metrics
    rms_body_accel = float(np.sqrt(np.mean(ddz_s**2)))
    
    from .quarter_car import _apply_wk_weighting, calculate_vdv
    dt = time[1] - time[0] if len(time) > 1 else 0.002
    fs = 1.0 / dt
    accel_wk = _apply_wk_weighting(ddz_s, dt=dt, fs=fs)
    rms_body_accel_wk = float(np.sqrt(np.mean(accel_wk**2)))
    vdv = calculate_vdv(accel_wk, fs=fs)
    
    rms_susp_travel = float(np.sqrt(np.mean(susp_travel**2)))
    rms_tire_load = float(np.sqrt(np.mean(tire_load_var**2)))
    peak_susp_travel = float(np.max(susp_travel) - np.min(susp_travel))

    res = QuarterCarResult()
    res.time = time
    res.z_s = z_s
    res.z_u = z_u
    res.z_r = z_r_arr
    res.dz_s = dz_s
    res.dz_u = dz_u
    res.ddz_s = ddz_s
    res.susp_travel = susp_travel
    res.tire_defl = tire_defl
    res.tire_load_var = tire_load_var
    res.rms_body_accel = rms_body_accel
    res.rms_body_accel_wk = rms_body_accel_wk
    res.vdv = vdv
    res.rms_susp_travel = rms_susp_travel
    res.rms_tire_load = rms_tire_load
    res.peak_susp_travel = peak_susp_travel
    res.minimum_Fz = float(np.min(F_z_total))

    return res
