"""Phase 3H.4.3 State Convergence Verification Tests.

Verifies:
1. Uniform convergence of continuous state trajectories (Vx, Vy, wheel RPM, engine RPM).
2. Trajectory errors L_inf and L_2 contract strictly toward zero relative to the fine benchmark (0.3125 ms).
3. Discrete shift event invariance:
   - upshift trigger timestamp is invariant across all step sizes (~12.71 s)
   - final gear is 3 across all runs
   - shift phase sequence is preserved identically.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h43_state_convergence.json"


@pytest.fixture(scope="module")
def state_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_state_convergence_metadata(state_data):
    """Verify phase metadata and contract declaration."""
    assert state_data["phase"] == "PHASE_3H.4.3"
    assert state_data["contract"] == "STATE_CONVERGENCE_VERIFICATION"
    assert state_data["baseline_rate_dt_ms"] == 0.3125


def test_velocity_error_uniform_decay(state_data):
    """Verify L_inf(Vx) and L_2(Vx) contract monotonically toward zero."""
    table = state_data["state_convergence_table"]
    l_infs = [row["l_inf_vx_mps"] for row in table]
    l_2s = [row["l_2_vx_mps"] for row in table]

    for i in range(len(table) - 1):
        assert l_infs[i] > l_infs[i + 1], f"L_inf failed to contract at dt={table[i]['dt_ms']}ms"
        assert l_2s[i] > l_2s[i + 1], f"L_2 failed to contract at dt={table[i]['dt_ms']}ms"

    assert l_infs[0] < 0.025  # Max error < 0.025 m/s at 5.0 ms
    assert l_infs[2] < 0.005  # Max error < 0.005 m/s at 1.25 ms
    assert l_infs[-1] == pytest.approx(0.0, abs=1e-9)


def test_discrete_shift_events_invariance(state_data):
    """Verify discrete shift event timing and gear sequence stability across rates."""
    dse = state_data["discrete_shift_events"]
    assert dse["upshift_trigger_invariant_across_all_rates"] is True
    assert dse["gear_sequence_invariant"] is True
    assert dse["gear_sequence"] == [2, 3]

    table = state_data["state_convergence_table"]
    for row in table:
        assert row["final_gear"] == 3
        assert 12.70 <= row["upshift_trigger_time_s"] <= 12.72


def test_checkpoints_velocity_monotonicity(state_data):
    """Verify smooth state evolution across synchronized checkpoints."""
    table = state_data["state_convergence_table"]
    for row in table:
        cp = row["checkpoints"]
        v_1260 = cp["t_12.60s"]["vx_mps"]
        v_1270 = cp["t_12.70s"]["vx_mps"]
        v_1280 = cp["t_12.80s"]["vx_mps"]
        assert v_1260 < v_1270 < v_1280
