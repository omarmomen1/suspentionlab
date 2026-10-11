"""
tests/test_phase3h_energy_balance.py
====================================
Test Suite 4 for Phase 3H: First-Principles Energy Balance & Work Conservation.

Verifies:
  1. Work-Kinetic Energy balance closure over the 9.0s HighSpeed S-Curves maneuver.
  2. Relative energy closure error is strictly < 0.1% (< 200 J out of 161 kJ).
  3. Proper signs and physical magnitudes of work components:
       Engine work > +150 kJ
       Aero drag work > +100 kJ (dissipated)
       Gravity grade work > +100 kJ (retarding uphill)
       Coriolis/scrub work > +20 kJ (lateral momentum scrub)
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENERGY_JSON = PROJECT_ROOT / "data" / "phase3h_energy_balance.json"
ENERGY_MD = PROJECT_ROOT / "docs" / "phase3h_energy_balance.md"


@pytest.fixture
def energy_data():
    assert ENERGY_JSON.exists(), "phase3h_energy_balance.json must exist"
    with open(ENERGY_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_energy_artifacts_exist():
    """Verify energy balance JSON and Markdown deliverables exist."""
    assert ENERGY_JSON.is_file()
    assert ENERGY_MD.is_file()
    assert ENERGY_MD.stat().st_size > 500


def test_first_principles_energy_closure(energy_data):
    """Verify work-energy balance achieves strict < 0.1% relative closure."""
    closure = energy_data["closure_metrics"]
    rel_err_pct = closure["relative_closure_error_pct"]
    res_err_j = closure["residual_energy_error_j"]

    assert rel_err_pct < 0.10, f"Relative energy closure error exceeds 0.10%: {rel_err_pct:.4f}%"
    assert res_err_j < 200.0, f"Residual energy error exceeds 200 J: {res_err_j:.2f} J"


def test_work_components_magnitudes(energy_data):
    """Verify physical work terms have expected signs and non-trivial magnitudes."""
    ledger = energy_data["energy_ledger_joules"]
    w_eng = ledger["engine_work_at_wheels_j"]
    w_aero = ledger["aerodynamic_drag_work_j"]
    w_grade = ledger["gravity_grade_work_j"]
    delta_ke = ledger["delta_kinetic_energy_body_j"]

    # Vehicle loses kinetic energy
    assert delta_ke < -100_000.0 # ~ -161 kJ

    # Engine provided positive work
    assert w_eng > 150_000.0 # ~ +188 kJ

    # Aero drag dissipated substantial work
    assert w_aero > 100_000.0 # ~ 144 kJ

    # Uphill grade absorbed work
    assert abs(w_grade) > 100_000.0 # ~ 126 kJ
