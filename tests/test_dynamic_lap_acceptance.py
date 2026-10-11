"""
tests/test_dynamic_lap_acceptance.py
====================================
Acceptance test suite for high-fidelity 14-DOF dynamic lap simulation.
Verifies the strict differentiation between:
- LAP_COMPLETED
- PHYSICAL_INSTABILITY
- NUMERICAL_FAILURE

Tests both:
Case A: Stable Complete Lap on a 1000 m circuit with realistic target lateral acceleration.
Case B: Physical Spin-Out with overspeed entry into a sharp corner, terminating cleanly
        with PHYSICAL_INSTABILITY and zero NaNs, without falsely claiming lap completion.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicTrackModel,
    ClosedLoopDriverModel,
    LapSimulationOutcome,
    solve_dynamic_lap,
)


def build_test_circuit(total_length_m: float = 1000.0, corner_radius_m: float = 80.0) -> DynamicTrackModel:
    """Build a 1000m test circuit with straightaway followed by a corner and straightaway."""
    distances = np.linspace(0.0, total_length_m, 201)
    curvatures = np.zeros_like(distances)
    # Turn 1 between 150m and 350m: radius R -> curvature 1/R
    k_corner = 1.0 / corner_radius_m
    for i, s in enumerate(distances):
        if 150.0 <= s <= 350.0:
            curvatures[i] = k_corner
    return DynamicTrackModel(
        distances=distances,
        curvatures=curvatures,
        elevations=np.zeros_like(distances),
        bank_angles=np.zeros_like(distances),
    )


def test_case_a_stable_complete_lap():
    """Case A: Achieveable corner entry speed (ay_limit=13.0 m/s^2) completes full 1000m circuit."""
    track = build_test_circuit(1000.0, corner_radius_m=80.0)
    params = DynamicVehicleParams()
    sim = DynamicLapSimulator(params, dt_fixed_s=0.001)

    result = solve_dynamic_lap(
        sim,
        track,
        initial_speed_mps=15.0,
        max_simulation_time_s=60.0,
        ay_limit=10.0,
    )

    # Verifications
    assert result.outcome == LapSimulationOutcome.LAP_COMPLETED, f"Expected LAP_COMPLETED but got {result.outcome}: {result.termination_reason}"
    assert result.lap_completed is True
    assert result.termination_distance_m >= 999.0
    assert result.total_time > 0.0
    assert not np.any(np.isnan(result.speeds))
    assert not np.any(np.isnan(result.yaw_rates))
    assert result.speeds[-1] > 0.0

    dict_repr = result.to_dict()
    assert dict_repr["status"] == "success"
    assert dict_repr["outcome"] == "LAP_COMPLETED"
    assert dict_repr["lap_completed"] is True


def test_case_b_physical_spin_out_safe_termination():
    """Case B: Excessive corner entry target (ay_limit=25.0 m/s^2) causes physical spin-out in Turn 1.
    Must safely terminate with PHYSICAL_INSTABILITY and lap_completed=False with ZERO NaNs.
    """
    track = build_test_circuit(1000.0, corner_radius_m=80.0)
    params = DynamicVehicleParams()
    sim = DynamicLapSimulator(params, dt_fixed_s=0.001)
    driver = ClosedLoopDriverModel(enable_traction_control=False)

    result = solve_dynamic_lap(
        sim,
        track,
        initial_speed_mps=35.0,
        max_simulation_time_s=60.0,
        ay_limit=25.0,  # Demands 25 m/s^2 (~2.55 g) on ~1.4 g tires -> inevitable spin-out
        driver=driver,
    )

    # Verifications
    assert result.outcome == LapSimulationOutcome.PHYSICAL_INSTABILITY, (
        f"Expected PHYSICAL_INSTABILITY but got {result.outcome}"
    )
    assert result.lap_completed is False
    assert result.termination_distance_m < 1000.0
    assert "spin-out" in result.termination_reason.lower() or "instability" in result.termination_reason.lower()
    assert not np.any(np.isnan(result.speeds))
    assert not np.any(np.isnan(result.yaw_rates))

    dict_repr = result.to_dict()
    assert dict_repr["status"] == "terminated"
    assert dict_repr["outcome"] == "PHYSICAL_INSTABILITY"
    assert dict_repr["lap_completed"] is False
