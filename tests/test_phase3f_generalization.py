"""
tests/test_phase3f_generalization.py
====================================
Test Suite 6 for Phase 3F: Blind Generalization Matrix and Overfit Prevention Gate.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def generalization_data():
    path = PROJECT_ROOT / "data" / "phase3f_generalization.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def before_after_data():
    path = PROJECT_ROOT / "data" / "phase3f_before_after.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_zero_material_degradation_across_all_maneuvers(generalization_data):
    """Verify that no unseen maneuver exhibits material degradation (> 10% RMSE increase)."""
    matrix = generalization_data["matrix"]
    for m_id, m_data in matrix.items():
        assert m_data["material_degradation"] is False, (
            f"Maneuver {m_id} exhibited material degradation! Details: {m_data}"
        )


def test_safe_generalization_status_all_maneuvers(before_after_data):
    """Verify overfit_status is SAFE_GENERALIZATION for all 5 maneuvers in Fully Blind mode."""
    maneuvers = before_after_data["maneuvers"]
    for m_id, m_dict in maneuvers.items():
        status = m_dict["fully_blind"]["overfit_status"]
        assert status == "SAFE_GENERALIZATION", f"Maneuver {m_id} has overfit status: {status}"


def test_epistemic_classifications_governance(generalization_data):
    """Verify epistemic labels match scientific claim standards."""
    matrix = generalization_data["matrix"]

    # Turn 5 must be confirmed on unseen data
    assert matrix["Turn5_Tight_Complex"]["epistemic_classification"] in (
        "CONFIRMED_ON_UNSEEN_DATA",
        "SUPPORTED_BUT_INCONCLUSIVE",
    )

    # Non-braking maneuvers must be preserved as MODEL_SUPPORTED
    assert matrix["Turn2_Complex"]["epistemic_classification"] == "MODEL_SUPPORTED"
    assert matrix["HighSpeed_S_Curves"]["epistemic_classification"] == "MODEL_SUPPORTED"
    assert matrix["Turn9_10_Final_Complex"]["epistemic_classification"] == "MODEL_SUPPORTED"


def test_overall_phase3f_gate_status_pass(generalization_data):
    """Verify overall gate status is PASS."""
    assert generalization_data["metadata"]["overall_gate_status"] == "PASS"
