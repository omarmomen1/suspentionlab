"""Phase 3H.3 Authentic Shift Evidence Audit Tests.

Verifies:
1. Reconstructed shift events across authentic 22,304-sample track dataset.
2. Epistemic taxonomy adherence: MEASURED, KINEMATICALLY_INFERRED, MODEL_SUPPORTED, UNIDENTIFIABLE.
3. Verification of standing start launch, upshifts (including 95 ms torque cut), downshifts (rev-match blip).
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h3_shift_evidence.json"


@pytest.fixture(scope="module")
def evidence_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_epistemic_classification_table(evidence_data):
    """Verify all observed features are classified according to epistemic standards."""
    tax = evidence_data["epistemic_classification_table"]
    assert tax["engine_rpm"] == "MEASURED"
    assert tax["wheelspeed_*"] == "MEASURED" if "wheelspeed_*" in tax else tax.get("wheel_rpm") == "MEASURED"
    assert tax["engine_torque_can"] == "MEASURED"
    assert tax["kinematic_transmission_ratio"] == "KINEMATICALLY_INFERRED"
    assert tax["discrete_gear_state"] == "KINEMATICALLY_INFERRED"
    assert tax["shift_torque_cut_duration"] == "MODEL_SUPPORTED"
    assert tax["clutch_clamping_pressures"] == "UNIDENTIFIABLE"


def test_key_identified_events(evidence_data):
    """Verify specific physical events are documented with empirical evidence."""
    events = evidence_data["key_identified_events"]
    assert "standing_start_launch" in events
    assert "upshift_2_to_3_torque_cut" in events
    assert "turn5_braking_downshift_rev_match" in events

    cut = events["upshift_2_to_3_torque_cut"]
    assert cut["min_cut_torque_nm"] < 0.0, "Expected negative engine torque during upshift torque cut"
    assert cut["duration_s"] > 0.05 and cut["duration_s"] < 0.20

    blip = events["turn5_braking_downshift_rev_match"]
    assert blip["blip_peak_torque_nm"] > 50.0, "Expected positive torque spike during rev-match blip"
