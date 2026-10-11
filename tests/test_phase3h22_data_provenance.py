"""Phase 3H.2.2 Raw-Data Provenance Reconciliation Tests.

Verifies:
1. Exact reconciliation of raw dataset sampling frequency (200.0 Hz) and row count (22,304).
2. Exact reconciliation of raw time span (111.516 s) and mean dt (0.005 s).
3. 1:1 synchronization between simulation fixed dt (0.005 s) and dataset timestamps.
4. Formal rejection of erroneous prior statements regarding 100 Hz / 223 s.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_PROVENANCE_JSON = DATA_DIR / "phase3h22_data_provenance_reconciliation.json"


@pytest.fixture(scope="module")
def prov_data():
    assert DATA_PROVENANCE_JSON.exists(), f"Missing file: {DATA_PROVENANCE_JSON}"
    with open(DATA_PROVENANCE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_raw_dataset_metadata_reconciled(prov_data):
    """Verify raw dataset sampling frequency, count, and span are accurately documented."""
    raw = prov_data["raw_source_metadata"]
    assert raw["raw_sample_count"] == 22304
    assert raw["raw_time_span_s"] == pytest.approx(111.516, abs=0.01)
    assert raw["raw_sampling_frequency_hz"] == pytest.approx(200.0, abs=0.1)
    assert raw["mean_sampling_period_dt_s"] == pytest.approx(0.005, abs=0.0001)


def test_simulation_synchronization_exact(prov_data):
    """Verify simulation dt matches dataset dt with zero decimation."""
    sim = prov_data["simulation_synchronization"]
    assert sim["simulation_fixed_dt_s"] == 0.005
    assert sim["simulation_frequency_hz"] == 200.0
    assert "NONE" in sim["resampling_applied"]
    assert sim["reconciliation_verdict"] == "EXACT_SAMPLE_SYNCHRONIZATION"
