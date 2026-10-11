"""
tests/test_telemetry_ontology.py
================================
Tests for telemetry channel ontology, vehicle metadata, and parser integration.
"""

import pytest
import numpy as np

from suspensionlab.physics.telemetry_parser import (
    TelemetryChannel,
    VehicleSessionMetadata,
    identify_channels,
    parse_telemetry_csv,
)


def test_channel_ontology_and_metadata():
    ch = TelemetryChannel(
        canonical_name="steering_angle",
        source_name="SteerAngle_deg",
        unit="deg",
        scale=1.0,
        offset=0.0,
        sampling_rate_hz=100.0,
        quality_score=0.98,
        data=np.array([0.0, 1.2, 2.5, 1.8]),
    )
    assert ch.canonical_name == "steering_angle"
    assert ch.quality_score > 0.9
    assert len(ch.data) == 4

    meta = VehicleSessionMetadata(
        vehicle_id="FormulaStudent-2026",
        driver="Driver_1",
        track="Silverstone",
        tire_compound="C3",
        weather_ambient_c=22.5,
    )
    assert meta.vehicle_id == "FormulaStudent-2026"
    assert "ISO 8855" in meta.coordinate_convention


def test_csv_parser_with_channel_identification():
    sample_csv = """time,speed,lateral acc,damper fl
0.0,20.0,0.1,5.0
0.01,20.5,0.3,5.2
0.02,21.0,0.8,5.4
0.03,21.2,1.2,5.5
"""
    parsed = parse_telemetry_csv(sample_csv)
    assert "_channel_info" in parsed
    assert "time" in parsed
    assert "speed" in parsed
    assert "lat_g" in parsed
    assert len(parsed["speed"]) == 4

