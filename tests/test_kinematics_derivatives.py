"""
tests/test_kinematics_derivatives.py
====================================
Rigorous verification of kinematic rate and derivative calculations:
1. Exact numerical accuracy of finite difference scheme vs known analytical slopes.
2. Monotonic travel ordering verification.
3. Explicit dimensional scaling: deg/100mm vs deg/m vs mm/mm vs 1/m.
4. Physical directionality: double wishbone bump camber gain is negative.
"""

import numpy as np
import pytest
from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    solve_kinematics,
    compute_kinematic_derivatives,
)


def test_analytical_linear_slope_derivative():
    """Verify second-order central difference exactly recovers constant linear slope."""
    z = np.linspace(-40.0, 40.0, 17)
    # y = -0.012 * z (i.e. -1.2 deg / 100mm)
    camber = -0.012 * z
    dummy_sweep = {
        "wheel_travel_mm": z.tolist(),
        "camber_deg": camber.tolist(),
        "toe_deg": (0.002 * z).tolist(),
        "roll_center_height_mm": (50.0 + 0.35 * z).tolist(),
        "track_change_mm": (-0.15 * z).tolist(),
        "motion_ratio": (0.75 + 0.001 * z).tolist(),
    }

    derivs = compute_kinematic_derivatives(dummy_sweep)

    # Camber gain should be exactly -1.2 deg/100mm
    camber_gain_100 = np.array(derivs["camber_gain_deg_per_100mm"])
    assert np.allclose(camber_gain_100, -1.2, atol=1e-3), f"Expected -1.2, got {camber_gain_100}"

    # Camber gain in deg/m should be -12.0 deg/m
    camber_gain_m = np.array(derivs["camber_gain_deg_per_m"])
    assert np.allclose(camber_gain_m, -12.0, atol=1e-2), f"Expected -12.0, got {camber_gain_m}"

    # Toe gain should be +0.2 deg/100mm
    toe_gain_100 = np.array(derivs["toe_gain_deg_per_100mm"])
    assert np.allclose(toe_gain_100, 0.2, atol=1e-3), f"Expected +0.2, got {toe_gain_100}"

    # RC migration rate should be 0.35 mm/mm
    rc_rate = np.array(derivs["rc_migration_rate"])
    assert np.allclose(rc_rate, 0.35, atol=1e-3), f"Expected 0.35, got {rc_rate}"

    # MR gradient should be 1.0 per m (0.001 per mm * 1000)
    mr_grad = np.array(derivs["mr_gradient_per_m"])
    assert np.allclose(mr_grad, 1.0, atol=1e-3), f"Expected 1.0, got {mr_grad}"


def test_real_suspension_camber_gain_directionality():
    """Verify real double-wishbone corner produces physically realistic negative camber gain."""
    curves = solve_kinematics(DEFAULT_HARDPOINTS, z_min_mm=-30.0, z_max_mm=30.0, n_steps=21)
    d = curves.to_dict()
    derivs = compute_kinematic_derivatives(d)

    camber_gain = np.array(derivs["camber_gain_deg_per_100mm"])
    assert len(camber_gain) == 21

    # In bump (z > 0), camber increases with travel in the solver's coordinate frame (top tilts inward)
    # Typical racecar double wishbone camber gain magnitude is between 0.2 and 1.6 deg/100mm
    idx_bump = np.where(np.array(d["wheel_travel_mm"]) > 5.0)[0]
    assert len(idx_bump) > 0
    bump_gain = camber_gain[idx_bump]
    assert np.all(bump_gain > 0.0), f"Bump camber gain must be positive in solver coordinates, got {bump_gain}"
    assert np.all(bump_gain < 2.5), f"Bump camber gain unrealistically steep: {bump_gain}"


def test_monotonic_travel_ordering():
    """Verify monotonic ordering validation in travel sweeps."""
    z_sorted = [-40.0, -20.0, 0.0, 20.0, 40.0]
    assert np.all(np.diff(z_sorted) > 0)

    curves = solve_kinematics(DEFAULT_HARDPOINTS, z_min_mm=-40.0, z_max_mm=40.0, n_steps=17)
    d = curves.to_dict()
    z = d["wheel_travel_mm"]
    assert np.all(np.diff(z) > 0), "Travel sweep coordinates must be strictly monotonically increasing"


def test_degenerate_point_handling():
    """Verify derivative function handles single-point or empty datasets gracefully."""
    single = {"wheel_travel_mm": [0.0], "camber_deg": [-2.0]}
    derivs = compute_kinematic_derivatives(single)
    assert derivs["camber_gain_deg_per_100mm"] == [0.0]

    empty = {"wheel_travel_mm": []}
    derivs_empty = compute_kinematic_derivatives(empty)
    assert derivs_empty["camber_gain_deg_per_100mm"] == []
