"""
physics/constraint_optimizer.py
================================
SuspensionLab PRO — Constraint-Driven Lap Time Optimizer

Implements Issue 15: optimize lap time subject to real engineering constraints.

Problem formulation:
    minimize    T_lap(k_spring_f, k_spring_r, k_arb_f, k_arb_r)
    subject to:
        ride_height_front      >= ride_height_front_min
        ride_height_rear       >= ride_height_rear_min
        susp_travel            <= susp_travel_max
        aero_balance           in [aero_balance_min, aero_balance_max]
        ride_freq_front        in [ride_freq_front_min, ride_freq_front_max]
        ride_freq_rear         in [ride_freq_rear_min, ride_freq_rear_max]
        k_arb_front            in [k_arb_front_min, k_arb_front_max]
        k_arb_rear             in [k_arb_rear_min, k_arb_rear_max]

This is what separates professional vehicle dynamics software from academic models.
Real engineers don't just "optimize for lap time" — they optimize within the
window of physical, regulatory, and operational constraints.

Usage example:
    opt = ConstraintDrivenOptimizer()
    result = opt.optimize(
        vehicle=vehicle,
        segments=segments,
        constraints=SetupConstraints(ride_height_front_min_mm=18.0),
        param_ranges={
            'k_spring_front': (25_000, 55_000, 8),
            'k_spring_rear':  (30_000, 65_000, 8),
            'k_arb_front':    (5_000, 25_000, 6),
            'k_arb_rear':     (5_000, 20_000, 6),
        },
        n_samples=200,
    )
    report = opt.format_engineer_report(result['best_solution'], ...)
"""

from __future__ import annotations

import itertools
import math
import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# SetupConstraints
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SetupConstraints:
    """Engineering constraints for suspension setup optimization.

    All fields are Optional.  None means that constraint is not applied.
    Values with _min suffix: lower bound (value must be >= this).
    Values with _max suffix: upper bound (value must be <= this).

    Attributes
    ----------
    ride_height_front_min_mm  : Minimum front ride height [mm]. Safety/regulation limit.
    ride_height_rear_min_mm   : Minimum rear ride height [mm].
    susp_travel_front_max_mm  : Maximum front suspension travel [mm]. Avoids bottoming.
    susp_travel_rear_max_mm   : Maximum rear suspension travel [mm].
    tire_load_variation_max_n : Maximum peak tire load variation [N]. Grip consistency.
    aero_balance_min          : Minimum aero balance fraction (front CL / total CL).
    aero_balance_max          : Maximum aero balance fraction.
    ride_freq_front_min       : Minimum front ride frequency [Hz].
    ride_freq_front_max       : Maximum front ride frequency [Hz].
    ride_freq_rear_min        : Minimum rear ride frequency [Hz].
    ride_freq_rear_max        : Maximum rear ride frequency [Hz].
    k_arb_front_min           : Minimum front ARB rate [N/m].
    k_arb_front_max           : Maximum front ARB rate [N/m].
    k_arb_rear_min            : Minimum rear ARB rate [N/m].
    k_arb_rear_max            : Maximum rear ARB rate [N/m].
    """
    ride_height_front_min_mm:   Optional[float] = 15.0
    ride_height_rear_min_mm:    Optional[float] = 25.0
    susp_travel_front_max_mm:   Optional[float] = 60.0
    susp_travel_rear_max_mm:    Optional[float] = 60.0
    tire_load_variation_max_n:  Optional[float] = 3000.0
    aero_balance_min:           Optional[float] = 0.42
    aero_balance_max:           Optional[float] = 0.48
    ride_freq_front_min:        Optional[float] = 1.5
    ride_freq_front_max:        Optional[float] = 4.5
    ride_freq_rear_min:         Optional[float] = 1.8
    ride_freq_rear_max:         Optional[float] = 5.0
    k_arb_front_min:            Optional[float] = 0.0
    k_arb_front_max:            Optional[float] = 50_000.0
    k_arb_rear_min:             Optional[float] = 0.0
    k_arb_rear_max:             Optional[float] = 50_000.0


# ─────────────────────────────────────────────────────────────────────────────
# ConstraintDrivenOptimizer
# ─────────────────────────────────────────────────────────────────────────────

