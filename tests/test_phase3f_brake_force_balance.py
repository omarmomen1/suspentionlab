"""
tests/test_phase3f_brake_force_balance.py
=========================================
Test Suite 2 for Phase 3F: Physical Force Balance Ledger and Conservation Laws.
"""

import json
from pathlib import Path
import pytest
import numpy as np

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    EngineOverrunMap,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def brake_chain_data():
    path = PROJECT_ROOT / "data" / "phase3f_brake_chain.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_force_balance_closure_instantaneous():
    """Verify that compute_derivatives satisfies sum Fx + F_drag + F_grade = m * ax within 1.0 N."""
    p = DynamicVehicleParams(engine_overrun_map=EngineOverrunMap(is_enabled=True))
    sim = DynamicLapSimulator(params=p)
    st = DynamicVehicleState(u_mps=25.0, v_mps=0.2, yaw_rate_rads=0.1)
    ctrl = DriverControls(
        throttle=0.0,
        brake_pressure_fl_bar=15.0,
        brake_pressure_fr_bar=40.0,
        brake_pressure_rl_bar=10.0,
        brake_pressure_rr_bar=25.0,
        gear=2,
    )
    derivs = sim.compute_derivatives(st, ctrl, road_bank_rad=0.02, road_grade_rad=-0.05)

    residual = derivs["force_balance_residual_n"]
    assert residual < 1.0, f"Force balance residual {residual} exceeded 1.0 N threshold!"


def test_force_balance_ledger_throughout_maneuver(brake_chain_data):
    """Verify that every recorded step in the Turn 5 trace satisfies force balance residual < 1.0 N."""
    traces = brake_chain_data["time_series_trace"]
    assert len(traces) > 0

    max_res = max(t["force_balance_residual_n"] for t in traces)
    assert max_res < 1.0, f"Max force residual {max_res} exceeded 1.0 N threshold!"
    assert max_res < 1e-4, f"Force residual {max_res} was not within numerical machine precision!"


def test_longitudinal_force_ledger_documentation_exists():
    """Verify docs/phase3f_longitudinal_force_ledger.md exists and is non-empty."""
    path = PROJECT_ROOT / "docs" / "phase3f_longitudinal_force_ledger.md"
    assert path.exists(), f"Missing {path}"
    assert path.stat().st_size > 500, "Documentation appears truncated or empty"
