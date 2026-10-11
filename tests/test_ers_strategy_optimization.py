"""
tests/test_ers_strategy_optimization.py
=======================================
Tests for 2026 FIA ERS power limits, 7 MJ recharge ceiling, and thermal state.
"""

import pytest
import numpy as np

from suspensionlab.physics.ers_model import (
    ERSConfig,
    ERSState,
    ERSThermalState,
    ERSDeploymentController,
)


def test_ers_config_2026_regulations():
    config = ERSConfig()
    assert config.mgu_k_max_power_w == 350_000.0       # 350 kW primary boost
    assert config.mgu_k_secondary_power_w == 250_000.0 # 250 kW secondary boost
    assert config.max_lap_recharge_j == 7_000_000.0     # 7 MJ recharge ceiling


def test_ers_thermal_state_update():
    thermal = ERSThermalState(battery_temp_c=45.0, mguk_temp_c=65.0)
    assert not thermal.is_derated
    
    # Simulate high sustained power deployment
    thermal.update(deploy_kw=350.0, regen_kw=0.0, dt=10.0)
    assert thermal.battery_temp_c > 45.0
    assert thermal.mguk_temp_c > 65.0
