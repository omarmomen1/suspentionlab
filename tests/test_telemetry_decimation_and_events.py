"""
tests/test_telemetry_decimation_and_events.py
=============================================
Tests for peak-preserving telemetry decimation and event detection (Findings 61, 62).
"""

import pytest
import numpy as np

from suspensionlab.physics.telemetry_decimation import (
    decimate_telemetry_trace,
    DecimatedTrace,
    LODLevel,
)


def test_min_max_peak_preservation():
    # Create 10,000 points of synthetic damper velocity telemetry with a single transient spike
    ts = np.linspace(0.0, 10.0, 10000)
    val = 0.05 * np.sin(2.0 * np.pi * 2.0 * ts)
    
    # Inject high-speed bump impact spike at t = 4.52 s
    spike_idx = 4520
    val[spike_idx] = 0.85  # 850 mm/s high-speed damper impact

    # Decimate to 1,000 points
    decimated = decimate_telemetry_trace(
        timestamps=ts,
        values=val,
        channel_name="damper_velocity_fl",
        target_points=1000,
        detect_events=True,
    )

    assert isinstance(decimated, DecimatedTrace)
    assert len(decimated.values) <= 1200
    assert len(decimated.values) >= 500

    # Verify peak is preserved in decimated output
    assert max(decimated.values) >= 0.80


    # Verify event was captured
    assert len(decimated.events_detected) >= 1
    spike_event = decimated.events_detected[0]
    assert spike_event.event_type == "DAMPER_SPIKE"
    assert spike_event.peak_value >= 0.80


def test_multiresolution_lod_profiles():
    ts = np.linspace(0.0, 5.0, 5000)
    val = np.cos(ts)

    # 1. Overview LOD
    overview = decimate_telemetry_trace(ts, val, target_points=1000)
    assert overview.lod_level == "OVERVIEW"

    # 2. Medium LOD
    medium = decimate_telemetry_trace(ts, val, target_points=10000)
    assert medium.lod_level == "RAW"  # Original has only 5000 pts

    dict_repr = overview.to_dict()
    assert "timestamps" in dict_repr
    assert "values" in dict_repr
