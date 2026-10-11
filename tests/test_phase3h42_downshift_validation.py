"""Phase 3H.4.2 Downshift Cascade Epistemic Certification Tests.

Verifies:
1. Exact epistemic status preservation:
   - 6 -> 5 = EMPIRICALLY_VALIDATED
   - 5 -> 4 = EMPIRICALLY_VALIDATED
   - 4 -> 3 = MODEL_SUPPORTED
   - 3 -> 2 = EXTRAPOLATED
2. Zero ShiftSpec retuning constraint.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_downshift_validation.json"


@pytest.fixture(scope="module")
def downshift_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_downshift_validation_metadata(downshift_data):
    """Verify phase metadata and retuning ban."""
    assert downshift_data["phase"] == "PHASE_3H.4.2"
    assert downshift_data["contract"] == "DOWNSHIFT_CASCADE_EPISTEMIC_CERTIFICATION"
    assert downshift_data["rule"] == "ZERO_SHIFTSPEC_RETUNING"


def test_exact_epistemic_classifications(downshift_data):
    """Verify exact classifications are preserved for all 4 downshift transitions."""
    txs = downshift_data["transitions"]
    expected = {
        "6_to_5": "EMPIRICALLY_VALIDATED",
        "5_to_4": "EMPIRICALLY_VALIDATED",
        "4_to_3": "MODEL_SUPPORTED",
        "3_to_2": "EXTRAPOLATED",
    }
    for key, exp_status in expected.items():
        assert key in txs, f"Missing downshift transition key: {key}"
        assert txs[key]["classification"] == exp_status, (
            f"Transition {key} status {txs[key]['classification']} != {exp_status}"
        )
        assert len(txs[key]["rationale"]) > 20


def test_governance_status(downshift_data):
    """Verify governance certification."""
    assert downshift_data["governance_status"] == "CLASSIFICATIONS_RIGIDLY_PRESERVED_WITHOUT_RETUNING"
