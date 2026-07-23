import numpy as np
import pytest
from scipy.linalg import expm
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, simulate_time_response, build_state_space
from suspensionlab.physics.full_car import FullCarParams, calculate_full_car_kpis

def test_quarter_car_analytical_benchmark():
    """
    Test quarter car numerical ODE solver vs analytical matrix exponential
    for a step input. Validates RMS error is < 0.01% as required by VnV.
    """
    # 1. Setup exact parameters from VnV benchmark doc
    params = QuarterCarParams(
        m_s=300.0,
        m_u=35.0,
        k_s=25000.0, # Will be mapped with MR
        c=2000.0,
        k_t=200000.0,
        MR=1.0, # Setting MR=1 to match equations exactly
        c_t=0.0
    )
    
    A, B = build_state_space(params)
    
    # Run analytical solution
    dt = 0.01
    t_end = 5.0
    t = np.arange(0, t_end, dt)
    step_amp = 0.05
    
    x_analytical = np.zeros((4, len(t)))
    for i, ti in enumerate(t):
        if ti >= 0.5: # simulate_time_response uses step at t=0.5
            # For a step input u(t), x(t) = A^-1 * (expm(A*t) - I) * B * u0
            # Assuming 0 initial conditions.
            A_inv = np.linalg.inv(A)
            x_analytical[:, i] = A_inv @ (expm(A * (ti - 0.5)) - np.eye(4)) @ B.flatten() * step_amp
            
    # Run numerical solver
    road = RoadProfile(profile_type="step", amplitude=0.05, duration=5.0)
    sim_res = simulate_time_response(params, road)
    res_t = sim_res["time"]
    res_x = sim_res["z_s"]
    
    # Calculate analytical on res_t exactly
    t_num = res_t
    z_s_num = res_x
    
    z_s_ana = np.zeros_like(t_num)
    for i, ti in enumerate(t_num):
        if ti >= 0.5:
            x_ana = np.linalg.inv(A) @ (expm(A * (ti - 0.5)) - np.eye(4)) @ B.flatten() * step_amp
            z_s_ana[i] = x_ana[0]
            
    # RMS Error
    diff = z_s_num - z_s_ana
    rms_error = np.sqrt(np.mean(diff**2))
    
    assert rms_error < 1e-4, f"RMS Error too high: {rms_error}"
    
    # Write JSON report
    import json
    with open("vnv_report.json", "w") as f:
        json.dump({
            "quarter_car_analytical_rms_error": float(rms_error),
            "status": "PASSED" if rms_error < 1e-4 else "FAILED"
        }, f)


def test_full_car_frequencies():
    """
    Test full car 14-DOF state space eigenvalues to extract mode shapes.
    Ensures that heave, pitch, and roll natural frequencies are within expected bounds.
    """
    params = FullCarParams(
        m_s=1500.0,
        I_x=400.0,
        I_y=2000.0,
        m_uf=40.0,
        m_ur=40.0,
        k_sf=25000.0,
        k_sr=30000.0,
        c_f=2000.0,
        c_r=2000.0,
        k_arb_f=10000.0,
        k_arb_r=5000.0,
        k_tf=250000.0,
        k_tr=250000.0,
        L=2.8,
        a=1.2,
        b=1.6,
        tw_f=1.5,
        tw_r=1.5,
        speed_mps=20.0
    )
    from collections import defaultdict
    mock_res = defaultdict(lambda: np.zeros(10))
    modes = calculate_full_car_kpis(params, mock_res)
    
    assert 0.5 < modes["f_n_heave"] < 3.0, f"Heave frequency {modes['f_n_heave']} out of bounds"
    assert 0.5 < modes["f_n_pitch"] < 3.0, f"Pitch frequency {modes['f_n_pitch']} out of bounds"
    assert 0.5 < modes["f_n_roll"] < 3.0, f"Roll frequency {modes['f_n_roll']} out of bounds"
    assert 10.0 < modes["f_n_uf"] < 20.0, f"Front unsprung frequency {modes['f_n_uf']} out of bounds"

def test_optimizer_convergence():
    """
    Test that the suspension optimizer converges to a valid solution.
    """
    from suspensionlab.physics.optimizer import optimize_setup
    
    params = QuarterCarParams(
        m_s=300.0, m_u=35.0, k_s=25000.0, c=2000.0, k_t=200000.0, MR=1.0, c_t=0.0
    )
    road = RoadProfile(profile_type="iso8608", iso_class="A", speed_mps=20.0, duration=2.0)
    
    # Run optimization for comfort
    res = optimize_setup(params, road, objective_type="comfort", max_travel=0.08)
    
    # Ensure it returns valid optimized params
    assert res["success"] is True, "Optimizer failed to converge"
    assert "optimal_ks" in res
    assert "optimal_c" in res
    
    assert res["optimal_ks"] > 0, "Optimized k_s should be positive"
    assert res["optimal_c"] > 0, "Optimized c should be positive"
