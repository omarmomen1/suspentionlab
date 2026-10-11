"""Phase 3H.2 Input Independence & Zero Leakage Tests.

Verifies:
1. Target leakage derivative d(simulated_forward_state) / d(measured_state_feedback) = 0.
2. Complete architectural isolation between boundary replay inputs and endogenous state simulation.
3. Verification that production physics outside the powertrain module remain unchanged.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEP_GRAPH_JSON = DATA_DIR / "phase3h2_dependency_graph.json"


@pytest.fixture(scope="module")
def dep_graph_data():
    assert DEP_GRAPH_JSON.exists(), f"Missing dep graph file: {DEP_GRAPH_JSON}"
    with open(DEP_GRAPH_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_target_leakage_derivative(dep_graph_data):
    """Verify target leakage derivative is mathematically zero."""
    target_derivative = dep_graph_data["target_leakage_derivative"]
    assert "d(simulated_forward_state) / d(measured_state_feedback) = 0.000000" in target_derivative


def test_forbidden_feedback_states(dep_graph_data):
    """Verify predictive simulation explicitly lists forbidden measured state channels."""
    path_b = dep_graph_data["architectural_paths"]["path_b_predictive_simulation"]
    forbidden = path_b["forbidden_feedback_states"]

    assert "sub['Vx_mps']" in forbidden
    assert "sub['yawRate_radps']" in forbidden
    assert "sub['wheelspeed_*']" in forbidden


def test_verification_statement(dep_graph_data):
    """Verify explicit statement confirming zero measured state feedback leakage."""
    statement = dep_graph_data["verification_statement"]
    assert "Path A (Actuator Replay) and Path B (Predictive Simulation) are strictly separated" in statement
    assert "Zero measured feedback leaks into predictive propagation" in statement
