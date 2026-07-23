import time
import numpy as np
from suspensionlab.physics.full_car import FullCarParams, FourCornerRoadProfile, run_full_car_analysis

def run_benchmark():
    # Setup test data
    params = FullCarParams(
        m_s=1200.0, I_x=300.0, I_y=1200.0, m_uf=40.0, m_ur=40.0,
        k_sf=30000.0, k_sr=35000.0, c_f=3000.0, c_r=3500.0,
        k_arb_f=10000.0, k_arb_r=5000.0, k_tf=250000.0, k_tr=250000.0,
        L=2.6, a=1.2, b=1.4, tw_f=1.6, tw_r=1.6, speed_mps=20.0
    )
    
    # 5 seconds of random road input at 1kHz
    t = np.linspace(0, 5, 5000)
    z_rfl = 0.05 * np.sin(2 * np.pi * 2 * t)
    z_rfr = 0.05 * np.sin(2 * np.pi * 2 * t + 0.1)
    z_rrl = 0.05 * np.sin(2 * np.pi * 2 * t + 0.2)
    z_rrr = 0.05 * np.sin(2 * np.pi * 2 * t + 0.3)
    
    profile = FourCornerRoadProfile(t, z_rfl, z_rfr, z_rrl, z_rrr)
    
    print("Warming up JIT...")
    res1 = run_full_car_analysis(params, profile)
    
    # Benchmark full analysis
    print("Benchmarking Full Car ODE Integration (LowLevelCallable + LSODA)...")
    t0 = time.perf_counter()
    res = run_full_car_analysis(params, profile)
    t1 = time.perf_counter()
    
    print(f"Total time for 5s of simulation (5000 steps): {t1 - t0:.5f} sec")
    print(f"Time per step: {(t1 - t0) / 5000 * 1e6:.2f} microseconds")

if __name__ == "__main__":
    run_benchmark()
