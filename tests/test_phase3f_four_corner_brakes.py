"""
tests/test_phase3f_four_corner_brakes.py
========================================
Test Suite 1 for Phase 3F: Multi-Corner Hydraulic Braking Architecture.
"""

import json
import math
from pathlib import Path
import pytest
import numpy as np

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    BrakeActuatorMap,
    EngineOverrunMap,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def brake_chain_data():
    path = PROJECT_ROOT / "data" / "phase3f_brake_chain.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_driver_controls_four_corner_fields():
    """Verify DriverControls supports 4 independent corner pressure channels."""
    ctrl = DriverControls(
        brake_pressure_fl_bar=14.3,
        brake_pressure_fr_bar=45.2,
        brake_pressure_rl_bar=9.1,
        brake_pressure_rr_bar=28.4,
    )
    assert ctrl.brake_pressure_fl_bar == 14.3
    assert ctrl.brake_pressure_fr_bar == 45.2
    assert ctrl.brake_pressure_rl_bar == 9.1
    assert ctrl.brake_pressure_rr_bar == 28.4


def test_symmetric_pressure_backward_compatibility():
    """Verify that when 4 corners have equal pressure P, total torque matches baseline exactly."""
    p_map = BrakeActuatorMap(
        pressure_breakpoints_bar=[0.0, 15.0, 40.0, 80.0, 120.0],
        demand_breakpoints=[0.0, 0.18, 0.52, 1.00, 1.00],
        max_brake_torque_nm=4800.0,
    )
    p = DynamicVehicleParams(
        brake_max_torque_nm=4800.0,
        brake_front_bias=0.62,
        brake_actuator_map=p_map,
        engine_overrun_map=EngineOverrunMap(is_enabled=False),
    )
    sim = DynamicLapSimulator(params=p)
    d30 = p_map.pressure_to_demand(30.0)
    st_single = DynamicVehicleState(u_mps=20.0, actuator_brake=d30)
    st_four = DynamicVehicleState(
        u_mps=20.0,
        actuator_brake=d30,
        actuator_brake_fl=d30,
        actuator_brake_fr=d30,
        actuator_brake_rl=d30,
        actuator_brake_rr=d30,
    )

    # 1. Single channel call
    ctrl_single = DriverControls(brake_pressure_bar=30.0)
    derivs_single = sim.compute_derivatives(st_single, ctrl_single)

    # 2. Four-corner symmetric call
    ctrl_four = DriverControls(
        brake_pressure_fl_bar=30.0,
        brake_pressure_fr_bar=30.0,
        brake_pressure_rl_bar=30.0,
        brake_pressure_rr_bar=30.0,
    )
    derivs_four = sim.compute_derivatives(st_four, ctrl_four)

    t_single = derivs_single["actuator_torque_nm"]
    t_four = derivs_four["T_brk_fl"] + derivs_four["T_brk_fr"] + derivs_four["T_brk_rl"] + derivs_four["T_brk_rr"]

    assert t_single > 1000.0
    assert pytest.approx(t_single, rel=1e-5) == t_four
    assert pytest.approx(derivs_four["T_brk_fl"], rel=1e-5) == derivs_four["T_brk_fr"]
    assert pytest.approx(derivs_four["T_brk_rl"], rel=1e-5) == derivs_four["T_brk_rr"]


def test_asymmetric_corner_torque_distribution():
    """Verify that differential caliper pressure produces differential clamping torque."""
    p_map = BrakeActuatorMap(
        pressure_breakpoints_bar=[0.0, 15.0, 40.0, 80.0, 120.0],
        demand_breakpoints=[0.0, 0.18, 0.52, 1.00, 1.00],
        max_brake_torque_nm=4800.0,
    )
    p = DynamicVehicleParams(
        brake_max_torque_nm=4800.0,
        brake_front_bias=0.62,
        brake_actuator_map=p_map,
        engine_overrun_map=EngineOverrunMap(is_enabled=False),
    )
    sim = DynamicLapSimulator(params=p)

    d_fl = p_map.pressure_to_demand(14.3)
    d_fr = p_map.pressure_to_demand(45.2)
    d_rl = p_map.pressure_to_demand(9.1)
    d_rr = p_map.pressure_to_demand(28.4)

    st = DynamicVehicleState(
        u_mps=20.0,
        actuator_brake_fl=d_fl,
        actuator_brake_fr=d_fr,
        actuator_brake_rl=d_rl,
        actuator_brake_rr=d_rr,
    )

    # Turn 5 apex entry conditions: high right-side (outside) pressure
    ctrl = DriverControls(
        brake_pressure_fl_bar=14.3,
        brake_pressure_fr_bar=45.2,
        brake_pressure_rl_bar=9.1,
        brake_pressure_rr_bar=28.4,
    )
    derivs = sim.compute_derivatives(st, ctrl)

    # Front right (outside) must have substantially higher torque than front left (inside)
    assert derivs["T_brk_fr"] > derivs["T_brk_fl"] * 2.0
    # Rear right (outside) must have substantially higher torque than rear left (inside)
    assert derivs["T_brk_rr"] > derivs["T_brk_rl"] * 2.0


def test_brake_chain_artifact_integrity(brake_chain_data):
    """Verify data/phase3f_brake_chain.json contains valid metadata, decomposition, and traces."""
    assert brake_chain_data["metadata"]["phase"] == "Phase 3F"
    assert "CF_A" in brake_chain_data["counterfactual_decomposition"]
    assert "CF_B" in brake_chain_data["counterfactual_decomposition"]
    assert "CF_C" in brake_chain_data["counterfactual_decomposition"]
    assert "CF_D" in brake_chain_data["counterfactual_decomposition"]
    assert len(brake_chain_data["time_series_trace"]) > 1000
