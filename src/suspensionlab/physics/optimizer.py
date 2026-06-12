"""
physics/optimizer.py
====================
Setup Solver Optimization Engine
"""

from scipy.optimize import minimize

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis
)

_cache = {}

def get_sim_result(x, base_params, profile):
    key = (float(x[0]), float(x[1]))
    if key not in _cache:
        p = QuarterCarParams(
            m_s=base_params.m_s, m_u=base_params.m_u,
            k_s=x[0], c=x[1],
            k_t=base_params.k_t, c_t=base_params.c_t, MR=base_params.MR  
        )
        _cache[key] = run_quarter_car_analysis(p, profile, f_min=1.0, f_max=20.0, n_freq=600)
    return _cache[key]

def objective(x, base_params: QuarterCarParams, profile: RoadProfile, objective_type: str, max_travel: float):
    result = get_sim_result(x, base_params, profile)

    rms_accel = getattr(result, "rms_body_accel", 0.0)
    peak_travel = getattr(result, "peak_susp_travel", 0.0)

    if objective_type == "Ride Comfort":
        cost = rms_accel
    elif objective_type == "Min Travel":
        cost = peak_travel * 100
    else: # Balanced
        cost = rms_accel + (peak_travel * 10)

    return cost

def travel_constraint_func(x, base_params, profile, objective_type, max_travel):
    result = get_sim_result(x, base_params, profile)
    peak_travel = getattr(result, "peak_susp_travel", 0.0)
    return max_travel - peak_travel


def optimize_setup(base_params: QuarterCarParams, profile: RoadProfile, objective_type: str, max_travel: float, heartbeat_callback=None):
    x0 = [base_params.k_s, base_params.c]


    bounds = [
        (10000.0, 150000.0), # Spring Rate bounds
        (500.0, 15000.0)     # Damping bounds
    ]

    print(f"\n--- STARTING AI OPTIMIZATION ({objective_type}) ---")

    global _cache
    _cache.clear()
    
    sol = minimize(
        objective,
        x0=x0,
        args=(base_params, profile, objective_type, max_travel),
        bounds=bounds,
        constraints={'type': 'ineq', 'fun': travel_constraint_func, 'args': (base_params, profile, objective_type, max_travel)},
        method="SLSQP",
        callback=heartbeat_callback,
        options={
            "maxiter": 100,
            "ftol": 1e-6,
        }
    )

    print(f"--- OPTIMIZATION FINISHED IN {sol.nfev} ITERATIONS ---\n")

    return {
        "optimal_ks": float(sol.x[0]),
        "optimal_c": float(sol.x[1]),
        "success": sol.success
    }