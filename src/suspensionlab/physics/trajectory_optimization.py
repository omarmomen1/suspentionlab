"""
physics/trajectory_optimization.py
==================================
SuspensionLab PRO — Dynamic Trajectory & Racing Line Optimization Subsystem

Implements the boundary-constrained optimal racing line optimization pipeline.
Couples track limits, curvature smoothing, and the canonical 14-DOF transient
vehicle dynamics solver to evaluate physical dynamic viability and minimum lap time.

Mathematical Formulation:
-------------------------
For a track with centerline coordinate s and centerline curvature kappa_0(s),
a vehicle racing line is parameterized by lateral offset n(s):

  Track boundaries:
    -width_right(s) + half_width <= n(s) <= width_left(s) - half_width

  Trajectory Curvature (Frenet-Serret frame approximation):
    kappa_traj(s) = (kappa_0(s) + d^2n/ds^2) / (1 - n(s) * kappa_0(s))

  Curvature & Kinetic Energy Minimization Objective:
    min ∫ [ kappa_traj(s)^2 + lambda_smooth * (dn/ds)^2 ] ds

  Physics Evaluation Coupling:
    Trajectory is synthesized into a DynamicTrackModel and evaluated through
    the authoritative 14-DOF transient ODE simulation (solve_dynamic_lap).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicTrackModel,
    DynamicLapResult,
    DynamicVehicleParams,
    solve_dynamic_lap,
)
from suspensionlab.physics.validity import (
    PhysicsValidityRecord,
    PhysicsValidityStatus,
)


from scipy.interpolate import CubicSpline


@dataclass
class TrajectoryBoundaryConstraint:
    """Track width limits and vehicle envelope constraints along track distance."""
    s_m: float
    width_left_m: float = 6.0
    width_right_m: float = 6.0
    vehicle_width_m: float = 1.90
    safety_margin_m: float = 0.20

    @property
    def max_offset_left_m(self) -> float:
        """Maximum allowable lateral offset to the left without exceeding track limits."""
        return max(0.0, self.width_left_m - 0.5 * self.vehicle_width_m - self.safety_margin_m)

    @property
    def max_offset_right_m(self) -> float:
        """Maximum allowable lateral offset to the right (-n direction)."""
        return max(0.0, self.width_right_m - 0.5 * self.vehicle_width_m - self.safety_margin_m)

    def clamp(self, offset_m: float) -> float:
        """Enforce strict physical track boundaries on a proposed lateral offset."""
        return float(np.clip(offset_m, -self.max_offset_right_m, self.max_offset_left_m))


@dataclass
class TrajectoryCandidate:
    """Optimized vehicle path candidate with lateral offsets, curvature, and physics telemetry."""
    distances: np.ndarray
    lateral_offsets_m: np.ndarray
    curvatures: np.ndarray
    curvature_reduction_pct: float = 0.0
    lap_result: Optional[DynamicLapResult] = None
    lap_time_s: float = 0.0
    converged: bool = True
    iterations: int = 0
    validity_record: Optional[PhysicsValidityRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "converged": self.converged,
            "iterations": self.iterations,
            "lap_time_s": self.lap_time_s,
            "curvature_reduction_pct": self.curvature_reduction_pct,
            "distances": self.distances.tolist(),
            "lateral_offsets_m": self.lateral_offsets_m.tolist(),
            "curvatures": self.curvatures.tolist(),
            "lap_result": self.lap_result.to_dict() if self.lap_result else None,
            "validity_record": self.validity_record.to_dict() if self.validity_record else None,
        }


class TrajectoryOptimizationInterface(ABC):
    """Authoritative interface coupling racing line generation to transient vehicle models."""

    @abstractmethod
    def optimize(
        self,
        track: DynamicTrackModel,
        simulator: DynamicLapSimulator,
        initial_speed_mps: float = 30.0,
    ) -> TrajectoryCandidate:
        """Generate and evaluate an optimal racing line across physical vehicle dynamics."""
        pass


class BoundedTrajectoryOptimizer(TrajectoryOptimizationInterface):
    """Boundary-constrained optimal racing line optimizer coupled to 14-DOF dynamic solver.

    Minimizes path curvature within physical track limit boundaries, constructs
    the effective dynamic trajectory track model, and evaluates it through
    the transient vehicle multi-body simulation.
    """

    def __init__(
        self,
        lambda_smooth: float = 0.01,
        vehicle_width_m: float = 1.90,
        safety_margin_m: float = 0.20,
        max_iterations: int = 150,
    ):
        self.lambda_smooth = lambda_smooth
        self.vehicle_width_m = vehicle_width_m
        self.safety_margin_m = safety_margin_m
        self.max_iterations = max_iterations

    def compute_trajectory_curvature(
        self,
        s_arr: np.ndarray,
        kappa_center: np.ndarray,
        n_offsets: np.ndarray,
        spline: Optional[CubicSpline] = None,
    ) -> np.ndarray:
        """Calculate effective trajectory curvature in the curvilinear Frenet-Serret frame."""
        n_pts = len(s_arr)
        if n_pts < 3:
            return kappa_center.copy()

        if spline is not None:
            d2n_ds2 = spline(s_arr, 2)
        else:
            dn_ds = np.gradient(n_offsets, s_arr)
            d2n_ds2 = np.gradient(dn_ds, s_arr)

        denom = np.maximum(1.0 - n_offsets * kappa_center, 0.1)
        kappa_traj = (kappa_center + d2n_ds2) / denom
        return kappa_traj

    def optimize(
        self,
        track: DynamicTrackModel,
        simulator: DynamicLapSimulator,
        initial_speed_mps: float = 30.0,
        ay_limit: float = 12.0,
    ) -> TrajectoryCandidate:
        """Solve bounded curvature minimization and evaluate via the transient 14-DOF ODE solver."""
        s_arr = track.distances
        n_pts = len(s_arr)
        kappa_0 = track.curvatures
        total_len = track.total_length_m

        tw_l = track.track_width_left_m if hasattr(track, "track_width_left_m") else np.full(n_pts, 6.0)
        tw_r = track.track_width_right_m if hasattr(track, "track_width_right_m") else np.full(n_pts, 6.0)

        # Discrete bounds
        discrete_bounds = [
            TrajectoryBoundaryConstraint(
                s_m=float(s_arr[i]),
                width_left_m=float(tw_l[i]),
                width_right_m=float(tw_r[i]),
                vehicle_width_m=self.vehicle_width_m,
                safety_margin_m=self.safety_margin_m,
            )
            for i in range(n_pts)
        ]

        is_closed = n_pts >= 2 and math.isclose(s_arr[0], 0.0) and math.isclose(s_arr[-1], total_len)

        # Knot parameterization (spaced ~30-50m)
        n_knots = max(8, min(35, int(np.ceil(total_len / 35.0)) + 1))
        knots_s = np.linspace(s_arr[0], s_arr[-1], n_knots)

        knot_bounds = []
        for ks in knots_s:
            wl = float(np.interp(ks, s_arr, tw_l))
            wr = float(np.interp(ks, s_arr, tw_r))
            c = TrajectoryBoundaryConstraint(
                s_m=float(ks),
                width_left_m=wl,
                width_right_m=wr,
                vehicle_width_m=self.vehicle_width_m,
                safety_margin_m=self.safety_margin_m,
            )
            knot_bounds.append((-c.max_offset_right_m, c.max_offset_left_m))

        bc_type = "periodic" if is_closed else "natural"
        ds = np.gradient(s_arr)

        def objective(knots_n: np.ndarray) -> float:
            k_n = knots_n.copy()
            if is_closed:
                k_n[-1] = k_n[0]
            cs = CubicSpline(knots_s, k_n, bc_type=bc_type)
            n_eval = cs(s_arr)
            d2n_eval = cs(s_arr, 2)
            dn_eval = cs(s_arr, 1)
            denom = np.maximum(1.0 - n_eval * kappa_0, 0.1)
            k_traj = (kappa_0 + d2n_eval) / denom
            curv_cost = float(np.sum((k_traj ** 2) * ds))
            smooth_cost = float(np.sum((dn_eval ** 2) * ds) * self.lambda_smooth)
            return curv_cost + smooth_cost

        n0 = np.zeros(n_knots)
        res = minimize(
            objective,
            n0,
            method="L-BFGS-B",
            bounds=knot_bounds,
            options={"maxiter": self.max_iterations, "ftol": 1e-6},
        )

        res_x = res.x.copy()
        if is_closed:
            res_x[-1] = res_x[0]
        cs_opt = CubicSpline(knots_s, res_x, bc_type=bc_type)
        n_opt = cs_opt(s_arr)
        # Ensure strict discrete bounds clamping
        for i in range(n_pts):
            n_opt[i] = discrete_bounds[i].clamp(n_opt[i])

        k_opt = self.compute_trajectory_curvature(s_arr, kappa_0, n_opt, cs_opt)

        pk_k_orig = float(np.max(np.abs(kappa_0))) if np.any(kappa_0) else 1e-4
        pk_k_opt = float(np.max(np.abs(k_opt)))
        k_reduc = max(0.0, (pk_k_orig - pk_k_opt) / max(pk_k_orig, 1e-6) * 100.0)

        # 3. Direct Physical Coupling: Synthesize optimized trajectory into dynamic track model
        # and evaluate with the 14-DOF transient vehicle ODE solver
        traj_track = DynamicTrackModel(
            distances=s_arr,
            curvatures=k_opt,
            elevations=track.elevations if hasattr(track, "elevations") else None,
            bank_angles=track.bank_angles if hasattr(track, "bank_angles") else None,
            track_width_left_m=tw_l - n_opt,
            track_width_right_m=tw_r + n_opt,
        )

        lap_res = solve_dynamic_lap(
            simulator,
            traj_track,
            initial_speed_mps=initial_speed_mps,
            ay_limit=ay_limit,
        )

        valid_rec = PhysicsValidityRecord(
            status=PhysicsValidityStatus.SIMULATION_ESTIMATE,
            model="Bounded-Trajectory-Optimizer-v1.0",
            assumptions=[
                "Frenet-Serret curvilinear offset parameterization",
                "Track boundaries strictly respected with vehicle half-width margin",
                "Candidate racing line curvature evaluated by transient 14-DOF multi-body solver",
            ],
            valid_parameter_domain={"lateral_offset_m": (-6.0, 6.0)},
            validation_evidence="Direct simulation coupling to DynamicLapSimulator",
            data_provenance={
                "optimizer": "L-BFGS-B",
                "iterations": int(res.nit),
                "curvature_reduction_pct": round(k_reduc, 2),
                "evaluated_lap_time_s": lap_res.total_time,
            },
        )

        return TrajectoryCandidate(
            distances=s_arr,
            lateral_offsets_m=n_opt,
            curvatures=k_opt,
            curvature_reduction_pct=round(k_reduc, 2),
            lap_result=lap_res,
            lap_time_s=lap_res.total_time,
            converged=res.success,
            iterations=int(res.nit),
            validity_record=valid_rec,
        )
