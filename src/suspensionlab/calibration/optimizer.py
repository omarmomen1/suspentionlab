"""SuspensionLab PRO — Derivative-Free Multi-Start Optimization (Phase 3J).

Requirements:
5. Optimization:
   Support at least one robust derivative-free method.
   Do not rely on noisy finite differences through adaptive ODE solves.

7. Multi-start calibration:
   Demonstrate whether multiple initial conditions converge to the same parameter region.

11. Hostile tests:
   - optimizer failure handling
   - local minima detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import numpy as np
from scipy.optimize import minimize

from suspensionlab.calibration.registry import ParameterDefinition, ParameterRegistry
from suspensionlab.calibration.regularization import PhysicalRegularizer


class DerivativeFreeSolver(str, Enum):
    """Authorized derivative-free solvers."""
    POWELL = "Powell"
    NELDER_MEAD = "Nelder-Mead"


class MultiStartConvergenceStatus(str, Enum):
    """Classification of multi-start optimization convergence."""
    CONVERGED_GLOBAL_CLUSTER = "CONVERGED_GLOBAL_CLUSTER"
    LOCAL_MINIMA_DETECTED = "LOCAL_MINIMA_DETECTED"
    OPTIMIZER_FAILED = "OPTIMIZER_FAILED"


@dataclass
class OptimizationTrajectory:
    """Record of a single optimization run from a given initial condition."""
    start_index: int
    start_vector: Dict[str, float]
    converged_vector: Dict[str, float]
    initial_loss: float
    final_loss: float
    iterations: int
    function_evaluations: int
    success: bool
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_index": self.start_index,
            "start_vector": {k: round(v, 4) for k, v in self.start_vector.items()},
            "converged_vector": {k: round(v, 4) for k, v in self.converged_vector.items()},
            "initial_loss": round(float(self.initial_loss), 6),
            "final_loss": round(float(self.final_loss), 6),
            "iterations": self.iterations,
            "function_evaluations": self.function_evaluations,
            "success": self.success,
            "message": self.message,
        }


@dataclass
class MultiStartConvergenceSummary:
    """Summary of multi-start calibration demonstrating convergence stability."""
    status: MultiStartConvergenceStatus
    num_starts: int
    dispersion_pct: float
    best_start_index: int
    best_parameters: Dict[str, float]
    best_loss: float
    parameter_dispersions: Dict[str, float]
    trajectories: List[OptimizationTrajectory]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "num_starts": self.num_starts,
            "dispersion_pct": round(float(self.dispersion_pct), 2),
            "best_start_index": self.best_start_index,
            "best_loss": round(float(self.best_loss), 6),
            "best_parameters": {k: round(v, 4) for k, v in self.best_parameters.items()},
            "parameter_dispersions": {k: round(v, 2) for k, v in self.parameter_dispersions.items()},
            "trajectories": [t.to_dict() for t in self.trajectories],
        }


class MultiStartOptimizer:
    """Robust multi-start derivative-free optimizer for physical parameter identification."""

    def __init__(
        self,
        registry: ParameterRegistry,
        regularizer: PhysicalRegularizer,
        solver: DerivativeFreeSolver = DerivativeFreeSolver.POWELL,
        num_starts: int = 3,
        max_iter: int = 40,
        ftol: float = 1e-4,
        dispersion_threshold_pct: float = 15.0,
    ):
        self.registry = registry
        self.regularizer = regularizer
        self.solver = solver
        self.num_starts = max(1, num_starts)
        self.max_iter = max_iter
        self.ftol = ftol
        self.dispersion_threshold_pct = dispersion_threshold_pct

    def generate_starting_points(
        self,
        param_names: List[str],
        nominal_dict: Optional[Dict[str, float]] = None,
        seed: int = 42,
    ) -> List[Dict[str, float]]:
        """Generate diverse initial condition vectors across the allowable parameter space."""
        rng = np.random.default_rng(seed)
        starts: List[Dict[str, float]] = []

        # Start 0: Nominal baseline
        start_0 = {}
        for p in param_names:
            if nominal_dict and p in nominal_dict:
                start_0[p] = float(nominal_dict[p])
            else:
                start_0[p] = float(self.registry.get(p).nominal_value)
        starts.append(start_0)

        if self.num_starts > 1:
            # Start 1: Lower portion of parameter domain
            start_1 = {}
            for p in param_names:
                defn = self.registry.get(p)
                low, high = defn.bounds
                val = low + 0.15 * (high - low)
                start_1[p] = float(np.clip(val, low, high))
            starts.append(start_1)

        if self.num_starts > 2:
            # Start 2: Upper portion of parameter domain
            start_2 = {}
            for p in param_names:
                defn = self.registry.get(p)
                low, high = defn.bounds
                val = high - 0.15 * (high - low)
                start_2[p] = float(np.clip(val, low, high))
            starts.append(start_2)

        # Additional random starts within bounds if num_starts > 3
        for k in range(3, self.num_starts):
            start_k = {}
            for p in param_names:
                defn = self.registry.get(p)
                low, high = defn.bounds
                # Sample from prior distribution
                sampled = float(defn.prior.sample(1, rng=rng)[0])
                start_k[p] = float(np.clip(sampled, low, high))
            starts.append(start_k)

        return starts

    def optimize(
        self,
        param_names: List[str],
        objective_evaluator: Callable[[Dict[str, float]], float],
        nominal_dict: Optional[Dict[str, float]] = None,
    ) -> MultiStartConvergenceSummary:
        """Execute multi-start derivative-free calibration."""
        if not param_names:
            return MultiStartConvergenceSummary(
                status=MultiStartConvergenceStatus.CONVERGED_GLOBAL_CLUSTER,
                num_starts=0,
                dispersion_pct=0.0,
                best_start_index=0,
                best_parameters={},
                best_loss=0.0,
                parameter_dispersions={},
                trajectories=[],
            )

        starting_points = self.generate_starting_points(param_names, nominal_dict)
        trajectories: List[OptimizationTrajectory] = []

        bounds_list = [self.registry.get(p).bounds for p in param_names]
        scales = [max(abs(self.registry.get(p).nominal_value), 1.0) for p in param_names]

        # Normalized parameter space transformation for solver stability
        def to_norm(p_vec: np.ndarray) -> np.ndarray:
            return np.array([p_vec[i] / scales[i] for i in range(len(p_vec))], dtype=np.float64)

        def from_norm(x_norm: np.ndarray) -> np.ndarray:
            return np.array([x_norm[i] * scales[i] for i in range(len(x_norm))], dtype=np.float64)

        norm_bounds = [(b[0] / scales[i], b[1] / scales[i]) for i, b in enumerate(bounds_list)]

        for idx, start_dict in enumerate(starting_points):
            p0_vec = np.array([start_dict[p] for p in param_names], dtype=np.float64)
            x0_norm = to_norm(p0_vec)

            # Combined objective function: Data loss + Regularization penalty
            def combined_obj(x_n: np.ndarray) -> float:
                p_current = from_norm(x_n)
                cur_dict = dict(zip(param_names, p_current))

                # Regularization penalty
                reg_pen = self.regularizer.evaluate(cur_dict)

                # Simulation error loss
                try:
                    data_loss = objective_evaluator(cur_dict)
                    if not math.isfinite(data_loss):
                        data_loss = 1.0e6
                except Exception:
                    data_loss = 1.0e6

                return float(data_loss + reg_pen.total_penalty)

            initial_loss = combined_obj(x0_norm)

            try:
                opt_res = minimize(
                    combined_obj,
                    x0=x0_norm,
                    bounds=norm_bounds,
                    method=self.solver.value,
                    options={"maxiter": self.max_iter, "ftol": self.ftol, "disp": False},
                )
                x_opt_norm = opt_res.x if opt_res.x is not None else x0_norm
                final_loss = float(opt_res.fun) if hasattr(opt_res, "fun") else initial_loss
                success = bool(opt_res.success) if hasattr(opt_res, "success") else True
                msg = str(getattr(opt_res, "message", "Optimization finished"))
                n_iters = int(getattr(opt_res, "nit", self.max_iter))
                n_fev = int(getattr(opt_res, "nfev", 0))
            except Exception as exc:
                x_opt_norm = x0_norm
                final_loss = initial_loss
                success = False
                msg = f"Solver crashed: {exc}"
                n_iters = 0
                n_fev = 0

            # Clip back to physical bounds
            p_final = from_norm(x_opt_norm)
            for i, p in enumerate(param_names):
                low, high = bounds_list[i]
                p_final[i] = float(np.clip(p_final[i], low, high))

            final_dict = dict(zip(param_names, p_final))

            trajectories.append(OptimizationTrajectory(
                start_index=idx,
                start_vector=dict(start_dict),
                converged_vector=final_dict,
                initial_loss=initial_loss,
                final_loss=final_loss,
                iterations=n_iters,
                function_evaluations=n_fev,
                success=success,
                message=msg,
            ))

        # Select best trajectory
        successful_trajectories = [t for t in trajectories if t.success]
        candidate_pool = successful_trajectories if successful_trajectories else trajectories

        best_traj = min(candidate_pool, key=lambda t: t.final_loss)
        best_idx = best_traj.start_index
        best_params = best_traj.converged_vector
        best_loss = best_traj.final_loss

        # Multi-start dispersion analysis
        param_dispersions: Dict[str, float] = {}
        for p in param_names:
            vals = [t.converged_vector[p] for t in candidate_pool]
            mean_v = float(np.mean(vals))
            ptp_v = float(np.ptp(vals))
            disp_pct = (ptp_v / max(abs(mean_v), 1e-6)) * 100.0
            param_dispersions[p] = disp_pct

        max_dispersion = max(param_dispersions.values()) if param_dispersions else 0.0

        if all(not t.success for t in trajectories):
            status = MultiStartConvergenceStatus.OPTIMIZER_FAILED
        elif max_dispersion > self.dispersion_threshold_pct:
            status = MultiStartConvergenceStatus.LOCAL_MINIMA_DETECTED
        else:
            status = MultiStartConvergenceStatus.CONVERGED_GLOBAL_CLUSTER

        return MultiStartConvergenceSummary(
            status=status,
            num_starts=len(trajectories),
            dispersion_pct=max_dispersion,
            best_start_index=best_idx,
            best_parameters=best_params,
            best_loss=best_loss,
            parameter_dispersions=param_dispersions,
            trajectories=trajectories,
        )
