"""
tests/test_tire_thermal_and_relaxation.py
=========================================
Tests for Multi-layer thermal dynamics, ideal gas dynamic pressure,
and First-order tire force relaxation ODEs with singularity handling.
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.tire_thermal import (
    TireThermalConfig,
    SingleTireThermalState,
    MultiLayerTireThermalState,
    TireThermalState,
)
from suspensionlab.physics.tire_model import TireRelaxationDynamics


def test_single_tire_thermal_state_evolution():
    cfg = TireThermalConfig(T_ambient=25.0, T_road=30.0, T_opt=85.0)
    state = SingleTireThermalState(T_surf=25.0, T_bulk=25.0, T_gas=25.0, p_bar=1.90)

    # Step under cornering load: Fz=4000 N, Fy=3500 N, lateral slip velocity = 2.0 m/s, vehicle speed = 40 m/s
    dt = 0.05
    for _ in range(100):  # 5.0 seconds of aggressive cornering
        state = state.step(
            config=cfg,
            Fz=4000.0,
            Fx=0.0,
            Fy=3500.0,
            v_slip_x=0.0,
            v_slip_y=2.0,
            v_vehicle=40.0,
            dt=dt,
        )

    # Surface temperature heats up rapidly from frictional work
    assert state.T_surf > 35.0
    # Heat conducts into carcass bulk
    assert state.T_bulk > 25.5
    # Inflation pressure rises with cavity gas temperature via Ideal Gas Law
    assert state.p_bar >= 1.90


def test_multilayer_4wheel_thermal_state_step():
    cfg = TireThermalConfig()
    state = MultiLayerTireThermalState(
        T_surf=np.array([25.0, 25.0, 25.0, 25.0]),
        T_bulk=np.array([25.0, 25.0, 25.0, 25.0]),
        T_gas=np.array([25.0, 25.0, 25.0, 25.0]),
    )

    # Right hand turn: FL (outer front) takes heavy load and slip
    Fz = np.array([5500.0, 1500.0, 4500.0, 1500.0])
    Fx = np.zeros(4)
    Fy = np.array([5000.0, 1200.0, 4000.0, 1200.0])
    vsx = np.zeros(4)
    vsy = np.array([2.5, 0.5, 2.0, 0.5])

    new_state = state.step(cfg, Fz, Fx, Fy, vsx, vsy, v_vehicle=45.0, dt=1.0)

    # Outer tires (FL and RL) heat up significantly more than inner tires
    assert new_state.T_surf[0] > new_state.T_surf[1]
    assert new_state.T_surf[2] > new_state.T_surf[3]

    pressures = new_state.pressures_bar(cfg)
    assert len(pressures) == 4
    assert pressures[0] >= cfg.p_cold_bar


def test_first_order_tire_relaxation_dynamics():
    relax = TireRelaxationDynamics()
    assert relax.Fx == 0.0
    assert relax.Fy == 0.0

    # Step input in target lateral force: Fy_eq = 3000 N, speed = 20 m/s, sigma_y = 0.35 m
    # Time constant tau = sigma / vx = 0.35 / 20 = 0.0175 s
    dt = 0.01
    fy_history = []
    for _ in range(10):
        _, fy = relax.step_time(
            Fx_eq=0.0, Fy_eq=3000.0, v_x=20.0, dt=dt, sigma_x=0.25, sigma_y=0.35
        )
        fy_history.append(fy)

    # Verify smooth exponential convergence toward steady state
    assert fy_history[0] > 0.0
    assert fy_history[-1] > fy_history[0]
    assert math.isclose(fy_history[-1], 3000.0, rel_tol=0.05)


def test_relaxation_zero_speed_regularisation():
    relax = TireRelaxationDynamics()

    # At vehicle standstill (v_x = 0.0 m/s), transport velocity regularisation prevents division by zero
    dFx_dt, dFy_dt = relax.calc_derivatives(
        Fx_eq=1000.0, Fy_eq=2000.0, v_x=0.0, sigma_x=0.25, sigma_y=0.35
    )
    assert np.isfinite(dFx_dt)
    assert np.isfinite(dFy_dt)
    assert dFx_dt > 0.0
    assert dFy_dt > 0.0

    # Distance step
    fx_dist, fy_dist = relax.step_distance(Fx_eq=500.0, Fy_eq=1000.0, ds=0.35, sigma_x=0.35, sigma_y=0.35)
    # After ds = sigma, force reaches approx (1 - 1/e) ~ 63.2% of equilibrium
    assert math.isclose(fy_dist, 1000.0 * (1.0 - math.exp(-1.0)), rel_tol=1e-3)
