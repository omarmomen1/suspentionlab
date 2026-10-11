"""
tests/test_telemetry_canonical_dataset.py
=========================================
Tests for Step 1, Step 2, Step 3, Step 6, and Step 7:
- Canonical TelemetryDataset container & metadata
- Non-destructive sample and timestamp preservation with QualityFlag bitmasks
- Multi-DAQ ontology (MoTeC, AiM, Cosworth, Bosch, CAN, generic CSV) with scaling and units
- Timestamp-aware continuous (PCHIP/linear) and discrete (ZOH) resampling
- Exact dt derivative calculation
"""

import pytest
import numpy as np

from suspensionlab.physics.telemetry_dataset import (
    TelemetryDataset,
    TelemetrySource,
    QualityFlag,
    PreservedChannelData,
    TrackReference,
    CornerSegment,
    resolve_channel_mapping,
)


def test_quality_flags_bitmask_and_preservation():
    """Verify QualityFlag bitmasks preserve sample validity and corruption categories."""
    flags = np.zeros(5, dtype=np.int32)
    flags[0] = QualityFlag.VALID
    flags[1] = QualityFlag.MISSING | QualityFlag.OUT_OF_RANGE
    flags[2] = QualityFlag.DERIVATIVE_SPIKE
    flags[3] = QualityFlag.DEAD_SENSOR_FLATLINE
    flags[4] = QualityFlag.INTERPOLATED

    assert flags[0] == 0
    assert (flags[1] & QualityFlag.MISSING) != 0
    assert (flags[1] & QualityFlag.OUT_OF_RANGE) != 0
    assert (flags[2] & QualityFlag.DERIVATIVE_SPIKE) != 0
    assert (flags[3] & QualityFlag.DEAD_SENSOR_FLATLINE) != 0
    assert (flags[4] & QualityFlag.INTERPOLATED) != 0


def test_preserved_channel_data_non_destructive():
    """Verify PreservedChannelData maintains raw values while returning scaled values and valid slices."""
    raw_t = np.array([0.0, 0.01, 0.02, 0.03, 0.04])
    raw_v = np.array([100.0, np.nan, 120.0, 130.0, 140.0]) # e.g. km/h

    ch = PreservedChannelData(
        canonical_name="speed",
        source_name="GPS_Speed_kmh",
        unit="m/s",
        scale=1.0 / 3.6, # km/h to m/s
        offset=0.0,
        raw_timestamps=raw_t,
        raw_values=raw_v,
    )

    assert len(ch.raw_values) == 5
    assert np.isnan(ch.raw_values[1])
    assert ch.missing_mask[1] == True
    assert (ch.quality_flags[1] & QualityFlag.MISSING) != 0

    # Scaled values
    scaled = ch.scaled_values
    assert pytest.approx(scaled[0], abs=1e-3) == 100.0 / 3.6
    assert np.isnan(scaled[1])

    # Valid series extraction
    t_val, y_val = ch.get_valid_series()
    assert len(t_val) == 4
    assert len(y_val) == 4
    assert np.all(np.isfinite(y_val))


def test_timestamp_aware_continuous_and_discrete_resampling():
    """Verify resampling uses linear/PCHIP for continuous channels and ZOH for discrete."""
    raw_t = np.array([0.0, 0.1, 0.2, 0.4]) # Non-uniform spacing
    raw_v_cont = np.array([10.0, 20.0, 30.0, 50.0])
    raw_v_disc = np.array([1.0, 2.0, 3.0, 4.0]) # Gear

    ch_cont = PreservedChannelData(
        canonical_name="speed",
        source_name="speed",
        unit="m/s",
        raw_timestamps=raw_t,
        raw_values=raw_v_cont,
        is_discrete=False,
    )
    ch_disc = PreservedChannelData(
        canonical_name="gear",
        source_name="gear",
        unit="-",
        raw_timestamps=raw_t,
        raw_values=raw_v_disc,
        is_discrete=True,
    )

    query_t = np.array([0.05, 0.15, 0.30])

    # Continuous linear interpolation at t=0.05 -> 15.0, at t=0.30 -> 40.0
    res_cont = ch_cont.resample_to(query_t, method="linear")
    assert pytest.approx(res_cont[0], abs=1e-3) == 15.0
    assert pytest.approx(res_cont[2], abs=1e-3) == 40.0

    # Discrete ZOH at t=0.05 -> 1.0 (held from t=0.0), at t=0.30 -> 3.0 (held from t=0.2)
    res_disc = ch_disc.resample_to(query_t)
    assert res_disc[0] == 1.0
    assert res_disc[1] == 2.0
    assert res_disc[2] == 3.0


