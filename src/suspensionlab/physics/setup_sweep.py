"""
physics/setup_sweep.py
======================
SuspensionLab PRO — Parameter Sensitivity Sweep Engine
Authoritative sensitivity sweeps for race vehicle setup optimization.

This module evaluates the sensitivity of lap time, sector times, and corner speeds
to continuous variations in key vehicle setup parameters:
- Springs (Front/Rear heave rates)
- Anti-Roll Bars (Front/Rear roll stiffness)
- Aerodynamics (Downforce CL, Drag CD)
- Mass & Distribution
- Ride Heights (Front/Rear aerodynamic rake)
- Powertrain power scaling
- Tire friction scale

Every candidate is evaluated through genuine physical simulation (QSS forward/backward
speed profile solver) with numerical gradient computation (dT/dp) via central differences.
"""

from __future__ import annotations

import copy
import enum
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np

from suspensionlab.physics.lap_sim import (
    LapSimVehicle,
    TrackSegment,
    solve_lap,
    LapSimResult,
)
from suspensionlab.physics.lap_sim_errors import LapSimError
from suspensionlab.physics.corner_analysis import detect_corners


class SweepParameter(str, enum.Enum):
    """Supported vehicle setup parameters for sensitivity sweeps."""
    SPRING_FRONT = "spring_front"          # Front spring stiffness [N/m]
    SPRING_REAR = "spring_rear"            # Rear spring stiffness [N/m]
    ARB_FRONT = "arb_front"                # Front ARB stiffness [N/m]
    ARB_REAR = "arb_rear"                  # Rear ARB stiffness [N/m]
    AERO_CL = "aero_cl"                    # Base downforce coefficient [-]
    AERO_CD = "aero_cd"                    # Base drag coefficient [-]
    MASS = "mass"                          # Vehicle total mass [kg]
    POWER_SCALE = "power_scale"            # Powertrain power scaling factor [-]
    RIDE_HEIGHT_FRONT = "ride_height_front"# Front static ride height [mm]
    RIDE_HEIGHT_REAR = "ride_height_rear"  # Rear static ride height [mm]
    TIRE_MU_SCALE = "tire_mu_scale"        # Tire friction multiplier [-]


PARAM_METADATA: Dict[SweepParameter, Dict[str, str]] = {
    SweepParameter.SPRING_FRONT: {
        "unit": "N/m",
        "description": "Front main spring stiffness",
        "category": "SUSPENSION",
        "derivative_symbol": "∂T/∂Ks,f",
        "derivative_name": "Sensitivity of Lap Time to Front Spring Stiffness",
        "sensitivity_unit": "s/(N/m)",
    },
    SweepParameter.SPRING_REAR: {
        "unit": "N/m",
        "description": "Rear main spring stiffness",
        "category": "SUSPENSION",
        "derivative_symbol": "∂T/∂Ks,r",
        "derivative_name": "Sensitivity of Lap Time to Rear Spring Stiffness",
        "sensitivity_unit": "s/(N/m)",
    },
    SweepParameter.ARB_FRONT: {
        "unit": "N/m",
        "description": "Front anti-roll bar stiffness",
        "category": "SUSPENSION",
        "derivative_symbol": "∂T/∂Karb,f",
        "derivative_name": "Sensitivity of Lap Time to Front Anti-Roll Bar Stiffness",
        "sensitivity_unit": "s/(N/m)",
    },
    SweepParameter.ARB_REAR: {
        "unit": "N/m",
        "description": "Rear anti-roll bar stiffness",
        "category": "SUSPENSION",
        "derivative_symbol": "∂T/∂Karb,r",
        "derivative_name": "Sensitivity of Lap Time to Rear Anti-Roll Bar Stiffness",
        "sensitivity_unit": "s/(N/m)",
    },
    SweepParameter.AERO_CL: {
        "unit": "-",
        "description": "Base aerodynamic downforce coefficient",
        "category": "AERO",
        "derivative_symbol": "∂T/∂CL",
        "derivative_name": "Sensitivity of Lap Time to Downforce Coefficient",
        "sensitivity_unit": "s",
    },
    SweepParameter.AERO_CD: {
        "unit": "-",
        "description": "Base aerodynamic drag coefficient",
        "category": "AERO",
        "derivative_symbol": "∂T/∂CD",
        "derivative_name": "Sensitivity of Lap Time to Drag Coefficient",
        "sensitivity_unit": "s",
    },
    SweepParameter.MASS: {
        "unit": "kg",
        "description": "Total vehicle mass including driver",
        "category": "CHASSIS",
        "derivative_symbol": "∂T/∂m",
        "derivative_name": "Sensitivity of Lap Time to Total Vehicle Mass",
        "sensitivity_unit": "s/kg",
    },
    SweepParameter.POWER_SCALE: {
        "unit": "multiplier",
        "description": "Powertrain maximum power scaling factor",
        "category": "POWERTRAIN",
        "derivative_symbol": "∂T/∂(P/P₀)",
        "derivative_name": "Sensitivity of Lap Time to Powertrain Power Scaling",
        "sensitivity_unit": "s/multiplier",
    },
    SweepParameter.RIDE_HEIGHT_FRONT: {
        "unit": "mm",
        "description": "Front static ride height",
        "category": "AERO_PLATFORM",
        "derivative_symbol": "∂T/∂rh,f",
        "derivative_name": "Sensitivity of Lap Time to Front Static Ride Height",
        "sensitivity_unit": "s/mm",
    },
    SweepParameter.RIDE_HEIGHT_REAR: {
        "unit": "mm",
        "description": "Rear static ride height",
        "category": "AERO_PLATFORM",
        "derivative_symbol": "∂T/∂rh,r",
        "derivative_name": "Sensitivity of Lap Time to Rear Static Ride Height",
        "sensitivity_unit": "s/mm",
    },
    SweepParameter.TIRE_MU_SCALE: {
        "unit": "multiplier",
        "description": "Tire friction coefficient scaling",
        "category": "TIRE",
        "derivative_symbol": "∂T/∂μ",
        "derivative_name": "Sensitivity of Lap Time to Tire Friction Coefficient",
        "sensitivity_unit": "s/multiplier",
    },
}


