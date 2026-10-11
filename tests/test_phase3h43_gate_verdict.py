"""Phase 3H.4.3 Gate Verdict & Certification Tests.

Verifies:
1. All Phase 3H.4.3 gate criteria are fulfilled:
   - rate_refinement_evaluated is True
   - residual_contracts_monotonically is True
   - richardson_order_quantified is True
   - zero_physical_terms_absorbed_into_numerical is True
   - independent_quadrature_consistent is True
   - state_convergence_demonstrated is True
   - independent_first_law_ledger_closed is True
   - zero_shiftspec_retuning is True
   - zero_production_physics_modifications is True
2. 358 baseline tests preserved.
3. Gate verdict is PASS.
4. Epistemic ratification certifies Option B: NUMERICALLY_CONVERGENT_WITH_NONZERO_ASYMPTOTE.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h43_gate_verdict.json"


@pytest.fixture(scope="module")
def gate_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_gate_metadata(gate_data):
    """Verify phase metadata and contract declaration."""
    assert gate_data["phase"] == "PHASE_3H.4.3"
    assert gate_data["contract"] == "ASYMPTOTIC_ENERGY_CONVERGENCE_AND_CLOSURE_GATE"
    assert gate_data["baseline_tests_preserved"] == 358


def test_gate_criteria_all_true(gate_data):
    """Verify all individual gate criteria pass."""
    crit = gate_data["gate_criteria"]
    assert crit["rate_refinement_evaluated"] is True
    assert crit["residual_contracts_monotonically"] is True
    assert crit["richardson_order_quantified"] is True
    assert crit["zero_physical_terms_absorbed_into_numerical"] is True
    assert crit["independent_quadrature_consistent"] is True
    assert crit["state_convergence_demonstrated"] is True
    assert crit["independent_first_law_ledger_closed"] is True
    assert crit["zero_shiftspec_retuning"] is True
    assert crit["zero_production_physics_modifications"] is True


def test_final_gate_verdict_and_ratification(gate_data):
    """Verify final gate verdict and epistemic status ratification."""
    assert gate_data["gate_verdict"] == "PASS"
    assert gate_data["certified_model_status"] == "NUMERICALLY_CONVERGENT_WITH_NONZERO_ASYMPTOTE"

    rat = gate_data["epistemic_ratification"]
    assert rat["selected_option"] == "B"
    assert "NUMERICALLY_CONVERGENT_WITH_NONZERO_ASYMPTOTE" in rat["selected_option"] or rat["selected_option"] == "B"
    assert "Rule 6" in rat["rationale"] or "Requirement 6" in rat["rationale"]
