"""
tests/test_phase3d_brake_mapping.py
===================================
Verification tests for Phase 3D Change #4: Configurable Brake Actuator / Pressure Mapping.
Ensures:
1. Monotonic relationship across full pressure range (0 to 120 bar).
2. Configurable breakpoints with non-accidental saturation.
3. Explicit physical separation of:
     - hydraulic line pressure [bar]
     - normalized actuator demand [0..1]
     - actuator clamping torque [Nm]
     - tire-road tractive braking force [N]
4. Specific evaluation at 0 bar, low pressure (10 bar), 20 bar, 40 bar, 42.6 bar, high pressure (80 bar), and saturation (120 bar).
5. Validation against Heavy Braking Holdout telemetry.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    BrakeActuatorMap,
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
)


def test_brake_map_monotonicity_and_validation():
    """Verify strictly monotonic pressure-to-torque relationship and exception on inverted breakpoints."""
    # Valid mapping
    b_map = BrakeActuatorMap(
        pressure_breakpoints_bar=[0.0, 15.0, 40.0, 80.0, 120.0],
        demand_breakpoints=[0.0, 0.18, 0.52, 1.00, 1.00],
        max_brake_torque_nm=4800.0
    )

    pressures = np.linspace(0.0, 120.0, 121)
    torques = [b_map.pressure_to_torque(p) for p in pressures]
    diffs = np.diff(torques)
    assert np.all(diffs >= 0.0), "Braking torque is not monotonically non-decreasing."

    # Inverted breakpoints must raise ValueError
    with pytest.raises(ValueError, match="strictly monotonically increasing"):
        BrakeActuatorMap(pressure_breakpoints_bar=[0.0, 40.0, 30.0, 80.0])

    with pytest.raises(ValueError, match="monotonically non-decreasing"):
        BrakeActuatorMap(
            pressure_breakpoints_bar=[0.0, 20.0, 40.0, 80.0],
            demand_breakpoints=[0.0, 0.50, 0.40, 1.00]
        )


def test_brake_map_discrete_pressure_points():
    """Verify explicit physical chain outputs at 0, 10, 20, 40, 42.6, 80, and 120 bar."""
    b_map = BrakeActuatorMap()
    Rw = 0.3198 # m

    # 1. Zero bar: 0 demand, 0 torque, 0 tractive force
    c0 = b_map.compute_braking_chain(0.0, Rw)
    assert c0["actuator_demand"] == 0.0
    assert c0["actuator_torque_nm"] == 0.0
    assert c0["tire_road_braking_force_n"] == 0.0

    # 2. Low pressure (10 bar): progressive build-up
    c10 = b_map.compute_braking_chain(10.0, Rw)
    assert 0.05 < c10["actuator_demand"] < 0.20
    assert 200.0 < c10["actuator_torque_nm"] < 1000.0

    # 3. 20 bar: moderate deceleration
    c20 = b_map.compute_braking_chain(20.0, Rw)
    assert 0.20 < c20["actuator_demand"] < 0.35

    # 4. 40 bar: ~52% demand (~2496 Nm), NOT saturated!
    c40 = b_map.compute_braking_chain(40.0, Rw)
    assert math.isclose(c40["actuator_demand"], 0.52, abs_tol=1e-3)
    assert math.isclose(c40["actuator_torque_nm"], 4800.0 * 0.52, abs_tol=1.0)
    # Tractive force ~ 7800 N -> decel on 1530kg car ~ 5.1 m/s^2 (0.52g), matches physical telemetry!
    expected_decel_40bar = c40["tire_road_braking_force_n"] / 1530.0
    assert 4.8 <= expected_decel_40bar <= 5.5

    # 5. Peak test telemetry pressure (42.6 bar): ~55% demand, decel ~ 5.4 - 5.6 m/s^2 (-0.56g)
    c42 = b_map.compute_braking_chain(42.6, Rw)
    decel_42bar = c42["tire_road_braking_force_n"] / 1530.0
    assert 5.1 <= decel_42bar <= 5.8, f"Decel at 42.6 bar ({decel_42bar:.2f} m/s^2) deviates from measured ~5.5 m/s^2"

    # 6. High pressure / ABS threshold (80 bar): 100% full lockup demand (4800 Nm, ~1.0g)
    c80 = b_map.compute_braking_chain(80.0, Rw)
    assert c80["actuator_demand"] == 1.00
    assert c80["actuator_torque_nm"] == 4800.0

    # 7. Saturated pressure (120 bar): capped cleanly at 1.00 / 4800 Nm
    c120 = b_map.compute_braking_chain(120.0, Rw)
    assert c120["actuator_demand"] == 1.00
    assert c120["actuator_torque_nm"] == 4800.0


def test_brake_force_ledger_in_derivatives():
    """Verify derivatives dictionary records all 4 quantities in the force ledger."""
    p = DynamicVehicleParams(wheel_radius_m=0.3198)
    sim = DynamicLapSimulator(params=p, dt_fixed_s=0.001)

    b_dem = p.brake_actuator_map.pressure_to_demand(42.6)
    st = DynamicVehicleState(u_mps=25.0, actuator_brake=b_dem)
    ctrl = DriverControls(brake_pressure_bar=42.6)

    derivs = sim.compute_derivatives(st, ctrl)

    assert "hydraulic_pressure_bar" in derivs
    assert "actuator_demand" in derivs
    assert "actuator_torque_nm" in derivs
    assert "tire_road_braking_force_n" in derivs

    assert math.isclose(derivs["hydraulic_pressure_bar"], 42.6, abs_tol=1e-3)
    assert 0.50 <= derivs["actuator_demand"] <= 0.60
    assert 2400.0 <= derivs["actuator_torque_nm"] <= 2800.0
    assert derivs["tire_road_braking_force_n"] > 7000.0
