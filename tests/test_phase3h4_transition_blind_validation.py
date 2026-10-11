"""Phase 3H.4 Transition Blind Validation Tests.

Verifies:
1. Window A (12.60 - 12.80 s) blind validation against authentic unseen telemetry.
2. Window B (48.60 - 52.00 s) blind validation across braking downshift cascade.
3. Strict Epistemic Classification per observable.
4. Final Gate Verdict certification: AUTONOMOUS_SHIFTING_EMPIRICALLY_VALIDATED.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_TRANS = DATA_DIR / "phase3h4_shift_transition_validation.json"
JSON_GATE = DATA_DIR / "phase3h4_gate_verdict.json"


@pytest.fixture(scope="module")
def trans_data():
    assert JSON_TRANS.exists(), f"Missing deliverable: {JSON_TRANS}"
    with open(JSON_TRANS, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def gate_data():
    assert JSON_GATE.exists(), f"Missing deliverable: {JSON_GATE}"
    with open(JSON_GATE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_window_a_blind_validation_metrics(trans_data):
    """Verify Window A blind validation accuracy."""
    win_a = trans_data["window_a_2_to_3_upshift"]
    assert win_a["vx_rmse_mps"] <= 0.25, f"Window A Vx RMSE too high: {win_a['vx_rmse_mps']}"
    assert win_a["gears_observed"] == [2, 3]


def test_window_b_blind_validation_metrics(trans_data):
    """Verify Window B downshift cascade accuracy."""
    win_b = trans_data["window_b_braking_cascade"]
    assert win_b["vx_rmse_mps"] <= 1.00, f"Window B Vx RMSE too high: {win_b['vx_rmse_mps']}"
    # Verify that multi-gear downshift cascade occurred
    assert len(win_b["shifts"]) >= 3
    # Initial gear was 6, downshifted to 5, 4, 3...
    shift_gears = [s["old_gear"] for s in win_b["shifts"]]
    assert 6 in shift_gears
    assert 5 in shift_gears
    assert 4 in shift_gears


def test_epistemic_classifications(trans_data):
    """Verify observable classifications match physical grounding."""
    evals_a = trans_data["window_a_2_to_3_upshift"]["epistemic_evaluations"]
    assert evals_a["gear_sequence_window_a"]["classification"] == "EMPIRICALLY_VALIDATED"
    assert evals_a["shift_timing_window_a"]["classification"] == "EMPIRICALLY_VALIDATED"
    assert evals_a["vx_trajectory_window_a"]["classification"] == "EMPIRICALLY_VALIDATED"
    assert evals_a["shift_duration_window_a"]["classification"] == "MODEL_SUPPORTED"
    assert evals_a["rpm_trajectory_window_a"]["classification"] == "MODEL_SUPPORTED"


def test_gate_verdict_certification(gate_data):
    """Verify Phase 3H.4 gate approval and certified model status."""
    assert gate_data["verdict"] == "PASS"
    assert gate_data["phase"] == "PHASE_3H.4"
    assert gate_data["certified_model_status"] == "AUTONOMOUS_SHIFTING_EMPIRICALLY_VALIDATED"
    assert "Window A" in gate_data["qualifications"]["unseen_transition_reproduction"]
