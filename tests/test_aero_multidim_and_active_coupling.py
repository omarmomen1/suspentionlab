"""
tests/test_aero_multidim_and_active_coupling.py
===============================================
Tests for multidimensional aero maps, 2026 active aero (Z-Mode, X-Mode),
and closed-loop under-relaxed equilibrium coupling.
"""

import pytest
import numpy as np

from suspensionlab.physics.suspension_aero_coupling import (
    MultidimensionalAeroMap,
    ActiveAeroMode,
    CoupledVehicleModel,
    SuspensionConfig,
)
from suspensionlab.physics.lap_sim import MassProperties


def test_multidimensional_aero_map_evaluation():
    aero = MultidimensionalAeroMap(cl_base=3.2, cd_base=1.1)
    
    # Baseline Z-Mode
    cl_z, cd_z, cop_z = aero.evaluate(front_rh_mm=25.0, rear_rh_mm=50.0, pitch_deg=0.5, yaw_deg=2.0, mode=ActiveAeroMode.Z_MODE)
    assert cl_z > 2.0
    assert cd_z > 0.8
    
    # Low-drag X-Mode
    cl_x, cd_x, cop_x = aero.evaluate(front_rh_mm=25.0, rear_rh_mm=50.0, pitch_deg=0.5, yaw_deg=2.0, mode=ActiveAeroMode.X_MODE)
    assert cl_x < cl_z * 0.7  # Downforce shed
    assert cd_x < cd_z * 0.6  # Drag significantly reduced


def test_closed_loop_suspension_aero_coupling_convergence():
    mp = MassProperties(total_mass=800.0, wheelbase=2.7, track_front=1.6, track_rear=1.6)
    sus = SuspensionConfig(k_spring_front=45000.0, k_spring_rear=45000.0, ride_height_front=28.0, ride_height_rear=55.0)
    aero = MultidimensionalAeroMap()
    
    model = CoupledVehicleModel(mp, aero, sus, tol=0.05, max_iter=25, relaxation_alpha=0.5)
    state = model.solve(v=65.0, ax=0.0, ay=12.0, yaw_deg=1.5, active_aero_mode=ActiveAeroMode.Z_MODE)
    
    assert state.converged
    assert state.n_iterations < 20
    assert state.rh_front_mm < 28.0  # Heave squatted down
    assert state.aero_df_total_n > 5000.0
    assert state.residual_norm < 0.05
