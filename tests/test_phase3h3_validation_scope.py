"""Phase 3H.3 Validation Scope and Epistemic Status Tests.

Verifies:
1. Current status is certified as GEAR_CONDITIONED_MODEL_SUPPORTED.
2. Prohibition of premature AUTONOMOUS_SHIFTING_EMPIRICALLY_VALIDATED claim on single-gear windows.
3. Candidate empirical shift validation intervals documented.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h3_validation_scope.json"


@pytest.fixture(scope="module")
def scope_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_certified_status(scope_data):
    """Verify current certified status and prohibited premature claim."""
    assert scope_data["current_status"] == "GEAR_CONDITIONED_MODEL_SUPPORTED"
    assert scope_data["prohibited_status"] == "AUTONOMOUS_SHIFTING_EMPIRICALLY_VALIDATED"


def test_candidate_shift_windows_defined(scope_data):
    """Verify candidate empirical shift windows are preregistered."""
    windows = scope_data["candidate_empirical_shift_windows"]
    assert len(windows) >= 2
    for w in windows:
        assert "time_window_s" in w
        assert "event" in w
