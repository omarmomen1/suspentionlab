"""
tests/test_phase3f_low_pressure_map.py
======================================
Test Suite 4 for Phase 3F: Low-Pressure Actuator Mapping and Monotonicity.
"""

from pathlib import Path
import pytest
import numpy as np

from suspensionlab.physics.dynamic_lap_sim import (
    BrakeActuatorMap,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_brake_actuator_map_monotonicity_and_bounds():
    """Verify BrakeActuatorMap enforces strictly increasing pressures and non-decreasing demands."""
    b_map = BrakeActuatorMap(
        pressure_breakpoints_bar=[0.0, 15.0, 40.0, 80.0, 120.0],
        demand_breakpoints=[0.0, 0.18, 0.52, 1.00, 1.00],
        max_brake_torque_nm=4800.0,
    )

    test_pressures = [0.0, 5.0, 10.0, 14.3, 15.0, 25.0, 40.0, 60.0, 80.0, 120.0, 150.0]
    demands = [b_map.pressure_to_demand(p) for p in test_pressures]
    torques = [b_map.pressure_to_torque(p) for p in test_pressures]

    # Demands and torques must be monotonically non-decreasing
    for i in range(len(demands) - 1):
        assert demands[i] <= demands[i+1], f"Demand decreased from {demands[i]} to {demands[i+1]}"
        assert torques[i] <= torques[i+1], f"Torque decreased from {torques[i]} to {torques[i+1]}"

    # Bounds check
    assert demands[0] == 0.0
    assert demands[-1] <= 1.0
    assert torques[-1] <= 4800.0


def test_corner_braking_chain_linear_scaling():
    """Verify compute_corner_braking_chain produces physically consistent forces and clamp loads."""
    b_map = BrakeActuatorMap()
    res = b_map.compute_corner_braking_chain(
        p_bar=15.0,
        corner_max_torque_nm=1488.0,
        wheel_radius_m=0.3198,
    )

    assert res["hydraulic_pressure_bar"] == 15.0
    assert pytest.approx(res["actuator_demand"], rel=1e-3) == 0.18
    expected_torque = 0.18 * 1488.0
    assert pytest.approx(res["brake_torque_nm"], rel=1e-3) == expected_torque
    expected_fx = expected_torque / 0.3198
    assert pytest.approx(res["wheel_longitudinal_force_n"], rel=1e-3) == expected_fx
    assert res["clamp_force_n"] > 0.0


def test_invalid_breakpoints_raise_validation_error():
    """Verify that non-monotonic breakpoint definitions are caught by constructor."""
    with pytest.raises(ValueError):
        BrakeActuatorMap(pressure_breakpoints_bar=[0.0, 20.0, 15.0])

    with pytest.raises(ValueError):
        BrakeActuatorMap(
            pressure_breakpoints_bar=[0.0, 15.0, 40.0],
            demand_breakpoints=[0.0, 0.5, 0.3],
        )
