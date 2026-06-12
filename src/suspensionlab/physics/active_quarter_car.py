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
    
    # Ideal Skyhook Control Logic for Semi-Active Damper
    # The damper can only dissipate energy, not add it.
    if dz_s * v_rel > 0:
        F_d = p.c_sky * dz_s
    else:
        F_d = p.c_min * v_rel

    # Clip F_d to simulate damper limits (e.g., max force 5000 N)
    F_d = np.clip(F_d, -5000.0, 5000.0)

    # Sprung acceleration
    ddz_s = (1.0 / p.m_s) * (
        - F_d
        - k_w * (z_s  - z_u)
    )

    # Unsprung acceleration
    ddz_u = (1.0 / p.m_u) * (
          F_d
        + k_w * (z_s   - z_u)
        - p.k_t * (z_u - z_r)
        - p.c_t  * (dz_u - dz_r)
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
        method="RK45",
        rtol=1e-5,
        atol=1e-7,
    )

    time = sol.t
    z_s = sol.y[0]
    dz_s = sol.y[1]
    z_u = sol.y[2]
    dz_u = sol.y[3]

    # Calculate accelerations and forces
    ddz_s = np.zeros_like(time)
    z_r_arr = np.zeros_like(time)
    
    for i, t_step in enumerate(time):
        dx = _active_quarter_car_ode(t_step, sol.y[:, i], p, zr_fn, dzr_fn)
        ddz_s[i] = dx[1]
        z_r_arr[i] = float(zr_fn(np.array([t_step]))[0])

    susp_travel = z_s - z_u
    tire_defl = z_u - z_r_arr
    tire_load_var = p.k_t * tire_defl

    # Metrics
    rms_body_accel = float(np.sqrt(np.mean(ddz_s**2)))
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
    res.rms_susp_travel = rms_susp_travel
    res.rms_tire_load = rms_tire_load
    res.peak_susp_travel = peak_susp_travel

    return res
