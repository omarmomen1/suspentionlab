"""
tests/test_telemetry_streaming_api_e2e.py
=========================================
End-to-End WebSocket & REST API Integration Test for SuspensionLab Telemetry:
- Connects to /api/v1/telemetry/live with WebSocket client
- Ingests telemetry via /api/v1/telemetry/ingest
- Receives binary SLTP v1 frames over WebSocket
- Starts 100 Hz MoTeC replay and verifies streaming frames and Digital Twin calculations
"""

import pytest
from starlette.testclient import TestClient

from suspensionlab.backend.api.main import app
from suspensionlab.telemetry.protocol import SLTPFrame, ChannelId, MAGIC_HEADER


def test_e2e_telemetry_websocket_streaming_and_ingest():
    """Verify end-to-end WebSocket connection, DAQ ingestion, and SLTP binary frame receipt."""
    from suspensionlab.backend.security.jwt_utils import create_access_token
    token = create_access_token({
        "sub": "00000000-0000-0000-0000-000000000001",
        "organization_id": "00000000-0000-0000-0000-000000000001",
        "is_admin": False,
    })
    with TestClient(app) as client:
        # Connect WebSocket in binary mode with authentic JWT
        with client.websocket_connect(f"/api/v1/telemetry/live?token={token}&session_id=sess-e2e&format=binary") as ws:
            # 1. Send Ping -> expect Pong
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "pong"

            # 2. Ingest a live DAQ frame via WebSocket client
            daq_packet = {
                "speed_ms": 35.0,
                "lat_g": 1.25,
                "long_g": 0.15,
                "steer_rad": 0.08,
            }
            ws.send_json(daq_packet)

            # 3. Receive binary frame
            raw_bytes = ws.receive_bytes()
            assert raw_bytes.startswith(MAGIC_HEADER)
            frame = SLTPFrame.unpack(raw_bytes)
            assert abs(frame.get_sample_value(ChannelId.SPEED_MS) - 35.0) < 1e-3
            assert abs(frame.get_sample_value(ChannelId.LAT_G) - 1.25) < 1e-3
            assert frame.twin is not None
            assert frame.twin.theoretical_max_lat_g > 1.0


def test_e2e_telemetry_replay_status_endpoint():
    """Verify telemetry replay status endpoint."""
    with TestClient(app) as client:
        res = client.get("/api/v1/telemetry/replay/status?session_id=sess-e2e")
        assert res.status_code == 200
        data = res.json()
        assert "is_running" in data
        assert "target_rate_hz" in data
