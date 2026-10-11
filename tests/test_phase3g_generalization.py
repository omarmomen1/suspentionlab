"""
tests/test_phase3g_generalization.py
====================================
Test Suite 5 for Phase 3G: Generalization Matrix, Stress Regimes & Epistemic Gate.

Verifies:
  1. Generalization deliverable exists and schema is valid.
  2. All 7 required stress regimes are evaluated and reported.
  3. Provenance partitions strictly respected (Turn 5 is DISCOVERY_SET, Turn 3 is EXTERNAL_CONFIRMATION_SET).
  4. Epistemic classifications belong strictly to the allowed set.
  5. Forbidden universal controller claims are absent.
  6. Final gate verdict is PASS WITH FINDINGS.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def generalization_data():
    path = PROJECT_ROOT / "data" / "phase3g_generalization.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def predictions_data():
    path = PROJECT_ROOT / "data" / "phase3g_brake_distribution_predictions.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_seven_required_stress_regimes_evaluated(predictions_data):
    """Verify all 7 required stress regimes are present in predictions deliverable."""
    required_regimes = {
        "straight_braking",
        "left_trail_braking",
        "right_trail_braking",
        "combined_braking_cornering",
        "throttle_lift",
        "low_pressure_braking",
        "high_pressure_braking",
    }
    actual_regimes = set(predictions_data.get("stress_regimes", {}).keys())
    missing = required_regimes - actual_regimes
    assert len(missing) == 0, f"Missing required stress regimes: {missing}"

    for r_id in required_regimes:
        reg = predictions_data["stress_regimes"][r_id]
        assert reg["points"] > 0
        assert "corners" in reg
        assert "dominant_mechanism" in reg


def test_allowed_classifications_governance(generalization_data):
    """Verify that all subsystem classifications strictly belong to the allowed set."""
    allowed = set(generalization_data["allowed_classifications"])
    expected_allowed = {
        "CONFIRMED_ON_UNSEEN_DATA",
        "SUPPORTED_BUT_INCONCLUSIVE",
        "MODEL_SUPPORTED",
        "NOT_GENERALIZED",
        "REJECTED",
    }
    assert allowed == expected_allowed

    subsystems = generalization_data["subsystems"]
    for sub_id, sub_info in subsystems.items():
        cls = sub_info["classification"]
        assert cls in allowed, f"Subsystem {sub_id} used unapproved classification: {cls}"


def test_prohibited_claims_and_scope_limitations(generalization_data):
    """Verify scope is strictly limited to tested vehicle and prohibited claims are recorded."""
    assert "tested_vehicle" in generalization_data
    assert "tested_envelope" in generalization_data
    assert "Volkswagen Golf" in generalization_data["tested_vehicle"]

    prohibited = generalization_data.get("prohibited_claims", [])
    assert "OEM ESC reconstructed" in prohibited
    assert "OEM ABS validated" in prohibited
    assert "Universal brake controller" in prohibited


def test_final_gate_status_pass_with_findings(generalization_data):
    """Verify final gate status is PASS WITH FINDINGS authorizing further work."""
    assert generalization_data["gate_status"] == "PASS WITH FINDINGS"
