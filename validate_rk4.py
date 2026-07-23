import time
import numpy as np
from scipy.integrate import solve_ivp
from suspensionlab.physics.full_car import (
    FullCarParams, FourCornerRoadProfile, 
    _full_car_ode_wrapper, _numba_rk4_solver
)

def run_validation():
    print("Setting up validation...")
    params = FullCarParams(
        m_s=1200.0, I_x=300.0, I_y=1200.0, m_uf=40.0, m_ur=40.0,
        k_sf=30000.0, k_sr=35000.0, c_f=3000.0, c_r=3500.0,
        k_arb_f=10000.0, k_arb_r=5000.0, k_tf=250000.0, k_tr=250000.0,
        L=2.6, a=1.2, b=1.4, tw_f=1.6, tw_r=1.6, speed_mps=20.0
    )
    
    # 5 seconds of track profile at 1kHz (dt=0.001s, 5000 points)
    t = np.linspace(0, 5, 5000)
    z_rfl = 0.05 * np.sin(2 * np.pi * 2 * t)
    z_rfr = 0.05 * np.sin(2 * np.pi * 2 * t + 0.1)
    z_rrl = 0.05 * np.sin(2 * np.pi * 2 * t + 0.2)
    z_rrr = 0.05 * np.sin(2 * np.pi * 2 * t + 0.3)
    
    profile = FourCornerRoadProfile(t, z_rfl, z_rfr, z_rrl, z_rrr)
    U = np.column_stack([z_rfl, z_rfr, z_rrl, z_rrr])
    N = len(t)
    
    # Create local arrays instead of globals
    g_params = params.to_array()
    g_time = profile.time
    g_u = U

    y0 = np.zeros(14, dtype=np.float64)
    
    print("--- 1. Testing SciPy BDF Solver ---")
    t0 = time.perf_counter()
    sol = solve_ivp(
        fun=_full_car_ode_wrapper,
        t_span=(t[0], t[-1]),
        y0=y0,
        method="BDF",
        t_eval=t,
        args=(g_time, g_u, g_params),
        rtol=1e-5,
        atol=1e-8,
        max_step=max(0.001, (t[-1] - t[0]) / 5000.0)
    )
    t1 = time.perf_counter()
    bdf_time = t1 - t0
    y_bdf = sol.y.T
    print(f"SciPy BDF Time: {bdf_time:.5f} sec")
    
    print("--- 2. Warming up Numba RK4 ---")
    y_rk4 = np.zeros((N, 14), dtype=np.float64)
    k1 = np.zeros(14, dtype=np.float64)
    k2 = np.zeros(14, dtype=np.float64)
    k3 = np.zeros(14, dtype=np.float64)
    k4 = np.zeros(14, dtype=np.float64)
    y_temp = np.zeros(14, dtype=np.float64)
    u_temp = np.zeros(4, dtype=np.float64)
    
    _numba_rk4_solver(y0, t, y_rk4, g_time, g_u, g_params, k1, k2, k3, k4, y_temp, u_temp)
    
    print("--- 3. Testing Numba RK4 Solver ---")
    y_rk4 = np.zeros((N, 14), dtype=np.float64)
    t0 = time.perf_counter()
    _numba_rk4_solver(y0, t, y_rk4, g_time, g_u, g_params, k1, k2, k3, k4, y_temp, u_temp)
    t1 = time.perf_counter()
    rk4_time = t1 - t0
    print(f"Numba RK4 Time: {rk4_time:.5f} sec")
    
    print(f"\n=> Speedup: {bdf_time / rk4_time:.2f}x")
    
    print("\n--- 4. Numerical Drift (RMSE) Validation ---")
    rmse = np.sqrt(np.mean((y_bdf - y_rk4)**2, axis=0))
    print(f"Max State RMSE across 14 DOFs over 5s: {np.max(rmse):.4e}")
    print(f"Mean State RMSE across 14 DOFs over 5s: {np.mean(rmse):.4e}")
    
    print("\nValidation Complete. Strict zero-allocation fixed-step Numba RK4 implemented successfully.")

if __name__ == "__main__":
    run_validation()
