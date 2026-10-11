"""Phase 3H.2.2 Discrete Channel-Mutation Tests.

Verifies:
1. Zero leakage across all 5 discrete channel mutation tests:
   Mutation A: measured engine RPM
   Mutation B: measured wheel RPM
   Mutation C: measured engine torque
   Mutation D: measured GearRatio
   Mutation E: measured vehicle speed
2. Max vehicle speed difference is zero to numerical precision (< 1e-9 m/s).
3. Max torque difference is zero to numerical precision (< 1e-9 Nm).
4. Gear sequence is 100% invariant across all mutations.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHANNEL_MUTATIONS_JSON = DATA_DIR / "phase3h22_channel_mutations.json"


@pytest.fixture(scope="module")
def mut_data():
    assert CHANNEL_MUTATIONS_JSON.exists(), f"Missing file: {CHANNEL_MUTATIONS_JSON}"
    with open(CHANNEL_MUTATIONS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_mutation_zero_leakage_all_channels(mut_data):
    """Verify that zero leakage occurs across all 5 channel mutations."""
    results = mut_data["results"]
    assert len(results) == 5

    for mut_name, m_res in results.items():
        assert m_res["leakage_detected"] is False, f"Leakage detected in {mut_name}"
        assert m_res["max_vx_diff_mps"] < 1e-9, f"Non-zero Vx diff in {mut_name}: {m_res['max_vx_diff_mps']}"
        assert m_res["max_torque_diff_nm"] < 1e-9, f"Non-zero torque diff in {mut_name}: {m_res['max_torque_diff_nm']}"
        assert m_res["gear_sequence_identical"] is True, f"Gear sequence mismatch in {mut_name}"


def test_verdict_certified(mut_data):
    """Verify authoritative zero leakage verdict."""
    assert "ZERO_TELEMETRY_LEAKAGE_CONFIRMED" in mut_data["verdict"]
