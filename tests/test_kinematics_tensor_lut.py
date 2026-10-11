"""
tests/test_kinematics_tensor_lut.py
===================================
Tests for 4D Heave x Roll x Steer x Pitch Kinematics Tensor LUT generation,
multilinear interpolation, and explicit out-of-domain policy verification.
"""

import pytest
import numpy as np

from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS
from suspensionlab.physics.kinematics_tensor_lut import (
    build_kinematics_tensor_lut,
    KinematicsTensorLUT,
    CHANNEL_NAMES,
)


def test_build_and_evaluate_4d_tensor_lut():
    lut = build_kinematics_tensor_lut(
        hardpoints=DEFAULT_HARDPOINTS,
        heave_range_mm=(-30.0, 30.0),
        n_heave=5,
        roll_range_deg=(-3.0, 3.0),
        n_roll=5,
        steer_range_deg=(-10.0, 10.0),
        n_steer=5,
        pitch_range_deg=(-1.0, 1.0),
        n_pitch=3,
        mode="cpp",
    )
    assert isinstance(lut, KinematicsTensorLUT)
    assert lut.tensor_data.shape == (5, 5, 5, 3, len(CHANNEL_NAMES))

    # Evaluate at nominal neutral
    res_neutral = lut.evaluate(heave_mm=0.0, roll_deg=0.0, steer_deg=0.0, pitch_deg=0.0)
    assert res_neutral["in_domain"] == 1.0
    assert "camber_l_deg" in res_neutral
    assert "camber_r_deg" in res_neutral
    assert "roll_center_z_mm" in res_neutral
    assert "motion_ratio_l" in res_neutral
    assert "anti_dive_pct" in res_neutral

    # Evaluate at mixed heave + roll + steer + pitch
    res_combined = lut.evaluate(heave_mm=12.5, roll_deg=2.2, steer_deg=4.5, pitch_deg=0.5)
    assert res_combined["in_domain"] == 1.0
    assert isinstance(res_combined["camber_l_deg"], float)
    assert isinstance(res_combined["toe_l_deg"], float)


def test_out_of_domain_policy_enforcement():
    """Verify explicit out-of-domain boundary handling (clamp, extrapolate, raise)."""
    lut = build_kinematics_tensor_lut(
        hardpoints=DEFAULT_HARDPOINTS,
        heave_range_mm=(-20.0, 20.0),
        n_heave=3,
        roll_range_deg=(-2.0, 2.0),
        n_roll=3,
        steer_range_deg=(-5.0, 5.0),
        n_steer=3,
        pitch_range_deg=(-1.0, 1.0),
        n_pitch=3,
        mode="cpp",
    )

    # In-bounds check
    assert lut.is_in_domain(heave_mm=10.0, roll_deg=1.0, steer_deg=2.0, pitch_deg=0.0) is True
    # Out-of-bounds check (heave = 45 mm > 20 mm)
    assert lut.is_in_domain(heave_mm=45.0, roll_deg=0.0, steer_deg=0.0, pitch_deg=0.0) is False

    # 1. Raise policy
    with pytest.raises(ValueError, match="is outside LUT domain"):
        lut.evaluate(heave_mm=45.0, roll_deg=0.0, steer_deg=0.0, pitch_deg=0.0, out_of_bounds="raise")

    # 2. Clamp policy (safe bounds clamping)
    res_clamped = lut.evaluate(heave_mm=45.0, roll_deg=0.0, steer_deg=0.0, pitch_deg=0.0, out_of_bounds="clamp")
    res_boundary = lut.evaluate(heave_mm=20.0, roll_deg=0.0, steer_deg=0.0, pitch_deg=0.0, out_of_bounds="clamp")
    assert res_clamped["in_domain"] == 0.0
    assert abs(res_clamped["camber_l_deg"] - res_boundary["camber_l_deg"]) < 1e-6

    # 3. Extrapolate policy
    res_extrap = lut.evaluate(heave_mm=45.0, roll_deg=0.0, steer_deg=0.0, pitch_deg=0.0, out_of_bounds="extrapolate")
    assert res_extrap["in_domain"] == 0.0
    assert isinstance(res_extrap["camber_l_deg"], float)
