import os
import sys
import numpy as np
from scipy.integrate import solve_ivp

# Add project root to path
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_dir)

from src.suspensionlab.physics.quarter_car import (
    QuarterCarParams, compute_modal_properties, _quarter_car_ode
)
from src.suspensionlab.physics.half_car import (
    HalfCarParams, _half_car_ode, simulate_time_response as sim_hc,
    RoadProfile as HCRoadProfile
)
from src.suspensionlab.physics.full_car import (
    FullCarParams, FourCornerRoadProfile, run_full_car_analysis
)
from src.suspensionlab.physics.handling_model import (
    HandlingParams, simulate_maneuver, calc_tire_forces
)

def run_tests():
    report = ["# Physics Engine Verification Report\n"]
    
    # ---------------------------------------------------------
    # 1. QUARTER CAR
    # ---------------------------------------------------------
    report.append("## 1. Quarter Car (2-DOF)")
    
    # Test 1A: Conservation of Energy (Undamped Free Vibration)
    p_qc = QuarterCarParams(c=0, c_t=0)
    def zr_zero(t): return np.zeros_like(t)
    def dzr_zero(t): return np.zeros_like(t)
    
    x0 = [0.1, 0.0, 0.1, 0.0] # Initial displacement z_s = 0.1, z_u = 0.1
    sol = solve_ivp(
        fun=_quarter_car_ode,
        t_span=(0, 10.0),
        y0=x0,
        args=(p_qc, zr_zero, dzr_zero),
        method="RK45",
        t_eval=np.linspace(0, 10.0, 5000),
        rtol=1e-8, atol=1e-10
    )
    
    z_s, dz_s, z_u, dz_u = sol.y
    KE = 0.5 * p_qc.m_s * dz_s**2 + 0.5 * p_qc.m_u * dz_u**2
    PE = 0.5 * p_qc.k_w * (z_s - z_u)**2 + 0.5 * p_qc.k_t * z_u**2
    E_total = KE + PE
    
    e_drift = np.max(E_total) - np.min(E_total)
    e_pct = (e_drift / E_total[0]) * 100
    report.append(f"- **Conservation of Energy:** Initial E = {E_total[0]:.4f} J. Drift over 10s = {e_drift:.2e} J ({e_pct:.4f}% error). {'✅' if e_pct < 0.1 else '❌'}")

    # Test 1B: Frequencies
    freqs = np.fft.rfftfreq(len(z_s), d=(10.0/5000))
    fft_zs = np.abs(np.fft.rfft(z_s - np.mean(z_s)))
    fft_zu = np.abs(np.fft.rfft(z_u - np.mean(z_u)))
    obs_f1 = freqs[np.argmax(fft_zs)]
    obs_f2 = freqs[np.argmax(fft_zu)]
    if obs_f1 > obs_f2:
        obs_f1, obs_f2 = obs_f2, obs_f1
        
    modal = compute_modal_properties(p_qc)
    err_f1 = abs(obs_f1 - modal['f_n_s']) / modal['f_n_s'] * 100
    err_f2 = abs(obs_f2 - modal['f_n_u']) / modal['f_n_u'] * 100
    report.append(f"- **Harmonic Frequencies:** Sprung expected {modal['f_n_s']:.2f} Hz, observed ~{obs_f1:.2f} Hz. Unsprung expected {modal['f_n_u']:.2f} Hz, observed ~{obs_f2:.2f} Hz. {'✅' if err_f1 < 5.0 and err_f2 < 5.0 else '❌'}")

    # Test 1C: Conservation of Momentum (Free Floating)
    p_float = QuarterCarParams(k_s=0, c=0, k_t=0, c_t=0)
    x0_mom = [0.0, 2.0, 0.0, 0.0] # v_s = 2.0 m/s
    sol_mom = solve_ivp(
        fun=_quarter_car_ode, t_span=(0, 2.0), y0=x0_mom,
        args=(p_float, zr_zero, dzr_zero), method="RK45",
        t_eval=np.linspace(0, 2.0, 100), rtol=1e-8, atol=1e-10
    )
    P_total = p_float.m_s * sol_mom.y[1] + p_float.m_u * sol_mom.y[3]
    p_drift = np.max(P_total) - np.min(P_total)
    report.append(f"- **Conservation of Momentum:** Initial P = {P_total[0]:.2f} kg*m/s. Drift = {p_drift:.2e}. {'✅' if p_drift < 1e-4 else '❌'}")


    # ---------------------------------------------------------
    # 2. HALF CAR
    # ---------------------------------------------------------
    report.append("\n## 2. Half Car (4-DOF)")
    
    # Test 2A: Geometric Constraint
    try:
        HalfCarParams(a=1.0, b=1.0, L=3.0)
        report.append("- **Geometric Constraints:** Did not raise error for L != a+b. ❌")
    except ValueError:
        report.append("- **Geometric Constraints:** Caught L != a+b successfully. ✅")
        
    # Test 2B: Pitch-Heave Decoupling
    p_hc = HalfCarParams(a=1.5, b=1.5, k_sf=30000, k_sr=30000, m_uf=40, m_ur=40, c_f=0, c_r=0, L=3.0, speed_mps=0)
    prof_hc = HCRoadProfile(profile_type="step", amplitude=0.1, duration=2.0)
    res_hc = sim_hc(p_hc, prof_hc)
    max_pitch = np.max(np.abs(res_hc["theta"]))
    report.append(f"- **Pitch-Heave Decoupling:** Max pitch for symmetric bump = {max_pitch:.2e} rad. {'✅' if max_pitch < 1e-8 else '❌'}")
    
    # Test 2C: Wheelbase delay
    p_hc2 = HalfCarParams(speed_mps=10.0, L=2.0, a=1.0, b=1.0)
    prof_hc2 = HCRoadProfile(profile_type="step", amplitude=0.1, duration=2.0)
    res_hc2 = sim_hc(p_hc2, prof_hc2)
    # Delay is 2.0 / 10.0 = 0.2s. At t=0.5s front hits bump. Rear should hit at 0.7s.
    t_idx_0_6 = np.argmin(np.abs(res_hc2["time"] - 0.6))
    t_idx_0_8 = np.argmin(np.abs(res_hc2["time"] - 0.8))
    z_rf_06 = res_hc2["z_rf"][t_idx_0_6] # > 0
    z_rr_06 = res_hc2["z_rr"][t_idx_0_6] # 0
    z_rr_08 = res_hc2["z_rr"][t_idx_0_8] # > 0
    delay_correct = (z_rf_06 > 0.05 and z_rr_06 < 0.01 and z_rr_08 > 0.05)
    report.append(f"- **Wheelbase Delay:** Delay correctly shifts rear input. {'✅' if delay_correct else '❌'}")


    # ---------------------------------------------------------
    # 3. FULL CAR
    # ---------------------------------------------------------
    report.append("\n## 3. Full Car (7-DOF)")
    
    p_fc = FullCarParams(
        m_s=1500, I_x=400, I_y=2000, m_uf=45, m_ur=45,
        k_sf=30000, k_sr=35000, c_f=3000, c_r=3000,
        k_arb_f=15000, k_arb_r=5000, k_tf=250000, k_tr=250000,
        L=2.8, a=1.3, b=1.5, tw_f=1.6, tw_r=1.6, speed_mps=20
    )
    t_arr = np.linspace(0, 5, 500)
    
    # Test 3A: Symmetric Response (Zero Roll)
    z_bump = np.where(t_arr > 1.0, 0.05, 0.0)
    prof_sym = FourCornerRoadProfile(time=t_arr, z_rfl=z_bump, z_rfr=z_bump, z_rrl=z_bump, z_rrr=z_bump)
    res_sym = run_full_car_analysis(p_fc, prof_sym)
    max_roll_sym = np.max(np.abs(res_sym.phi))
    report.append(f"- **Symmetric Response:** Max roll angle = {max_roll_sym:.2e} rad. {'✅' if max_roll_sym < 1e-10 else '❌'}")
    
    # Test 3B: Anti-Symmetric (Roll Stiffness Dist)
    z_bump_right = -z_bump
    prof_asym = FourCornerRoadProfile(time=t_arr, z_rfl=z_bump, z_rfr=z_bump_right, z_rrl=z_bump, z_rrr=z_bump_right)
    res_asym = run_full_car_analysis(p_fc, prof_asym)
    max_llt_f = np.max(np.abs(res_asym.lateral_load_transfer_f))
    max_llt_r = np.max(np.abs(res_asym.lateral_load_transfer_r))
    obs_roll_dist = (max_llt_f / (max_llt_f + max_llt_r)) * 100 if (max_llt_f + max_llt_r) > 0 else 0
    theo_roll_dist = res_asym.roll_stiffness_dist
    err_roll_dist = abs(obs_roll_dist - theo_roll_dist)
    report.append(f"- **Roll Stiffness Distribution:** Expected {theo_roll_dist:.1f}%, Observed {obs_roll_dist:.1f}%. Error: {err_roll_dist:.2f}%. {'✅' if err_roll_dist < 5.0 else '❌'}")


    # ---------------------------------------------------------
    # 4. HANDLING MODEL
    # ---------------------------------------------------------
    report.append("\n## 4. Handling Model (3-DOF)")
    
    # Test 4A: Steady State Cornering
    p_hm = HandlingParams()
    v_test = 20.0
    res_hm = simulate_maneuver(
        p=p_hm,
        v_x_init=v_test,
        steering_func=lambda t: np.radians(2.0), # 2 degrees steer
        throttle_func=lambda t: 0.1, # slight throttle to maintain speed
        brake_func=lambda t: 0.0,
        duration=10.0,
        dt=0.05
    )
    
    # Check Newton's second law at steady state (t=9.0s)
    idx = -1
    v_x_ss = res_hm["v_x"][idx]
    v_y_ss = res_hm["v_y"][idx]
    omega_ss = res_hm["yaw_rate"][idx]
    a_y_kinematic = v_x_ss * omega_ss
    a_y_dynamic = res_hm["a_y"][idx]
    err_ay = abs(a_y_kinematic - a_y_dynamic) / max(abs(a_y_kinematic), 1e-6) * 100
    report.append(f"- **Steady-State Cornering:** v_x={v_x_ss:.2f}, v_y={v_y_ss:.2f}, omega={omega_ss:.2f} rad/s. Kinematic a_y = {a_y_kinematic:.2f} m/s², Dynamic a_y = {a_y_dynamic:.2f} m/s². Error = {err_ay:.2f}%. {'✅' if err_ay < 5.0 and abs(a_y_kinematic) < 50.0 else '❌'}")

    # Test 4B: Aero Downforce
    W_static = p_hm.m * 9.81
    v_mag = np.sqrt(v_x_ss**2 + res_hm["v_y"][idx]**2)
    F_aero_l = 0.5 * p_hm.rho_air * p_hm.C_l * p_hm.frontal_area * v_mag**2
    # The handling model uses aero implicitly in load transfer calculation inside ODE.
    # But does it return the total tire loads to verify?
    # Handling model does NOT return tire loads currently. It only returns vehicle states.
    # We will verify the velocity decay in straight line braking instead.
    
    res_brake = simulate_maneuver(
        p=p_hm,
        v_x_init=30.0,
        steering_func=lambda t: 0.0,
        throttle_func=lambda t: 0.0,
        brake_func=lambda t: 1.0, # Full brake
        duration=3.0,
        dt=0.05
    )
    v_end = res_brake["v_x"][-1]
    report.append(f"- **Longitudinal Dynamics:** Braking from 30 m/s for 3s. Final speed = {v_end:.2f} m/s. Deceleration works. {'✅' if v_end < 15.0 else '❌'}")


    # ---------------------------------------------------------
    # WRITE REPORT
    # ---------------------------------------------------------
    report_path = os.path.join(project_dir, "physics_verification_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
        
    print(f"Report successfully generated at {report_path}")

if __name__ == "__main__":
    run_tests()
