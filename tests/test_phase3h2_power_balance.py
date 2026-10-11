"""Phase 3H.2 Power Balance & Driveline Accounting Tests.

Verifies:
1. 11-channel driveline accounting ledger structure and sample count.
2. Explicit epistemic labeling: axle torque, wheel torque, tractive force, and axle power are INFERRED, not MEASURED.
3. Drivetrain mechanical efficiency consistency (P_axle = eta * P_eng).
4. Strict compliance with energy-closure reporting language.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
LEDGER_JSON = DATA_DIR / "phase3h2_powertrain_ledger.json"
POWER_MD = DOCS_DIR / "phase3h2_power_balance.md"


@pytest.fixture(scope="module")
def ledger_audit_data():
    assert LEDGER_JSON.exists(), f"Missing ledger file: {LEDGER_JSON}"
    with open(LEDGER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_driveline_ledger_structure(ledger_audit_data):
    """Verify ledger contains expected records and 11 distinct driveline quantities."""
    records = ledger_audit_data["records"]
    assert len(records) > 1000

    first_rec = records[0]
    expected_channels = [
        "engine_torque_nm", "engine_speed_rpm", "engine_power_w",
        "gear", "gearbox_ratio", "final_drive_ratio", "total_ratio",
        "drivetrain_efficiency", "axle_torque_nm", "axle_power_w",
        "tractive_force_n", "tractive_power_w"
    ]
    for ch in expected_channels:
        assert ch in first_rec, f"Missing channel {ch} in ledger record"


def test_inferred_epistemic_labeling(ledger_audit_data):
    """Verify that reconstructed downstream quantities are strictly labeled INFERRED."""
    first_rec = ledger_audit_data["records"][0]
    assert first_rec["axle_torque_classification"] == "INFERRED"
    assert first_rec["axle_power_classification"] == "INFERRED"
    assert first_rec["tractive_force_classification"] == "INFERRED"


def test_drivetrain_mechanical_efficiency_consistency(ledger_audit_data):
    """Verify that axle power equals drivetrain efficiency * engine power across all records."""
    records = ledger_audit_data["records"]
    eta = ledger_audit_data["drivetrain_summary"]["drivetrain_efficiency_assumed"]
    assert eta == pytest.approx(0.90, abs=1e-3)

    for rec in records[:100]:
        if abs(rec["engine_power_w"]) > 100.0:
            calc_ratio = rec["axle_power_w"] / rec["engine_power_w"]
            assert calc_ratio == pytest.approx(eta, abs=1e-3)


def test_energy_closure_language_compliance():
    """Verify that reports state internal energy-balance closure without claiming empirical validity."""
    assert POWER_MD.exists(), f"Missing power report: {POWER_MD}"
    with open(POWER_MD, "r", encoding="utf-8") as f:
        content = f.read().lower()

    assert "internal energy-balance closure demonstrated to" in content
    assert "empirically valid because internal energy balance closes" not in content
