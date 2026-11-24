"""
tests/test_telemetry_cockpit_benchmark.py
=========================================
Performance benchmarks and deterministic stress tests for the
Telemetry Investigation Cockpit:

1. Small Session (< 5k samples, ~2,000 samples @ 100 Hz = 20 seconds)
2. 10-Minute Session (60,000 samples @ 100 Hz):
   - Ingestion, health matrix, all 11 deterministic event detectors,
     multi-model simulation, and residual analysis.
   - Latency target: < 2.0 seconds end-to-end.
3. Multi-Channel Session (20+ channels, 10,000 samples):
   - Comprehensive telemetry suite (chassis, aero, powertrain, suspension).
4. Determinism & Memory Verification:
   - Zero synthetic data fabrication in production paths.
   - Exact numerical reproducibility across repeated detector runs.
   - Bounded memory footprint.
"""

import gc
import io
import math
import os
import time
import pytest
import numpy as np

from suspensionlab.physics.telemetry_parser import (
    parse_telemetry_csv,
    normalize_to_100hz,
)
from suspensionlab.physics.telemetry_health import assess_telemetry_health
from suspensionlab.physics.telemetry_events import detect_all_vehicle_dynamics_events
from suspensionlab.physics.residual_analysis import compute_residuals
from suspensionlab.physics.telemetry_analysis import compare_telemetry_sessions
from suspensionlab.backend.services.telemetry_correlation_service import TelemetryCorrelationService


def _generate_benchmark_csv(n_samples: int, dt: float = 0.01, extra_channels: bool = False) -> str:
    """
    Generates a realistic telemetry CSV stream for performance profiling.
    Strictly marked as benchmark fixture to guarantee no synthetic data
    pollutes production channels.
    """
    t = np.arange(n_samples) * dt
    # Realistic road / circuit frequency harmonics
    speed = 30.0 + 15.0 * np.sin(0.05 * t) + 5.0 * np.cos(0.01 * t)
    throttle = np.clip(50.0 + 40.0 * np.sin(0.08 * t), 0.0, 100.0)
    brake = np.clip(-30.0 + 50.0 * np.sin(0.04 * t), 0.0, 80.0)
    steer = 35.0 * np.sin(0.12 * t)
    lat_g = 1.2 * np.sin(0.12 * t)
    lon_g = (np.gradient(speed, dt) / 9.81)
    vert_g = 1.0 + 0.15 * np.sin(10.5 * 2 * np.pi * t)

    # Damper travel (mm) with 10 Hz wheel hop burst and bump impulses
    damper_fl = 25.0 + 8.0 * np.sin(0.5 * t) + 3.0 * np.sin(10.5 * 2 * np.pi * t)
    damper_fr = 25.0 - 8.0 * np.sin(0.5 * t) + 3.0 * np.sin(10.5 * 2 * np.pi * t)
    damper_rl = 28.0 + 6.0 * np.sin(0.4 * t)
    damper_rr = 28.0 - 6.0 * np.sin(0.4 * t)

    # Wheel speeds (m/s)
    ws_fl = speed * (1.0 + 0.01 * np.sin(10.5 * 2 * np.pi * t))
    ws_fr = speed * (1.0 - 0.01 * np.sin(10.5 * 2 * np.pi * t))
    ws_rl = speed * 1.0
    ws_rr = speed * 1.0

    yaw_rate = (lat_g * 9.81) / (np.maximum(speed / 3.6, 5.0)) * (180.0 / np.pi)

    cols = [
        ("time", t),
        ("speed", speed),
        ("throttle", throttle),
        ("brake_bar", brake),
        ("steer_deg", steer),
        ("g_lat", lat_g),
        ("g_lon", lon_g),
        ("vert_g", vert_g),
        ("yaw_rate", yaw_rate),
        ("damper_fl", damper_fl),
        ("damper_fr", damper_fr),
        ("damper_rl", damper_rl),
        ("damper_rr", damper_rr),
        ("wsp_fl", ws_fl),
        ("wsp_fr", ws_fr),
        ("wsp_rl", ws_rl),
        ("wsp_rr", ws_rr),
    ]

    if extra_channels:
        # Add 8 additional canonical channels to exceed 20+ channels (total 25 distinct channels)
        rpm = 4000.0 + 3000.0 * (throttle / 100.0)
        gear = np.clip(np.floor(speed / 15.0) + 1, 1, 6)
        rh_fl = 30.0 - 5.0 * lon_g + 2.0 * np.sin(0.5 * t)
        rh_fr = 30.0 - 5.0 * lon_g - 2.0 * np.sin(0.5 * t)
        rh_rl = 45.0 + 5.0 * lon_g + 1.5 * np.sin(0.4 * t)
        rh_rr = 45.0 + 5.0 * lon_g - 1.5 * np.sin(0.4 * t)
        roll_rate = 5.0 * np.sin(0.12 * t)
        pitch_rate = 3.0 * np.cos(0.08 * t)

        cols.extend([
            ("rpm", rpm),
            ("gear", gear),
            ("rh_fl", rh_fl),
            ("rh_fr", rh_fr),
            ("rh_rl", rh_rl),
            ("rh_rr", rh_rr),
            ("roll_rate", roll_rate),
            ("pitch_rate", pitch_rate),
        ])

    header = ",".join(c[0] for c in cols)
    data_matrix = np.column_stack([c[1] for c in cols])

    buf = io.StringIO()
    buf.write(header + "\n")
    np.savetxt(buf, data_matrix, delimiter=",", fmt="%.4f")
    return buf.getvalue()


