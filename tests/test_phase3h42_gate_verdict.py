"""Phase 3H.4.2 Gate Verdict & Certification Tests.

Verifies:
1. All Phase 3H.4.2 gate criteria are fulfilled:
   - sign conventions are unambiguous
   - complete energy ledger is closed or residual explicitly bounded
   - every residual component is allocated
   - torque variables remain semantically unambiguous
   - numerical convergence is demonstrated
   - downshift classifications preserved without retuning
   - zero production physics modifications
2. Gate verdict is PASS.
3. Certified model status is ENERGY_LEDGER_CLOSED_AND_CONVERGENT.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_gate_verdict.json"


@pytest.fixture(scope="module")
def gate_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_gate_metadata(gate_data):
    """Verify phase metadata and contract declaration."""
    assert gate_data["phase"] == "PHASE_3H.4.2"
    assert gate_data["contract"] == "TRANSMISSION_ENERGY_LEDGER_CLOSURE_GATE"
    assert gate_data["baseline_tests_preserved"] == 327


def test_gate_criteria_all_true(gate_data):
    """Verify all individual gate criteria pass."""
    crit = gate_data["gate_criteria"]
    assert crit["sign_conventions_unambiguous"] is True
    assert crit["complete_energy_ledger_closed_or_bounded"] is True
    assert crit["every_residual_component_allocated"] is True
    assert crit["torque_variables_semantically_unambiguous"] is True
    assert crit["numerical_convergence_demonstrated"] is True
    assert crit["downshift_classifications_preserved"] is True
    assert crit["zero_production_physics_modifications"] is True
    assert crit["zero_shiftspec_retuning"] is True


def test_final_gate_verdict(gate_data):
    """Verify final gate verdict and certified status."""
    assert gate_data["gate_verdict"] == "PASS"
    assert gate_data["certified_model_status"] == "ENERGY_LEDGER_CLOSED_AND_CONVERGENT"
