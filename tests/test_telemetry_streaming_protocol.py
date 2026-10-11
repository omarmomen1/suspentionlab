"""
tests/test_telemetry_streaming_protocol.py
==========================================
Tests for SLTP v1 compact binary protocol serialization, deserialization,
and corruption handling.
"""

import pytest
import struct

from suspensionlab.telemetry.protocol import (
    SLTPFrame,
    ChannelSample,
    ChannelId,
    QualityCode,
    DigitalTwinState,
    GripStatusCode,
    MAGIC_HEADER,
)


def test_sltp_roundtrip_complete():
    """Verify bit-exact roundtrip packing and unpacking of SLTPFrame."""
    samples = [
        ChannelSample(ChannelId.SPEED_MS, 55.4, QualityCode.GOOD),
        ChannelSample(ChannelId.LAT_G, 2.15, QualityCode.GOOD),
        ChannelSample(ChannelId.LONG_G, -1.82, QualityCode.GOOD),
        ChannelSample(ChannelId.VERT_G, 1.05, QualityCode.DEGRADED),
        ChannelSample(ChannelId.STEER_RAD, 0.125, QualityCode.GOOD),
        ChannelSample(ChannelId.SUSP_TRAVEL_FL, 14.2, QualityCode.GOOD),
        ChannelSample(ChannelId.SUSP_TRAVEL_FR, 18.9, QualityCode.GOOD),
        ChannelSample(ChannelId.SUSP_TRAVEL_RL, 12.1, QualityCode.GOOD),
        ChannelSample(ChannelId.SUSP_TRAVEL_RR, 16.4, QualityCode.GOOD),
        ChannelSample(ChannelId.BRAKE_PRESS_F, 85.0, QualityCode.GOOD),
        ChannelSample(ChannelId.THROTTLE_POS, 0.0, QualityCode.GOOD),
        ChannelSample(ChannelId.ENGINE_RPM, 11200.0, QualityCode.GOOD),
    ]
    twin = DigitalTwinState(
        theoretical_max_lat_g=2.45,
        actual_lat_g=2.15,
        divergence_pct=12.24,
        grip_status=GripStatusCode.OPTIMAL,
    )
    frame = SLTPFrame(
        sequence_number=1042,
        timestamp=1719928345.1234,
        org_id="org-ferrari-f1",
        session_id="silverstone-fp2",
        samples=samples,
        twin=twin,
    )

    packed = frame.pack()
    assert packed.startswith(MAGIC_HEADER)
    # Total size should be compact (< 150 bytes)
    assert len(packed) < 150

    unpacked = SLTPFrame.unpack(packed)
    assert unpacked.sequence_number == 1042
    assert abs(unpacked.timestamp - 1719928345.1234) < 1e-4
    assert unpacked.org_id == "org-ferrari-f1"
    assert unpacked.session_id == "silverstone-fp2"
    assert len(unpacked.samples) == 12

    # Check channels
    assert abs(unpacked.get_sample_value(ChannelId.SPEED_MS) - 55.4) < 1e-3
    assert abs(unpacked.get_sample_value(ChannelId.LAT_G) - 2.15) < 1e-3
    assert abs(unpacked.get_sample_value(ChannelId.BRAKE_PRESS_F) - 85.0) < 1e-3

    # Check Digital Twin block
    assert unpacked.twin is not None
    assert abs(unpacked.twin.theoretical_max_lat_g - 2.45) < 1e-3
    assert abs(unpacked.twin.actual_lat_g - 2.15) < 1e-3
    assert abs(unpacked.twin.divergence_pct - 12.24) < 1e-2
    assert unpacked.twin.grip_status == GripStatusCode.OPTIMAL


def test_sltp_unpack_corrupted_header_raises():
    """Verify corrupted magic header is rejected immediately."""
    corrupted = b"SLTX\x00\x00\x00\x01" + b"\x00" * 30
    with pytest.raises(ValueError, match="Invalid magic header"):
        SLTPFrame.unpack(corrupted)


def test_sltp_unpack_truncated_frame_raises():
    """Verify truncated frame raises clear underrun error."""
    with pytest.raises(ValueError, match="SLTP frame too small"):
        SLTPFrame.unpack(b"SLT1\x00\x01")


def test_sltp_to_dict_and_json():
    """Verify dictionary and JSON export suitable for web clients."""
    frame = SLTPFrame(
        sequence_number=5,
        timestamp=0.05,
        org_id="org-test",
        session_id="sess-1",
        samples=[ChannelSample(ChannelId.SPEED_MS, 40.0, QualityCode.GOOD)],
        twin=DigitalTwinState(1.3, 1.1, 15.4, GripStatusCode.OPTIMAL),
    )
    d = frame.to_dict()
    assert d["seq"] == 5
    assert d["speed_ms"] == 40.0
    assert d["twin"]["grip_status"] == "Optimal"
    assert "channels" in d
    json_str = frame.to_json()
    assert "Optimal" in json_str