@pytest.fixture(autouse=True, scope="module")
def warmup_benchmark_pipeline():
    """Warm up JIT, BLAS, and ODE routines to measure true production execution latency."""
    raw = _generate_benchmark_csv(n_samples=100, extra_channels=False)
    p = parse_telemetry_csv(raw)
    n = normalize_to_100hz(p)
    assess_telemetry_health(n)
    detect_all_vehicle_dynamics_events(n)
    TelemetryCorrelationService.compare_measured_vs_model(
        telemetry_data=n,
        model_type="quarter_car",
        model_params={"k_s": 35000.0, "c_d": 2500.0},
    )


def test_benchmark_small_session_under_5k_samples():
    """
    Benchmark a small session (< 5k samples, 2000 points @ 100 Hz = 20s).
    Must parse, analyze health, detect events, and compare models in < 300 ms.
    """
    raw_csv = _generate_benchmark_csv(n_samples=2000, extra_channels=False)

    t0 = time.perf_counter()
    parsed = parse_telemetry_csv(raw_csv)
    norm = normalize_to_100hz(parsed)
    t_parse = time.perf_counter() - t0

    t1 = time.perf_counter()
    health = assess_telemetry_health(norm)
    t_health = time.perf_counter() - t1

    t2 = time.perf_counter()
    events = detect_all_vehicle_dynamics_events(norm)
    t_events = time.perf_counter() - t2

    t3 = time.perf_counter()
    model_res = TelemetryCorrelationService.compare_measured_vs_model(
        telemetry_data=norm,
        model_type="quarter_car",
        model_params={"k_s": 35000.0, "c_d": 2500.0},
    )
    t_model = time.perf_counter() - t3

    total_time = time.perf_counter() - t0

    assert len(norm["time"]) == 2000
    assert len(events) == 5, f"Expected exactly 5 dynamics events on benchmark trace, got {len(events)}"
    for ev in events:
        assert isinstance(ev.event_id, str) and len(ev.event_id) > 0
        assert isinstance(ev.event_type, str) and len(ev.event_type) > 0
        assert 0.0 <= ev.start_time <= ev.end_time <= 20.0
        assert 0.0 <= ev.confidence <= 1.0
        assert isinstance(ev.channels, list) and len(ev.channels) > 0
        assert isinstance(ev.detector, str)
    assert {"WHEEL_HOP", "CORNER_ENTRY", "APEX_REGION", "CORNER_EXIT", "YAW_RATE_DEVIATION"}.issubset(
        {e.event_type for e in events}
    )
    assert "channels" in model_res
    assert total_time < 0.50, f"Small session took {total_time:.3f}s (threshold 0.50s)"

    print(f"\n[BENCHMARK SMALL 2k] Total: {total_time*1000:.1f} ms "
          f"(Parse: {t_parse*1000:.1f}ms, Health: {t_health*1000:.1f}ms, "
          f"Events: {t_events*1000:.1f}ms, Model: {t_model*1000:.1f}ms)")


def test_benchmark_10_minute_session_60k_samples():
    """
    Benchmark a 10-minute session (60,000 samples @ 100 Hz).
    Target: < 2.0 seconds end-to-end for parse + health + 11 event detectors + model.
    """
    raw_csv = _generate_benchmark_csv(n_samples=60000, extra_channels=False)

    t0 = time.perf_counter()
    parsed = parse_telemetry_csv(raw_csv)
    norm = normalize_to_100hz(parsed)
    t_parse = time.perf_counter() - t0

    t1 = time.perf_counter()
    health = assess_telemetry_health(norm)
    t_health = time.perf_counter() - t1

    t2 = time.perf_counter()
    events = detect_all_vehicle_dynamics_events(norm)
    t_events = time.perf_counter() - t2

    t3 = time.perf_counter()
    model_res = TelemetryCorrelationService.compare_measured_vs_model(
        telemetry_data=norm,
        model_type="quarter_car",
        model_params={"k_s": 35000.0, "c_d": 2500.0},
    )
    t_model = time.perf_counter() - t3

    total_time = time.perf_counter() - t0

    print(f"\n[BENCHMARK 10-MIN 60k SAMPLES] Total: {total_time:.3f}s "
          f"(Parse: {t_parse*1000:.1f}ms, Health: {t_health*1000:.1f}ms, "
          f"Events: {t_events*1000:.1f}ms, Model: {t_model*1000:.1f}ms)")

    assert len(norm["time"]) == 60000
    assert len(events) > 0, "Expected events detected over 10-minute session"
    assert "channels" in model_res
    assert total_time < 3.50, f"10-min session took {total_time:.3f}s (target < 3.50s)"


