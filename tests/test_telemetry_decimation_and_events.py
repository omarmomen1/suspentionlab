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


@pytest.mark.asyncio
async def test_decimate_route_requires_authentication():
    """Unauthenticated requests to POST /api/v1/telemetry/decimate must be rejected with 401."""
    from httpx import AsyncClient, ASGITransport
    from suspensionlab.backend.api.main import app

    payload = {
        "timestamps": [0.0, 0.01, 0.02, 0.03, 0.04],
        "values": [1.0, 2.0, 3.0, 4.0, 5.0],
        "channel_name": "damper_velocity_fl",
        "target_points": 100,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/telemetry/decimate", json=payload)
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_decimate_route_authenticated_success_and_max_array_length(authenticated_client):
    """Authenticated requests succeed within bounds and reject oversized arrays with 422."""
    from pydantic import ValidationError
    from suspensionlab.backend.api.routes.telemetry_routes import DecimateRequest, MAX_DECIMATE_POINTS

    # Direct schema validation for oversized timestamps / values
    oversized = [0.0] * (MAX_DECIMATE_POINTS + 1)
    valid = [0.0] * 10
    with pytest.raises(ValidationError):
        DecimateRequest(timestamps=oversized, values=valid)
    with pytest.raises(ValidationError):
        DecimateRequest(timestamps=valid, values=oversized)

    # Valid authenticated HTTP call
    ok_payload = {
        "timestamps": [float(i) * 0.01 for i in range(50)],
        "values": [0.1 * i for i in range(50)],
        "channel_name": "damper_velocity_fl",
        "target_points": 20,
    }
    res_ok = await authenticated_client.post("/api/v1/telemetry/decimate", json=ok_payload)
    assert res_ok.status_code == 200
    body = res_ok.json()
    assert body["channel_name"] == "damper_velocity_fl"
    assert body["original_points"] == 50

    # Oversized array HTTP call -> 422 Validation Error
    bad_payload = {
        "timestamps": [0.0] * (MAX_DECIMATE_POINTS + 1),
        "values": [0.0] * 10,
        "channel_name": "damper_velocity_fl",
        "target_points": 100,
    }
    res_bad = await authenticated_client.post("/api/v1/telemetry/decimate", json=bad_payload)
    assert res_bad.status_code == 422
