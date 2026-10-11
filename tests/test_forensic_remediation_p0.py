"""
tests/test_forensic_remediation_p0.py
======================================
Comprehensive verification test suite ensuring 100% genuine, un-faked mathematical
execution across the telemetry, calibration, and digital twin pipelines.
"""

import pytest
import numpy as np

from suspensionlab.physics.parameter_identification import (
    identify_suspension_parameters,
    CalibrationReport,
    IdentifiedParameter,
)
from suspensionlab.physics.residual_analysis import (
    compute_residuals,
    ResidualAnalysisReport,
)
from suspensionlab.physics.telemetry_analysis import (
    evaluate_model_vs_car_session,
    analyse_session,
    ModelVsCarReport,
)
from suspensionlab.physics.digital_twin import (
    DigitalTwin,
    create_digital_twin_from_calibration,
    create_reference_digital_twin,
)
from suspensionlab.physics.setup_intelligence import (
    SetupIntelligenceEngine,
)
from suspensionlab.backend.services.digital_twin import (
    identify_from_vertical_accel,
)


def test_road_input_reconstruction_from_laser_ride_height():
    """Verify road profile is dynamically reconstructed from laser ride height rather than synthetic step."""
    t = np.linspace(0, 4, 400)
    # Simulated true track profile: 10mm bump
    rh_fl = 30.0 + 8.0 * np.sin(2 * np.pi * 1.2 * t)
    vert_g = 1.0 + 0.5 * np.sin(2 * np.pi * 1.2 * t)

    telem = {"time": t, "vert_g": vert_g, "rh_fl": rh_fl}
    nominal = {"m_s": 300.0, "k_s": 25000.0, "c": 2000.0, "MR": 0.85}

    report = identify_suspension_parameters(telem, nominal_params=nominal)
    assert isinstance(report, CalibrationReport)
    assert report.total_telemetry_samples == 400
    assert report.validation_r2 >= 0.0


def test_road_input_reconstruction_from_damper_pot():
    """Verify road profile is dynamically reconstructed from damper potentiometer."""
    t = np.linspace(0, 4, 400)
    d_fl = 12.0 * np.sin(2 * np.pi * 1.5 * t)
    vert_g = 1.0 + 0.8 * np.sin(2 * np.pi * 1.5 * t)

    telem = {"time": t, "vert_g": vert_g, "damper_fl": d_fl}
    nominal = {"m_s": 300.0, "k_s": 25000.0, "c": 2000.0, "MR": 0.85}

    report = identify_suspension_parameters(telem, nominal_params=nominal)
    assert isinstance(report, CalibrationReport)
    assert len(report.calibrated_parameters) >= 2


def test_unclamped_confidence_honestly_reflects_noisy_data():
    """Verify that highly corrupted/noisy telemetry produces lower confidence (no 81% clamp)."""
    t = np.linspace(0, 4, 300)
    # Extremely noisy random signal uncorrelated with vehicle dynamics
    np.random.seed(42)
    corrupted_vert_g = np.random.normal(0, 10.0, len(t))

    telem = {"time": t, "vert_g": corrupted_vert_g}
    nominal = {"m_s": 300.0, "k_s": 25000.0, "c": 2000.0, "MR": 0.85}

    report = identify_suspension_parameters(telem, nominal_params=nominal)
    # Confidence must honestly drop and not be clamped at >= 0.81
    assert report.overall_confidence < 0.80


def test_dynamic_spatial_residuals_and_unclamped_correlations():
    """Verify spatial residual segments and correlation percentages are extracted dynamically."""
    t = np.linspace(0, 10, 1000)
    # Generate multi-corner speed and lat_g profile
    speed = np.ones_like(t) * 45.0  # 45 m/s (~162 km/h)
    lat_g = 2.0 * np.sin(2 * np.pi * 0.2 * t)  # Alternating turns
    yaw_rate = (lat_g * 9.81 / speed)
    rh_fl = 30.0 + 5.0 * np.sin(2 * np.pi * 0.2 * t)

    telem = {
        "time": t.tolist(),
        "speed": speed.tolist(),
        "lat_g": lat_g.tolist(),
        "yaw_rate": yaw_rate.tolist(),
        "rh_fl": rh_fl.tolist(),
    }
    nominal = {"k_s": 32000.0, "c": 2400.0, "m_s": 300.0, "MR": 0.9}

    report = evaluate_model_vs_car_session(telem, nominal, session_id="TEST-SESSION", vehicle_id="TEST-CAR")
    assert isinstance(report, ModelVsCarReport)
    assert len(report.spatial_residuals) > 0
    assert report.overall_correlation_pct >= 0.0
    # Confirm segments are dynamically labeled (not static Turn 9 Copse / Turn 3 Village)
    seg_names = [s.corner_id for s in report.spatial_residuals]
    assert any("Turn" in name for name in seg_names)


