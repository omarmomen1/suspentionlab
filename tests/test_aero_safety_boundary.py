"""
tests/test_aero_safety_boundary.py
==================================
Rigorous verification of the 20mm aerodynamic safety boundary:
1. MultidimensionalAeroMap.check_bounds strictly rejects RH < 20mm
2. Coupled vehicle equilibrium flags EXTRAPOLATED when 1mm < RH_front < 20mm
3. Coupled vehicle equilibrium flags UNSUPPORTED and is_valid=False when bottomed out
4. High ride height (> 20mm) remains MODEL_SUPPORTED and valid
"""

import pytest
import numpy as np

from suspensionlab.physics.suspension_aero_coupling import (
    MultidimensionalAeroMap,
    CoupledVehicleModel,
    SuspensionConfig,
    ActiveAeroMode,
)
from suspensionlab.physics.lap_sim import MassProperties
from suspensionlab.physics.validity import PhysicsValidityStatus


def test_aero_map_check_bounds_boundary():
    """Verify that MultidimensionalAeroMap enforces rh_min_mm >= 20.0 mm."""
    aero = MultidimensionalAeroMap()
    assert aero.rh_min_mm == 20.0

    # Operating at 22 mm front, 40 mm rear is valid
    assert aero.check_bounds(front_rh_mm=22.0, rear_rh_mm=40.0, pitch_deg=0.0, yaw_deg=0.0) is True

    # Operating at 18 mm front (< 20mm boundary) is strictly invalid
    assert aero.check_bounds(front_rh_mm=18.0, rear_rh_mm=40.0, pitch_deg=0.0, yaw_deg=0.0) is False

    # Operating at 15 mm rear (< 20mm boundary) is strictly invalid
    assert aero.check_bounds(front_rh_mm=25.0, rear_rh_mm=15.0, pitch_deg=0.0, yaw_deg=0.0) is False


def test_coupled_solver_extrapolated_below_20mm():
    """Verify that when equilibrium pulls front ride height into (1mm, 20mm), status is EXTRAPOLATED."""
    mp = MassProperties(total_mass=800.0, wheelbase=2.7, track_front=1.6, track_rear=1.6)
    # Soft springs and low static ride height (22mm) so aero downforce pulls front RH into 10-18mm
    sus = SuspensionConfig(
        k_spring_front=35000.0,
        k_spring_rear=45000.0,
        ride_height_front=28.0,
        ride_height_rear=50.0,
    )
    aero = MultidimensionalAeroMap(cl_base=3.2, cd_base=1.1)
    model = CoupledVehicleModel(mp, aero, sus, tol=0.05, max_iter=25, relaxation_alpha=0.5)

    state = model.solve(v=28.0, ax=0.0, ay=0.0, active_aero_mode=ActiveAeroMode.Z_MODE)

    # Front ride height should have dropped below 20mm but not zero
    assert 1.0 < state.rh_front_mm < 20.0, f"Expected 1 < RH < 20, got {state.rh_front_mm:.2f} mm"
    assert state.validity_record is not None
    assert state.validity_record.status == PhysicsValidityStatus.EXTRAPOLATED
    assert any("20.0 mm" in w for w in state.validity_record.warnings)


def test_coupled_solver_unsupported_on_bottoming():
    """Verify that severe downforce bottoming out flags UNSUPPORTED and is_valid=False."""
    mp = MassProperties(total_mass=800.0, wheelbase=2.7, track_front=1.6, track_rear=1.6)
    # Extremely soft springs (10 kN/m) and massive speed (80 m/s) forces complete chassis bottoming
    sus = SuspensionConfig(
        k_spring_front=10000.0,
        k_spring_rear=15000.0,
        ride_height_front=15.0,
        ride_height_rear=30.0,
    )
    aero = MultidimensionalAeroMap(cl_base=4.0, cd_base=1.2)
    model = CoupledVehicleModel(mp, aero, sus, tol=0.05, max_iter=25, relaxation_alpha=0.5)

    state = model.solve(v=80.0, ax=0.0, ay=0.0, active_aero_mode=ActiveAeroMode.Z_MODE)

    assert state.bottomed_out is True
    assert state.validity_record is not None
    assert state.validity_record.status == PhysicsValidityStatus.UNSUPPORTED
    assert state.validity_record.is_valid is False
    assert any("bottomed out" in w.lower() for w in state.validity_record.warnings)


def test_coupled_solver_supported_above_20mm():
    """Verify that stiff setup maintaining RH >= 20mm is MODEL_SUPPORTED and valid."""
    mp = MassProperties(total_mass=800.0, wheelbase=2.7, track_front=1.6, track_rear=1.6)
    sus = SuspensionConfig(
        k_spring_front=80000.0,
        k_spring_rear=80000.0,
        ride_height_front=35.0,
        ride_height_rear=60.0,
    )
    aero = MultidimensionalAeroMap(cl_base=2.5, cd_base=1.0)
    model = CoupledVehicleModel(mp, aero, sus, tol=0.05, max_iter=25, relaxation_alpha=0.5)

    state = model.solve(v=45.0, ax=0.0, ay=0.0, active_aero_mode=ActiveAeroMode.Z_MODE)

    assert state.rh_front_mm >= 20.0
    assert state.validity_record is not None
    assert state.validity_record.status == PhysicsValidityStatus.MODEL_SUPPORTED
    assert state.validity_record.is_valid is True
