"""
tests/test_telemetry_ingestion_gateway.py
=========================================
Tests for Telemetry Ingestion Gateway validation, packet loss tracking,
boundary enforcement, and real Pacejka Digital Twin calculations.
"""

import pytest
from suspensionlab.telemetry.gateway import TelemetryIngestionGateway
from suspensionlab.telemetry.protocol import (
    ChannelId,
    ChannelSample,
    QualityCode,
    GripStatusCode,
    SLTPFrame,
)


def test_gateway_sequence_loss_and_duplicate_tracking():
    """Verify dropped, duplicate, and out-of-order packets are accurately tracked."""
    gw = TelemetryIngestionGateway()
    sess = "test-session-seq"

    # Frame 1
    gw.validate_and_process({"seq": 1, "ts": 0.01, "speed_ms": 20.0, "lat_g": 0.5}, session_id=sess)
    # Frame 2
    gw.validate_and_process({"seq": 2, "ts": 0.02, "speed_ms": 20.5, "lat_g": 0.6}, session_id=sess)
    # Jump to Frame 5 (dropped seq 3, 4 -> 2 drops)
    gw.validate_and_process({"seq": 5, "ts": 0.05, "speed_ms": 21.0, "lat_g": 0.7}, session_id=sess)

    stats = gw.get_stats(sess)
    assert stats["dropped_packets"] == 2
    assert stats["total_received"] == 3

    # Send duplicate seq 2
    gw.validate_and_process({"seq": 2, "ts": 0.02, "speed_ms": 20.5, "lat_g": 0.6}, session_id=sess)
    stats = gw.get_stats(sess)
    assert stats["duplicate_packets"] == 1

    # Send out-of-order seq 3 (lower than 5, but not seen before)
    gw.validate_and_process({"seq": 3, "ts": 0.03, "speed_ms": 20.7, "lat_g": 0.65}, session_id=sess)
    stats = gw.get_stats(sess)
    assert stats["out_of_order_packets"] == 1


def test_gateway_physical_boundary_clamping_and_quality():
    """Verify physical sensor limit violations are flagged as OUT_OF_RANGE."""
    gw = TelemetryIngestionGateway()
    sess = "test-session-bounds"

    # Speed exceeds 125 m/s (450 km/h), Lat G exceeds 6.5g
    frame = gw.validate_and_process({
        "seq": 1,
        "ts": 0.01,
        "speed_ms": 250.0,   # Extreme out of range
        "lat_g": 12.0,       # Extreme out of range
        "brake_press_f": -5.0 # Sub-zero brake pressure
    }, session_id=sess)

    stats = gw.get_stats(sess)
    assert stats["boundary_violations"] >= 2

    # Verify quality flags are OUT_OF_RANGE
    for s in frame.samples:
        if s.channel_id in (ChannelId.SPEED_MS, ChannelId.LAT_G, ChannelId.BRAKE_PRESS_F):
            assert s.quality == QualityCode.OUT_OF_RANGE


def test_gateway_real_pacejka_digital_twin_evaluation():
    """Verify Digital Twin evaluates real LapSimVehicle ay_max physics model."""
    gw = TelemetryIngestionGateway()
    sess = "test-session-twin"

    # Test at 25 m/s (90 km/h) with 0.8g lateral acceleration
    frame = gw.validate_and_process({
        "seq": 10,
        "ts": 0.1,
        "speed_ms": 25.0,
        "lat_g": 0.8,
    }, session_id=sess)

    assert frame.twin is not None
    # Pacejka maximum lateral G should be between 1.1g and 2.5g for racecar at 25 m/s
    assert 1.0 < frame.twin.theoretical_max_lat_g < 3.0
    assert frame.twin.actual_lat_g == 0.8
    # With 0.8g vs ~1.25g max, car is under-utilising grip
    assert frame.twin.grip_status == GripStatusCode.UNDER_UTILISING

    # Test exceeding limit (e.g. 3.0g at low speed)
    frame2 = gw.validate_and_process({
        "seq": 11,
        "ts": 0.11,
        "speed_ms": 15.0,
        "lat_g": 2.8,
    }, session_id=sess)

    assert frame2.twin.grip_status == GripStatusCode.EXCEEDING_LIMIT


def test_gateway_metadata_traceability():
    """Verify Rule 12 engineering metadata traceability is present."""
    gw = TelemetryIngestionGateway()
    stats = gw.get_stats("any-session")
    meta = stats["metadata"]
    assert "model_version" in meta
    assert "solver" in meta
    assert "backend" in meta
    assert "parameter_version" in meta
    assert "software_build" in meta
