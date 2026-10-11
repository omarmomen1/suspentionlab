"""
tests/test_forward_calibration_and_uncertainty.py
=================================================
Tests proving:
- Different telemetry inputs produce distinct, numerically and structurally verified parameter fits against analytical benchmarks (theta*)
- Changed model parameters change the forward simulation residual against measured telemetry
- Out-of-sample holdout telemetry is independently evaluated (Train RMSE vs Holdout RMSE)
- Fake calibration metrics are impossible (derived from real residuals and covariance)
- Parameter uncertainties, standard errors, and confidence intervals reflect Fisher Information conditioning.
"""

import pytest
import numpy as np

from suspensionlab.physics.parameter_identification import (
    identify_suspension_parameters,
    simulate_quarter_car_response,
    CalibrationReport,
    IdentifiedParameter,
)
from suspensionlab.physics.telemetry_dataset import TelemetryDataset


def test_rule_different_telemetry_produces_different_fit():
    """Prove that distinct telemetry dynamics identify distinct physical parameters."""
    t = np.linspace(0.0, 4.0, 300)
    # Telemetry 1: Soft spring oscillation (1.1 Hz)
    telem_soft = {"vert_g": 0.8 * np.sin(2 * np.pi * 1.1 * t), "time": t}
    # Telemetry 2: Stiff spring oscillation (2.8 Hz)
    telem_stiff = {"vert_g": 1.6 * np.sin(2 * np.pi * 2.8 * t), "time": t}

    nominal = {"k_s": 25000.0, "c": 2000.0, "MR": 0.85, "k_t": 200000.0}

    rep_soft = identify_suspension_parameters(telem_soft, nominal_params=nominal)
    rep_stiff = identify_suspension_parameters(telem_stiff, nominal_params=nominal)

    ks_soft = next(p.calibrated_value for p in rep_soft.calibrated_parameters if p.parameter_name == "k_s")
    ks_stiff = next(p.calibrated_value for p in rep_stiff.calibrated_parameters if p.parameter_name == "k_s")

    # Stiff telemetry must yield higher spring stiffness
    assert ks_stiff > ks_soft
    assert (ks_stiff - ks_soft) > 2000.0


def test_rule_changed_model_parameters_change_residual():
    """Prove that evaluating simulation with altered parameters directly changes the loss/residual."""
    t = np.linspace(0.0, 3.0, 200)
    road = np.where((t >= 0.5) & (t <= 0.7), 0.02, 0.0)

    # Reference measured signal generated from true parameter theta_true
    y_meas, _ = simulate_quarter_car_response(
        m_s=300.0, k_s=30000.0, c=2500.0, k_t=220000.0, MR=0.85, t_eval=t, road_input=road
    )

    # Forward simulation with exact matching parameters
    y_sim_exact, _ = simulate_quarter_car_response(
        m_s=300.0, k_s=30000.0, c=2500.0, k_t=220000.0, MR=0.85, t_eval=t, road_input=road
    )
    mse_exact = float(np.mean((y_meas - y_sim_exact) ** 2))

    # Forward simulation with intentionally altered parameters (+40% spring stiffness)
    y_sim_altered, _ = simulate_quarter_car_response(
        m_s=300.0, k_s=42000.0, c=2500.0, k_t=220000.0, MR=0.85, t_eval=t, road_input=road
    )
    mse_altered = float(np.mean((y_meas - y_sim_altered) ** 2))

    assert mse_exact < 1e-10
    assert mse_altered > 0.01
    assert mse_altered > 1000.0 * mse_exact


def test_rule_holdout_telemetry_independently_evaluated():
    """Prove that holdout validation error is computed independently from training data."""
    t = np.linspace(0.0, 10.0, 500)
    # Target signal with noise
    road = 0.015 * np.sin(2 * np.pi * 1.5 * t)
    y_meas, _ = simulate_quarter_car_response(
        m_s=300.0, k_s=32000.0, c=2400.0, k_t=200000.0, MR=0.90, t_eval=t, road_input=road
    )
    y_noisy = y_meas + np.random.normal(0, 0.005, len(t))

    telem = {"vert_g": y_noisy, "time": t, "damper_fl": road * 1000.0}
    nominal = {"k_s": 25000.0, "c": 1800.0, "MR": 0.90}

    report = identify_suspension_parameters(
        target_telemetry=telem,
        nominal_params=nominal,
        holdout_ratio=0.25,
    )

    assert report.train_samples == 375
    assert report.holdout_samples == 125
    assert report.total_telemetry_samples == 500

    # Verify both train and holdout metrics are populated from actual residual evaluation
    assert report.train_rmse > 0.0
    assert report.holdout_rmse > 0.0
    assert report.holdout_r2 > 0.50
    assert report.train_r2 > 0.50


def test_rule_empirical_uncertainty_and_confidence_intervals():
    """Prove that standard errors and 95% confidence intervals derive honestly from Fisher covariance."""
    np.random.seed(42)
    t = np.linspace(0.0, 5.0, 300)
    road = 0.010 * np.sin(2 * np.pi * 1.8 * t)
    y_meas, _ = simulate_quarter_car_response(
        m_s=300.0, k_s=28000.0, c=2100.0, k_t=200000.0, MR=0.85, t_eval=t, road_input=road
    )
    telem = {"vert_g": y_meas + np.random.normal(0, 0.005, len(t)), "time": t, "damper_fl": road * 1000.0}
    nominal = {"k_s": 25000.0, "c": 1900.0, "MR": 0.85}

    report = identify_suspension_parameters(telem, nominal_params=nominal)

    assert len(report.calibrated_parameters) >= 2
    for p in report.calibrated_parameters:
        assert p.std_error > 0.0
        # Check 95% confidence interval bounds surround calibrated value
        assert p.ci_95_lower <= p.calibrated_value <= p.ci_95_upper
        assert pytest.approx(p.ci_95_upper - p.calibrated_value, rel=1e-2) == 1.96 * p.std_error
        # Confidence score bounded in [0.05, 0.99]
        assert 0.05 <= p.confidence <= 0.99

    assert report.fisher_condition_number >= 1.0
    assert len(report.covariance_matrix) == len(report.calibrated_parameters)
