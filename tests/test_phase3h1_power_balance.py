"""Phase 3H.1 Power Balance Tests.

Verifies:
1. Engine and axle power independent calculation.
2. Axle power deficit (~19.03 kW / 47.5%) and integrated energy deficit (~171.3 kJ).
3. Strict compliance with internal energy closure reporting standards (no empirical validity claims from internal closure).
4. Drivetrain mechanical efficiency consistency (eta = 0.90).
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
POWER_BALANCE_FILE = DATA_DIR / "phase3h1_power_balance.json"
POWER_MD_FILE = DOCS_DIR / "phase3h1_power_balance.md"
VALIDATION_MD_FILE = DOCS_DIR / "phase3h1_validation_status.md"


@pytest.fixture(scope="module")
def power_balance_data():
    assert POWER_BALANCE_FILE.exists(), f"Missing power balance file: {POWER_BALANCE_FILE}"
    with open(POWER_BALANCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_power_balance_metrics(power_balance_data):
    """Verify mean engine power, axle power, power deficit, and integrated energy deficit."""
    summary = power_balance_data["power_summary_watts"]

    assert summary["mean_engine_power_meas_w"] == pytest.approx(44550.0, rel=0.03)
    assert summary["mean_axle_power_meas_w"] == pytest.approx(40100.0, rel=0.03)
    assert summary["mean_axle_power_sim_w"] == pytest.approx(21070.0, rel=0.03)
    power_deficit_w = summary["mean_axle_power_meas_w"] - summary["mean_axle_power_sim_w"]
    assert power_deficit_w == pytest.approx(19030.0, rel=0.03)
    power_deficit_pct = power_deficit_w / summary["mean_axle_power_meas_w"] * 100.0
    assert power_deficit_pct == pytest.approx(47.45, abs=1.0)
    assert summary["integrated_axle_energy_deficit_j"] == pytest.approx(171250.0, rel=0.05)


def test_drivetrain_efficiency_consistency(power_balance_data):
    """Verify drivetrain efficiency eta = 0.90 relates physical engine power to axle power."""
    p_eng = power_balance_data["power_summary_watts"]["mean_engine_power_meas_w"]
    p_axle = power_balance_data["power_summary_watts"]["mean_axle_power_meas_w"]
    eta = p_axle / p_eng

    assert eta == pytest.approx(0.90, abs=1e-3), f"Expected drivetrain efficiency 0.90, got {eta}"


def test_internal_energy_balance_closure_compliance(power_balance_data):
    """Verify that reports state internal energy-balance closure without claiming empirical powertrain validity."""
    compliance = power_balance_data["energy_closure_language_compliance"]
    assert "internal energy-balance closure demonstrated to" in compliance["internal_closure_statement"].lower()
    assert "does not claim empirical powertrain validity" in compliance["epistemic_disclaimer"].lower()

    # Also verify text in Markdown report
    assert POWER_MD_FILE.exists(), f"Missing doc: {POWER_MD_FILE}"
    with open(POWER_MD_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    assert "internal energy-balance closure demonstrated to" in content.lower()
    # Verify prohibited claim is not made
    assert "empirically valid because internal energy balance closes" not in content.lower()
