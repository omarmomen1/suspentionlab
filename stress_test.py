import sys
import os
import math
import traceback
import time
import numpy as np
import multiprocessing

# Adjust path to find suspensionlab
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis
)
from suspensionlab.physics.exceptions import MathConvergenceError

def check_results(name, result, t_elapsed):
    issues = []
    
    if t_elapsed > 1.0:
        issues.append(f"Performance degradation (Took {t_elapsed:.2f}s)")
        
    for field in ["omega_n_s", "omega_n_u", "f_n_s", "f_n_u", "zeta_s", "zeta_u", "rms_body_accel", "rms_body_accel_wk", "rms_susp_travel", "rms_tire_load"]:
        val = getattr(result, field)
        if math.isnan(val) or math.isinf(val):
            issues.append(f"Numerical instability in scalar {field}: {val}")
            
    for array_field in ["transmissibility_body", "z_s", "dz_s", "ddz_s", "susp_travel"]:
        arr = getattr(result, array_field)
        if arr is not None and len(arr) > 0:
            if np.isnan(arr).any() or np.isinf(arr).any():
                issues.append(f"Numerical instability in array {array_field}: contains NaN or Inf")
    
    return issues

def _run_test_worker(name, params_dict, road_dict, return_dict):
    try:
        p = QuarterCarParams(**(params_dict or {}))
        r = RoadProfile(**(road_dict or {}))
        
        t0 = time.time()
        res = run_quarter_car_analysis(p, r)
        t_elapsed = time.time() - t0
        
        issues = check_results(name, res, t_elapsed)
        return_dict['issues'] = issues
        return_dict['t_elapsed'] = t_elapsed
    except Exception as e:
        return_dict['exception'] = f"{type(e).__name__} - {str(e)}"

def run_test(name, params_dict=None, road_dict=None):
    manager = multiprocessing.Manager()
    return_dict = manager.dict()
    p = multiprocessing.Process(target=_run_test_worker, args=(name, params_dict, road_dict, return_dict))
    p.start()
    p.join(timeout=3.0)
    
    if p.is_alive():
        print(f"CRASH/FREEZE [{name}]: Process hung/froze and timed out after 3.0s", flush=True)
        p.terminate()
        p.join()
    else:
        if 'exception' in return_dict:
            print(f"CRASH/EXCEPTION [{name}]: {return_dict['exception']}", flush=True)
        else:
            issues = return_dict.get('issues', [])
            t_elapsed = return_dict.get('t_elapsed', 0.0)
            if issues:
                print(f"FAILED [{name}]:", flush=True)
                for i in issues:
                    print(f"  - {i}", flush=True)
            else:
                print(f"PASSED [{name}] in {t_elapsed:.3f}s", flush=True)

if __name__ == '__main__':
    print("--- Starting Stress Tests ---", flush=True)

    # 1. Extremely high values
    run_test("Extremely High Mass", {"m_s": 1e9, "m_u": 1e9})
    run_test("Extremely High Stiffness", {"k_s": 1e12, "k_t": 1e12})
    run_test("Extremely High Damping", {"c": 1e12})
    run_test("Extremely Long Duration", road_dict={"duration": 1000.0, "profile_type": "step"}) # To test performance

    # 2. Extremely low values
    run_test("Extremely Low Mass", {"m_s": 1e-9, "m_u": 1e-9})
    run_test("Extremely Low Stiffness", {"k_s": 1e-9, "k_t": 1e-9})

    # 3. Zero values
    run_test("Zero Sprung Mass", {"m_s": 0.0})
    run_test("Zero Unsprung Mass", {"m_u": 0.0})
    run_test("Zero Gravity / Zero Stiffness", {"k_s": 0.0, "k_t": 0.0})
    run_test("Zero Damping", {"c": 0.0, "c_t": 0.0})

    # 4. Negative values
    run_test("Negative Mass", {"m_s": -100.0})
    run_test("Negative Stiffness", {"k_s": -25000.0})
    run_test("Negative Damping", {"c": -2050.0})

    # 5. NaN / undefined / empty inputs
    run_test("NaN Mass", {"m_s": float('nan')})
    run_test("NaN Stiffness", {"k_s": float('nan')})
    run_test("Empty Road Profile", road_dict={"profile_type": ""})
    
    print("--- Stress Tests Completed ---", flush=True)
