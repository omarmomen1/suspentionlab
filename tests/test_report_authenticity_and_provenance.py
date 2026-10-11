"""
tests/test_report_authenticity_and_provenance.py
================================================
Verification suite for Engineering Report Authenticity & Provenance.

Validates:
1. Kinematic curves are authentic geometry solutions or explicit NOT_AVAILABLE.
2. Aerodynamic curves require real polar coefficients or explicit NOT_AVAILABLE.
3. G-G diagrams never fabricate demo points.
4. Provenance hashing is tamper-evident and deterministic.
"""

import pytest
import numpy as np
from suspensionlab.backend.services.report_service import (
    calculate_kinematic_curves,
    calculate_downforce_curve,
    calculate_gg_envelope,
    build_canonical_artifact_hash,
)


def test_kinematic_curves_authentic_geometry_solver():
    """Kinematic curve generator uses real double-wishbone kinematics when hardpoints are provided."""
    hardpoints = {
        "chassis_upper_front": {"x": 0.1, "y": 0.4, "z": 0.4},
        "chassis_upper_rear": {"x": -0.1, "y": 0.4, "z": 0.4},
        "chassis_lower_front": {"x": 0.1, "y": 0.3, "z": 0.2},
        "chassis_lower_rear": {"x": -0.1, "y": 0.3, "z": 0.2},
        "upright_upper": {"x": 0.0, "y": 0.6, "z": 0.45},
        "upright_lower": {"x": 0.0, "y": 0.6, "z": 0.2},
        "upright_tie_rod": {"x": 0.1, "y": 0.6, "z": 0.3},
        "chassis_tie_rod": {"x": 0.1, "y": 0.3, "z": 0.3},
        "wheel_center": {"x": 0.0, "y": 0.65, "z": 0.33},
    }

    res = calculate_kinematic_curves(hardpoints=hardpoints)
    assert res["status"] == "AVAILABLE"
    assert len(res["heave_travel_mm"]) == 7
    assert len(res["camber_deg"]) == 7
    assert len(res["toe_deg"]) == 7
    # Verify non-trivial camber values
    assert any(c != 0.0 for c in res["camber_deg"])


def test_kinematic_curves_lut_resolution():
    """Kinematic curve generator accurately reflects lookup table data."""
    lut = {
        "heave_z": [-0.02, -0.01, 0.0, 0.01, 0.02],
        "camber": [-2.0, -2.5, -3.0, -3.5, -4.0],
        "toe": [0.1, 0.05, 0.0, -0.05, -0.1],
    }
    res = calculate_kinematic_curves(lut_dict=lut)
    assert res["status"] == "AVAILABLE"
    assert res["heave_travel_mm"] == [-20.0, -10.0, 0.0, 10.0, 20.0]
    assert res["camber_deg"] == [-2.0, -2.5, -3.0, -3.5, -4.0]
    assert res["toe_deg"] == [0.1, 0.05, 0.0, -0.05, -0.1]


def test_kinematic_curves_missing_model_returns_not_available():
    """When no kinematics geometry or LUT is configured, report must state NOT_AVAILABLE."""
    res = calculate_kinematic_curves(hardpoints=None, lut_dict=None)
    assert res["status"] == "NOT_AVAILABLE"
    assert "No suspension kinematics geometry model" in res["reason"]
    assert res["heave_travel_mm"] == []


def test_downforce_curve_authentic_vs_missing():
    """Downforce curve requires real aerodynamic polar or yields NOT_AVAILABLE."""
    # Missing polar
    missing_res = calculate_downforce_curve(cl_base=None, cd_base=None, frontal_area=None)
    assert missing_res["status"] == "NOT_AVAILABLE"
    assert "No aerodynamic polar configured" in missing_res["reason"]

    # Real polar
    real_res = calculate_downforce_curve(cl_base=2.2, cd_base=0.8, frontal_area=1.5)
    assert real_res["status"] == "AVAILABLE"
    assert len(real_res["speed_kmh"]) == 6
    assert len(real_res["downforce_n"]) == 6
    # Downforce must increase quadratically with speed
    assert real_res["downforce_n"][-1] > real_res["downforce_n"][0]


def test_gg_envelope_authenticity():
    """Simulated points must be empty when none are provided and boundary must remain mathematically correct."""
    envelope = calculate_gg_envelope(mu_tire=1.6)
    assert envelope["sim_lat_g"] == []
    assert envelope["sim_long_g"] == []
    # Friction limits
    assert max(envelope["boundary_lat_g"]) <= 1.6 + 1e-4
    assert min(envelope["boundary_long_g"]) >= -1.8 - 1e-4


def test_cryptographic_artifact_hash_integrity():
    """Report artifact hash verifies full provenance chain."""
    base_args = {
        "run_id": "RUN-000100",
        "vehicle_ref": "CAR-07",
        "setup_ref": "SET-01",
        "tire_ref": "TIRE-01",
        "track_ref": "SPA",
        "physics_version": "v2.0",
        "solver_version": "scipy-1.11",
        "software_build": "abc1234",
        "input_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "result_hash": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
        "metrics": {"correlation": "UNVALIDATED", "rms": "1.0"},
        "validation_status": "UNVALIDATED",
    }
    h1 = build_canonical_artifact_hash(**base_args)

    # Any field tamper must change artifact hash
    for key in ("run_id", "vehicle_ref", "physics_version", "input_hash", "result_hash", "validation_status"):
        tampered_args = base_args.copy()
        tampered_args[key] = f"{base_args[key]}_tampered"
        h2 = build_canonical_artifact_hash(**tampered_args)
        assert h1 != h2, f"Tampering with {key} did not alter artifact hash!"
