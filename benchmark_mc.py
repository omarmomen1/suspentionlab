import time
import numpy as np
from suspensionlab.physics.full_car import FullCarParams, FourCornerRoadProfile
from suspensionlab.physics.monte_carlo import run_monte_carlo_sweep

def run_monte_carlo_benchmark():
    NUM_RUNS = 10000
    print(f"Setting up Monte Carlo Benchmark with {NUM_RUNS} runs...")
    
    # 1. Generate base parameters
    base_params = FullCarParams(
        m_s=1200.0, I_x=300.0, I_y=1200.0, m_uf=40.0, m_ur=40.0,
        k_sf=30000.0, k_sr=35000.0, c_f=3000.0, c_r=3500.0,
        k_arb_f=10000.0, k_arb_r=5000.0, k_tf=250000.0, k_tr=250000.0,
        L=2.6, a=1.2, b=1.4, tw_f=1.6, tw_r=1.6, speed_mps=20.0
    )
    base_array = base_params.to_array()
    
    # Create batch parameter arrays
    params_batch = np.zeros((NUM_RUNS, len(base_array)), dtype=np.float64)
    for i in range(NUM_RUNS):
        params_batch[i] = base_array.copy()
        # Randomize spring and damper rates by +/- 10%
        # Indices: k_sf=5, k_sr=6, c_f=7, c_r=8
        params_batch[i, 5] *= np.random.uniform(0.9, 1.1)
        params_batch[i, 6] *= np.random.uniform(0.9, 1.1)
        params_batch[i, 7] *= np.random.uniform(0.9, 1.1)
        params_batch[i, 8] *= np.random.uniform(0.9, 1.1)

    # 2. Setup track profile (5 seconds, 5000 steps)
    NUM_STEPS = 5000
    t = np.linspace(0, 5, NUM_STEPS)
    z_rfl = 0.05 * np.sin(2 * np.pi * 2 * t)
    z_rfr = 0.05 * np.sin(2 * np.pi * 2 * t + 0.1)
    z_rrl = 0.05 * np.sin(2 * np.pi * 2 * t + 0.2)
    z_rrr = 0.05 * np.sin(2 * np.pi * 2 * t + 0.3)
    
    U = np.column_stack([z_rfl, z_rfr, z_rrl, z_rrr])
    
    # 3. Setup global memory arrays for integration
    G_TIME = np.zeros(NUM_STEPS, dtype=np.float64)
    G_TIME[:] = t
    G_U = np.zeros((NUM_STEPS, 4), dtype=np.float64)
    G_U[:] = U
    
    BATCH_SIZE = 1000
    y0_batch = np.zeros((BATCH_SIZE, 14), dtype=np.float64)
    y_out_batch = np.zeros((BATCH_SIZE, NUM_STEPS, 14), dtype=np.float64)
    
    print("--- 1. Compiling & Warming up Numba Parallel Loop ---")
    t0 = time.perf_counter()
    # Run once to compile
    run_monte_carlo_sweep(y0_batch[:2], t, y_out_batch[:2], G_TIME, G_U, params_batch[:2])
    y_out_batch.fill(0.0)
    t1 = time.perf_counter()
    print(f"Compilation Time: {t1 - t0:.3f} sec")
    
    print("\n--- 2. Executing Monte Carlo Sweep in Batches ---")
    t0 = time.perf_counter()
    
    num_batches = NUM_RUNS // BATCH_SIZE
    for chunk in range(num_batches):
        start_idx = chunk * BATCH_SIZE
        end_idx = start_idx + BATCH_SIZE
        run_monte_carlo_sweep(y0_batch, t, y_out_batch, G_TIME, G_U, params_batch[start_idx:end_idx])
        
    t1 = time.perf_counter()
    
    total_time = t1 - t0
    runs_per_sec = NUM_RUNS / total_time
    
    print(f"\nExecution Complete: {NUM_RUNS} full-car 5s simulations")
    print(f"Total Wall-clock Time: {total_time:.4f} seconds")
    print(f"Throughput: {runs_per_sec:.2f} runs per second!")

if __name__ == "__main__":
    run_monte_carlo_benchmark()
