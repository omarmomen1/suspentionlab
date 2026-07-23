import time
import numpy as np
from suspensionlab.physics.magic_formula import TireCoeffs, calc_tire_forces, calc_tire_forces_vectorized, _calc_tire_forces_fast

def run_benchmark():
    N = 100000
    Fz_arr = np.random.uniform(2000, 6000, N)
    alpha_arr = np.random.uniform(-0.1, 0.1, N)
    kappa_arr = np.random.uniform(-0.1, 0.1, N)
    camber_arr = np.zeros(N)
    
    coeffs = TireCoeffs()
    coeffs_arr = coeffs.to_array()
    
    # 1. Warmup Numba JIT
    print("Warming up JIT...")
    _calc_tire_forces_fast(4000.0, 0.05, 0.05, 0.0, coeffs_arr)
    
    out_Fx = np.zeros(N)
    out_Fy = np.zeros(N)
    calc_tire_forces_vectorized(Fz_arr, alpha_arr, kappa_arr, camber_arr, coeffs_arr, out_Fx, out_Fy)
    
    # 2. Benchmark Vectorized Numba
    print(f"Benchmarking {N} vectorized calls...")
    t0 = time.perf_counter()
    calc_tire_forces_vectorized(Fz_arr, alpha_arr, kappa_arr, camber_arr, coeffs_arr, out_Fx, out_Fy)
    t1 = time.perf_counter()
    t_numba_vec = t1 - t0
    
    # 3. Benchmark Naive Python Wrapper (simulating old behavior)
    print(f"Benchmarking {N} scalar wrapper calls...")
    t0 = time.perf_counter()
    for i in range(N):
        calc_tire_forces(Fz_arr[i], alpha_arr[i], kappa_arr[i], camber_arr[i], coeffs)
    t1 = time.perf_counter()
    t_scalar_wrapper = t1 - t0
    
    print(f"Vectorized Numba Time: {t_numba_vec:.5f} sec ({t_numba_vec/N*1e9:.2f} ns/call)")
    print(f"Scalar Wrapper Time:   {t_scalar_wrapper:.5f} sec ({t_scalar_wrapper/N*1e9:.2f} ns/call)")
    print(f"Speedup Factor:        {t_scalar_wrapper / t_numba_vec:.2f}x")
    
    import numba
    print("Type Disassembly for _calc_tire_forces_fast:")
    for sig, impl in _calc_tire_forces_fast.overloads.items():
        print(sig)
        
if __name__ == "__main__":
    run_benchmark()
