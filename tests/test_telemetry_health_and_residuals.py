"""
tests/test_telemetry_health_and_residuals.py
============================================
Tests for automatic telemetry health validation and model-to-telemetry residual maps.
"""

import pytest
import numpy as np

from suspensionlab.physics.telemetry_health import (
    assess_telemetry_health,
    TelemetryHealthReport,
    ChannelHealth,
)
from suspensionlab.physics.residual_analysis import (
    compute_residuals,
    ResidualAnalysisReport,
    ChannelResidualMetrics,
)


def test_telemetry_health_valid_dataset():
    t = np.linspace(0, 10, 1000)
    data = {
        "speed": 25.0 + 5.0 * np.sin(0.5 * t),
        "lat_g": 1.2 * np.sin(0.8 * t),
        "damper_fl": 15.0 * np.sin(2.0 * t),
    }
    report = assess_telemetry_health(data, time_channel=t)
    assert isinstance(report, TelemetryHealthReport)
    assert report.can_proceed
    assert report.is_healthy
    assert len(report.blocking_reasons) == 0


def test_telemetry_health_blocks_unsafe_missing_data():
    t = np.linspace(0, 10, 100)
    damper_fl = np.ones(100) * 10.0
    # Inject 25% NaNs (exceeds 10% block threshold)
    damper_fl[:25] = np.nan
    
    data = {
        "speed": np.ones(100) * 20.0,
        "damper_fl": damper_fl,
    }
    report = assess_telemetry_health(data, time_channel=t)
    assert not report.can_proceed
    assert len(report.blocking_reasons) > 0
    assert "damper_fl" in report.blocking_reasons[0]


def test_telemetry_health_detects_dead_sensor_flatline():
    t = np.linspace(0, 10, 100)
    # Exactly flatline zero variance
    dead_sensor = np.ones(100) * 5.0
    data = {
        "speed": 20.0 + np.random.normal(0, 1, 100),
        "damper_rl": dead_sensor,
    }
    report = assess_telemetry_health(data, time_channel=t)
    assert report.channels["damper_rl"].flatline_detected
    assert len(report.warnings) > 0


def test_model_to_telemetry_residual_analysis():
    t = np.linspace(0, 10, 500)
    # True measured telemetry
    tel_speed = 25.0 + 5.0 * np.sin(0.5 * t)
    tel_lat_g = 1.5 * np.sin(0.8 * t)
    
    # Simulated model output with small discrepancy
    sim_speed = tel_speed - 0.5 # 0.5 m/s bias
    sim_lat_g = tel_lat_g * 0.95
    
    telem = {"speed": tel_speed, "lat_g": tel_lat_g}
    sim = {"speed": sim_speed, "lat_g": sim_lat_g}
    
    rep = compute_residuals(telem, sim, sample_rate_hz=50.0)
    assert isinstance(rep, ResidualAnalysisReport)
    assert rep.overall_correlation_pct > 80.0
    assert "speed" in rep.channels
    assert "lat_g" in rep.channels
    
    speed_metrics = rep.channels["speed"]
    assert pytest.approx(speed_metrics.mean_bias, abs=1e-2) == 0.5
    assert speed_metrics.mae > 0.4
    assert len(rep.phase_attributions) > 0