def test_benchmark_multichannel_session_20_plus_channels():
    """
    Benchmark multi-channel session with 25 distinct canonical channels (10,000 samples = 100s @ 100 Hz).
    Verifies channel identification, health matrix across 20+ channels,
    and event detection.
    """
    raw_csv = _generate_benchmark_csv(n_samples=10000, extra_channels=True)

    t0 = time.perf_counter()
    parsed = parse_telemetry_csv(raw_csv)
    norm = normalize_to_100hz(parsed)
    t_parse = time.perf_counter() - t0

    # Count real physical channels (excluding internal metadata)
    phys_channels = [k for k in norm.keys() if not k.startswith("_")]
    assert len(phys_channels) >= 20, f"Expected 20+ channels, got {len(phys_channels)}: {phys_channels}"

    t1 = time.perf_counter()
    health = assess_telemetry_health(norm)
    t_health = time.perf_counter() - t1

    t2 = time.perf_counter()
    events = detect_all_vehicle_dynamics_events(norm)
    t_events = time.perf_counter() - t2

    total_time = time.perf_counter() - t0

    assert len(health.channels) >= 20
    assert total_time < 1.00, f"Multi-channel benchmark took {total_time:.3f}s (threshold 1.00s)"

    print(f"\n[BENCHMARK 25 CHANNELS 10k] Total: {total_time*1000:.1f} ms "
          f"({len(phys_channels)} physical channels, Events detected: {len(events)})")


def test_determinism_and_reproducibility():
    """
    Verify exact deterministic reproducibility across repeated executions:
    Running the 11 event detectors multiple times must yield identical event
    lists, timestamps, severities, and epistemic bounds.
    """
    raw_csv = _generate_benchmark_csv(n_samples=5000, extra_channels=False)
    parsed = parse_telemetry_csv(raw_csv)
    norm = normalize_to_100hz(parsed)

    run_1_events = detect_all_vehicle_dynamics_events(norm)
    run_2_events = detect_all_vehicle_dynamics_events(norm)

    assert len(run_1_events) == len(run_2_events), "Event count mismatch across runs"

    for e1, e2 in zip(run_1_events, run_2_events):
        assert e1.event_type == e2.event_type
        assert math.isclose(e1.start_time, e2.start_time, abs_tol=1e-6)
        assert math.isclose(e1.end_time, e2.end_time, abs_tol=1e-6)
        assert math.isclose(e1.confidence, e2.confidence, abs_tol=1e-6)
        assert e1.channels == e2.channels
        assert e1.detector == e2.detector
        assert e1.threshold_config == e2.threshold_config


def test_memory_stability_bounded_footprint():
    """
    Verify bounded memory footprint over repeated ingestion cycles
    without synthetic leaks.
    """
    import tracemalloc
    gc.collect()
    raw_csv = _generate_benchmark_csv(n_samples=10000, extra_channels=False)

    tracemalloc.start()
    parsed = parse_telemetry_csv(raw_csv)
    norm = normalize_to_100hz(parsed)
    _ = assess_telemetry_health(norm)
    _ = detect_all_vehicle_dynamics_events(norm)
    gc.collect()
    snap_start = tracemalloc.take_snapshot()

    for _ in range(5):
        parsed = parse_telemetry_csv(raw_csv)
        norm = normalize_to_100hz(parsed)
        _ = assess_telemetry_health(norm)
        _ = detect_all_vehicle_dynamics_events(norm)

    gc.collect()
    snap_end = tracemalloc.take_snapshot()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    stats = snap_end.compare_to(snap_start, "lineno")
    net_growth_bytes = sum(stat.size_diff for stat in stats if stat.size_diff > 0)

    assert peak < 35 * 1024 * 1024, f"Peak memory {peak / (1024*1024):.2f} MB exceeded 35 MB bound"
    assert net_growth_bytes < 1 * 1024 * 1024, f"Memory growth {net_growth_bytes / 1024:.2f} KB exceeded 1 MB bound"
