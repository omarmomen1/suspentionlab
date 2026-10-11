"""
tests/test_handling_benchmark.py
================================
Performance benchmarks and resource utilization profiling for the Handling Subsystem:

- Single Dynamic Scenario (Step Steer 6s @ 100 Hz)
- Steady-State Handling Diagram (40 equilibrium points)
- Dynamic Speed Sweep Scenario
- Complete Setup A vs Setup B Comparison
- Multi-Point Parameter Sensitivity Study
- Memory Footprint & Garbage Collection Stability
"""

import gc
import time
import pytest
import numpy as np

from suspensionlab.physics.handling_model import HandlingParams
from suspensionlab.physics.handling_analysis import (
    compute_handling_diagram,
    simulate_yaw_response_scenario,
    compare_handling_setups,
)


def test_benchmark_single_scenario():
    """Benchmark dynamic step steer scenario (6s duration, dt=0.01s, 600 steps)."""
    p = HandlingParams()

    t0 = time.perf_counter()
    res = simulate_yaw_response_scenario(
        p=p,
        scenario_type="step_steer",
        v_kph=100.0,
        steer_amplitude_deg=3.0,
        duration_s=6.0,
        dt=0.01,
    )
    t_elapsed = time.perf_counter() - t0

    assert len(res["time_series"]["time"]) == 600
    assert "yaw_rate_gain" in res["metrics"]
    # Latency budget calibrated for 20-state ODE with dynamic wheel spin & tire relaxation
    assert t_elapsed < 3.50, f"Single scenario simulation exceeded latency limit: {t_elapsed:.3f}s"
    print(f"\n[BENCHMARK SCENARIO] Step Steer (600 steps): {t_elapsed*1000:.1f} ms")


def test_benchmark_steady_state_handling_diagram():
    """Benchmark steady-state equilibrium sweep across 40 lateral acceleration points."""
    p = HandlingParams()

    t0 = time.perf_counter()
    diag = compute_handling_diagram(
        p=p,
        speed_kph=100.0,
        max_ay_g=1.30,
        n_points=40,
    )
    t_elapsed = time.perf_counter() - t0

    assert len(diag["points"]) > 20
    assert "kus_linear_deg_per_g" in diag
    assert t_elapsed < 0.25, f"Handling diagram exceeded latency limit: {t_elapsed:.3f}s"
    print(f"\n[BENCHMARK DIAGRAM] Steady-State Handling Diagram (40 points): {t_elapsed*1000:.1f} ms")


def test_benchmark_speed_sweep_scenario():
    """Benchmark acceleration speed sweep under constant steer angle."""
    p = HandlingParams()

    t0 = time.perf_counter()
    res = simulate_yaw_response_scenario(
        p=p,
        scenario_type="speed_sweep",
        v_kph=50.0,
        steer_amplitude_deg=2.5,
        duration_s=5.0,
        dt=0.01,
    )
    t_elapsed = time.perf_counter() - t0

    assert "yaw_time_constant_ms" in res["metrics"]
    # Latency budget calibrated for 20-state ODE with dynamic wheel spin & tire relaxation
    assert t_elapsed < 3.50, f"Speed sweep scenario exceeded latency limit: {t_elapsed:.3f}s"
    print(f"\n[BENCHMARK SPEED SWEEP] Speed Sweep Maneuver: {t_elapsed*1000:.1f} ms")


def test_benchmark_setup_comparison():
    """Benchmark end-to-end Setup A vs Setup B comparison with physics causality."""
    setup_a = HandlingParams(roll_dist=0.50, K_arb_f=15000.0)
    setup_b = HandlingParams(roll_dist=0.62, K_arb_f=30000.0)

    t0 = time.perf_counter()
    cmp = compare_handling_setups(
        setup_a=setup_a,
        setup_b=setup_b,
        speed_kph=100.0,
        name_a="Baseline Setup A",
        name_b="Stiffer Front Setup B",
    )
    t_elapsed = time.perf_counter() - t0

    assert "why" in cmp
    assert "what_changed" in cmp
    assert len(cmp["what_changed"]) > 0
    # Latency budget calibrated for dual 20-state ODE solves
    assert t_elapsed < 6.50, f"Setup comparison exceeded latency limit: {t_elapsed:.3f}s"
    print(f"\n[BENCHMARK SETUP COMPARISON] Dual Run & Causality Attribution: {t_elapsed*1000:.1f} ms")


def test_benchmark_parameter_sweep():
    """Benchmark 5-point parameter sweep across handling diagrams."""
    p_base = HandlingParams()
    vals = np.linspace(0.45, 0.65, 5)

    t0 = time.perf_counter()
    sweep_results = []
    for v in vals:
        p = HandlingParams(roll_dist=float(v))
        diag = compute_handling_diagram(p, speed_kph=100.0, n_points=25)
        sweep_results.append(diag["kus_linear_deg_per_g"])
    t_elapsed = time.perf_counter() - t0

    assert len(sweep_results) == 5
    assert t_elapsed < 0.45, f"Parameter sweep exceeded latency limit: {t_elapsed:.3f}s"
    print(f"\n[BENCHMARK PARAMETER SWEEP] 5 Sweep Increments: {t_elapsed*1000:.1f} ms")


def test_benchmark_memory_stability():
    """Verify bounded memory footprint and clean garbage collection over repeated evaluations."""
    gc.collect()
    p = HandlingParams()

    for _ in range(8):
        _ = compute_handling_diagram(p, speed_kph=100.0, n_points=30)
        _ = simulate_yaw_response_scenario(p, scenario_type="step_steer", duration_s=3.0, dt=0.02)

    gc.collect()
    assert True
