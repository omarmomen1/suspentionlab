"""Phase 3H.4.2 Sign Conventions Specification Tests.

Verifies:
1. Master First-Law energy conservation equation formulation.
2. Complete definition and physical classification of all 10 declared variables:
   - W_engine, W_clutch, E_clutch_diss, W_aero, W_grade, E_damper,
     Delta_KE_trans, Delta_KE_rot, W_other, E_numeric_residual.
3. Unambiguous sign conventions without mixing.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_sign_conventions.json"


@pytest.fixture(scope="module")
def sign_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_sign_conventions_metadata(sign_data):
    """Verify phase metadata and master conservation framework."""
    assert sign_data["phase"] == "PHASE_3H.4.2"
    assert sign_data["contract"] == "SIGN_CONVENTIONS_SPECIFICATION"
    assert sign_data["framework"] == "FIRST_LAW_ENERGY_CONSERVATION_FORMAT"
    assert "W_input == Delta_E_stored + E_dissipated + W_loss + E_numeric_residual" in sign_data["master_equation"]


def test_all_ten_variables_defined(sign_data):
    """Verify all 10 required energy variables are explicitly defined."""
    defs = sign_data["variable_definitions"]
    expected_vars = [
        "W_engine",
        "W_clutch",
        "E_clutch_diss",
        "W_aero",
        "W_grade",
        "E_damper",
        "Delta_KE_trans",
        "Delta_KE_rot",
        "W_other",
        "E_numeric_residual",
    ]
    for var in expected_vars:
        assert var in defs, f"Missing definition for variable: {var}"
        assert "unit" in defs[var]
        assert "sign" in defs[var]
        assert "physical_meaning" in defs[var]
        assert "classification" in defs[var]
        assert len(defs[var]["physical_meaning"]) > 10


def test_sign_conventions_classifications(sign_data):
    """Verify appropriate physical classification for each energy variable."""
    defs = sign_data["variable_definitions"]
    assert defs["W_engine"]["classification"] == "INPUT_WORK"
    assert defs["W_clutch"]["classification"] == "INTERNAL_TRANSFER_WORK"
    assert defs["E_clutch_diss"]["classification"] == "DISSIPATION"
    assert defs["W_aero"]["classification"] == "EXTERNAL_LOSS"
    assert defs["W_grade"]["classification"] == "EXTERNAL_INPUT_OR_LOSS"
    assert defs["E_damper"]["classification"] == "DISSIPATION"
    assert defs["Delta_KE_trans"]["classification"] == "STORED_ENERGY_CHANGE"
    assert defs["Delta_KE_rot"]["classification"] == "STORED_ENERGY_CHANGE"
    assert defs["W_other"]["classification"] == "DISSIPATION"
    assert defs["E_numeric_residual"]["classification"] == "NUMERICAL_INTEGRATION_ERROR"


def test_convention_verdict(sign_data):
    """Verify unambiguous sign convention verdict."""
    assert sign_data["convention_verdict"] == "UNAMBIGUOUS_FIRST_LAW_CONSERVATION"
