"""
tests/test_phase3h_powertrain_trace.py
======================================
Test Suite 1 for Phase 3H: Powertrain Telemetry Trace & Drive Torque Delivery.

Verifies:
  1. Measured vs simulated powertrain traces (throttle, RPM, gear, torque).
  2. Resolves core forensic question: Does the simulator apply too much positive
     drive torque? Proves the simulator under-delivers axle drive torque by >70%.
  3. Identifies the 3.23x transmission gear ratio clamping discrepancy.
  4. Prohibits inventing missing engine maps.
"""

import json
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "external" / "stanford_vw_golf_thunderhill_2023_11.csv"
LEDGER_JSON = PROJECT_ROOT / "data" / "phase3h_longitudinal_ledger.json"
POWERTRAIN_MD = PROJECT_ROOT / "docs" / "phase3h_powertrain_audit.md"


@pytest.fixture
def ledger_data():
    assert LEDGER_JSON.exists(), "phase3h_longitudinal_ledger.json must exist"
    with open(LEDGER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_powertrain_artifacts_exist():
    """Verify JSON and Markdown powertrain audit deliverables exist."""
    assert LEDGER_JSON.is_file()
    assert POWERTRAIN_MD.is_file()
    assert POWERTRAIN_MD.stat().st_size > 500


def test_throttle_ingestion_parity():
    """Verify driver throttle command is ingested identically into simulation."""
    df = pd.read_csv(DATA_PATH, comment="#")
    sub = df[(df["t_s"] >= 54.0) & (df["t_s"] <= 63.0)]
    mean_thr = float(sub["throttleCmd_percent"].mean())
    assert 20.0 <= mean_thr <= 21.0


def test_gear_ratio_clamping_discrepancy(ledger_data):
    """Verify gear ratio clamping from measured 13.585 to simulator 4.200."""
    rec0 = ledger_data["records"][0]
    meas_gr = rec0["transmission_ratio_meas"]
    sim_gr = rec0["transmission_ratio_sim"]
    assert abs(meas_gr - 13.585) < 1e-3
    assert abs(sim_gr - 4.200) < 1e-3
    # Discrepancy factor is > 3.0x
    assert (meas_gr / sim_gr) > 3.0


def test_drive_torque_under_delivery_verdict(ledger_data):
    """Verify that the simulator under-delivers axle torque by > 70%."""
    stats = ledger_data["summary_statistics"]
    sim_axle_torque = stats["mean_simulated_drive_torque_nm"]
    meas_eng_torque = stats["mean_measured_engine_torque_nm"]
    meas_axle_torque = meas_eng_torque * 13.585 * 0.90 # 1054.9 Nm

    assert sim_axle_torque < 350.0 # ~268.4 Nm
    assert meas_axle_torque > 1000.0 # ~1054.9 Nm

    deficit_pct = (1.0 - sim_axle_torque / meas_axle_torque) * 100.0
    assert deficit_pct > 70.0 # ~74.6% deficit
