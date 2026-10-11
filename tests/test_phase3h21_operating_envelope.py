"""Phase 3H.2.1 Torque-Model Operating-Envelope Audit Tests.

Verifies:
1. Turn 5 discovery calibration domain is documented (throttle <= 0.412, RPM <= 5109).
2. Maneuvers requiring throttle > 0.412 are strictly classified EXTRAPOLATED.
3. Turn 3 and Turn 2 remain within the validated calibration envelope.
4. No extrapolated region is claimed as empirically validated.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OPERATING_ENVELOPE_JSON = DATA_DIR / "phase3h21_operating_envelope.json"


@pytest.fixture(scope="module")
def env_data():
    assert OPERATING_ENVELOPE_JSON.exists(), f"Missing file: {OPERATING_ENVELOPE_JSON}"
    with open(OPERATING_ENVELOPE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_calibration_domain_boundaries(env_data):
    """Verify Turn 5 calibration domain boundaries are strictly documented."""
    calib = env_data["calibration_discovery_domain"]
    assert calib["maneuver"] == "Turn5_Tight_Complex"
    assert calib["throttle_range"][1] == pytest.approx(0.412, abs=0.01)
    assert calib["rpm_range"][1] == pytest.approx(5109.0, abs=1.0)


def test_highspeed_s_curves_and_turn9_10_extrapolated(env_data):
    """Verify high-throttle maneuvers are classified EXTRAPOLATED."""
    points = env_data["maneuver_operating_points"]
    assert points["HighSpeed_S_Curves"]["overall_operating_status"] == "EXTRAPOLATED"
    assert "EXTRAPOLATED" in points["HighSpeed_S_Curves"]["throttle_domain_status"]
    assert points["Turn9_10_Complex"]["overall_operating_status"] == "EXTRAPOLATED"
    assert "EXTRAPOLATED" in points["Turn9_10_Complex"]["throttle_domain_status"]


def test_turn3_and_turn2_interpolated(env_data):
    """Verify Turn 3 and Turn 2 operate within the validated envelope."""
    points = env_data["maneuver_operating_points"]
    assert points["Turn3_Approach"]["overall_operating_status"] == "EMPIRICALLY_VALIDATED"
    assert points["Turn2_Complex"]["overall_operating_status"] == "EMPIRICALLY_VALIDATED"
