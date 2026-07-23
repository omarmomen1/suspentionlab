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

def get_sim_result(x, base_params, profile, cache_dict):
    key = (float(x[0]), float(x[1]))
    if key not in cache_dict:
        p = QuarterCarParams(
            m_s=base_params.m_s, m_u=base_params.m_u,
            k_s=x[0], c=x[1],
            k_t=base_params.k_t, c_t=base_params.c_t, MR=base_params.MR  
        )
        cache_dict[key] = run_quarter_car_analysis(p, profile, f_min=1.0, f_max=20.0, n_freq=600)
    return cache_dict[key]

def objective(x, base_params: QuarterCarParams, profile: RoadProfile, objective_type: str, max_travel: float, cache_dict: dict):
    result = get_sim_result(x, base_params, profile, cache_dict)

    rms_accel = getattr(result, "rms_body_accel", 0.0)
    peak_travel = getattr(result, "peak_susp_travel", 0.0)

    if objective_type == "Ride Comfort":
        cost = rms_accel
    elif objective_type == "Min Travel":
        cost = peak_travel * 100
    else: # Balanced
        cost = rms_accel + (peak_travel * 10)

    return cost

def travel_constraint_func(x, base_params, profile, objective_type, max_travel, cache_dict):
    result = get_sim_result(x, base_params, profile, cache_dict)
    peak_travel = getattr(result, "peak_susp_travel", 0.0)
    return max_travel - peak_travel


def optimize_setup(base_params: QuarterCarParams, profile: RoadProfile, objective_type="Ride Comfort", max_travel=0.08, heartbeat_callback=None):
    cache_dict = {}
    
    x0 = [base_params.k_s, base_params.c]
    from scipy.optimize import NonlinearConstraint
    
    def constraint_fun(x):
        return travel_constraint_func(x, base_params, profile, objective_type, max_travel, cache_dict)
        
    constraints = [
        {'type': 'ineq', 'fun': constraint_fun},
        {'type': 'ineq', 'fun': lambda x: x[0] - 10000.0},
        {'type': 'ineq', 'fun': lambda x: 50000.0 - x[0]},
        {'type': 'ineq', 'fun': lambda x: x[1] - 1000.0},
        {'type': 'ineq', 'fun': lambda x: 5000.0 - x[1]}
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
        "success": sol.success
    }