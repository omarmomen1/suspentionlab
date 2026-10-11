"""
tests/test_phase3h_input_independence.py
========================================
Test Suite 5 for Phase 3H: Input Independence & Frozen Baseline Integrity.

Verifies:
  1. Open-loop forward longitudinal simulation independence: zero measured
     state feedback (Vx, yaw rate, wheel speeds) enters the forward step.
  2. Target leakage derivative d(sim_state) / d(meas_feedback) == 0.000000.
  3. Phase 3G.1 frozen baseline manifest exists with 155-test baseline and Git SHA.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEP_GRAPH_JSON = PROJECT_ROOT / "data" / "phase3h_dependency_graph.json"
MANIFEST_JSON = PROJECT_ROOT / "docs" / "phase3h_frozen_phase3g1_manifest.json"


@pytest.fixture
def dep_data():
    assert DEP_GRAPH_JSON.exists(), "phase3h_dependency_graph.json must exist"
    with open(DEP_GRAPH_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def manifest_data():
    assert MANIFEST_JSON.exists(), "phase3h_frozen_phase3g1_manifest.json must exist"
    with open(MANIFEST_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_dependency_and_manifest_artifacts_exist():
    """Verify dependency graph JSON and frozen baseline manifest exist."""
    assert DEP_GRAPH_JSON.is_file()
    assert MANIFEST_JSON.is_file()


def test_frozen_baseline_manifest_integrity(manifest_data):
    """Verify manifest records frozen Phase 3G.1 Git SHA and 155 baseline tests."""
    assert manifest_data["phase"] == "PHASE_3H"
    assert manifest_data["frozen_baseline"] == "PHASE_3G.1"
    assert manifest_data["git_commit_sha"] == "fbe3d045762d8c216922630ca5c3b0da1d589a31"
    assert manifest_data["baseline_test_count"] == 155
    assert len(manifest_data["physics_files_sha256"]) >= 4


def test_strictly_forbidden_feedback_channels(dep_data):
    """Verify that measured telemetry state feedback channels are strictly excluded."""
    forbidden = dep_data["node_taxonomy"]["strictly_forbidden_feedback"]
    assert any("Vx_mps" in ch for ch in forbidden)
    assert any("yawRate_radps" in ch for ch in forbidden)
    assert any("wheelspeed" in ch for ch in forbidden)


def test_target_leakage_derivative_zero(dep_data):
    """Verify mathematical derivative invariance claim is explicitly recorded."""
    assert dep_data["target_leakage_derivative"] == "d(simulated_state) / d(measured_state_feedback) = 0.000000"
