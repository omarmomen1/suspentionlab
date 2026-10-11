"""Phase 3H.4.1 Discrete Transition Event Resolution Tests.

Verifies:
1. Simulation discrete time step dt = 0.005 s (5 ms).
2. Maximum discrete event quantization error <= 5 ms.
3. Observed shift trigger discrepancy = 40 ms.
4. Discrepancy to quantization ratio >= 5.0x (actual 8.0x).
5. Separation verdict confirming discrepancy is physical, not numerical artifact.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h41_event_resolution.json"


@pytest.fixture(scope="module")
def resolution_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_event_resolution_metadata(resolution_data):
    """Verify metadata and contract declaration."""
    assert resolution_data["phase"] == "PHASE_3H.4.1"
    assert resolution_data["contract"] == "TRANSITION_EVENT_RESOLUTION_ANALYSIS"


def test_quantization_bounds(resolution_data):
    """Verify discrete simulation time step and quantization error bounds."""
    dt = resolution_data["simulation_dt_s"]
    max_err = resolution_data["max_event_quantization_error_s"]
    mean_err = resolution_data["mean_quantization_error_s"]

    assert dt == 0.005, f"Simulation dt {dt} != 0.005 s"
    assert max_err == 0.005
    assert mean_err == 0.0025


def test_trigger_discrepancy_vs_quantization(resolution_data):
    """Verify observed discrepancy dominates quantization error by at least 5x."""
    disc = resolution_data["observed_trigger_discrepancy_s"]
    ratio = resolution_data["discrepancy_to_quantization_ratio"]

    assert disc == pytest.approx(0.040, abs=0.005)
    assert ratio >= 5.0, f"Discrepancy ratio {ratio:.1f}x insufficient to prove physical separation"
    assert ratio == pytest.approx(8.0, abs=0.1)


def test_separation_verdict(resolution_data):
    """Verify separation verdict confirms physical discrepancy."""
    verdict = resolution_data["separation_verdict"]
    assert "8.0x" in verdict
    assert "physical" in verdict.lower()
    assert "not discrete time-step quantization" in verdict.lower()
