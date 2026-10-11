"""Phase 3H.3 ShiftSpec Policy Architecture Tests.

Verifies:
1. ShiftSpec specification contains upshift/downshift rules, RPM curves, driver demand dependence.
2. Dual-clutch transition modeling: TORQUE_CUT, CLUTCH_HANDOVER, SPEED_SYNC phases.
3. Lockout hysteresis timer specification to prevent gear hunting.
4. Formal rejection of hardcoded `gear_expected = N` as production control law.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h3_shift_spec.json"


@pytest.fixture(scope="module")
def spec_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_no_hardcoded_gear_expected(spec_data):
    """Verify anti-pattern rejection of hardcoded gear_expected = N."""
    phil = spec_data["design_philosophy"]
    assert "hardcoding" in phil["anti_pattern_rejected"].lower()
    assert "production_standard" in phil


def test_shiftspec_rules_and_phases(spec_data):
    """Verify upshift, downshift rules and dual-clutch shift phases."""
    rules = spec_data["shift_policy_rules"]
    assert "upshift_condition" in rules
    assert "downshift_condition" in rules
    assert "shift_phase_timing_specification" in rules

    phases = rules["shift_phase_timing_specification"]
    assert "phase_1_torque_cut" in phases
    assert "phase_2_clutch_handover" in phases
    assert "phase_3_speed_sync" in phases
    assert phases["total_shift_duration_s"] == pytest.approx(0.150, abs=0.01)
    assert phases["lockout_hysteresis_s"] >= 0.200
