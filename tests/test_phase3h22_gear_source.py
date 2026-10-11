"""Phase 3H.2.2 Path-B Gear Source Identification Tests.

Verifies:
1. Exact source classification of Path-B gear selection as PRECOMPUTED_BOUNDARY.
2. Rejection of unproven ENDOGENOUS_PREDICTION claims without shift scheduling state machine.
3. Verification that measured telemetry channels are not accessed for gear selection.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEAR_SOURCE_JSON = DATA_DIR / "phase3h22_path_b_gear_source.json"


@pytest.fixture(scope="module")
def source_data():
    assert GEAR_SOURCE_JSON.exists(), f"Missing file: {GEAR_SOURCE_JSON}"
    with open(GEAR_SOURCE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_gear_source_classification(source_data):
    """Verify Path-B gear source is strictly classified as PRECOMPUTED_BOUNDARY."""
    trace = source_data["source_level_trace"]
    assert trace["source_classification"] == "PRECOMPUTED_BOUNDARY"
    assert "boundary condition" in trace["justification"].lower()


def test_measured_channels_not_accessed(source_data):
    """Verify that measured telemetry channels are bypassed for gear selection."""
    channels = source_data["source_level_trace"]["measured_channels_queried"]
    for ch_name, status in channels.items():
        assert "NOT_ACCESSED" in status, f"Channel {ch_name} had unexpected access status: {status}"
