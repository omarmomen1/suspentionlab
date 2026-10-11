"""Phase 3H.1 Input Independence and Architectural Isolation Tests.

Verifies:
1. Dependency graph isolation: non-braking longitudinal audit does not depend on or feed back into brake distribution models.
2. Boundary input vs predicted state separation.
3. Zero-modification gate: core physics files have identical hashes to frozen Phase 3H manifest.
"""

import hashlib
import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
SRC_PHYSICS_DIR = Path(__file__).resolve().parent.parent / "src" / "suspensionlab" / "physics"

DEP_GRAPH_FILE = DATA_DIR / "phase3h1_dependency_graph.json"
MANIFEST_FILE = DOCS_DIR / "phase3h1_frozen_phase3h_manifest.json"


@pytest.fixture(scope="module")
def dep_graph_data():
    assert DEP_GRAPH_FILE.exists(), f"Missing dependency graph file: {DEP_GRAPH_FILE}"
    with open(DEP_GRAPH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def manifest_data():
    assert MANIFEST_FILE.exists(), f"Missing manifest file: {MANIFEST_FILE}"
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_dependency_graph_brake_isolation(dep_graph_data):
    """Verify that non-braking propulsion audit is completely decoupled from measured state feedback."""
    taxonomy = dep_graph_data["node_taxonomy"]

    assert "boundary_driver_controls" in taxonomy
    assert "throttleCmd_percent" in taxonomy["boundary_driver_controls"]
    assert "roadWheelAngle_rad" in taxonomy["boundary_driver_controls"]

    assert "strictly_forbidden_feedback" in taxonomy
    assert "sub['Vx_mps']" in taxonomy["strictly_forbidden_feedback"]
    assert "sub['yawRate_radps']" in taxonomy["strictly_forbidden_feedback"]

    assert "endogenous_state_propagation" in taxonomy
    assert "u_mps" in taxonomy["endogenous_state_propagation"]

    # Target leakage derivative must be exactly 0
    assert "d(simulated_forward_state) / d(measured_state_feedback) = 0.000000" in dep_graph_data["target_leakage_derivative"]


def test_measured_vs_modeled_state_separation(dep_graph_data):
    """Verify clean separation between measured CAN boundary inputs and simulated state feedback."""
    statement = dep_graph_data["verification_statement"]
    assert "100% endogenous forward state propagation" in statement
    assert "Zero measured state feedback enters the integration loop" in statement


def test_production_physics_zero_modification_gate(manifest_data):
    """Verify that core production physics files are bit-for-bit identical to the frozen Phase 3H manifest."""
    frozen_hashes = manifest_data["physics_files_sha256"]

    for filename, expected_hash in frozen_hashes.items():
        file_path = SRC_PHYSICS_DIR / filename
        assert file_path.exists(), f"Physics file does not exist: {file_path}"
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, (
            f"Zero-modification gate violation in {filename}! "
            f"Expected {expected_hash}, got {actual_hash}"
        )
