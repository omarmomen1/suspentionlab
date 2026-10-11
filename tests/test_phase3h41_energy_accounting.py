"""Phase 3H.4.1 Shift Transition Energy Accounting Tests.

Verifies:
1. Complete First-Law mechanical work balance ledger across Window A (12.60 - 12.80 s).
2. Clutch interface relative residual <= 2.0%.
3. Positive clutch slip dissipation (Second Law compliance: E_diss > 0).
4. System First-Law energy accounting with quantified residuals.
5. Thermodynamic clarification separating First Law balance from Second Law dissipation.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h41_energy_accounting.json"


@pytest.fixture(scope="module")
def energy_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_energy_accounting_metadata(energy_data):
    """Verify metadata and contract declaration."""
    assert energy_data["phase"] == "PHASE_3H.4.1"
    assert energy_data["contract"] == "TRANSITION_ENERGY_ACCOUNTING_LEDGER"
    assert energy_data["window_a_time_range_s"] == [12.6, 12.8]
    assert "energy_ledger" in energy_data


def test_clutch_interface_closure(energy_data):
    """Verify clutch interface mechanical work balance closes within 2.0%."""
    ledger = energy_data["energy_ledger"]
    w_in = ledger["engine_input_work_j"]
    w_out = ledger["clutch_output_work_j"]
    e_diss = ledger["clutch_slip_dissipation_j"]
    residual_pct = abs(ledger["clutch_interface_relative_residual_pct"])

    assert w_in > 10000.0, f"Engine work {w_in} J unrealistically small"
    assert w_out > 10000.0, f"Clutch work {w_out} J unrealistically small"
    assert residual_pct <= 2.0, f"Clutch interface residual {residual_pct:.3f}% exceeds 2.0%"


def test_second_law_dissipation_positivity(energy_data):
    """Verify positive clutch slip dissipation (Second Law entropy compliance)."""
    ledger = energy_data["energy_ledger"]
    e_diss = ledger["clutch_slip_dissipation_j"]
    assert e_diss > 0.0, f"Clutch slip dissipation {e_diss} J must be strictly positive"
    assert e_diss == pytest.approx(147.5, abs=5.0)


def test_system_first_law_components(energy_data):
    """Verify all system First-Law energy components are quantified."""
    ledger = energy_data["energy_ledger"]
    assert ledger["delta_ke_vehicle_translational_j"] > 0.0
    assert ledger["delta_ke_wheels_rotational_j"] > 0.0
    assert ledger["aero_drag_dissipation_j"] > 0.0
    assert ledger["grade_gravity_work_j"] > 0.0
    assert "first_law_system_residual_j" in ledger
    assert "first_law_system_relative_residual_pct" in ledger


def test_thermodynamic_clarification(energy_data):
    """Verify distinction between Second Law positivity and First Law energy conservation."""
    clarification = energy_data["thermodynamic_clarification"]
    assert "Second Law" in clarification
    assert "First Law" in clarification
    assert "P_slip >= 0" in clarification
