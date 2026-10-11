"""Phase 3H.4.2 Completed First-Law Energy Ledger Tests.

Verifies:
1. Complete First-Law mechanical balance ledger across Window A (12.60 - 12.80 s).
2. Independent reporting of input work, stored energy, dissipations, external losses, and numerical residual.
3. Strict energy balance closure: Total Input Work == Stored + Dissipation + Losses + Residual.
4. Non-negativity of friction dissipations (clutch, damper, drivetrain, tire, bearing).
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_energy_ledger.json"


@pytest.fixture(scope="module")
def ledger_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_energy_ledger_metadata(ledger_data):
    """Verify phase metadata and time range."""
    assert ledger_data["phase"] == "PHASE_3H.4.2"
    assert ledger_data["contract"] == "COMPLETED_FIRST_LAW_ENERGY_LEDGER"
    assert ledger_data["window_a_time_range_s"] == [12.60, 12.80]


def test_independent_ledger_components_present(ledger_data):
    """Verify each category of the First Law is reported independently."""
    comps = ledger_data["energy_ledger_components"]
    assert "input_work" in comps
    assert "stored_energy" in comps
    assert "dissipation" in comps
    assert "external_losses" in comps
    assert "numerical_residual" in comps

    inp = comps["input_work"]
    assert inp["W_engine_j"] > 10000.0
    assert inp["W_grade_downhill_gravity_input_j"] > 1500.0
    assert inp["total_input_work_j"] == pytest.approx(inp["W_engine_j"] + inp["W_grade_downhill_gravity_input_j"], rel=1e-6)

    stored = comps["stored_energy"]
    assert stored["Delta_KE_translational_j"] > 10000.0
    assert stored["Delta_KE_rotational_wheels_j"] > 500.0

    diss = comps["dissipation"]
    assert diss["E_clutch_slip_dissipation_j"] > 0.0
    assert diss["E_drivetrain_efficiency_loss_j"] > 1000.0
    assert diss["E_tire_longitudinal_and_lateral_slip_j"] > 500.0
    assert diss["E_suspension_damper_dissipation_j"] > 30.0
    assert diss["E_wheel_bearing_damping_j"] > 100.0

    losses = comps["external_losses"]
    assert losses["W_aero_drag_loss_j"] > 2000.0


def test_first_law_balance_closure(ledger_data):
    """Verify mathematical First-Law balance closure."""
    comps = ledger_data["energy_ledger_components"]
    w_in = comps["input_work"]["total_input_work_j"]
    e_stored = comps["stored_energy"]["total_stored_energy_change_j"]
    e_diss = comps["dissipation"]["total_dissipated_energy_j"]
    w_loss = comps["external_losses"]["total_external_losses_j"]
    e_res = comps["numerical_residual"]["E_numeric_residual_j"]

    rhs = e_stored + e_diss + w_loss + e_res
    assert w_in == pytest.approx(rhs, abs=1e-6)
    assert ledger_data["balance_verification"]["is_closed"] is True


def test_dissipations_non_negativity(ledger_data):
    """Verify all modeled physical dissipation terms are strictly non-negative (Second Law)."""
    diss = ledger_data["energy_ledger_components"]["dissipation"]
    assert diss["E_clutch_slip_dissipation_j"] >= 0.0
    assert diss["E_drivetrain_efficiency_loss_j"] >= 0.0
    assert diss["E_tire_longitudinal_and_lateral_slip_j"] >= 0.0
    assert diss["E_suspension_damper_dissipation_j"] >= 0.0
    assert diss["E_wheel_bearing_damping_j"] >= 0.0
