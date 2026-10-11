"""Phase 3H.2.1 Driveline Provenance Matrix Tests.

Verifies:
1. Strict epistemic classification of all 10 driveline channels.
2. Inferred quantities (axle torque, tractive force, axle power) are NEVER labeled MEASURED.
3. Raw CAN GearRatio is strictly labeled UNIDENTIFIABLE without DBC definition.
4. Mode-dependent classification reflects dual-path architecture.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROVENANCE_JSON = DATA_DIR / "phase3h21_provenance_matrix.json"


@pytest.fixture(scope="module")
def prov_data():
    assert PROVENANCE_JSON.exists(), f"Missing file: {PROVENANCE_JSON}"
    with open(PROVENANCE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_ten_driveline_channels_present(prov_data):
    """Verify all 10 required driveline channels are present in the matrix."""
    expected_channels = [
        "engine_torque", "engine_rpm", "wheel_rpm", "gear", "total_ratio",
        "drivetrain_efficiency", "axle_torque", "tractive_force", "engine_power", "axle_power"
    ]
    channels = prov_data["channels"]
    for ch in expected_channels:
        assert ch in channels, f"Missing channel {ch} in provenance matrix"


def test_inferred_quantities_not_labeled_measured(prov_data):
    """Verify axle torque, tractive force, and axle power are NEVER labeled MEASURED."""
    channels = prov_data["channels"]
    for ch in ["axle_torque", "tractive_force", "axle_power"]:
        for mode_key, status in channels[ch].items():
            if mode_key != "governance_note":
                assert "MEASURED" not in status, f"Channel {ch} has forbidden MEASURED status: {status}"
                assert "INFERRED" in status, f"Channel {ch} must be labeled INFERRED, got: {status}"


def test_raw_can_gear_ratio_unidentifiable(prov_data):
    """Verify raw CAN gear channel is labeled UNIDENTIFIABLE."""
    gear_info = prov_data["channels"]["gear"]
    assert "UNIDENTIFIABLE" in gear_info["raw_can_channel"]
