"""
physics/optimizer.py
====================
Setup Solver Optimization Engine
"""

from scipy.optimize import minimize

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    simulate_time_response,
    compute_metrics,
    SolverMode,
)

def get_sim_result(x, base_params, profile, cache_dict):
    key = (round(float(x[0]), 2), round(float(x[1]), 2))
    if key not in cache_dict:
        p = QuarterCarParams(
            m_s=base_params.m_s, m_u=base_params.m_u,
            k_s=x[0], c=x[1],
            k_t=base_params.k_t, c_t=base_params.c_t, MR=base_params.MR  
        )
        time_res = simulate_time_response(p, profile, solver_mode=SolverMode.FAST)
        metrics = compute_metrics(time_res, p)
        cache_dict[key] = {
            "rms_body_accel": float(metrics.get("rms_body_accel", 0.0)),
            "peak_susp_travel": float(metrics.get("peak_susp_travel", 0.0)),
        }
    return cache_dict[key]

def objective(x, base_params: QuarterCarParams, profile: RoadProfile, objective_type: str, max_travel: float, cache_dict: dict):
    result = get_sim_result(x, base_params, profile, cache_dict)

    rms_accel = result.get("rms_body_accel", 0.0)
    peak_travel = result.get("peak_susp_travel", 0.0)

    obj_str = str(objective_type).strip().lower()
    if "comfort" in obj_str:
        cost = rms_accel
    elif "travel" in obj_str:
        cost = peak_travel * 100.0
    else: # Balanced
        cost = rms_accel + (peak_travel * 10.0)

    return cost

def travel_constraint_func(x, base_params, profile, objective_type, max_travel, cache_dict):
    result = get_sim_result(x, base_params, profile, cache_dict)
    peak_travel = result.get("peak_susp_travel", 0.0)
    return max_travel - peak_travel


def optimize_setup(
    base_params: QuarterCarParams,
    profile: RoadProfile,
    objective_type="Ride Comfort",
    max_travel=0.08,
    heartbeat_callback=None,
    bounds=None,
):
    cache_dict = {}

    if bounds and "k_s" in bounds:
        ks_min, ks_max = float(bounds["k_s"][0]), float(bounds["k_s"][1])
    else:
        ks_min = max(2000.0, min(10000.0, base_params.k_s * 0.4))
        ks_max = max(50000.0, base_params.k_s * 2.5)

    if bounds and "c" in bounds:
        c_min, c_max = float(bounds["c"][0]), float(bounds["c"][1])
    else:
        c_min = max(200.0, min(1000.0, base_params.c * 0.4))
        c_max = max(5000.0, base_params.c * 2.5)

    init_ks = min(max(base_params.k_s, ks_min + 1.0), ks_max - 1.0)
    init_c  = min(max(base_params.c, c_min + 1.0), c_max - 1.0)
    x0 = [init_ks, init_c]

    def constraint_fun(x):
        return travel_constraint_func(x, base_params, profile, objective_type, max_travel, cache_dict)

    constraints = [
        {'type': 'ineq', 'fun': constraint_fun},
        {'type': 'ineq', 'fun': lambda x, kmin=ks_min: x[0] - kmin},
        {'type': 'ineq', 'fun': lambda x, kmax=ks_max: kmax - x[0]},
        {'type': 'ineq', 'fun': lambda x, cmin=c_min: x[1] - cmin},
        {'type': 'ineq', 'fun': lambda x, cmax=c_max: cmax - x[1]}
    ]


    sol = minimize(
        objective,
        x0=x0,
        args=(base_params, profile, objective_type, max_travel, cache_dict),
        method="COBYLA",
        constraints=constraints,
        callback=heartbeat_callback,
        options={
            "maxiter": 100,
            "tol": 1e-3,
        }
    )

    return {
        "optimal_ks": float(sol.x[0]),
        "optimal_c": float(sol.x[1]),
        "success": bool(sol.success or (getattr(sol, "status", 0) in (1, 2, 3) and sol.fun < 1e5)),
    }