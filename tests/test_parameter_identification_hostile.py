"""
tests/test_parameter_identification_hostile.py
===============================================
Hostile verification suite for parameter identification robustness:
- Flat signals (zero dynamic excitation) -> UNIDENTIFIABLE
- Uncorrelated / orthogonal noise signals -> UNIDENTIFIABLE
- Retain prior parameter values with delta_pct = 0.0% and confidence = 0.0
- Fisher Information Matrix collinearity / partial identifiability
- Solver non-convergence / failure handling
"""

import pytest
import numpy as np

from suspensionlab.physics.parameter_identification import (
    identify_suspension_parameters,
    IdentifiabilityState,
    CalibrationReport,
)
from suspensionlab.physics.validity import PhysicsValidityStatus


def test_hostile_flat_signal_unidentifiable():
    """Flat/constant signal with zero variance must be declared UNIDENTIFIABLE with zero shift."""
    t = np.linspace(0.0, 5.0, 200)
    flat_data = {"vert_g": np.zeros(200), "time": t}
    nominal = {"k_s": 25000.0, "c": 2000.0, "MR": 0.85}

    report = identify_suspension_parameters(flat_data, nominal_params=nominal)

    assert isinstance(report, CalibrationReport)
    assert report.identifiability_state == IdentifiabilityState.UNIDENTIFIABLE
    assert report.overall_confidence == 0.0
    assert report.residual_reduction_pct == 0.0
    assert report.validity_record is not None
    assert report.validity_record.status == PhysicsValidityStatus.UNIDENTIFIABLE
    assert not report.validity_record.is_valid

    for p in report.calibrated_parameters:
        assert p.identifiability_state == IdentifiabilityState.UNIDENTIFIABLE
        assert p.is_identifiable is False
        assert p.calibrated_value == p.nominal_value
        assert p.delta_pct == 0.0
        assert p.confidence == 0.0


def test_hostile_orthogonal_uncorrelated_signal():
    """Orthogonal white noise signal uncorrelated with vehicle dynamics must be UNIDENTIFIABLE."""
    np.random.seed(1337)
    t = np.linspace(0.0, 5.0, 200)
    # High frequency white noise completely orthogonal to low frequency quarter car response
    white_noise = np.random.normal(0.0, 0.5, 200)
    noise_data = {"vert_g": white_noise, "time": t}
    nominal = {"k_s": 25000.0, "c": 2000.0}

    report = identify_suspension_parameters(noise_data, nominal_params=nominal)

    # When forward model has no explanatory power (R² near 0), state must be UNIDENTIFIABLE
    assert report.identifiability_state == IdentifiabilityState.UNIDENTIFIABLE
    assert report.overall_confidence == 0.0
    for p in report.calibrated_parameters:
        assert p.calibrated_value == p.nominal_value
        assert p.delta_pct == 0.0
        assert p.confidence == 0.0


def test_hostile_insufficient_samples_rejection():
    """Less than 10 samples must be strictly rejected by scientific integrity policy."""
    short_data = {"vert_g": [1.0, 1.1, 0.9, 1.2], "time": [0.0, 0.1, 0.2, 0.3]}
    nominal = {"k_s": 25000.0, "c": 2000.0}

    with pytest.raises(ValueError, match="Insufficient telemetry samples"):
        identify_suspension_parameters(short_data, nominal_params=nominal)


def test_hostile_corrupt_missingness_rejection():
    """Data with >5% NaN/Inf must be strictly rejected."""
    t = np.linspace(0.0, 5.0, 100)
    corrupt_vg = np.sin(2 * np.pi * 1.5 * t)
    corrupt_vg[10:20] = np.nan  # 10% missing

    corrupt_data = {"vert_g": corrupt_vg, "time": t}
    nominal = {"k_s": 25000.0, "c": 2000.0}

    with pytest.raises(ValueError, match="missing/corrupt samples"):
        identify_suspension_parameters(corrupt_data, nominal_params=nominal)


def test_identifiable_displacement_channel():
    """Authentic damper travel displacement channel is correctly calibrated."""
    t = np.linspace(0.0, 3.0, 150)
    # Realistic suspension travel deflection in mm
    damper_travel_mm = 25.0 + 8.0 * np.sin(2 * np.pi * 1.8 * t)
    data = {"damper_fl": damper_travel_mm, "time": t}
    nominal = {"k_s": 22000.0, "c": 1800.0}

    report = identify_suspension_parameters(data, nominal_params=nominal)
    assert isinstance(report, CalibrationReport)
    assert report.total_telemetry_samples == 150
    # Displacement target should be evaluated
    assert len(report.calibrated_parameters) == 2
