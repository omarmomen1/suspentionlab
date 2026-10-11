"""
tests/test_quarter_car_bump_stop.py
===================================
Rigorous verification & validation suite for Progressive Bump Stop mechanics:
1. Exact backward compatibility with default bump_stop_rate = 0.0
2. Inactive regime when suspension displacement is within clearance gap
3. Progressive force engagement when deflection exceeds bump stop gap
4. Travel limiting effect: Bump stops strictly reduce peak suspension displacement
5. Acceleration spike: Severe bump impact increases peak sprung mass acceleration
"""

import pytest
import numpy as np

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis,
)


def test_bump_stop_default_disabled_backward_compatibility():
    """Verify that default QuarterCarParams has bump_stop_rate=0.0 and zero bump stop forces."""
    p_default = QuarterCarParams()
    assert p_default.bump_stop_rate == 0.0

    profile = RoadProfile(profile_type="step", amplitude=0.04, duration=3.0)
    res = run_quarter_car_analysis(p_default, profile)

    assert res.bump_stop_engaged is False
    assert np.all(res.bump_stop_force == 0.0)


def test_bump_stop_inactive_within_clearance_gap():
    """Verify that small excitations staying inside the bump stop clearance gap produce zero bump stop force."""
    # 35mm gap, small 15mm step
    p = QuarterCarParams(
        bump_stop_gap=0.035,
        bump_stop_rate=80000.0,
        bump_stop_exp=40.0,
    )
    profile = RoadProfile(profile_type="step", amplitude=0.015, duration=2.0)
    res = run_quarter_car_analysis(p, profile)

    # Maximum deflection should not exceed 35mm
    max_travel = np.max(np.abs(res.susp_travel))
    assert max_travel < 0.035

    assert res.bump_stop_engaged is False
    assert np.all(res.bump_stop_force == 0.0)


def test_bump_stop_engagement_and_travel_reduction():
    """Verify that under severe excitation exceeding gap, bump stops engage and reduce suspension compression travel."""
    # Without bump stops (linear only)
    p_linear = QuarterCarParams(bump_stop_rate=0.0)

    # With progressive bump stop (30mm gap, 100 kN/m rate)
    p_bumpstop = QuarterCarParams(
        bump_stop_gap=0.030,
        bump_stop_rate=100000.0,
        bump_stop_exp=40.0,
    )

    # Severe 80mm step bump excitation
    profile = RoadProfile(profile_type="step", amplitude=0.080, duration=2.0)

    res_linear = run_quarter_car_analysis(p_linear, profile)
    res_bumpstop = run_quarter_car_analysis(p_bumpstop, profile)

    # Bump stop must engage
    assert res_bumpstop.bump_stop_engaged is True
    assert np.max(np.abs(res_bumpstop.bump_stop_force)) > 100.0

    # Progressive bump stop must restrict maximum suspension travel
    max_travel_linear = np.max(np.abs(res_linear.susp_travel))
    max_travel_bumpstop = np.max(np.abs(res_bumpstop.susp_travel))
    assert max_travel_bumpstop < max_travel_linear

    # Sprung mass acceleration increases due to bump stop stiffness impact
    max_accel_linear = np.max(np.abs(res_linear.ddz_s))
    max_accel_bumpstop = np.max(np.abs(res_bumpstop.ddz_s))
    assert max_accel_bumpstop > max_accel_linear
