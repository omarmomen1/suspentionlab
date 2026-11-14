"""
tests/test_golden_defaults.py
=============================
Golden baseline physics verification suite for default HandlingParams and canonical vehicle dynamics.
"""

import pytest
import numpy as np

from suspensionlab.physics.handling_model import (
    HandlingParams,
    simulate_maneuver,
    simulate_vehicle_handling,
)
from suspensionlab.physics.vehicle_presets import (
    CANONICAL_PRESETS,
    get_canonical_preset,
)


def test_default_handling_step_steer_steady_state_acceleration():
    """
    Step steer maneuver:
    Input: delta = 2.0 degrees at v = 20.0 m/s with default HandlingParams().
    Assert steady-state lateral acceleration a_y is in [0.48g, 0.56g].
    """
    p = HandlingParams()
    delta_rad = np.radians(2.0)

    # Step steer starting at t = 0.5s with realistic cruise throttle sustaining ~20 m/s
    res = simulate_vehicle_handling(
        p=p,
        v_x_init=20.0,
        steering_func=lambda t: delta_rad if t >= 0.5 else 0.0,
        throttle_func=lambda t: 0.045 if t >= 0.5 else 0.0,
        brake_func=lambda t: 0.0,
        duration=3.0,
        dt=0.01,
    )

    ay_final = res["a_y"][-1]
    g = 9.81
    ay_g = ay_final / g

    assert 0.48 <= ay_g <= 0.56, (
        f"Steady-state lateral acceleration {ay_g:.4f}g is outside expected [0.48g, 0.56g] range."
    )


def test_canonical_vehicle_presets_integrity():
    """Verify that all canonical vehicle presets generate valid simulation parameters."""
    for preset_key, preset in CANONICAL_PRESETS.items():
        assert preset.total_mass > 100.0
        assert 0.40 <= preset.front_weight_dist <= 0.65

        # Check quarter car conversion
        qc_f = preset.to_quarter_car_params("front")
        qc_r = preset.to_quarter_car_params("rear")
        assert qc_f.m_s > 0.0 and qc_r.m_s > 0.0
        assert qc_f.k_w > 0.0 and qc_r.k_w > 0.0

        # Check half car conversion
        hc = preset.to_half_car_params()
        assert hc.m_s == preset.m_s
        assert hc.L == preset.L

        # Check full car conversion
        fc = preset.to_full_car_params()
        assert fc.m_s == preset.m_s
        assert fc.I_x == preset.I_x
        assert fc.tw_f == preset.tw_f

        # Check handling params conversion
        hp = preset.to_handling_params()
        assert hp.m == preset.total_mass
        assert hp.K_spring_f > 0.0
        assert hp.K_arb_f > 0.0


def test_unilateral_tire_liftoff_clamping_and_detection():
    """
    Verify that severe road disturbance (-0.12 m step curb drop) engages unilateral
    tire contact clamping: total vertical force F_z >= 0.0 and tire_liftoff_detected is True.
    """
    from suspensionlab.physics.half_car import HalfCarParams, run_half_car_analysis, RoadProfile
    from suspensionlab.physics.full_car import FourCornerRoadProfile, run_full_car_analysis

    # 1. Half-car unilateral contact verification
    p_hc = HalfCarParams()
    prof_hc = RoadProfile(profile_type="step", amplitude=-0.12, duration=2.0)
    res_hc = run_half_car_analysis(p_hc, prof_hc)

    assert res_hc.tire_liftoff_detected is True, "Half-car failed to detect tire liftoff on -0.12m drop"
    assert res_hc.minimum_Fz_f >= 0.0, f"Half-car minimum front Fz {res_hc.minimum_Fz_f} violated unilateral non-negative contact constraint"
    assert res_hc.minimum_Fz_r >= 0.0, f"Half-car minimum rear Fz {res_hc.minimum_Fz_r} violated unilateral non-negative contact constraint"

    # 2. Full-car unilateral contact verification
    preset = get_canonical_preset("compact_hatchback")
    p_fc = preset.to_full_car_params()
    fc_time = np.linspace(0.0, 2.0, 1000)
    fc_zr = np.where(fc_time >= 0.2, -0.12, 0.0)
    prof_fc = FourCornerRoadProfile(fc_time, fc_zr, fc_zr, fc_zr, fc_zr)
    res_fc = run_full_car_analysis(p_fc, prof_fc)

    assert res_fc.tire_liftoff_detected is True, "Full-car failed to detect tire liftoff on -0.12m drop"
    assert res_fc.minimum_Fz >= 0.0, f"Full-car minimum Fz {res_fc.minimum_Fz} violated unilateral non-negative contact constraint"


def test_heavy_braking_to_standstill():
    """
    Verify that 100% brake application brings the vehicle smoothly down to standstill (~0 m/s)
    without numerical divergence, step-size underflow, or NaN generation in states or accelerations.
    """
    p = HandlingParams()
    res = simulate_vehicle_handling(
        p=p,
        v_x_init=20.0,
        steering_func=lambda t: 0.0,
        throttle_func=lambda t: 0.0,
        brake_func=lambda t: 1.0,
        duration=4.0,
        dt=0.01,
    )

    vx_final = float(res["v_x"][-1])
    assert 0.0 <= vx_final < 0.05, f"Expected vehicle to come to standstill, but v_x final is {vx_final} m/s"
    assert not np.isnan(res["v_x"]).any(), "NaN found in v_x during heavy braking"
    assert not np.isnan(res["a_x"]).any(), "NaN found in a_x during heavy braking"
    assert not np.isnan(res["a_y"]).any(), "NaN found in a_y during heavy braking"


def test_kinematics_cpp_fallback_behavior():
    """
    Verify that kinematics modules gracefully fall back to pure-Python routines
    if compiled C++ binaries are absent, without throwing unhandled exceptions.
    """
    from suspensionlab.physics import kinematics, api_models
    import suspensionlab.physics.handling_model as hm

    assert hasattr(hm, "HAS_CPP_KINEMATICS")
    # Verify api_models safe_generate_kinematic_lut falls back cleanly
    lut = api_models.safe_generate_kinematic_lut(
        topology_type="double_wishbone",
        hardpoints={},
        heave_range=np.linspace(-0.05, 0.05, 11),
        roll_range=np.zeros(11),
    )
    assert "camber" in lut
    assert len(lut["camber"]) == 11
    assert "toe" in lut