@dataclass
class SweepResult:
    """Result of a parameter sensitivity sweep across a track."""
    parameter: str
    unit: str
    description: str
    values: List[float]
    lap_times_s: List[float]
    deltas_s: List[float]
    sector_times_s: List[List[float]]
    min_corner_speeds_mps: List[List[float]]
    max_speeds_kmh: List[float]
    sensitivities_s_per_unit: List[float]
    convergence_flags: List[bool]
    baseline_index: int
    summary: str
    derivative_symbol: str = "∂T/∂p"
    sensitivity_unit: str = "s/unit"
    model_assumptions_caveat: str = (
        "Parameter sensitivity is computed using quasi-steady state simulation. "
        "Gradients reflect steady-state grip and aero platform equilibrium, neglecting "
        "transient yaw inertia and damper dynamic force responses."
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert sweep result to dictionary with JSON-safe nulls."""
        def _clean_val(v: Any) -> Any:
            if isinstance(v, (float, np.floating)):
                if math.isnan(v) or math.isinf(v):
                    return None
                return float(v)
            return v

        return {
            "parameter": self.parameter,
            "unit": self.unit,
            "description": self.description,
            "derivative_symbol": self.derivative_symbol,
            "sensitivity_unit": self.sensitivity_unit,
            "values": [_clean_val(v) for v in self.values],
            "lap_times_s": [_clean_val(t) for t in self.lap_times_s],
            "deltas_s": [_clean_val(d) for d in self.deltas_s],
            "sector_times_s": [
                [_clean_val(st) for st in s_list] for s_list in self.sector_times_s
            ],
            "min_corner_speeds_mps": [
                [_clean_val(cs) for cs in c_list] for c_list in self.min_corner_speeds_mps
            ],
            "max_speeds_kmh": [_clean_val(ms) for ms in self.max_speeds_kmh],
            "sensitivities_s_per_unit": [_clean_val(s) for s in self.sensitivities_s_per_unit],
            "convergence_flags": self.convergence_flags,
            "baseline_index": self.baseline_index,
            "summary": self.summary,
            "model_assumptions_caveat": self.model_assumptions_caveat,
        }


def _apply_parameter(
    vehicle: LapSimVehicle,
    param: SweepParameter,
    val: float,
    baseline_power: float,
) -> None:
    """Mutate vehicle parameters in-place for a sweep evaluation point."""
    if param == SweepParameter.SPRING_FRONT:
        vehicle.suspension.k_spring_front = float(val)
    elif param == SweepParameter.SPRING_REAR:
        vehicle.suspension.k_spring_rear = float(val)
    elif param == SweepParameter.ARB_FRONT:
        vehicle.suspension.k_arb_front = float(val)
    elif param == SweepParameter.ARB_REAR:
        vehicle.suspension.k_arb_rear = float(val)
    elif param == SweepParameter.AERO_CL:
        vehicle.aero.cl_base = float(val)
    elif param == SweepParameter.AERO_CD:
        vehicle.aero.cd_base = float(val)
    elif param == SweepParameter.MASS:
        vehicle.mass_props.total_mass = float(val)
    elif param == SweepParameter.POWER_SCALE:
        # Scale max torque proportionally with power scale
        scale = max(float(val), 0.01)
        vehicle.powertrain.max_power_w = baseline_power * scale
        vehicle.powertrain.max_torque_nm = (
            vehicle.powertrain.max_torque_nm * scale
            if hasattr(vehicle.powertrain, "max_torque_nm") else 400.0 * scale
        )
    elif param == SweepParameter.RIDE_HEIGHT_FRONT:
        vehicle.suspension.ride_height_front = float(val)
    elif param == SweepParameter.RIDE_HEIGHT_REAR:
        vehicle.suspension.ride_height_rear = float(val)
    elif param == SweepParameter.TIRE_MU_SCALE:
        # Scale tire friction coefficients (pDy1 and pDx1)
        scale = max(float(val), 0.1)
        vehicle.tire_coeffs.pDy1 = 1.0 * scale
        vehicle.tire_coeffs.pDx1 = 1.0 * scale


def run_parameter_sweep(
    baseline_vehicle: LapSimVehicle,
    track: List[TrackSegment],
    parameter: Union[str, SweepParameter],
    values: Sequence[float],
    *,
    baseline_val: Optional[float] = None,
    fast_mode: bool = True,
    ggv_resolution: tuple[int, int] = (20, 10),
) -> SweepResult:
    """
    Run a parameter sensitivity sweep across a sequence of values.

    Parameters
    ----------
    baseline_vehicle : Baseline LapSimVehicle instance.
    track : List of validated TrackSegment instances.
    parameter : Target setup parameter to vary.
    values : Sequence of parameter values to evaluate.
    baseline_val : Optional reference value within the sequence (defaults to closest to baseline).
    fast_mode : If True, uses moderate GGV resolution (20x10) to balance fidelity and speed.
    ggv_resolution : Tuple of (n_speeds, n_ay) for GGV grid construction.

    Returns
    -------
    SweepResult containing lap times, deltas, numerical sensitivities, and corner metrics.
    """
    if isinstance(parameter, str):
        try:
            param = SweepParameter(parameter.lower())
        except ValueError:
            valid = [p.value for p in SweepParameter]
            raise ValueError(f"Invalid sweep parameter '{parameter}'. Valid choices: {valid}")
    else:
        param = parameter

    meta = PARAM_METADATA.get(param, {"unit": "", "description": param.value})
    sorted_values = [float(v) for v in values]
    n_points = len(sorted_values)

    if n_points == 0:
        raise ValueError("Sweep values list cannot be empty.")

    # Identify baseline value index
    if baseline_val is not None:
        idx_closest = int(np.argmin(np.abs(np.array(sorted_values) - float(baseline_val))))
    else:
        idx_closest = n_points // 2

    p_w = getattr(baseline_vehicle.powertrain, "max_power_w", 500_000.0)
    baseline_power = float(p_w() if callable(p_w) else p_w)

    lap_times: List[float] = []
    sector_times_list: List[List[float]] = []
    corner_speeds_list: List[List[float]] = []
    max_speeds: List[float] = []
    convergence_flags: List[bool] = []

    # Parameters that require GGV rebuilding
    ggv_altering_params = {
        SweepParameter.MASS,
        SweepParameter.AERO_CL,
        SweepParameter.AERO_CD,
        SweepParameter.POWER_SCALE,
        SweepParameter.TIRE_MU_SCALE,
    }

    n_speeds, n_ay = ggv_resolution

    for val in sorted_values:
        v_cand = copy.deepcopy(baseline_vehicle)
        _apply_parameter(v_cand, param, val, baseline_power)

        try:
            # Rebuild GGV if parameter alters friction/aero/mass or if GGV is not built
            if param in ggv_altering_params or v_cand._ggv_ax_accel is None:
                v_cand.build_ggv(n_speeds=n_speeds, n_ay=n_ay)

            res = solve_lap(v_cand, track)
            lap_times.append(float(res.total_time))
            sector_times_list.append([float(st) for st in res.sector_times])
            max_speeds.append(float(res.max_speed_kmh))
            convergence_flags.append(bool(res.solver_converged))

            # Extract corner minimum speeds
            try:
                dt = np.zeros(len(res.distances))
                for k in range(1, len(res.distances)):
                    ds = res.distances[k] - res.distances[k - 1]
                    dt[k] = ds / max(0.5 * (res.speeds[k] + res.speeds[k - 1]), 0.1)

                corners = detect_corners(
                    res.distances, res.speeds, res.curvatures,
                    res.lateral_g, res.longitudinal_g, dt=dt,
                )
                corner_speeds_list.append([float(c.min_speed_mps) for c in corners])
            except Exception:
                corner_speeds_list.append([])

        except (LapSimError, Exception):
            lap_times.append(float("nan"))
            sector_times_list.append([])
            corner_speeds_list.append([])
            max_speeds.append(float("nan"))
            convergence_flags.append(False)

    # Compute deltas relative to baseline index
    ref_time = lap_times[idx_closest] if not math.isnan(lap_times[idx_closest]) else np.nanmin(lap_times)
    deltas = [
        float(t - ref_time) if not math.isnan(t) and not math.isnan(ref_time) else float("nan")
        for t in lap_times
    ]

    # Compute numerical sensitivities (dT/dp) via central differences
    sensitivities = _compute_sensitivities(sorted_values, lap_times)

    # Build human-readable engineering summary
    valid_times = [t for t in lap_times if not math.isnan(t)]
    if len(valid_times) >= 2:
        min_t, max_t = min(valid_times), max(valid_times)
        best_val = sorted_values[int(np.nanargmin(lap_times))]
        delta_span = max_t - min_t
        mean_sens = float(np.nanmean(sensitivities)) if len(sensitivities) else 0.0

        summary = (
            f"Sweep of {meta['description']} ({meta['unit']}) across [{sorted_values[0]:.2f}, {sorted_values[-1]:.2f}]: "
            f"Lap time span = {delta_span:.3f}s. Optimal candidate = {best_val:.2f} {meta['unit']} ({min_t:.3f}s). "
            f"Mean sensitivity dT/dp = {mean_sens:+.4e} s/{meta['unit']}."
        )
    else:
        summary = f"Sweep of {meta['description']} completed with insufficient converged points."

    return SweepResult(
        parameter=param.value,
        unit=meta["unit"],
        description=meta["description"],
        values=sorted_values,
        lap_times_s=lap_times,
        deltas_s=deltas,
        sector_times_s=sector_times_list,
        min_corner_speeds_mps=corner_speeds_list,
        max_speeds_kmh=max_speeds,
        sensitivities_s_per_unit=sensitivities,
        convergence_flags=convergence_flags,
        baseline_index=idx_closest,
        summary=summary,
        derivative_symbol=meta.get("derivative_symbol", "∂T/∂p"),
        sensitivity_unit=meta.get("sensitivity_unit", f"s/{meta['unit']}"),
    )


def _compute_sensitivities(x: List[float], y: List[float]) -> List[float]:
    """Compute first derivative dy/dx using central differences with forward/backward endpoints."""
    n = len(x)
    sens = [float("nan")] * n
    if n < 2:
        return sens

    for i in range(n):
        if math.isnan(y[i]):
            continue
        if i == 0:
            # Forward difference
            if not math.isnan(y[1]) and abs(x[1] - x[0]) > 1e-12:
                sens[i] = (y[1] - y[0]) / (x[1] - x[0])
        elif i == n - 1:
            # Backward difference
            if not math.isnan(y[n - 2]) and abs(x[n - 1] - x[n - 2]) > 1e-12:
                sens[i] = (y[n - 1] - y[n - 2]) / (x[n - 1] - x[n - 2])
        else:
            # Central difference
            y_next, y_prev = y[i + 1], y[i - 1]
            x_next, x_prev = x[i + 1], x[i - 1]
            if not math.isnan(y_next) and not math.isnan(y_prev) and abs(x_next - x_prev) > 1e-12:
                sens[i] = (y_next - y_prev) / (x_next - x_prev)
            elif not math.isnan(y_next) and abs(x_next - x[i]) > 1e-12:
                sens[i] = (y_next - y[i]) / (x_next - x[i])
            elif not math.isnan(y_prev) and abs(x[i] - x_prev) > 1e-12:
                sens[i] = (y[i] - y_prev) / (x[i] - x_prev)

    return sens
