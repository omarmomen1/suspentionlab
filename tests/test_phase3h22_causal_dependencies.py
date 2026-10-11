"""Phase 3H.2.2 Causal Dependencies & Anti-Leakage Formalization Tests.

Verifies:
1. Rejection of unphysical d(State)/d(Feedback) = 0 assertion.
2. Adoption of rigorous d(PredictedOutput) / d(ProhibitedMeasuredInput) == 0.
3. Formal documentation of permitted forward physical dynamical couplings.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CAUSAL_DEP_JSON = DATA_DIR / "phase3h22_causal_dependency_graph.json"


@pytest.fixture(scope="module")
def dep_data():
    assert CAUSAL_DEP_JSON.exists(), f"Missing file: {CAUSAL_DEP_JSON}"
    with open(CAUSAL_DEP_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_rejection_of_unphysical_assertion(dep_data):
    """Verify ambiguous assertion is explicitly documented as rejected."""
    rejected = dep_data["forbidden_assertions_rejected"]
    assert any("d(State)/d(Feedback)" in s for s in rejected)


def test_anti_leakage_assertion_formalized(dep_data):
    """Verify correct anti-leakage formula is formalized."""
    formula = dep_data["authoritative_anti_leakage_assertion"]
    assert "d(PredictedOutput)" in formula
    assert "d(ProhibitedMeasuredInput)" in formula


def test_permitted_physical_dependencies_documented(dep_data):
    """Verify healthy forward physical couplings are listed."""
    couplings = dep_data["permitted_physical_dynamic_dependencies"]["forward_couplings"]
    assert len(couplings) >= 4
    for c in couplings:
        assert c["status"] == "PERMITTED_PHYSICAL_COUPLING"
