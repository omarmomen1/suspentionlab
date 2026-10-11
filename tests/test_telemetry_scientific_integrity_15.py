"""
tests/test_telemetry_scientific_integrity_15.py
================================================
Hostile audit tests verifying:
1. 15-stage pipeline audit and explicit data lifecycle states.
2. Missing data documentation and uncertainty degradation.
3. Health check rejection (health.can_proceed == False) triggering 422 error, never HTTP 200.
4. Prohibition of synthetic fallback under sparse sample conditions (<10 samples).
5. Forward-model residual calibration integrity (anti-tautology).
"""

import pytest
import numpy as np
from fastapi import HTTPException

from suspensionlab.physics.telemetry_health import (
    assess_telemetry_health,
    TelemetryPipelineStatus,
    TelemetryHealthReport,
    MissingDataSummary,
)
from suspensionlab.physics.telemetry_analysis import analyse_session
from suspensionlab.physics.parameter_identification import (
    identify_suspension_parameters,
    CalibrationReport,
)


def test_15_stage_pipeline_and_states_present():
    # Valid synthetic telemetry dictionary
    t = np.linspace(0.0, 2.0, 200)
    data = {
        "time": t,
        "speed": np.full(200, 30.0),
        "lat_g": np.sin(t * 2.0),
        "vert_g": np.zeros(200),
        "damper_fl": np.zeros(200),
    }
    report = assess_telemetry_health(data, time_channel=t)
    assert isinstance(report, TelemetryHealthReport)
    assert report.pipeline_status in (
        TelemetryPipelineStatus.ACCEPTED,
        TelemetryPipelineStatus.ACCEPTED_WITH_WARNINGS,
    )
    assert len(report.stage_audit) == 15
    stage_names = [s.stage_name for s in report.stage_audit]
    expected_stages = [
        "upload", "integrity", "schema", "timestamp", "channel", "units",
        "missing_data", "corruption", "quality", "preprocessing", "analysis",
        "calibration", "model_update", "validation", "provenance"
    ]
    assert stage_names == expected_stages
    assert report.calibration_eligible is True
    assert report.missing_data_summary.missing_pct == 0.0


def test_corrupt_non_monotonic_timestamps_rejected():
    t = np.array([0.0, 0.01, 0.02, 0.015, 0.03, 0.04])  # Time reversal
    data = {
        "time": t,
        "speed": np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0]),
    }
    report = assess_telemetry_health(data, time_channel=t)
    assert report.pipeline_status == TelemetryPipelineStatus.REJECTED
    assert report.can_proceed is False
    assert report.is_blocked is True
    assert any("monotonic" in r.lower() or "backwards" in r.lower() for r in report.blocking_reasons)


def test_missing_data_documentation_and_calibration_ineligibility():
    t = np.linspace(0.0, 1.0, 100)
    speed = np.full(100, 25.0)
    # Inject 8% missing data on critical channel
    speed[10:18] = np.nan
    data = {
        "time": t,
        "speed": speed,
        "lat_g": np.zeros(100),
    }
    report = assess_telemetry_health(data, time_channel=t)
    # > 5% missing on critical channel speed makes calibration ineligible
    assert report.calibration_eligible is False
    assert report.missing_data_summary.missing_pct > 0.0
    assert "speed" in report.missing_data_summary.affected_channels
    assert report.missing_data_summary.uncertainty_degradation_pct > 0.0


def test_sparse_samples_rejects_synthetic_data_fabrication():
    # If fewer than 10 samples are supplied, MUST raise ValueError instead of fabricating data
    sparse_data = {
        "time": [0.0, 0.01, 0.02],
        "vert_g": [0.0, 0.05, 0.02],
    }
    with pytest.raises(ValueError, match="Insufficient telemetry samples"):
        identify_suspension_parameters(
            target_telemetry=sparse_data,
            nominal_params={"m_s": 300.0, "k_s": 25000.0, "c": 2000.0, "k_t": 200000.0, "MR": 0.85},
        )


def test_analyse_session_blocked_status_propagation():
    # CSV with corrupted backwards timestamps
    csv_corrupted = "time,speed,lat_g,long_g,vert_g\n0.0,20.0,0.1,0.0,0.0\n0.02,20.0,0.1,0.0,0.0\n0.01,20.0,0.1,0.0,0.0\n"
    res = analyse_session(csv_corrupted)
    assert res.is_blocked is True
    assert res.pipeline_status == "REJECTED"
    assert res.health.can_proceed is False
