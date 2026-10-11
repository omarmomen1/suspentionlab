import math
import time
import numpy as np

from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    PacejkaMF52TireModel,
    calc_tire_forces,
    calc_tire_forces_vectorized,
    _calc_tire_forces_fast,
    _calc_tire_forces_and_moments_fast,
)
from suspensionlab.physics.tire_model import (
    TireLUTModel,
    TireRelaxationDynamics,
    TireDefinition,
)
from suspensionlab.physics.tire_thermal import (
    TireThermalConfig,
    MultiLayerTireThermalState,
    SingleTireThermalState,
)
from suspensionlab.physics.tire_fitting import (
    TireDataset,
    TireModelFitter,
)


def run_benchmark():
    print("=" * 70)
    print(" SUSPENSIONLAB PRO — TIRE SUBSYSTEM COMPREHENSIVE BENCHMARK SUITE")
    print("=" * 70)

    N = 100000
    rng = np.random.default_rng(42)
    Fz_arr = rng.uniform(2000, 6000, N)
    alpha_arr = rng.uniform(-0.1, 0.1, N)
    kappa_arr = rng.uniform(-0.1, 0.1, N)
    camber_arr = np.zeros(N)

    coeffs = TireCoeffs()
    coeffs_arr = coeffs.to_array()
    model = PacejkaMF52TireModel(coeffs=coeffs)

    # 1. Warmup Numba JIT
    print("\n[1/6] Warming up Numba JIT kernels...")
    _calc_tire_forces_fast(4000.0, 0.05, 0.05, 0.0, coeffs_arr)
    _calc_tire_forces_and_moments_fast(4000.0, 0.05, 0.05, 0.0, coeffs_arr)

    out_Fx = np.zeros(N)
    out_Fy = np.zeros(N)
    calc_tire_forces_vectorized(Fz_arr, alpha_arr, kappa_arr, camber_arr, coeffs_arr, out_Fx, out_Fy)

    # 2. Benchmark Vectorized Numba
    print(f"\n[2/6] Benchmarking {N} vectorized MF5.2 force evaluations...")
    t0 = time.perf_counter()
    calc_tire_forces_vectorized(Fz_arr, alpha_arr, kappa_arr, camber_arr, coeffs_arr, out_Fx, out_Fy)
    t1 = time.perf_counter()
    t_numba_vec = t1 - t0
    ns_vec = (t_numba_vec / N) * 1e9
    print(f"  -> Vectorized Numba Time: {t_numba_vec:.5f} s ({ns_vec:.2f} ns/call)")

    # 3. Benchmark Canonical Object Interface
    N_obj = 10000
    print(f"\n[3/6] Benchmarking {N_obj} canonical TireModel.evaluate() calls...")
    t0 = time.perf_counter()
    for i in range(N_obj):
        model.evaluate(Fz=Fz_arr[i], alpha=alpha_arr[i], kappa=kappa_arr[i], camber=0.0)
    t1 = time.perf_counter()
    t_obj = t1 - t0
    ns_obj = (t_obj / N_obj) * 1e9
    print(f"  -> Canonical evaluate() Time: {t_obj:.5f} s ({ns_obj:.2f} ns/call)")

    # 4. Benchmark Multi-Axis LUT Model
    print(f"\n[4/6] Benchmarking Multi-Axis TireLUTModel ({N_obj} evaluations)...")
    Fz_g = np.array([2000.0, 4000.0, 6000.0])
    al_g = np.linspace(-0.20, 0.20, 11)
    ka_g = np.linspace(-0.20, 0.20, 11)
    Fx_tab = np.ones((3, 11, 11)) * 3000.0
    Fy_tab = np.ones((3, 11, 11)) * 2500.0
    lut_model = TireLUTModel(Fz_g, al_g, ka_g, Fx_tab, Fy_tab)

    t0 = time.perf_counter()
    for i in range(N_obj):
        lut_model.evaluate(Fz=Fz_arr[i], alpha=alpha_arr[i], kappa=kappa_arr[i])
    t1 = time.perf_counter()
    t_lut = t1 - t0
    ns_lut = (t_lut / N_obj) * 1e9
    print(f"  -> TireLUTModel evaluate() Time: {t_lut:.5f} s ({ns_lut:.2f} ns/call)")

    # 5. Benchmark Thermal and Relaxation Stepping
    print(f"\n[5/6] Benchmarking Thermal and Relaxation Step Dynamics ({N_obj} steps)...")
    th_cfg = TireThermalConfig()
    th_state = SingleTireThermalState()
    relax = TireRelaxationDynamics()

    t0 = time.perf_counter()
    for i in range(N_obj):
        th_state = th_state.step(th_cfg, Fz=4000.0, Fx=500.0, Fy=2000.0, v_slip_x=0.0, v_slip_y=1.0, v_vehicle=30.0, dt=0.01)
        relax.step_time(Fx_eq=500.0, Fy_eq=2000.0, v_x=30.0, dt=0.01)
    t1 = time.perf_counter()
    t_dyn = t1 - t0
    ns_dyn = (t_dyn / N_obj) * 1e9
    print(f"  -> Coupled Dynamics Time: {t_dyn:.5f} s ({ns_dyn:.2f} ns/step)")

    # 6. Benchmark Parameter Fitting Pipeline
    print("\n[6/6] Benchmarking Tire Parameter Fitting Pipeline Optimization Time...")
    synth_dataset = TireDataset.generate_synthetic(coeffs=coeffs, n_samples=600, noise_std=5.0, seed=42)
    fitter = TireModelFitter()

    t0 = time.perf_counter()
    fitted_model, residuals = fitter.fit(synth_dataset, val_fraction=0.20, seed=42)
    t1 = time.perf_counter()
    t_fit = t1 - t0

    print(f"  -> Multi-Stage Optimization Time: {t_fit:.3f} s")
    print(f"  -> Fitted R2 (Fx): {residuals.r2_Fx:.4f}, (Fy): {residuals.r2_Fy:.4f}, (Mz): {residuals.r2_Mz:.4f}")
    print(f"  -> Fitted RMSE (Fx): {residuals.rmse_Fx:.2f} N, (Fy): {residuals.rmse_Fy:.2f} N, (Mz): {residuals.rmse_Mz:.2f} N·m")
    print(f"  -> Holdout Validation R2: {residuals.holdout_r2:.4f}")
    print(f"  -> Confidence Score: {residuals.confidence_score:.3f}")

    print("\n" + "=" * 70)
    print(" BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()

