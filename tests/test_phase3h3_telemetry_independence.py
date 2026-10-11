"""Phase 3H.3 Telemetry Independence Mutation Tests.

Verifies:
1. Complete invariance of Case B simulation outputs to 5 prohibited measured channels:
   - Mutation A: measured engine RPM
   - Mutation B: measured wheel RPM
   - Mutation C: measured engine torque
   - Mutation D: measured CAN GearRatio
   - Mutation E: measured vehicle speed Vx
2. Machine-precision delta = 0.0 across all outputs.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h3_telemetry_independence.json"


@pytest.fixture(scope="module")
def indep_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_channel_mutations_strict_zero_delta(indep_data):
    """Verify that every mutated channel produces zero delta across all observables."""
    muts = indep_data["mutation_results"]
    assert len(muts) == 5

    for mut_name, res in muts.items():
        assert res["status"] == "PASS", f"Mutation {mut_name} failed independence check"
        assert res["max_gear_delta"] == 0
        assert res["max_engine_rpm_delta"] == pytest.approx(0.0, abs=1e-12)
        assert res["max_wheel_rpm_delta"] == pytest.approx(0.0, abs=1e-12)
        assert res["max_tractive_force_delta_n"] == pytest.approx(0.0, abs=1e-12)
        assert res["max_vx_delta_mps"] == pytest.approx(0.0, abs=1e-12)
        assert res["leakage_detected"] is False


def test_causal_derivatives_zero(indep_data):
    """Verify formal causal derivative verdict."""
    verdict = indep_data["causal_derivative_verdict"]
    assert verdict["verdict"] == "STRICT_MACHINE_PRECISION_INVARIANCE"
    assert verdict["d_gear_d_measured_rpm"] == 0.0
    assert verdict["d_gear_d_measured_wheel_rpm"] == 0.0
    assert verdict["d_gear_d_measured_torque"] == 0.0
    assert verdict["d_gear_d_measured_gearratio"] == 0.0
    assert verdict["d_gear_d_measured_vx"] == 0.0
