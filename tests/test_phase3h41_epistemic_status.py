"""Phase 3H.4.1 Final Epistemic Status Ratification Tests.

Verifies:
1. Ratification of all 7 domain certifications:
   - AUTONOMOUS_GEAR_SELECTION (EMPIRICALLY_VALIDATED)
   - SHIFT_TIMING (EMPIRICALLY_VALIDATED)
   - SHIFT_DURATION (MODEL_SUPPORTED)
   - TORQUE_CUT (MODEL_SUPPORTED)
   - CLUTCH_HANDOVER (MODEL_SUPPORTED)
   - ENERGY_ACCOUNTING (MODEL_SUPPORTED)
   - TELEMETRY_INDEPENDENCE (EMPIRICALLY_VALIDATED)
2. All gate compliance checks pass.
3. Final gate verdict is PASS.
4. Certified model status is SHIFT_DYNAMICS_FORENSICALLY_CHARACTERIZED.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h41_epistemic_status.json"


@pytest.fixture(scope="module")
def epistemic_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_epistemic_status_metadata(epistemic_data):
    """Verify metadata and contract declaration."""
    assert epistemic_data["phase"] == "PHASE_3H.4.1"
    assert epistemic_data["contract"] == "FINAL_EPISTEMIC_STATUS_RATIFICATION"


def test_all_seven_certifications(epistemic_data):
    """Verify all 7 domain certifications are ratified with correct classifications."""
    certs = epistemic_data["certifications"]
    expected = {
        "AUTONOMOUS_GEAR_SELECTION": "EMPIRICALLY_VALIDATED",
        "SHIFT_TIMING": "EMPIRICALLY_VALIDATED",
        "SHIFT_DURATION": "MODEL_SUPPORTED",
        "TORQUE_CUT": "MODEL_SUPPORTED",
        "CLUTCH_HANDOVER": "MODEL_SUPPORTED",
        "ENERGY_ACCOUNTING": "MODEL_SUPPORTED",
        "TELEMETRY_INDEPENDENCE": "EMPIRICALLY_VALIDATED",
    }
    for domain, exp_status in expected.items():
        assert domain in certs, f"Missing domain certification: {domain}"
        assert certs[domain]["status"] == exp_status, (
            f"Domain {domain} status {certs[domain]['status']} != {exp_status}"
        )
        assert len(certs[domain]["rationale"]) > 10, f"Rationale for {domain} empty or insufficient"


def test_gate_compliance(epistemic_data):
    """Verify all gate compliance criteria are satisfied."""
    comp = epistemic_data["gate_compliance"]
    assert comp["gear_selection_certified"] is True
    assert comp["shift_provenance_reconciled"] is True
    assert comp["torque_cut_discrepancy_characterized"] is True
    assert comp["energy_ledger_closed_with_quantified_residual"] is True
    assert comp["no_ambiguous_torque_variables"] is True
    assert comp["zero_production_physics_modifications"] is True


def test_final_gate_verdict(epistemic_data):
    """Verify final gate verdict and certified model status."""
    assert epistemic_data["gate_verdict"] == "PASS"
    assert epistemic_data["certified_model_status"] == "SHIFT_DYNAMICS_FORENSICALLY_CHARACTERIZED"
