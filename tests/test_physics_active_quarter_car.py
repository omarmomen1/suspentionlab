"""
tests/test_physics_active_quarter_car.py
Unit tests for the active quarter car suspension model.
"""
import pytest
import numpy as np
from suspensionlab.physics.quarter_car import RoadProfile
from suspensionlab.physics.active_quarter_car import (
    ActiveQuarterCarParams,
    simulate_active_time_response,
)

def test_active_quarter_car_simulation():
    # Setup test parameters
    params = ActiveQuarterCarParams(
        m_s=300.0,
        m_u=35.0,
        k_s=25000.0,
        c=2000.0,
        k_t=200000.0,
        MR=1.0,
        c_t=0.0,
        c_sky=4000.0,
        c_min=500.0
    )
    # Simple step road profile
    road = RoadProfile(profile_type="step", amplitude=0.05, duration=2.0)
    
    # Run the simulation
    result = simulate_active_time_response(params, road, t_eval_dt=0.01)
    
    # Check outputs are correct types and shapes
    assert result.time is not None
    assert len(result.time) > 0
    assert len(result.time) == len(result.z_s)
    assert len(result.z_u) == len(result.time)
    
    # Ensure reasonable values (e.g. suspension travel is calculated)
    assert hasattr(result, "rms_body_accel")
    assert result.rms_body_accel > 0
    assert result.peak_susp_travel > 0
    
    # Test Skyhook Logic path implicitly (velocity signs crossing) by simulating an ISO road
    road_iso = RoadProfile(profile_type="iso8608", duration=1.0)
    result_iso = simulate_active_time_response(params, road_iso, t_eval_dt=0.01)
    assert result_iso.rms_body_accel > 0
