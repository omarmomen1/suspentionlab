import sys
import os
import math
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from suspensionlab.physics.magic_formula import calc_tire_forces, TireCoeffs
from suspensionlab.physics.handling_model import HandlingParams, simulate_maneuver

print("--- Testing magic_formula.py ---")
def test_mf(name, fz, alpha, kappa, camber):
    try:
        fx, fy = calc_tire_forces(fz, alpha, kappa, camber)
        if math.isnan(fx) or math.isnan(fy) or math.isinf(fx) or math.isinf(fy):
            print(f"[{name}] Numerical instability! Result: Fx={fx}, Fy={fy}")
        else:
            print(f"[{name}] Passed. Fx={fx:.2f}, Fy={fy:.2f}")
    except Exception as e:
        print(f"[{name}] Crashed: {type(e).__name__} - {str(e)}")

test_mf("Normal", 4000.0, 0.1, 0.1, 0.0)
test_mf("Negative Fz", -1000.0, 0.1, 0.1, 0.0)
test_mf("Zero Fz", 0.0, 0.1, 0.1, 0.0)
test_mf("NaN Fz", float('nan'), 0.1, 0.1, 0.0)
test_mf("Inf Alpha", 4000.0, float('inf'), 0.1, 0.0)
test_mf("NaN Alpha", 4000.0, float('nan'), 0.1, 0.0)
test_mf("Extremely high Fz", 1e9, 0.1, 0.1, 0.0)

print("\n--- Testing handling_model.py ---")
def test_handling(name, params_dict=None, v_init=20.0):
    try:
        p = HandlingParams(**(params_dict or {}))
        # Simple inputs
        steer = lambda t: 0.1
        throttle = lambda t: 0.5
        brake = lambda t: 0.0
        
        res = simulate_maneuver(p, v_init, steer, throttle, brake, duration=1.0, dt=0.01)
        # Check for NaN in results
        has_nan = any(np.isnan(res[k]).any() for k in res if isinstance(res[k], np.ndarray))
        if has_nan:
            print(f"[{name}] Numerical instability: Output contains NaN!")
        else:
            print(f"[{name}] Passed.")
    except Exception as e:
        print(f"[{name}] Crashed: {type(e).__name__} - {str(e)}")

test_handling("Normal")
test_handling("Zero Mass", {"m": 0.0})
test_handling("Negative Mass", {"m": -1200.0})
test_handling("Zero Inertia", {"I_z": 0.0})
test_handling("NaN Mass", {"m": float('nan')})
test_handling("Zero Track Width", {"tw_f": 0.0, "tw_r": 0.0})
test_handling("Zero Velocity", v_init=0.0)
test_handling("Negative Velocity", v_init=-10.0)
