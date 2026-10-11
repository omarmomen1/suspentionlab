"""Phase 3H.4.1 Pre-Registered Acceptance Tolerances Tests.

Verifies:
1. All 7 acceptance tolerances are formally pre-registered and frozen before tuning.
2. Exact numeric thresholds for gear sequence match, timing, duration, RPM, torque cut, and Vx RMSE.
3. Governance rule prohibiting retrospective threshold expansion.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h41_preregistered_tolerances.json"


@pytest.fixture(scope="module")
def tolerance_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_preregistered_tolerances_metadata(tolerance_data):
    """Verify metadata, contract, and frozen status."""
    assert tolerance_data["phase"] == "PHASE_3H.4.1"
    assert tolerance_data["contract"] == "PRE_REGISTERED_ACCEPTANCE_TOLERANCES"
    assert tolerance_data["status"] == "FROZEN_BEFORE_TUNING"
    assert "preregistered_tolerances" in tolerance_data


def test_all_seven_tolerances_present(tolerance_data):
    """Verify all 7 preregistered tolerance keys exist."""
    tols = tolerance_data["preregistered_tolerances"]
    expected_keys = [
        "gear_sequence_exact_match",
        "shift_trigger_time",
        "shift_completion_time",
        "pre_shift_rpm",
        "post_shift_rpm",
        "torque_cut_magnitude",
        "vx_during_transition_rmse",
    ]
    for key in expected_keys:
        assert key in tols, f"Missing tolerance key: {key}"


def test_exact_tolerance_thresholds(tolerance_data):
    """Verify frozen numerical thresholds."""
    tols = tolerance_data["preregistered_tolerances"]

    assert tols["gear_sequence_exact_match"]["tolerance"] == 0
    assert tols["shift_trigger_time"]["tolerance"] == 0.05
    assert tols["shift_completion_time"]["tolerance"] == 0.05
    assert tols["pre_shift_rpm"]["tolerance"] == 100.0
    assert tols["post_shift_rpm"]["tolerance"] == 200.0
    assert tols["torque_cut_magnitude"]["tolerance"] == 40.0
    assert tols["vx_during_transition_rmse"]["tolerance"] == 0.25


def test_governance_mandate(tolerance_data):
    """Verify anti-tampering governance mandate."""
    mandate = tolerance_data["governance_mandate"]
    assert "retrospective threshold expansion is strictly prohibited" in mandate.lower()
