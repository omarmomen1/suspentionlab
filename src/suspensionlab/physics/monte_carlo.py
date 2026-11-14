import os
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from scipy.integrate import solve_ivp

from suspensionlab.physics.full_car import _full_car_ode_wrapper

def _worker(y0, t_span, t_eval, G_TIME, G_U, params):
    try:
        sol = solve_ivp(
            fun=_full_car_ode_wrapper,
            t_span=t_span,
            y0=y0,
            t_eval=t_eval,
            method='BDF',
            args=(G_TIME, G_U, params),
            rtol=1e-5,
            atol=1e-7
        )
        if sol.success:
            return sol.y.T, True
        else:
            return np.full((len(t_eval), len(y0)), np.nan), False
    except Exception:
        return np.full((len(t_eval), len(y0)), np.nan), False

def run_monte_carlo_sweep(
    y0_batch: np.ndarray, 
    t_eval: np.ndarray, 
    y_out_batch: np.ndarray, 
    G_TIME: np.ndarray, 
    G_U: np.ndarray, 
    params_batch: np.ndarray
) -> int:
    """
    Executes multiple simulations in parallel using ProcessPoolExecutor.
    y0_batch: shape (num_runs, num_states)
    t_eval: shape (num_steps,)
    y_out_batch: shape (num_runs, num_steps, num_states)
    params_batch: shape (num_runs, num_params)

    Returns
    -------
    failed_runs_count : int
        Number of runs that failed to converge.
    """
    num_runs = params_batch.shape[0]
    if y_out_batch.shape[0] < num_runs:
        num_runs = y_out_batch.shape[0]
    if y0_batch.shape[0] < num_runs:
        num_runs = y0_batch.shape[0]
        
    t_span = (t_eval[0], t_eval[-1])
    
    max_workers = max(1, (os.cpu_count() or 4) // 2)
    # Use ProcessPoolExecutor to parallelize Python solve_ivp without GIL blocking
    failed_runs_count = 0
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i in range(num_runs):
            futures.append(executor.submit(_worker, y0_batch[i], t_span, t_eval, G_TIME, G_U, params_batch[i]))
            
        for i, future in enumerate(futures):
            res, success = future.result()
            if not success:
                failed_runs_count += 1
            y_out_batch[i] = res
    return failed_runs_count
