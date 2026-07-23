import os
import sys
import time
import numpy as np

# Ensure the app can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from scipy.integrate import solve_ivp
from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    _road_profile_fn,
    _quarter_car_ode
)

def run_solver(method, rtol, atol, p, zr_fn, dzr_fn, t_span, t_eval):
    x0 = [0.0, 0.0, 0.0, 0.0]
    
    t0 = time.time()
    sol = solve_ivp(
        fun=_quarter_car_ode,
        t_span=t_span,
        y0=x0,
        method=method,
        t_eval=t_eval,
        args=(p, zr_fn, dzr_fn),
        rtol=rtol,
        atol=atol,
        dense_output=False
    )
    t1 = time.time()
    
    # Check simple metrics
    accels = []
    susp_travels = []
    
    if sol.success:
        z_s, z_u, dz_s, dz_u = sol.y
        for i in range(len(sol.t)):
            t_curr = sol.t[i]
            x_curr = sol.y[:, i]
            dz_r_val = dzr_fn(t_curr)
            dx = _quarter_car_ode(t_curr, x_curr, p, zr_fn, dzr_fn)
            accels.append(dx[2])
            susp_travels.append(z_s[i] - z_u[i])
            
        rms_accel = np.sqrt(np.mean(np.square(accels)))
        peak_travel = np.max(np.abs(susp_travels))
    else:
        rms_accel = float('nan')
        peak_travel = float('nan')

    return {
        "success": sol.success,
        "time": t1 - t0,
        "nfev": sol.nfev,
        "rms_accel": rms_accel,
        "peak_travel": peak_travel,
        "message": sol.message
    }

def main():
    methods = ["BDF", "Radau", "LSODA", "RK45"]
    rtols = [1e-3, 1e-5, 1e-7]
    atols = [1e-6, 1e-8, 1e-10]
    
    p = QuarterCarParams(m_s=1000, m_u=100, k_s=25000, k_t=250000, c=2000, c_t=50)
    profile = RoadProfile(duration=5.0, profile_type="step")
    zr_fn, dzr_fn = _road_profile_fn(profile)
    t_span = (0.0, profile.duration)
    t_eval = np.arange(0.0, profile.duration, 0.005) # 200Hz
    
    print(f"{'Method':<8} | {'Tol':<8} | {'Success':<7} | {'Time (s)':<8} | {'NFEV':<6} | {'RMS Accel':<10} | {'Peak Trvl':<10}")
    print("-" * 75)
    
    for method in methods:
        for rtol, atol in zip(rtols, atols):
            label_tol = f"{rtol:.0e}"
            try:
                res = run_solver(method, rtol, atol, p, zr_fn, dzr_fn, t_span, t_eval)
                succ = "Yes" if res["success"] else "No"
                t_str = f"{res['time']:.3f}"
                nfev = f"{res['nfev']}"
                rms = f"{res['rms_accel']:.4f}"
                pt = f"{res['peak_travel']:.4f}"
            except Exception as e:
                succ = "Err"
                t_str = "N/A"
                nfev = "N/A"
                rms = "N/A"
                pt = "N/A"
                
            print(f"{method:<8} | {label_tol:<8} | {succ:<7} | {t_str:<8} | {nfev:<6} | {rms:<10} | {pt:<10}")

if __name__ == "__main__":
    main()
