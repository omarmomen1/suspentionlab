"""
physics/pareto_optimizer.py
============================
SuspensionLab PRO — Multi-Objective Pareto Frontier Optimizer

Replaces the rudimentary single-objective optimizer with a proper
multi-objective optimization that presents the engineer with a
Pareto frontier — the set of non-dominated solutions.

An engineer can then choose their preferred trade-off point rather
than receiving a single "optimal" answer that may not match their
priorities.

Philosophy
----------
    "The optimizer should not choose for the engineer.
     It should show the engineer the space of possible choices."

Example output for comfort vs grip:
    Setup A: +2.1% grip,  -5.3% ride quality  (aggressive)
    Setup B: +1.4% grip,  -2.0% ride quality  (balanced)  ← best compromise
    Setup C: +0.4% grip,  -8.9% ride quality  (comfortable)

The engineer picks.

References
----------
- Deb, K. "Multi-Objective Optimization using Evolutionary Algorithms", Wiley 2001.
- Milliken & Milliken, "Race Car Vehicle Dynamics", SAE 1995. Ch. 16.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OptimizationObjective:
    """A single optimization objective.

    Attributes
    ----------
    name        : str   Identifier, must match a key in the evaluation result dict
    minimize    : bool  True = minimize, False = maximize
    weight      : float For weighted-sum fallback (not used in Pareto ranking)
    unit        : str   Physical unit for display (e.g. 'm/s²', 'N', 'mm')
    description : str   Human-readable description
    """
    name:        str
    minimize:    bool  = True
    weight:      float = 1.0
    unit:        str   = ""
    description: str   = ""


@dataclass
class OptimizationConstraint:
    """An inequality constraint: lower ≤ value ≤ upper.

    Attributes
    ----------
    name  : str   Must match a key in the evaluation result dict
    lower : float Minimum acceptable value (-inf = unconstrained)
    upper : float Maximum acceptable value (+inf = unconstrained)
    unit  : str
    hard  : bool  True = solution is infeasible if violated (default True)
    """
    name:        str
    lower:       float = -np.inf
    upper:       float = np.inf
    unit:        str   = ""
    description: str   = ""
    hard:        bool  = True

    def satisfied(self, value: float) -> bool:
        """True if value satisfies this constraint."""
        return self.lower <= value <= self.upper

    def headroom(self, value: float) -> float:
        """Distance to nearest constraint boundary (positive = feasible)."""
        if np.isfinite(self.lower) and np.isfinite(self.upper):
            return min(value - self.lower, self.upper - value)
        elif np.isfinite(self.lower):
            return value - self.lower
        elif np.isfinite(self.upper):
            return self.upper - value
        return np.inf


@dataclass
class ParetoPoint:
    """One evaluated point, possibly on the Pareto frontier.

    Attributes
    ----------
    params      : dict  Parameter values that produced this result
    objectives  : dict  Objective function values
    constraints : dict  Constraint function values
    feasible    : bool  True if all hard constraints satisfied
    pareto_rank : int   0 = Pareto-optimal (non-dominated)
    """
    params:      Dict
    objectives:  Dict
    constraints: Dict
    feasible:    bool
    pareto_rank: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# ParetoFrontier
# ─────────────────────────────────────────────────────────────────────────────

class ParetoFrontier:
    """Store evaluated points and compute Pareto dominance ranks.

    A point A dominates point B if:
    - A is at least as good as B on all objectives, AND
    - A is strictly better than B on at least one objective

    Parameters
    ----------
    objectives : list[OptimizationObjective]  Defines which values to compare
    """

    def __init__(self, objectives: List[OptimizationObjective]):
        self.objectives: List[OptimizationObjective] = objectives
        self._points:    List[ParetoPoint]            = []

    # ── Public interface ──────────────────────────────────────────────────────

    def add_point(self, point: ParetoPoint) -> None:
        """Add a point and update Pareto ranks for all points."""
        self._points.append(point)
        self._recompute_ranks()

    def add_points(self, points: List[ParetoPoint]) -> None:
        """Batch add (more efficient than calling add_point repeatedly)."""
        self._points.extend(points)
        self._recompute_ranks()

    def get_frontier(self) -> List[ParetoPoint]:
        """Return only Pareto-rank-0 (non-dominated) feasible points."""
        return [p for p in self._points if p.pareto_rank == 0 and p.feasible]

    def all_feasible(self) -> List[ParetoPoint]:
        """Return all feasible points, sorted by Pareto rank then first objective."""
        feasible = [p for p in self._points if p.feasible]
        first_obj = self.objectives[0].name if self.objectives else ""
        sign = -1.0 if (self.objectives and not self.objectives[0].minimize) else 1.0
        return sorted(feasible, key=lambda p: (p.pareto_rank, sign * p.objectives.get(first_obj, 0.0)))

    def dominates(self, a: ParetoPoint, b: ParetoPoint) -> bool:
        """True if point a dominates point b (on feasible objectives)."""
        at_least_as_good = True
        strictly_better  = False
        for obj in self.objectives:
            va = a.objectives.get(obj.name)
            vb = b.objectives.get(obj.name)
            if va is None or vb is None:
                continue
            if obj.minimize:
                if va > vb + 1e-10:
                    at_least_as_good = False
                    break
                if va < vb - 1e-10:
                    strictly_better = True
            else:  # maximize
                if va < vb - 1e-10:
                    at_least_as_good = False
                    break
                if va > vb + 1e-10:
                    strictly_better = True
        return at_least_as_good and strictly_better

    def best_compromise(self) -> Optional[ParetoPoint]:
        """Return the Pareto-optimal point closest to the utopia point.

        The utopia point has the best value of every objective simultaneously
        (generally unachievable).  The closest point on the frontier is a
        reasonable balanced recommendation.
        """
        frontier = self.get_frontier()
        if not frontier:
            return None
        if len(frontier) == 1:
            return frontier[0]

        # Collect objective arrays; normalise to [0,1]
        obj_names = [o.name for o in self.objectives]
        obj_matrix = np.array([
            [p.objectives.get(n, 0.0) for n in obj_names]
            for p in frontier
        ])
        # Flip maximization objectives for minimization
        for j, obj in enumerate(self.objectives):
            if not obj.minimize:
                obj_matrix[:, j] = -obj_matrix[:, j]

        mins = obj_matrix.min(axis=0)
        maxs = obj_matrix.max(axis=0)
        ranges = maxs - mins
        ranges[ranges < 1e-10] = 1.0  # avoid zero division

        normalized = (obj_matrix - mins) / ranges
        utopia     = np.zeros(len(obj_names))  # all zeros after normalization
        dists      = np.linalg.norm(normalized - utopia, axis=1)
        return frontier[int(np.argmin(dists))]

    def to_dict(self) -> dict:
        """Serialize the full frontier to a JSON-safe dict."""
        frontier = self.get_frontier()
        all_pts  = self.all_feasible()
        cand_id_map = {id(pt): f"CAND-{idx + 1:02d}" for idx, pt in enumerate(all_pts)}

        def _pt(p: ParetoPoint, fallback_idx: int = 0) -> dict:
            cid = cand_id_map.get(id(p), f"CAND-{fallback_idx + 1:02d}")
            return {
                "candidate_id":    cid,
                "params":          p.params,
                "objectives":      {k: round(v, 6) for k, v in p.objectives.items()},
                "constraints":     {k: round(v, 6) for k, v in p.constraints.items()},
                "feasible":        p.feasible,
                "pareto_rank":     p.pareto_rank,
                "is_pareto_optimal": bool(p.pareto_rank == 0 and p.feasible),
            }

        best = self.best_compromise()
        return {
            "n_total":          len(self._points),
            "n_feasible":       len(all_pts),
            "n_pareto_optimal": len(frontier),
            "objectives":       [o.name for o in self.objectives],
            "frontier":         [_pt(p, i) for i, p in enumerate(frontier)],
            "all_feasible":     [_pt(p, i) for i, p in enumerate(all_pts[:50])],  # cap for API
            "best_compromise":  _pt(best, 0) if best else None,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _recompute_ranks(self) -> None:
        """Recompute Pareto dominance ranks for all points."""
        feasible = [p for p in self._points if p.feasible]
        n = len(feasible)

        # Reset
        for p in feasible:
            p.pareto_rank = 0

        # Simple O(n²) dominance check (fine for n < 5000)
        dominated = [False] * n
        for i in range(n):
            for j in range(n):
                if i != j and self.dominates(feasible[j], feasible[i]):
                    dominated[i] = True
                    break
        for i, p in enumerate(feasible):
            p.pareto_rank = 0 if not dominated[i] else 1


# ─────────────────────────────────────────────────────────────────────────────
# SuspensionParetoOptimizer
# ─────────────────────────────────────────────────────────────────────────────

class SuspensionParetoOptimizer:
    """Multi-objective suspension setup optimizer using structured grid search.

    Sweeps spring rate and damping combinations, evaluates each with the
    quarter-car model, and builds a Pareto frontier.

    Parameters
    ----------
    (none — stateless, all configuration passed to optimize())
    """

    # Pre-defined objective sets for common use cases
    PRESET_OBJECTIVES = {
        "comfort_vs_grip": [
            OptimizationObjective(
                "rms_body_accel", minimize=True, unit="m/s²",
                description="RMS body acceleration (ride comfort). Lower = more comfortable.",
            ),
            OptimizationObjective(
                "tire_load_variation", minimize=True, unit="N",
                description="Peak tire load variation (grip consistency). Lower = more consistent grip.",
            ),
        ],
        "grip_vs_travel": [
            OptimizationObjective(
                "tire_load_variation", minimize=True, unit="N",
                description="Peak tire load variation",
            ),
            OptimizationObjective(
                "peak_susp_travel", minimize=True, unit="mm",
                description="Peak suspension travel. Lower = less risk of bottoming.",
            ),
        ],
        "comfort_vs_travel": [
            OptimizationObjective(
                "rms_body_accel", minimize=True, unit="m/s²",
                description="RMS body acceleration",
            ),
            OptimizationObjective(
                "peak_susp_travel", minimize=True, unit="mm",
                description="Peak suspension travel",
            ),
        ],
    }

    def optimize(
        self,
        base_params,
        profile,
        objectives: List[OptimizationObjective],
        constraints: List[OptimizationConstraint],
        param_ranges: Dict,
        progress_callback: Optional[Callable] = None,
    ) -> ParetoFrontier:
        """Run multi-objective optimization by grid search.

        Parameters
        ----------
        base_params    : QuarterCarParams  Base vehicle parameters
        profile        : RoadProfile       Road excitation profile
        objectives     : list[OptimizationObjective]  What to optimize
        constraints    : list[OptimizationConstraint] What to constrain
        param_ranges   : dict  e.g. {'k_s': (10000, 80000, 12), 'c': (1000, 6000, 10)}
                               Keys must be valid QuarterCarParams attributes.
                               Values are (min, max, n_steps) tuples.
        progress_callback : callable(current, total) -> None  Optional progress hook

        Returns
        -------
        ParetoFrontier  with all evaluated points and Pareto ranks
        """
        from suspensionlab.physics.quarter_car import QuarterCarParams, run_quarter_car_analysis

        frontier = ParetoFrontier(objectives)

        # Build parameter grid
        param_arrays = {}
        for param_name, (lo, hi, n_steps) in param_ranges.items():
            param_arrays[param_name] = np.linspace(lo, hi, int(n_steps))

        names  = list(param_arrays.keys())
        grids  = list(param_arrays.values())
        combos = list(itertools.product(*grids))
        total  = len(combos)

        points = []
        for idx, combo in enumerate(combos):
            params = dict(zip(names, combo))

            # Evaluate
            result_dict = self._evaluate_point(params, base_params, profile, run_quarter_car_analysis)

            # Check constraints
            feasible = True
            constraint_vals = {}
            for c in constraints:
                val = result_dict.get(c.name)
                if val is not None:
                    constraint_vals[c.name] = float(val)
                    if c.hard and not c.satisfied(float(val)):
                        feasible = False
                else:
                    constraint_vals[c.name] = 0.0

            # Extract objective values
            obj_vals = {o.name: float(result_dict.get(o.name, 0.0)) for o in objectives}

            points.append(ParetoPoint(
                params=params,
                objectives=obj_vals,
                constraints=constraint_vals,
                feasible=feasible,
            ))

            if progress_callback and (idx % 10 == 0 or idx == total - 1):
                progress_callback(idx + 1, total)

        frontier.add_points(points)
        return frontier

    def _evaluate_point(
        self,
        params: dict,
        base_params,
        profile,
        run_analysis_fn,
    ) -> dict:
        """Evaluate objectives at a single parameter point.

        Parameters
        ----------
        params         : dict  Parameter overrides (e.g. {'k_s': 25000, 'c': 2000})
        base_params    : QuarterCarParams
        profile        : RoadProfile
        run_analysis_fn: callable

        Returns
        -------
        dict with: rms_body_accel, peak_susp_travel, tire_load_variation, ride_freq
        """
        from suspensionlab.physics.quarter_car import QuarterCarParams, SolverMode

        try:
            p_dict = {
                "m_s": base_params.m_s,
                "m_u": base_params.m_u,
                "k_s": base_params.k_s,
                "c":   base_params.c,
                "k_t": base_params.k_t,
                "c_t": getattr(base_params, "c_t", 0.0),
                "MR":  base_params.MR,
            }
            p_dict.update({k: float(v) for k, v in params.items()})
            p = QuarterCarParams(**p_dict)

            try:
                result = run_analysis_fn(p, profile, f_min=0.5, f_max=25.0, n_freq=20, solver_mode=SolverMode.FAST)
            except TypeError:
                result = run_analysis_fn(p, profile, f_min=0.5, f_max=25.0, n_freq=20)

            rms_accel   = float(getattr(result, "rms_body_accel",    0.0))
            peak_travel = float(getattr(result, "peak_susp_travel",  0.0)) * 1000.0  # m → mm
            tire_var    = float(getattr(result, "rms_tire_load", getattr(result, "rms_tire_load_var", 0.0)))

            # Ride frequency (natural frequency of sprung mass)
            import math
            k_eff   = p_dict.get("k_s", base_params.k_s) * base_params.MR ** 2
            ride_hz = math.sqrt(k_eff / max(base_params.m_s, 1.0)) / (2 * math.pi)

            return {
                "rms_body_accel":      rms_accel,
                "peak_susp_travel":    peak_travel,
                "tire_load_variation": tire_var,
                "ride_freq":           ride_hz,
            }
        except Exception as exc:
            logger.warning(
                "Pareto optimizer: candidate evaluation failed; returning penalty metrics "
                "so the point ranks last instead of silently distorting the frontier. Error: %s",
                exc,
            )
            return {
                "rms_body_accel":      9999.0,
                "peak_susp_travel":    9999.0,
                "tire_load_variation": 9999.0,
                "ride_freq":           0.0,
            }

    def explain_tradeoff(
        self,
        frontier: ParetoFrontier,
        idx_a: int,
        idx_b: int,
    ) -> dict:
        """Explain the engineering tradeoff between two Pareto-frontier points.

        Parameters
        ----------
        frontier : ParetoFrontier
        idx_a    : index into frontier.get_frontier()
        idx_b    : index into frontier.get_frontier()

        Returns
        -------
        dict with: param_deltas, objective_deltas_pct, recommendation
        """
        pts = frontier.get_frontier()
        if idx_a >= len(pts) or idx_b >= len(pts):
            return {"error": "Index out of range"}

        a = pts[idx_a]
        b = pts[idx_b]

        # Parameter differences
        param_deltas = {}
        for k in a.params:
            if k in b.params:
                delta = b.params[k] - a.params[k]
                param_deltas[k] = round(delta, 2)

        # Objective differences in %
        obj_deltas = {}
        for o in frontier.objectives:
            va = a.objectives.get(o.name, 0.0)
            vb = b.objectives.get(o.name, 0.0)
            if abs(va) > 1e-9:
                pct = (vb - va) / abs(va) * 100.0
            else:
                pct = 0.0
            obj_deltas[o.name + "_delta_pct"] = round(pct, 2)

        # Build recommendation string
        obj_names = [o.name for o in frontier.objectives]
        if len(obj_names) >= 2:
            n0, n1 = obj_names[0], obj_names[1]
            d0 = obj_deltas.get(n0 + "_delta_pct", 0.0)
            d1 = obj_deltas.get(n1 + "_delta_pct", 0.0)
            direction = "B" if (d0 < 0) == frontier.objectives[0].minimize else "A"
            rec = (
                f"Moving from Setup A to Setup B "
                f"{'improves' if d0 < 0 else 'worsens'} {n0} by {abs(d0):.1f}% "
                f"at the cost of "
                f"{'worsening' if d1 > 0 else 'improving'} {n1} by {abs(d1):.1f}%. "
                f"Prefer Setup {direction} for {'better performance' if direction == 'B' else 'better balance'}."
            )
        else:
            rec = "Single-objective comparison."

        return {
            "param_deltas":        param_deltas,
            "objective_deltas_pct": obj_deltas,
            "recommendation":      rec,
        }