def test_exact_dt_derivative_calculation():
    """Verify rate of change is calculated using exact sample-to-sample timestamp deltas."""
    # Quadratic speed profile: v(t) = 5 * t^2 -> dv/dt = 10 * t
    t = np.array([0.0, 0.1, 0.3, 0.6, 1.0]) # Highly non-uniform dt
    v = 5.0 * (t ** 2)

    ch = PreservedChannelData(
        canonical_name="speed",
        source_name="speed",
        unit="m/s",
        raw_timestamps=t,
        raw_values=v,
    )

    t_mid, accel = ch.compute_timestamp_aware_derivative()
    assert len(t_mid) == 4
    # Check that derivative matches 10 * t_mid
    expected_accel = 10.0 * t_mid
    np.testing.assert_allclose(accel, expected_accel, rtol=1e-2)


def test_universal_daq_ontology_resolution():
    """Verify ontology resolver correctly maps MoTeC, AiM, Cosworth, Bosch, and CAN channels."""
    # MoTeC alias
    k1, u1, s1, o1, c1 = resolve_channel_mapping("Ground Speed", TelemetrySource.MOTEC)
    assert k1 == "speed"
    assert u1 == "m/s"

    # AiM alias
    k2, u2, s2, o2, c2 = resolve_channel_mapping("GPS_LatAcc", TelemetrySource.AIM)
    assert k2 == "lat_g"
    assert u2 == "G"

    # Cosworth / Pi alias
    k3, u3, s3, o3, c3 = resolve_channel_mapping("r_damper_fl", TelemetrySource.COSWORTH)
    assert k3 == "damper_fl"
    assert u3 == "mm"

    # Bosch WinDARAB alias
    k4, u4, s4, o4, c4 = resolve_channel_mapping("delta_sw", TelemetrySource.BOSCH)
    assert k4 == "steer_deg"
    assert u4 == "deg"

    # CAN alias
    k5, u5, s5, o5, c5 = resolve_channel_mapping("CAN_WheelSpeed_FL", TelemetrySource.CAN)
    assert k5 == "wsp_fl"
    assert u5 == "m/s"


def test_telemetry_dataset_ingestion_and_canonical_grid():
    """Verify TelemetryDataset ingests CSV, maps ontology, and creates uniform canonical grid."""
    csv_data = """Time,Ground Speed,Lateral Accel,Heave Accel,Damper FL,Steering
0.00,25.0,0.1,0.02,10.0,0.0
0.01,25.2,0.3,0.05,10.2,1.2
0.02,25.5,0.8,0.10,10.5,3.5
0.03,25.9,1.2,0.12,10.9,5.0
0.04,26.4,1.8,0.15,11.4,7.2
"""
    ds = TelemetryDataset.from_csv_string(
        csv_content=csv_data,
        source=TelemetrySource.MOTEC,
        vehicle="CAR-2026-07",
        setup="SETUP-SILVERSTONE-Q",
        track="Silverstone",
        session="Qualifying",
    )

    assert ds.vehicle == "CAR-2026-07"
    assert ds.source == TelemetrySource.MOTEC
    assert ds.has_channel("speed")
    assert ds.has_channel("lat_g")
    assert ds.has_channel("vert_g")
    assert ds.has_channel("damper_fl")
    assert ds.has_channel("steer_deg")
    assert len(ds.timestamps) == 5
    assert len(ds.provenance_hash) == 64

    # Create canonical analysis grid
    canon_grid = ds.to_canonical_grid(target_dt=0.005)
    assert len(canon_grid.timestamps) == 9 # 0.00 to 0.04 with dt=0.005
    assert canon_grid.sampling_rate == 200.0
    assert canon_grid.has_channel("speed")
    assert pytest.approx(canon_grid.get_channel("speed")[0], abs=1e-3) == 25.0


def test_telemetry_dataset_train_holdout_split():
    """Verify dataset splits cleanly into training and independent holdout sets."""
    t = np.linspace(0.0, 10.0, 100)
    speed = 20.0 + 5.0 * np.sin(0.5 * t)
    
    ds = TelemetryDataset(
        timestamps=t,
        sampling_rate=10.0,
        vehicle="CAR-07",
        session="FP2",
    )
    ds.add_channel("speed", speed, "m/s")
    
    train_ds, val_ds = ds.split_train_holdout(train_ratio=0.8)
    
    assert len(train_ds.timestamps) == 80
    assert len(val_ds.timestamps) == 20
    assert train_ds.session == "FP2-Train"
    assert val_ds.session == "FP2-Holdout"
    assert train_ds.get_channel("speed")[-1] == speed[79]
    assert val_ds.get_channel("speed")[0] == speed[80]
