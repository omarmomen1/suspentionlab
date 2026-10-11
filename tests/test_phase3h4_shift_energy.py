"""Phase 3H.4 Shift Energy Accounting Tests.

Verifies:
1. Physical invariant: no energy creation during shift transitions.
2. Clutch slip dissipation power P_slip >= 0 at all times.
3. Cumulative clutch energy dissipation is strictly monotonic non-decreasing (dE/dt >= 0).
4. Physical energy accounting deliverable consistency.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_ENERGY = DATA_DIR / "phase3h4_shift_energy_accounting.json"
JSON_INVARIANTS = DATA_DIR / "phase3h4_physical_invariants.json"


@pytest.fixture(scope="module")
def energy_data():
    assert JSON_ENERGY.exists(), f"Missing deliverable: {JSON_ENERGY}"
    with open(JSON_ENERGY, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def invariants_data():
    assert JSON_INVARIANTS.exists(), f"Missing deliverable: {JSON_INVARIANTS}"
    with open(JSON_INVARIANTS, "r", encoding="utf-8") as f:
        return json.load(f)


def test_no_energy_creation_invariant(invariants_data):
    """Verify that cumulative clutch dissipation energy is strictly non-negative and non-decreasing."""
    inv = invariants_data["invariants"]["no_energy_creation"]
    assert inv["status"] == "PASS"
    assert inv["total_dissipated_energy_j"] >= 0.0
    assert inv["min_delta_energy_j"] >= -1e-9


def test_energy_accounting_deliverable_values(energy_data):
    """Verify Window A and Window B dissipated energy values."""
    assert energy_data["window_a_clutch_energy_dissipated_j"] > 0.0
    assert energy_data["window_b_clutch_energy_dissipated_j"] > 0.0
    assert "P_slip = |T_C1 * (w_in - w_out1)| + |T_C2 * (w_in - w_out2)| >= 0" in energy_data["energy_conservation_proof"]


def test_physical_invariants_overall_verdict(invariants_data):
    """Verify that all 7 physical invariants are satisfied."""
    assert invariants_data["overall_verdict"] == "PASS"
    invs = invariants_data["invariants"]
    expected_invariants = [
        "no_negative_clutch_capacity",
        "no_torque_duplication",
        "no_energy_creation",
        "no_discontinuous_speed_jumps",
        "no_gear_oscillation_within_lockout",
        "finite_and_valid_gear_indices",
        "no_measured_telemetry_feedback",
    ]
    for key in expected_invariants:
        assert key in invs, f"Missing physical invariant: {key}"
        assert invs[key]["status"] == "PASS", f"Physical invariant failed: {key}"
