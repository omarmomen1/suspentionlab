"""Phase 3H.4.1 Downshift Cascade Reconciliation Tests.

Verifies:
1. Window B (48.60 - 52.00 s) empirical transition sequence [6 -> 5 -> 4 -> hold 4].
2. Predicted transition sequence [6 -> 5 -> 4 -> 3 -> 2].
3. Empirical validation of 6 -> 5 and 5 -> 4 downshifts.
4. Forensic characterization of 4 -> 3 and 3 -> 2 divergences.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h41_downshift_reconciliation.json"


@pytest.fixture(scope="module")
def reconciliation_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_downshift_reconciliation_metadata(reconciliation_data):
    """Verify metadata and contract declaration."""
    assert reconciliation_data["phase"] == "PHASE_3H.4.1"
    assert reconciliation_data["contract"] == "DOWNSHIFT_CASCADE_RECONCILIATION"
    assert reconciliation_data["window_b_time_range_s"] == [48.6, 52.0]


def test_empirical_transitions(reconciliation_data):
    """Verify empirical transitions in Window B."""
    emp = reconciliation_data["empirical_transitions"]
    events = [e["event"] for e in emp]
    assert "6 -> 5" in events
    assert "5 -> 4" in events
    for e in emp:
        assert e["classification"] == "EMPIRICALLY_VALIDATED"


def test_predicted_transitions(reconciliation_data):
    """Verify predicted transitions and their classifications."""
    pred = reconciliation_data["predicted_transitions"]
    pred_events = [p["event"] for p in pred]
    assert "6 -> 5" in pred_events
    assert "5 -> 4" in pred_events
    assert "4 -> 3" in pred_events
    assert "3 -> 2" in pred_events

    # 6->5 and 5->4 must be EMPIRICALLY_VALIDATED
    p_65 = next(p for p in pred if p["event"] == "6 -> 5")
    p_54 = next(p for p in pred if p["event"] == "5 -> 4")
    assert p_65["classification"] == "EMPIRICALLY_VALIDATED"
    assert p_54["classification"] == "EMPIRICALLY_VALIDATED"

    # 4->3 is MODEL_SUPPORTED, 3->2 is EXTRAPOLATED
    p_43 = next(p for p in pred if p["event"] == "4 -> 3")
    p_32 = next(p for p in pred if p["event"] == "3 -> 2")
    assert p_43["classification"] == "MODEL_SUPPORTED"
    assert p_32["classification"] == "EXTRAPOLATED"


def test_divergence_forensic_explanations(reconciliation_data):
    """Verify rigorous engineering rationale for downshift divergence."""
    expl = reconciliation_data["divergent_transitions_forensic_explanation"]
    assert "4_to_3_transition" in expl
    assert "3_to_2_transition" in expl
    assert "downshift_rpm_brake" in expl["4_to_3_transition"]
    assert "kickdown" in expl["3_to_2_transition"].lower()
    assert "wheelspin" in expl["3_to_2_transition"].lower()
