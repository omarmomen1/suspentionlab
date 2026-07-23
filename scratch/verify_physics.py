import sys
import numpy as np
from suspensionlab.physics.quarter_car import QuarterCarParams, simulate_time_response, RoadProfile
from suspensionlab.physics.handling_model import HandlingParams, simulate_maneuver

def run_tests():
    score = 100
    deductions = []

    print("--- Physics Engine Verification ---")
    
    # 1. Quarter Car - Energy Conservation
    p_qc = QuarterCarParams(c=0, c_t=0, m_s=300, m_u=35, k_s=25000, k_t=200000, MR=1.0)
    profile = RoadProfile(profile_type="step", amplitude=0.0, duration=10.0) # Zero input
    
    # We can't set initial conditions easily via simulate_time_response, so we'll test stability
    # with a tiny impulse and then zero input.
    profile = RoadProfile(profile_type="impulse", amplitude=0.01, duration=5.0)
    res = simulate_time_response(p_qc, profile, t_eval_dt=0.01)
    
    # Calculate energy at t > 1.0 (after impulse)
    idx = np.where(res["time"] > 1.0)[0]
    if len(idx) > 0:
        z_s, dz_s = res["z_s"][idx], res["dz_s"][idx]
        z_u, dz_u = res["z_u"][idx], res["dz_u"][idx]
        z_r = res["z_r"][idx]
        
        # E = 0.5*m_s*v_s^2 + 0.5*m_u*v_u^2 + 0.5*k_w*(z_s-z_u)^2 + 0.5*k_t*(z_u-z_r)^2
        E = (0.5 * p_qc.m_s * dz_s**2 + 
             0.5 * p_qc.m_u * dz_u**2 + 
             0.5 * p_qc.k_w * (z_s - z_u)**2 + 
             0.5 * p_qc.k_t * (z_u - z_r)**2)
        
        E_start = E[0]
        E_end = E[-1]
        drift = abs(E_end - E_start)
        
        if E_start > 0:
            error_pct = (drift / E_start) * 100
            print(f"Quarter Car Energy Drift: {error_pct:.6f}%")
            if error_pct > 1.0:
                print("FAIL: Energy is not conserved.")
                score -= 10
                deductions.append("-10: Quarter car energy conservation failed.")
            else:
                print("PASS: Energy is conserved (within numerical tolerance).")
        else:
            print("Quarter Car Energy: 0")

    # 2. Handling Model - Braking physics (Reverse acceleration issue)
    p_hm = HandlingParams()
    # Brake from 10 m/s for 10 seconds. Should stop, not go in reverse.
    res_hm = simulate_maneuver(
        p_hm, 
        v_x_init=10.0, 
        steering_func=lambda t: 0.0,
        throttle_func=lambda t: 0.0,
        brake_func=lambda t: 1.0,
        duration=10.0,
        dt=0.1
    )
    
    final_vx = res_hm["v_x"][-1]
    print(f"Handling Model Final v_x after full braking: {final_vx:.3f} m/s")
    
    if final_vx < -0.1:
        print("FAIL: Car accelerates in reverse when braking to a stop.")
        score -= 25
        deductions.append("-25: Handling model allows braking to accelerate car in reverse (v_x clamping issue in ODE).")
    elif final_vx > 0.5:
        print("FAIL: Car did not stop as expected.")
        score -= 10
        deductions.append("-10: Handling model braking ineffective.")
    else:
        print("PASS: Car stops correctly under braking.")
        
    # 3. Handling Model - Newton's Second Law F = m*a
    # Check if a_x = dv_x/dt approx matches Fx/m
    a_x = res_hm["a_x"]
    # Check max lateral acceleration consistency with kinematics (F_y = m * v * omega)
    res_turn = simulate_maneuver(
        p_hm, 
        v_x_init=20.0, 
        steering_func=lambda t: 0.1, # Constant steering
        throttle_func=lambda t: 0.0,
        brake_func=lambda t: 0.0,
        duration=5.0,
        dt=0.1
    )
    v_x_t = res_turn["v_x"][-1]
    v_y_t = res_turn["v_y"][-1]
    yaw_t = res_turn["yaw_rate"][-1]
    a_y_kin = v_x_t * yaw_t
    a_y_dyn = res_turn["a_y"][-1]
    
    error_ay = abs(a_y_kin - a_y_dyn) / max(abs(a_y_dyn), 1e-3) * 100
    print(f"Handling Model Steady-State a_y error: {error_ay:.3f}%")
    if error_ay > 5.0:
        print("FAIL: Newton's second law / kinematic a_y mismatch.")
        score -= 15
        deductions.append("-15: Handling model steady-state lateral acceleration mismatch.")
    else:
        print("PASS: Handling model steady-state a_y consistent.")

    # 4. Mass constraints
    try:
         QuarterCarParams(m_s=0)
         print("FAIL: Allowed zero mass in QuarterCarParams.")
         score -= 5
         deductions.append("-5: Missing zero mass validation in QuarterCarParams.")
    except ValueError:
         print("PASS: Zero mass properly rejected in QuarterCarParams.")
         
    try:
        HandlingParams(m=0) # wait, HandlingParams doesn't have __post_init__ validation in code I saw
        print("FAIL: Allowed zero mass in HandlingParams.")
        score -= 5
        deductions.append("-5: Missing zero mass validation in HandlingParams.")
    except ValueError:
        print("PASS: Zero mass properly rejected in HandlingParams.")

    print(f"\nFinal Physics Readiness Score: {score}/100")
    for d in deductions:
        print(f"  {d}")

if __name__ == '__main__':
    run_tests()