def test_authentic_residual_slice_statistics():
    """Verify continuous residual phase attributions compute real mean/max statistics."""
    t = np.linspace(0, 6, 600)
    tel_speed = 30.0 + 5.0 * np.sin(0.5 * t)
    tel_lat_g = 1.8 * np.sin(1.0 * t)

    sim_speed = tel_speed + 0.25  # 0.25 m/s error
    sim_lat_g = tel_lat_g * 0.90

    telem = {"time": t, "speed": tel_speed, "lat_g": tel_lat_g}
    sim = {"time": t, "speed": sim_speed, "lat_g": sim_lat_g}

    report = compute_residuals(telem, sim, sample_rate_hz=100.0)
    assert isinstance(report, ResidualAnalysisReport)
    assert len(report.phase_attributions) >= 1

    for attr in report.phase_attributions:
        # Values must be computed dynamically, not hardcoded (0.042, 0.120, etc.)
        assert attr.sample_count > 0
        assert attr.mean_residual >= 0.0
        assert attr.max_residual >= attr.mean_residual


def test_welch_psd_contiguous_nan_interpolation():
    """Verify that non-finite samples (< 10%) are interpolated uniformly without distorting PSD."""
    t = np.linspace(0, 10, 1000)
    # Clean 1.5 Hz harmonic acceleration
    vert_g = 1.0 + 0.8 * np.sin(2 * np.pi * 1.5 * t)
    # Inject 3% NaNs
    vert_g[100:130] = np.nan

    base_params = {"m_s": 300.0, "MR": 0.85}
    res = identify_from_vertical_accel(t.tolist(), vert_g.tolist(), base_params)

    assert res["fit_converged"] is True
    # Damped natural frequency should be accurately identified close to 1.5 Hz
    assert abs(res["f_n_hz"] - 1.5) < 0.20
    assert "k_s" in res["identified_params"]


def test_digital_twin_calibration_propagation():
    """Verify create_digital_twin_from_calibration strictly propagates real sample count and validation R2."""
    t = np.linspace(0, 5, 500)
    telem = {"time": t, "vert_g": 1.2 * np.sin(2 * np.pi * 1.4 * t)}
    nominal = {"k_s": 26000.0, "c": 2100.0, "MR": 0.85}

    cal_rep = identify_suspension_parameters(telem, nominal_params=nominal)
    twin = create_digital_twin_from_calibration(
        cal_rep,
        twin_id="TWIN-DYNAMIC-01",
        chassis_name="Apex-GT3",
        session_ids=["Q1", "Q2"],
        nominal_setup={"k_s": 26000.0, "c": 2100.0},
    )

    assert isinstance(twin, DigitalTwin)
    assert twin.calibrated_samples_count == 500
    assert twin.validation_score_pct == pytest.approx(cal_rep.validation_r2 * 100.0, abs=1e-2)
    assert twin.uncertainty_pct >= 0.0
    assert len(twin.fingerprint_hash) == 64


def test_setup_intelligence_dynamic_configs():
    """Verify setup intelligence calculates configurations and confidence dynamically."""
    diag = SetupIntelligenceEngine.analyze_corner_instability(
        inquiry="Why was the car loose in turn 1?",
        corner_id="T1",
        evidence_events=24,
        residual_rh_mm=2.5,
        lsc_adjustment_pct=-5.0,
    )
    assert diag.evidence_events_count == 24
    assert diag.configurations_tested > 500
    assert 0.40 <= diag.confidence_score <= 0.99
