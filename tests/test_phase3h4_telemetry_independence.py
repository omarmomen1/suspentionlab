"""Phase 3H.4 Telemetry Independence Mutation Tests.

Verifies:
1. Complete invariance of autonomous transmission simulator to 5 prohibited measured channels:
   - Mutation A: measured engine RPM
   - Mutation B: measured wheel RPM
   - Mutation C: measured engine torque
   - Mutation D: measured CAN GearRatio
   - Mutation E: measured vehicle speed Vx
2. Machine-precision delta = 0.0 across all outputs.
3. Zero leakage confirmation.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h4_telemetry_independence.json"


@pytest.fixture(scope="module")
def indep_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_autonomous_mutations_strict_zero_delta(indep_data):
    """Verify that every mutated channel produces zero delta across all observables."""
    muts = indep_data["mutations"]
    assert len(muts) == 5

    for mut_name, res in muts.items():
        assert res["status"] == "PASS", f"Mutation {mut_name} failed independence check"
        assert res["max_gear_delta"] == 0, f"Mutation {mut_name} affected gear selection"
        assert res["max_rpm_delta"] == pytest.approx(0.0, abs=1e-12), f"Mutation {mut_name} affected RPM"
        assert res["max_torque_delta_nm"] == pytest.approx(0.0, abs=1e-12), f"Mutation {mut_name} affected torque"
        assert res["max_vx_delta_mps"] == pytest.approx(0.0, abs=1e-12), f"Mutation {mut_name} affected Vx"


def test_zero_leakage_verdict(indep_data):
    """Verify overall independence verdict."""
    assert indep_data["verdict"] == "ZERO_LEAKAGE_CONFIRMED"
    assert indep_data["target"] == "Autonomous_PowertrainCorrectedLapSimulator"
