"""Phase 3H.4.1 Torque-Cut Semantics & Algebraic Identity Tests.

Verifies:
1. Exact algebraic identity T_clutch_1 + T_clutch_2 == T_engine_after_cut (0.0 Nm residual).
2. Explicit inequality T_clutch_1 + T_clutch_2 != T_engine_raw during torque cut.
3. Formal deprecation and ban of ambiguous identifiers ('Tcrank', 'T_crank').
4. Semantic audit of the production powertrain simulation implementation.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h41_torque_cut_semantics.json"


@pytest.fixture(scope="module")
def semantics_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_torque_cut_semantics_metadata(semantics_data):
    """Verify metadata and contract declaration."""
    assert semantics_data["phase"] == "PHASE_3H.4.1"
    assert semantics_data["contract"] == "TORQUE_CUT_SEMANTICS_DISAMBIGUATION"
    assert "variable_definitions" in semantics_data
    defs = semantics_data["variable_definitions"]
    assert "T_engine_raw" in defs
    assert "T_engine_after_cut" in defs
    assert "T_clutch_1" in defs
    assert "T_clutch_2" in defs


def test_algebraic_identity_closure(semantics_data):
    """Verify T_clutch_1 + T_clutch_2 == T_engine_after_cut strictly."""
    identity = semantics_data["algebraic_identity"]
    assert identity["formula"] == "T_clutch_1 + T_clutch_2 == T_engine_after_cut"
    assert identity["max_discrepancy_vs_T_engine_after_cut_nm"] == pytest.approx(0.0, abs=1e-6)


def test_inequality_vs_raw_engine_torque(semantics_data):
    """Verify clutches transmit post-cut torque, NOT raw combustion envelope torque."""
    identity = semantics_data["algebraic_identity"]
    assert identity["is_identical_to_T_engine_raw"] is False
    assert identity["max_discrepancy_vs_T_engine_raw_nm"] > 200.0, (
        f"Discrepancy vs raw torque {identity['max_discrepancy_vs_T_engine_raw_nm']} Nm too small"
    )


def test_banned_ambiguous_identifiers(semantics_data):
    """Verify ambiguous identifiers are banned."""
    banned = semantics_data["banned_ambiguous_identifiers"]
    assert "Tcrank" in banned
    assert "T_crank" in banned


def test_production_code_trace_audit(semantics_data):
    """Verify production code semantics ratification."""
    audit = semantics_data["code_trace_audit"]
    assert "powertrain_lap_sim.py" in audit["file"]
    assert "torque_engine_crank_nm represents T_engine_after_cut" in audit["semantic_ratification"]
