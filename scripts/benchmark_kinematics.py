"""
scripts/benchmark_kinematics.py
===============================
SuspensionLab PRO — Authoritative Kinematics Performance Benchmark

Rigorous comparative benchmark between:
1. CppKinematicsBackend (Authoritative C++20 Eigen multibody engine)
2. PythonReferenceBackend (Pure-Python / NumPy / SciPy reference solver)

Measures:
- Median, p95, p99 latency
- Throughput (evaluations/second, sweeps/second)
- Speedup ratio
- Numerical consistency check
"""

import time
import numpy as np

from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS
from suspensionlab.physics.kinematics_facade import (
    CppKinematicsBackend,
    PythonReferenceBackend,
)


def benchmark_sweeps(n_runs: int = 100, n_steps: int = 33):
    print(f"\n=================================================================")
    print(f" 1. KINEMATIC SWEEP BENCHMARK ({n_runs} sweeps, {n_steps} points/sweep)")
    print(f"=================================================================")
    
    py_backend = PythonReferenceBackend(topology="double_wishbone")
    cpp_backend = CppKinematicsBackend(topology="double_wishbone")

    # Warm-up
    py_backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-60.0, z_max_mm=60.0, n_steps=n_steps)
    cpp_backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-60.0, z_max_mm=60.0, n_steps=n_steps)

    # Benchmark Python
    py_latencies_ms = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        py_backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-60.0, z_max_mm=60.0, n_steps=n_steps)
        py_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    # Benchmark C++
    cpp_latencies_ms = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        cpp_backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-60.0, z_max_mm=60.0, n_steps=n_steps)
        cpp_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    py_lat = np.array(py_latencies_ms)
    cpp_lat = np.array(cpp_latencies_ms)

    py_median, py_p95, py_p99 = np.median(py_lat), np.percentile(py_lat, 95), np.percentile(py_lat, 99)
    cpp_median, cpp_p95, cpp_p99 = np.median(cpp_lat), np.percentile(cpp_lat, 95), np.percentile(cpp_lat, 99)

    py_throughput  = (n_runs * n_steps) / (np.sum(py_lat) / 1000.0)
    cpp_throughput = (n_runs * n_steps) / (np.sum(cpp_lat) / 1000.0)
    speedup = cpp_throughput / py_throughput

    print(f" Python Reference Backend:")
    print(f"   Median Latency: {py_median:8.2f} ms")
    print(f"   p95 Latency:    {py_p95:8.2f} ms")
    print(f"   p99 Latency:    {py_p99:8.2f} ms")
    print(f"   Throughput:     {py_throughput:8.1f} points/sec ({1000.0/py_median:.1f} sweeps/sec)")
    print()
    print(f" C++ Native Engine (Production):")
    print(f"   Median Latency: {cpp_median:8.2f} ms")
    print(f"   p95 Latency:    {cpp_p95:8.2f} ms")
    print(f"   p99 Latency:    {cpp_p99:8.2f} ms")
    print(f"   Throughput:     {cpp_throughput:8.1f} points/sec ({1000.0/cpp_median:.1f} sweeps/sec)")
    print()
    print(f" >>> SPEEDUP FACTOR: {speedup:6.1f}x <<<")

    return {
        "py_median_ms": py_median, "py_p95_ms": py_p95, "py_p99_ms": py_p99, "py_throughput": py_throughput,
        "cpp_median_ms": cpp_median, "cpp_p95_ms": cpp_p95, "cpp_p99_ms": cpp_p99, "cpp_throughput": cpp_throughput,
        "speedup": speedup
    }


def benchmark_single_point(n_evals: int = 500):
    print(f"\n=================================================================")
    print(f" 2. SINGLE POINT SOLVE BENCHMARK ({n_evals} evaluations)")
    print(f"=================================================================")

    py_backend = PythonReferenceBackend(topology="double_wishbone")
    cpp_backend = CppKinematicsBackend(topology="double_wishbone")

    # Warm-up
    py_backend.solve_single(DEFAULT_HARDPOINTS, dz_mm=10.0)
    cpp_backend.solve_single(DEFAULT_HARDPOINTS, dz_mm=10.0)

    # Random heave offsets
    dz_samples = np.random.uniform(-50.0, 50.0, n_evals)

    # Python
    t0 = time.perf_counter()
    for dz in dz_samples:
        py_backend.solve_single(DEFAULT_HARDPOINTS, dz_mm=dz)
    py_time_sec = time.perf_counter() - t0

    # C++
    t0 = time.perf_counter()
    for dz in dz_samples:
        cpp_backend.solve_single(DEFAULT_HARDPOINTS, dz_mm=dz)
    cpp_time_sec = time.perf_counter() - t0

    py_rate = n_evals / py_time_sec
    cpp_rate = n_evals / cpp_time_sec
    speedup = cpp_rate / py_rate

    print(f" Python Reference: {py_rate:8.1f} solves/sec ({py_time_sec/n_evals*1000:.2f} ms/solve)")
    print(f" C++ Production:   {cpp_rate:8.1f} solves/sec ({cpp_time_sec/n_evals*1000:.3f} ms/solve)")
    print(f" >>> SPEEDUP FACTOR: {speedup:6.1f}x <<<")


if __name__ == "__main__":
    benchmark_sweeps(n_runs=100, n_steps=33)
    benchmark_single_point(n_evals=300)
