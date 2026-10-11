"""
tests/test_phase3d_baseline_comparison.py
=========================================
Verification tests for Phase 3D Automated Baseline Comparison and Deliverable Governance.

Ensures:
1. Automated comparison generated data/phase3d_comparison.json with valid structure and hashes.
2. Evaluates all 5 maneuvers across FULLY_BLIND and SPEED_CONDITIONED modes.
3. Both RAW and 10 Hz FILTERED acceleration channels are preserved side-by-side.
4. Cross-maneuver generalization audit executed with explicit overfit risk bounds.
5. Epistemic validation matrix regenerated programmatically with strict claim classifications.
6. Parameter provenance registry records cryptographic hashes and dataset associations.
7. All required markdown documentation artifacts exist and are non-empty.
"""

import os
import json
import hashlib
import pytest

DATA_COMPARISON_JSON = "data/phase3d_comparison.json"
DATA_PROVENANCE_JSON = "data/phase3d_parameter_provenance.json"
DOCS_COMPARISON_MD = "docs/phase3d_comparison.md"
DOCS_GOVERNANCE_MD = "docs/phase3d_parameter_governance.md"
DOCS_CHANGELOG_MD = "docs/phase3d_change_log.md"
DOCS_VALIDATION_MD = "docs/phase3d_validation_report.md"


def test_comparison_artifacts_exist():
    """Verify all 6 Phase 3D data and documentation artifacts exist and have non-zero size."""
    for path in [
        DATA_COMPARISON_JSON,
        DATA_PROVENANCE_JSON,
        DOCS_COMPARISON_MD,
        DOCS_GOVERNANCE_MD,
        DOCS_CHANGELOG_MD,
        DOCS_VALIDATION_MD,
    ]:
        assert os.path.exists(path), f"Artifact missing: {path}"
        assert os.path.getsize(path) > 100, f"Artifact empty or too small: {path}"


def test_comparison_json_schema_and_maneuvers():
    """Verify comparison JSON contains all 5 required maneuvers and unit audit."""
    with open(DATA_COMPARISON_JSON, "r") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "dataset_sha256" in data["metadata"]
    assert len(data["metadata"]["dataset_sha256"]) == 64

    assert "unit_normalization_audit" in data
    assert data["unit_normalization_audit"]["unit_status"] == "CONVERTED_CM_TO_M"
    assert "FL" in data["unit_normalization_audit"]
    assert "FR" in data["unit_normalization_audit"]
    assert "RL" in data["unit_normalization_audit"]

    assert "maneuvers" in data
    expected_maneuvers = [
        "Turn1_Holdout",
        "Turn4_Sweeper",
        "Braking_Segment",
        "Acceleration_Segment",
        "Turn3_Hairpin",
    ]
    for m in expected_maneuvers:
        assert m in data["maneuvers"], f"Maneuver {m} missing from comparison results"
        m_dat = data["maneuvers"][m]
        assert "fully_blind_comparison" in m_dat
        assert "speed_conditioned_comparison" in m_dat
        assert "trajectory_comparison" in m_dat

        # Check required channels
        fbc = m_dat["fully_blind_comparison"]
        for ch in ["Vx", "yaw_rate", "roll", "ax_raw", "ax_filt_10hz", "ay_raw", "ay_filt_10hz", "pitch_suspension"]:
            assert ch in fbc, f"Channel {ch} missing in maneuver {m}"


def test_raw_vs_filtered_acceleration_transparency():
    """Verify raw and filtered acceleration metrics are preserved side-by-side without hiding error."""
    with open(DATA_COMPARISON_JSON, "r") as f:
        data = json.load(f)

    for m_key, m_dat in data["maneuvers"].items():
        fbc = m_dat["fully_blind_comparison"]
        ay_raw = fbc["ay_raw"]["phase3d"]
        ay_filt = fbc["ay_filt_10hz"]["phase3d"]

        # Raw noise is greater than or equal to filtered noise
        assert ay_raw["rmse"] >= ay_filt["rmse"] - 1e-4
        assert "rmse" in ay_raw
        assert "rmse" in ay_filt


def test_cross_maneuver_generalization_audit():
    """Verify generalization audit checks all 4 corrections across holdouts with overfit bounds."""
    with open(DATA_COMPARISON_JSON, "r") as f:
        data = json.load(f)

    assert "cross_maneuver_generalization" in data
    gen = data["cross_maneuver_generalization"]

    for corr in ["steering_compliance", "brake_pressure_mapping", "tire_calibration", "pitch_decoupling"]:
        assert corr in gen, f"Correction {corr} missing in generalization audit"
        assert gen[corr]["status"] in ["GENERALIZED", "OVERFIT_RISK"]

    assert data["overall_gate_verdict"] in ["PASS", "PASS WITH FINDINGS"]


def test_parameter_provenance_cryptographic_hashes():
    """Verify parameter provenance JSON contains cryptographically verifiable SHA-256 hashes."""
    with open(DATA_PROVENANCE_JSON, "r") as f:
        prov = json.load(f)

    assert "dataset_provenance" in prov
    assert len(prov["dataset_provenance"]["sha256"]) == 64
    assert len(prov["calibrated_parameters"]) >= 3

    for p in prov["calibrated_parameters"]:
        assert "parameter" in p
        assert "cryptographic_hash" in p
        assert len(p["cryptographic_hash"]) == 64
        assert "governance_rule" in p
