"""
tests/test_trajectory_optimization.py
======================================
Tests for boundary-constrained racing line and trajectory optimization.
Verifies that:
1. Track boundaries and vehicle envelope constraints are strictly respected.
2. The optimizer reduces peak curvature across corners relative to centerline.
3. The candidate trajectory is physically coupled to the canonical 14-DOF transient solver.
4. Epistemic validity records and provenance are properly propagated.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicTrackModel,
    LapSimulationOutcome,
)
from suspensionlab.physics.trajectory_optimization import (
    TrajectoryBoundaryConstraint,
    TrajectoryCandidate,
    TrajectoryOptimizationInterface,
    BoundedTrajectoryOptimizer,
)
from suspensionlab.physics.validity import PhysicsValidityStatus


def test_trajectory_boundary_constraints():
    """Verify physical track limits and vehicle envelope clamping."""
    c = TrajectoryBoundaryConstraint(
        s_m=100.0,
        width_left_m=6.0,
        width_right_m=5.0,
        vehicle_width_m=1.90,
        safety_margin_m=0.20,
    )
    # Expected limits:
    # max left = 6.0 - 0.95 - 0.20 = 4.85 m
    # max right = 5.0 - 0.95 - 0.20 = 3.85 m
    assert math.isclose(c.max_offset_left_m, 4.85)
    assert math.isclose(c.max_offset_right_m, 3.85)

    # Test clamping
    assert math.isclose(c.clamp(10.0), 4.85)
    assert math.isclose(c.clamp(-10.0), -3.85)
    assert math.isclose(c.clamp(2.0), 2.0)


def test_bounded_trajectory_optimization_coupled_to_transient_sim():
    """Verify that racing line optimization reduces curvature and physically evaluates lap time via 14-DOF sim."""
    # Build a simple S-bend / chicane track
    distances = np.linspace(0.0, 500.0, 101)
    curvatures = np.zeros_like(distances)
    # Corner from 100m to 250m: R = 60m
    for i, s in enumerate(distances):
        if 100.0 <= s <= 250.0:
            curvatures[i] = 1.0 / 60.0

    track = DynamicTrackModel(
        distances=distances,
        curvatures=curvatures,
        track_width_left_m=np.full_like(distances, 5.0),
        track_width_right_m=np.full_like(distances, 5.0),
    )

    params = DynamicVehicleParams()
    sim = DynamicLapSimulator(params, dt_fixed_s=0.001)

    optimizer = BoundedTrajectoryOptimizer(
        lambda_smooth=0.01,
        vehicle_width_m=1.90,
        safety_margin_m=0.20,
        max_iterations=100,
    )

    candidate = optimizer.optimize(
        track,
        sim,
        initial_speed_mps=15.0,
        ay_limit=11.0,
    )

    # 1. Verification of optimization outputs
    assert isinstance(candidate, TrajectoryCandidate)
    assert candidate.converged is True
    assert len(candidate.lateral_offsets_m) == len(distances)

    # 2. Strict boundary enforcement
    max_allowable_offset = 5.0 - 0.5 * 1.90 - 0.20  # 3.85 m
    assert np.all(candidate.lateral_offsets_m <= max_allowable_offset + 1e-4)
    assert np.all(candidate.lateral_offsets_m >= -max_allowable_offset - 1e-4)

    # 3. Curvature smoothing (racing line should cut the corner, reducing peak curvature)
    pk_orig_curv = float(np.max(np.abs(curvatures)))
    pk_opt_curv = float(np.max(np.abs(candidate.curvatures)))
    assert pk_opt_curv <= pk_orig_curv, f"Expected optimized curvature {pk_opt_curv} <= {pk_orig_curv}"
    assert candidate.curvature_reduction_pct >= 0.0

    # 4. Direct physics coupling verification
    assert candidate.lap_result is not None
    assert candidate.lap_result.outcome == LapSimulationOutcome.LAP_COMPLETED
    assert candidate.lap_time_s > 0.0
    assert len(candidate.lap_result.speeds) > 0
    assert not np.any(np.isnan(candidate.lap_result.speeds))

    # 5. Provenance and validity record
    assert candidate.validity_record is not None
    assert candidate.validity_record.status == PhysicsValidityStatus.SIMULATION_ESTIMATE
    assert "data_provenance" in candidate.validity_record.to_dict()

    d = candidate.to_dict()
    assert d["converged"] is True
    assert "lap_result" in d
    assert "lateral_offsets_m" in d
