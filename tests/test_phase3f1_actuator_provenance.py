"""
tests/test_phase3f1_actuator_provenance.py
==========================================
Test Suite 1 for Phase 3F.1: Actuator-Replay Provenance & Terminology Audit.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def actuator_provenance_data():
    path = PROJECT_ROOT / "data" / "phase3f1_actuator_provenance.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_formal_actuator_replay_declaration(actuator_provenance_data):
    """Verify explicit statement: 'The simulation replays measured corner brake actuation.'"""
    stmt = actuator_provenance_data["formal_declarations"]["core_statement"]
    assert stmt == "The simulation replays measured corner brake actuation."
    assert actuator_provenance_data["formal_declarations"]["validation_category"] == "ACTUATOR_REPLAY_VALIDATION"
    assert actuator_provenance_data["formal_declarations"]["autonomous_brake_prediction_present"] is False


def test_channel_classification_boundary_actuator_inputs(actuator_provenance_data):
    """Verify all 4 corner pressure channels are classified as boundary actuator inputs."""
    channels = actuator_provenance_data["channel_classification"]
    for ch in ("brake_fl_bar", "brake_fr_bar", "brake_rl_bar", "brake_rr_bar"):
        assert ch in channels
        assert "BOUNDARY_ACTUATOR_INPUT" in channels[ch]


def test_taxonomy_orthogonal_dimensions(actuator_provenance_data):
    """Verify taxonomy decouples state feedback from actuator replay."""
    taxonomy = actuator_provenance_data["decoupled_classification_taxonomy"]
    assert "state_feedback_dimension" in taxonomy
    assert "actuator_replay_dimension" in taxonomy
    assert "FULLY_BLIND" in taxonomy["state_feedback_dimension"]
    assert "FOUR_CORNER_HYDRAULIC" in taxonomy["actuator_replay_dimension"]


def test_documentation_contains_mandated_declaration():
    """Verify docs/phase3f1_actuator_provenance.md contains the exact required sentence."""
    path = PROJECT_ROOT / "docs" / "phase3f1_actuator_provenance.md"
    assert path.exists(), f"Missing {path}"
    text = path.read_text(encoding="utf-8")
    assert "The simulation replays measured corner brake actuation." in text
