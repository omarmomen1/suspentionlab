"""
tests/test_physics_negative_guards.py
======================================
Tests for physical boundary guards, input sanitization,
and singularity handling across models (Finding 73).
"""


import math
import pytest
import numpy as np

from suspensionlab.physics.quarter_car import QuarterCarParams, run_quarter_car_analysis, RoadProfile
from suspensionlab.physics.lap_sim import LapSimVehicle, MassProperties
from suspensionlab.physics.magic_formula import TireCoeffs, calc_tire_forces
from suspensionlab.physics.telemetry_health import assess_telemetry_health


def test_negative_and_zero_mass_raises_error():
    with pytest.raises(ValueError):
        QuarterCarParams(m_s=-500.0)

    with pytest.raises(ValueError):
        QuarterCarParams(m_s=0.0)

    with pytest.raises(ValueError):
        QuarterCarParams(m_u=-40.0)


def test_invalid_motion_ratio_raises_error():
    with pytest.raises(ValueError):
        QuarterCarParams(MR=-0.5)

    with pytest.raises(ValueError):
        QuarterCarParams(MR=0.0)



def test_negative_stiffness_and_damping_raises_error():
    with pytest.raises(ValueError):
        QuarterCarParams(k_s=-1000.0)

    with pytest.raises(ValueError):
        QuarterCarParams(c=-50.0)



def test_zero_and_negative_wheelbase_raises_error():
    with pytest.raises(ValueError):
        MassProperties(wheelbase=0.0)

    with pytest.raises(ValueError):
        MassProperties(wheelbase=-2.5)

    with pytest.raises(ValueError):
        MassProperties(total_mass=-100.0)


def test_negative_tire_load_returns_zero_force():
    from suspensionlab.physics.magic_formula import _calc_tire_forces_fast, TireCoeffs
    coeffs = TireCoeffs().to_array()
    # Normal load Fz <= 0 must strictly return 0.0 force without NaN/Inf
    fx, fy = _calc_tire_forces_fast(Fz=-100.0, alpha_rad=0.1, kappa=0.05, camber_rad=0.0, coeffs=coeffs)
    assert fx == 0.0
    assert fy == 0.0



def test_nan_and_inf_telemetry_health_blockers():
    bad_telemetry = {
        "time": [0.0, 0.01, 0.02, 0.03, 0.04],
        "speed": [np.nan, np.nan, np.nan, np.nan, np.nan],
        "lat_g": [np.inf, -np.inf, np.nan, 0.0, 0.0],
    }
    health = assess_telemetry_health(bad_telemetry, time_channel=bad_telemetry["time"])
    assert not health.can_proceed
    assert health.is_blocked
    assert len(health.blocking_reasons) > 0


def test_extreme_damper_velocity_and_road_spike_bounded():
    p = QuarterCarParams()
    extreme_profile = RoadProfile(profile_type="step", amplitude=1.0, duration=1.0)
    result = run_quarter_car_analysis(p, extreme_profile)
    assert all(math.isfinite(val) for val in result.z_s)
    assert all(math.isfinite(val) for val in result.ddz_s)
    assert result.peak_susp_travel > 0.0
