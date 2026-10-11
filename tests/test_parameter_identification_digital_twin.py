"""
tests/test_parameter_identification_digital_twin.py
===================================================
Tests for parameter identification, calibrated digital twin, and cryptographic lineage.
"""

import pytest
import numpy as np

from suspensionlab.physics.parameter_identification import (
    identify_suspension_parameters,
    CalibrationReport,
    IdentifiedParameter,
)
from suspensionlab.physics.digital_twin import (
    DigitalTwin,
    VersionLineage,
    create_reference_digital_twin,
)


def test_parameter_identification_engine():
    t = np.linspace(0, 5, 200)
    measured_data = {"vert_g": 1.2 * np.sin(2 * np.pi * 1.5 * t), "time": t}
    nominal = {"k_s": 25000.0, "c": 2000.0, "MR": 0.85}
    
    report = identify_suspension_parameters(
        target_telemetry=measured_data,
        nominal_params=nominal,
        evidence_sessions=4,
        evidence_events=3500,
    )
    assert isinstance(report, CalibrationReport)
    assert len(report.calibrated_parameters) >= 2
    assert report.overall_confidence > 0.45
    assert "3500 telemetry corner events" in report.evidence_summary

    k_s_param = next(p for p in report.calibrated_parameters if p.parameter_name == "k_s")
    assert k_s_param.confidence > 0.45
    assert k_s_param.units == "N/m"


def test_parameter_identification_dynamics_sensitivity_A_vs_B():
    """Verify changing telemetry dynamics changes the fitted parameters (Finding 68)."""
    t = np.linspace(0, 4, 150)
    # Telemetry A: Low-frequency soft response (1.0 Hz)
    telem_A = {"vert_g": 0.8 * np.sin(2 * np.pi * 1.0 * t), "time": t}
    # Telemetry B: High-frequency stiff response (2.5 Hz)
    telem_B = {"vert_g": 1.8 * np.sin(2 * np.pi * 2.5 * t), "time": t}
    
    nominal = {"k_s": 28000.0, "c": 2000.0, "MR": 0.90}
    
    report_A = identify_suspension_parameters(telem_A, nominal_params=nominal)
    report_B = identify_suspension_parameters(telem_B, nominal_params=nominal)
    
    ks_A = next(p.calibrated_value for p in report_A.calibrated_parameters if p.parameter_name == "k_s")
    ks_B = next(p.calibrated_value for p in report_B.calibrated_parameters if p.parameter_name == "k_s")
    
    # Stiff oscillation telemetry must identify significantly higher spring rate than soft
    assert ks_B > ks_A
    assert abs(ks_B - ks_A) > 1000.0


def test_parameter_identification_residual_improvement():
    """Verify optimizer strictly minimizes forward model error (Finding 68)."""
    t = np.linspace(0, 3, 100)
    telem = {"vert_g": 1.5 * np.sin(2 * np.pi * 1.8 * t), "time": t}
    nominal = {"k_s": 18000.0, "c": 1200.0, "MR": 0.80}
    
    report = identify_suspension_parameters(telem, nominal_params=nominal)
    assert report.residual_reduction_pct >= 0.0
    assert report.train_mse_final <= report.train_mse_initial




def test_digital_twin_creation_and_fingerprinting():
    twin = create_reference_digital_twin("CAR-07-v14")
    assert isinstance(twin, DigitalTwin)
    assert twin.twin_id == "CAR-07-v14"
    assert twin.validation_score_pct > 80.0
    assert twin.uncertainty_pct <= 10.0
    
    # 1. Verify cryptographic fingerprint hash is deterministic
    fp1 = twin.compute_fingerprint()
    fp2 = twin.compute_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 length

    # 2. Fingerprint Sensitivity: changing parameters produces distinct hash
    twin_modified = create_reference_digital_twin("CAR-07-v14-tuned")
    twin_modified.suspension["k_spring_front"] = 42000.0
    fp_mod = twin_modified.compute_fingerprint()
    assert fp_mod != fp1

    # 3. Serialization and lineage structure
    d = twin.to_dict()
    assert "fingerprint_hash" in d
    assert "geometry" in d
    assert "mass_properties" in d
    assert d["twin_id"] == "CAR-07-v14"

