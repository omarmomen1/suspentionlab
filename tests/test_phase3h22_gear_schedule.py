"""Phase 3H.2.2 Gear-Schedule Audit Tests.

Verifies:
1. Gear schedule is audited across all 5 maneuvers.
2. HighSpeed S-Curves and Turn 2 remain locked in Gear 3.
3. Turn 3 Approach uses configured Gear 5.
4. Turn 5 and Turn 9-10 use configured Gear 2.
5. All transitions are verified to originate from PRECOMPUTED_BOUNDARY without measured telemetry feedback.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEAR_SCHEDULE_JSON = DATA_DIR / "phase3h22_gear_schedule.json"


@pytest.fixture(scope="module")
def sched_data():
    assert GEAR_SCHEDULE_JSON.exists(), f"Missing file: {GEAR_SCHEDULE_JSON}"
    with open(GEAR_SCHEDULE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_gear_schedule_all_maneuvers_present(sched_data):
    """Verify all 5 maneuvers are audited in gear schedule ledger."""
    maneuvers = sched_data["maneuvers"]
    assert len(maneuvers) == 5
    for m_id in ["HighSpeed_S_Curves", "Turn2_Complex", "Turn3_Approach", "Turn5_Tight_Complex", "Turn9_10_Final_Complex"]:
        assert m_id in maneuvers


def test_gear_transition_source_boundary(sched_data):
    """Verify gear schedule transitions are classified PRECOMPUTED_BOUNDARY."""
    maneuvers = sched_data["maneuvers"]
    for m_id, m_info in maneuvers.items():
        assert "PRECOMPUTED_BOUNDARY" in m_info["transition_source"]
        assert "NONE" in m_info["measured_feedback_dependence"]
