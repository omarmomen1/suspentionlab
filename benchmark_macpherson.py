import numpy as np
import time
from suspensionlab.physics.api_models import safe_generate_kinematic_lut

def create_macpherson_suspension():
    return {
        "chassis_strut_top": np.array([0.0, 0.5, 0.7]),
        "chassis_lower_front": np.array([0.2, 0.2, 0.1]),
        "chassis_lower_rear": np.array([-0.2, 0.2, 0.12]),
        "upright_lower": np.array([0.0, 0.72, 0.15]),
        "upright_strut_mount": np.array([0.0, 0.70, 0.35]),
        "upright_tie_rod": np.array([0.1, 0.72, 0.25]),
        "chassis_tie_rod": np.array([0.1, 0.2, 0.25]),
        "wheel_center": np.array([0.0, 0.8, 0.3])
    }

def run_benchmark():
    print("Testing Pydantic validation and C++ MacPherson implementation...")
    
    # 1. Provide bad hardpoints to test validation
    bad_hardpoints = create_macpherson_suspension()
    bad_hardpoints["wheel_center"] = np.array([0.0, 0.8]) # missing Z
    
    try:
        safe_generate_kinematic_lut("macpherson", bad_hardpoints, np.linspace(-0.1, 0.1, 5), np.array([0.0]))
        print("FAIL: Pydantic failed to catch invalid hardpoints")
        exit(1)
    except ValueError as e:
        print(f"PASS: Pydantic correctly caught invalid hardpoints: {e}")
        
    # 2. Provide good hardpoints
    good_hardpoints = create_macpherson_suspension()
    heave_range = np.linspace(-0.1, 0.1, 50)
    
    t0 = time.time()
    try:
        lut = safe_generate_kinematic_lut("macpherson", good_hardpoints, heave_range, np.array([0.0]))
        t1 = time.time()
        print(f"PASS: MacPherson sweep completed in {(t1 - t0)*1000:.2f} ms")
        print(f"Camber at 0 heave: {lut['camber'][25]:.3f} deg")
        print(f"Camber at -0.1 heave: {lut['camber'][0]:.3f} deg")
        print(f"Camber at +0.1 heave: {lut['camber'][49]:.3f} deg")
        print(f"RC Height at 0 heave: {lut['rc_z'][25]:.3f} m")
    except Exception as e:
        print(f"FAIL: MacPherson solver threw an exception: {e}")
        exit(1)

if __name__ == "__main__":
    run_benchmark()