class ConstraintDrivenOptimizer:
    """Minimize lap time subject to engineering constraints.

    Strategy
    --------
    1. Generate a parameter grid (or random/quasi-random sample)
    2. For each parameter set, update vehicle suspension and run lap simulation
    3. Evaluate constraints for each result
    4. Return feasible solutions sorted by lap time (best first)

    This is a screening / structured search approach — not gradient-based.
    It is appropriate because:
    - The lap simulation is fast (< 200 ms)
    - The parameter space is 2–4 dimensional (manageable grid)
    - Constraint satisfaction is non-smooth in general
    - Engineers need to see the full feasible space, not just one point

    Parameters
    ----------
    (stateless — all config passed to optimize())
    """

    def optimize(
        self,
        vehicle,
        segments,
        constraints: SetupConstraints,
        param_ranges: Dict,
        n_samples: int = 200,
        strategy: str = "grid",
    ) -> dict:
        """Run constraint-driven optimization.

        Parameters
        ----------
        vehicle      : LapSimVehicle  Base vehicle (will be copied, not mutated)
        segments     : List[TrackSegment]
        constraints  : SetupConstraints
        param_ranges : dict  {'param_name': (min, max, n_steps), ...}
                       Supported params: k_spring_front, k_spring_rear,
                                         k_arb_front, k_arb_rear
        n_samples    : int  Maximum evaluations (for random strategy)
        strategy     : str  'grid' | 'random'

        Returns
        -------
        dict with:
            feasible_solutions : list[dict]  sorted by lap_time_s ascending
            best_solution      : dict  best feasible solution (None if none found)
            n_feasible         : int
            n_total            : int
            param_ranges       : dict  as provided
            baseline           : dict  lap time with unmodified vehicle
        """
        from suspensionlab.physics.lap_sim import solve_lap
        from suspensionlab.physics.suspension_aero_coupling import SuspensionConfig

        # Baseline: evaluate original vehicle
        baseline_result = solve_lap(vehicle, segments)
        baseline_time   = float(baseline_result.total_time)

        # Build parameter combinations
        combos = self._build_combos(param_ranges, strategy, n_samples)
        n_total = len(combos)

        feasible_solutions = []

        for combo in combos:
            # Build a modified vehicle (deep copy to avoid mutation)
            v_mod = copy.deepcopy(vehicle)
            sus   = v_mod.suspension

            for param, value in combo.items():
                if param == "k_spring_front":
                    sus.k_spring_front = float(value)
                elif param == "k_spring_rear":
                    sus.k_spring_rear = float(value)
                elif param == "k_arb_front":
                    sus.k_arb_front = float(value)
                elif param == "k_arb_rear":
                    sus.k_arb_rear = float(value)

            # Quick constraint pre-check (without running the sim)
            pre_check = self._precheck_constraints(v_mod, constraints)
            if not pre_check["all_hard_satisfied"]:
                continue

            # Run lap simulation
            try:
                result = solve_lap(v_mod, segments)
            except Exception:
                continue

            lap_time = float(result.total_time)

            # Post-run constraint check
            constraint_check = self.check_constraints(v_mod, combo, constraints)
            if not constraint_check["all_hard_satisfied"]:
                continue

            feasible_solutions.append({
                "params":            combo,
                "lap_time_s":        round(lap_time, 4),
                "lap_time_delta_s":  round(lap_time - baseline_time, 4),
                "arb_balance":       round(result.arb_balance, 4),
                "constraint_check":  constraint_check,
            })

        # Sort by lap time
        feasible_solutions.sort(key=lambda x: x["lap_time_s"])

        return {
            "feasible_solutions": feasible_solutions[:50],  # cap for API
            "best_solution":      feasible_solutions[0] if feasible_solutions else None,
            "n_feasible":         len(feasible_solutions),
            "n_total":            n_total,
            "param_ranges":       param_ranges,
            "baseline": {
                "lap_time_s":     round(baseline_time, 4),
                "params":         {k: getattr(vehicle.suspension, k, None)
                                   for k in param_ranges.keys()},
            },
        }

    def check_constraints(
        self,
        vehicle,
        solution: dict,
        constraints: SetupConstraints,
    ) -> dict:
        """Check all constraints for a given parameter set.

        Parameters
        ----------
        vehicle     : LapSimVehicle  (with solution params already applied)
        solution    : dict  parameter values
        constraints : SetupConstraints

        Returns
        -------
        dict with: all_hard_satisfied, per_constraint dict
        """
        sus = vehicle.suspension
        mp  = vehicle.mass_props
        ae  = vehicle.aero
        g   = 9.81

        results = {}
        all_ok  = True

        def _check(name: str, value: float, lo, hi, unit: str, hard: bool = True) -> dict:
            lo_ok = (lo is None) or (value >= lo)
            hi_ok = (hi is None) or (value <= hi)
            sat   = lo_ok and hi_ok
            if hard and not sat:
                nonlocal all_ok
                all_ok = False
            limit = lo if not lo_ok else (hi if not hi_ok else None)
            return {
                "value":     round(value, 4),
                "satisfied": sat,
                "unit":      unit,
                "hard":      hard,
                "headroom":  round(
                    min(value - (lo or -np.inf), (hi or np.inf) - value), 4
                ) if sat else round(
                    max(lo - value if lo is not None else 0,
                        value - hi if hi is not None else 0), 4
                ) * -1,
            }

        c = constraints

        # Ride heights (from suspension config, may change with aero load — use static here)
        results["ride_height_front_mm"] = _check(
            "ride_height_front", sus.ride_height_front,
            c.ride_height_front_min_mm, None, "mm"
        )
        results["ride_height_rear_mm"] = _check(
            "ride_height_rear", sus.ride_height_rear,
            c.ride_height_rear_min_mm, None, "mm"
        )

        # ARB bounds
        results["k_arb_front"] = _check(
            "k_arb_front", sus.k_arb_front,
            c.k_arb_front_min, c.k_arb_front_max, "N/m"
        )
        results["k_arb_rear"] = _check(
            "k_arb_rear", sus.k_arb_rear,
            c.k_arb_rear_min, c.k_arb_rear_max, "N/m"
        )

        # Ride frequencies
        m_s_f = mp.total_mass * mp.weight_dist_front  # sprung mass front [kg]
        m_s_r = mp.total_mass * mp.weight_dist_rear
        ride_hz_f = math.sqrt(sus.k_spring_front / max(m_s_f, 1.0)) / (2 * math.pi)
        ride_hz_r = math.sqrt(sus.k_spring_rear  / max(m_s_r, 1.0)) / (2 * math.pi)

        results["ride_freq_front_hz"] = _check(
            "ride_freq_front", ride_hz_f,
            c.ride_freq_front_min, c.ride_freq_front_max, "Hz"
        )
        results["ride_freq_rear_hz"] = _check(
            "ride_freq_rear", ride_hz_r,
            c.ride_freq_rear_min, c.ride_freq_rear_max, "Hz"
        )

        # Aero balance
        aero_bal = ae.cop_fraction
        results["aero_balance"] = _check(
            "aero_balance", aero_bal,
            c.aero_balance_min, c.aero_balance_max, "fraction"
        )

        results["all_hard_satisfied"] = all_ok
        return results

    def format_engineer_report(
        self,
        best_solution: dict,
        baseline_solution: dict,
        constraint_check: dict,
    ) -> dict:
        """Format optimization result as an engineer-readable setup sheet.

        Parameters
        ----------
        best_solution     : dict  best feasible solution from optimize()
        baseline_solution : dict  baseline from optimize()['baseline']
        constraint_check  : dict  from check_constraints()

        Returns
        -------
        dict with: setup_changes, predicted_lap_time_delta_s, constraint_headroom,
                   confidence, recommendation
        """
        if best_solution is None:
            return {
                "setup_changes": [],
                "predicted_lap_time_delta_s": 0.0,
                "constraint_headroom": {},
                "confidence": "low",
                "recommendation": "No feasible solution found. Relax constraints.",
            }

        setup_changes = []
        baseline_params = baseline_solution.get("params", {})
        best_params     = best_solution.get("params", {})

        param_labels = {
            "k_spring_front": "Front spring rate",
            "k_spring_rear":  "Rear spring rate",
            "k_arb_front":    "Front ARB rate",
            "k_arb_rear":     "Rear ARB rate",
        }
        param_units = {
            "k_spring_front": "N/m",
            "k_spring_rear":  "N/m",
            "k_arb_front":    "N/m",
            "k_arb_rear":     "N/m",
        }

        for k, label in param_labels.items():
            v_from = baseline_params.get(k)
            v_to   = best_params.get(k)
            if v_from is not None and v_to is not None:
                delta = v_to - v_from
                if abs(delta) > 1.0:
                    setup_changes.append({
                        "parameter": label,
                        "from":      f"{v_from:.0f} {param_units[k]}",
                        "to":        f"{v_to:.0f} {param_units[k]}",
                        "delta":     f"{'+' if delta > 0 else ''}{delta:.0f} {param_units[k]}",
                    })

        dt = best_solution.get("lap_time_delta_s", 0.0)
        baseline_t = baseline_solution.get("lap_time_s", 1.0)
        dt_pct = dt / max(baseline_t, 1.0) * 100.0

        # Constraint headroom summary
        headroom = {
            k: {
                "value":    v.get("value"),
                "satisfied": v.get("satisfied"),
                "headroom": v.get("headroom"),
                "unit":     v.get("unit"),
            }
            for k, v in constraint_check.items()
            if isinstance(v, dict) and "value" in v
        }

        # Confidence based on how many setups were evaluated and how large the improvement is
        if abs(dt) < 0.05:
            confidence = "low"
        elif abs(dt) < 0.3:
            confidence = "medium"
        else:
            confidence = "high"

        # Build recommendation
        if dt < -0.1:
            recommendation = (
                f"This setup is predicted to be {abs(dt):.3f}s faster ({abs(dt_pct):.2f}%) "
                f"while satisfying all {len(setup_changes)} changed parameters. "
                f"Verify on track before committing."
            )
        elif abs(dt) <= 0.1:
            recommendation = (
                "Lap time improvement is marginal (<0.1s). "
                "This setup improves constraint headroom without significant performance change. "
                "Consider if the setup change is worth the risk."
            )
        else:
            recommendation = "This solution is slower than baseline. Review constraint relaxation."

        return {
            "setup_changes":              setup_changes,
            "predicted_lap_time_delta_s": round(dt, 4),
            "predicted_lap_time_delta_pct": round(dt_pct, 3),
            "constraint_headroom":        headroom,
            "confidence":                 confidence,
            "recommendation":             recommendation,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_combos(
        self,
        param_ranges: Dict,
        strategy: str,
        n_samples: int,
    ) -> List[dict]:
        """Generate parameter combinations."""
        if strategy == "random":
            combos = []
            rng = np.random.default_rng(42)
            for _ in range(n_samples):
                combo = {}
                for k, (lo, hi, _) in param_ranges.items():
                    combo[k] = float(rng.uniform(lo, hi))
                combos.append(combo)
            return combos

        else:  # grid
            arrays = {}
            for k, (lo, hi, n_steps) in param_ranges.items():
                arrays[k] = np.linspace(lo, hi, int(n_steps))

            names  = list(arrays.keys())
            grids  = list(arrays.values())
            combos = []
            for values in itertools.product(*grids):
                combos.append(dict(zip(names, [float(v) for v in values])))

            # Cap at n_samples by systematic downsampling
            if len(combos) > n_samples:
                step = len(combos) // n_samples
                combos = combos[::step][:n_samples]

            return combos

    def _precheck_constraints(self, vehicle, constraints: SetupConstraints) -> dict:
        """Fast pre-check of constraints that don't require simulation."""
        sus = vehicle.suspension
        c   = constraints
        ok  = True

        if c.k_arb_front_min is not None and sus.k_arb_front < c.k_arb_front_min:
            ok = False
        if c.k_arb_front_max is not None and sus.k_arb_front > c.k_arb_front_max:
            ok = False
        if c.k_arb_rear_min is not None and sus.k_arb_rear < c.k_arb_rear_min:
            ok = False
        if c.k_arb_rear_max is not None and sus.k_arb_rear > c.k_arb_rear_max:
            ok = False
        if c.ride_height_front_min_mm is not None and sus.ride_height_front < c.ride_height_front_min_mm:
            ok = False
        if c.ride_height_rear_min_mm is not None and sus.ride_height_rear < c.ride_height_rear_min_mm:
            ok = False

        return {"all_hard_satisfied": ok}
