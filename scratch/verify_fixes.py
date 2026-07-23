import sys
import os
import traceback
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

def verify_quarter_car():
    print("--- Verifying Quarter Car ---")
    from suspensionlab.physics.quarter_car import QuarterCarParams
    # 1. Motion Ratio Inversion
    # MR = 0.85, k_s = 25000, c = 2050
    # Expected k_w = 25000 * 0.85**2 = 18062.5
    # Expected c_w = 2050 * 0.85**2 = 1481.125
    p = QuarterCarParams(k_s=25000, c=2050, MR=0.85)
    
    expected_kw = 25000 * (0.85 ** 2)
    expected_cw = 2050 * (0.85 ** 2)
    
    assert abs(p.k_w - expected_kw) < 1e-5, f"k_w mismatch: {p.k_w} vs {expected_kw}"
    assert abs(p.c_w - expected_cw) < 1e-5, f"c_w mismatch: {p.c_w} vs {expected_cw}"
    print("[PASS] Quarter Car MR Calculation is correct.")

def verify_full_car():
    print("--- Verifying Full Car ---")
    from suspensionlab.physics.full_car import FullCarParams, FourCornerRoadProfile, run_full_car_analysis
    
    # 2. Thread-unsafe globals
    import suspensionlab.physics.full_car as fc
    
    globals_present = [g for g in ["MAX_POINTS", "G_PARAMS", "G_TIME", "G_U", "G_N"] if hasattr(fc, g)]
    assert len(globals_present) == 0, f"Globals are still present in full_car namespace: {globals_present}"
    print("[PASS] Globals removed from full_car.py")
    
    # Run analysis to ensure it works
    p = FullCarParams(
        m_s=1500, I_x=500, I_y=2000, m_uf=40, m_ur=40,
        k_sf=30000, k_sr=30000, c_f=2000, c_r=2000,
        k_arb_f=10000, k_arb_r=5000, k_tf=200000, k_tr=200000,
        L=2.6, a=1.2, b=1.4, tw_f=1.5, tw_r=1.5, speed_mps=20
    )
    
    # Normal profile
    t = np.linspace(0, 1, 100)
    z_road = np.sin(2 * np.pi * t) * 0.05
    profile = FourCornerRoadProfile(time=t, z_rfl=z_road, z_rfr=z_road, z_rrl=z_road, z_rrr=z_road)
    
    try:
        res = run_full_car_analysis(p, profile)
        print("[PASS] Full car analysis executed successfully without globals.")
    except Exception as e:
        print(f"[FAIL] Full car analysis crashed: {e}")
        traceback.print_exc()
        
    # 3. Monotonic time array check
    t_bad = np.array([0.0, 0.1, 0.1, 0.2]) # Duplicate timestamp
    profile_bad = FourCornerRoadProfile(time=t_bad, z_rfl=np.zeros(4), z_rfr=np.zeros(4), z_rrl=np.zeros(4), z_rrr=np.zeros(4))
    
    try:
        run_full_car_analysis(p, profile_bad)
        print("[FAIL] Full car analysis did not raise error for non-monotonic time.")
    except ValueError as e:
        if "strictly monotonically increasing" in str(e):
            print("[PASS] Full car correctly raises ValueError on duplicate timestamps.")
        else:
            print(f"[FAIL] Unexpected ValueError: {e}")
            traceback.print_exc()

def verify_half_car():
    print("--- Verifying Half Car ---")
    from suspensionlab.physics.half_car import HalfCarParams, run_half_car_analysis
    from suspensionlab.physics.quarter_car import RoadProfile
    
    # Ensure it runs without issues
    p = HalfCarParams()
    profile = RoadProfile(duration=2.0)
    try:
        res = run_half_car_analysis(p, profile)
        print("[PASS] Half car analysis executed successfully.")
    except Exception as e:
        print(f"[FAIL] Half car analysis crashed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    verify_quarter_car()
    verify_full_car()
    verify_half_car()
