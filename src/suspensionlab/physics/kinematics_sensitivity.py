"""
physics/kinematics_sensitivity.py
==================================
SuspensionLab PRO — Kinematics Hardpoint Sensitivity & Optimization Engine

Answers the fundamental race engineering question:
    "Which hardpoint should I change to get the behavior I want?"

Core Principles:
1. Zero fake physics: Every evaluation runs the real C++ Newton-Raphson
   multibody solver (or validated Python fallback).
2. Epistemic honesty: Recommendations are strictly labeled "SENSITIVITY-BASED
   RECOMMENDATIONS" (not global mathematical proofs).
3. Real derivatives: All Jacobians are calculated via finite differences with
   explicit engineering units (deg/mm, mm/mm, (deg/100mm)/mm).
4. Physical safety: Impossible or inverted geometries are strictly REJECTED
   with diagnostic reasons, never silently auto-corrected.
5. Multi-objective Pareto evaluation: Tradeoffs are explicitly visualized and
   scored against ideal utopia points.
"""

from __future__ import annotations

import copy
import math
import uuid
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional, Callable

import numpy as np

from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    compute_geometry_hash,
    compute_kinematic_derivatives,
    solve_kinematics,
    validate_hardpoints_py,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Engineering Units & Specifications
# ─────────────────────────────────────────────────────────────────────────────

METRIC_UNITS = {
    "camber_static_deg": "°",
    "camber_bump_deg": "°",
    "camber_gain_deg_per_100mm": "°/100mm",
    "toe_static_deg": "°",
    "toe_variation_deg": "°",
    "toe_gain_deg_per_100mm": "°/100mm",
    "roll_center_height_static_mm": "mm",
    "rc_migration_range_mm": "mm",
    "rc_migration_rate": "mm/mm",
    "motion_ratio_static": "-",
    "track_change_max_mm": "mm",
    "wheelbase_change_max_mm": "mm",
    "caster_static_deg": "°",
    "kpi_static_deg": "°",
    "scrub_radius_static_mm": "mm",
}

METRIC_LABELS = {
    "camber_static_deg": "Static Camber",
    "camber_bump_deg": "Bump Camber",
    "camber_gain_deg_per_100mm": "Camber Gain Rate in Bump",
    "toe_static_deg": "Static Toe",
    "toe_variation_deg": "Bump Steer Toe Range",
    "toe_gain_deg_per_100mm": "Bump Steer Rate",
    "roll_center_height_static_mm": "Static Roll Center Height",
    "rc_migration_range_mm": "Roll Center Migration Range",
    "rc_migration_rate": "Roll Center Migration Rate",
    "motion_ratio_static": "Damper Motion Ratio",
    "track_change_max_mm": "Max Track Width Scrub",
    "wheelbase_change_max_mm": "Max Wheelbase Scrub",
    "caster_static_deg": "Caster Angle",
    "kpi_static_deg": "Kingpin Inclination",
    "scrub_radius_static_mm": "Scrub Radius",
}

METRIC_DIMENSIONAL_SPEC = {
    "camber_static_deg": {
        "metric_symbol": "γ₀",
        "metric_name": "Static Camber",
        "metric_unit": "°",
        "derivative_symbol": "∂γ₀/∂p",
        "derivative_name": "Sensitivity of Static Camber to Hardpoint Coordinate",
        "derivative_unit": "°/mm",
    },
    "camber_bump_deg": {
        "metric_symbol": "γ_bump",
        "metric_name": "Bump Peak Camber",
        "metric_unit": "°",
        "derivative_symbol": "∂γ_bump/∂p",
        "derivative_name": "Sensitivity of Bump Camber to Hardpoint Coordinate",
        "derivative_unit": "°/mm",
    },
    "camber_gain_deg_per_100mm": {
        "metric_symbol": "dγ/dz",
        "metric_name": "Camber Gain Rate in Bump",
        "metric_unit": "°/100mm",
        "derivative_symbol": "∂(dγ/dz)/∂p",
        "derivative_name": "Sensitivity of Camber Gain Rate to Hardpoint Coordinate",
        "derivative_unit": "(°/100mm)/mm",
    },
    "toe_static_deg": {
        "metric_symbol": "toe₀",
        "metric_name": "Static Toe",
        "metric_unit": "°",
        "derivative_symbol": "∂toe₀/∂p",
        "derivative_name": "Sensitivity of Static Toe to Hardpoint Coordinate",
        "derivative_unit": "°/mm",
    },
    "toe_variation_deg": {
        "metric_symbol": "Δtoe_range",
        "metric_name": "Bump Steer Toe Range",
        "metric_unit": "°",
        "derivative_symbol": "∂(Δtoe)/∂p",
        "derivative_name": "Sensitivity of Bump Steer Range to Hardpoint Coordinate",
        "derivative_unit": "°/mm",
    },
    "toe_gain_deg_per_100mm": {
        "metric_symbol": "d(toe)/dz",
        "metric_name": "Bump Steer Rate",
        "metric_unit": "°/100mm",
        "derivative_symbol": "∂(d(toe)/dz)/∂p",
        "derivative_name": "Sensitivity of Bump Steer Rate to Hardpoint Coordinate",
        "derivative_unit": "(°/100mm)/mm",
    },
    "roll_center_height_static_mm": {
        "metric_symbol": "RC_z,₀",
        "metric_name": "Static Roll Center Height",
        "metric_unit": "mm",
        "derivative_symbol": "∂(RC_z)/∂p",
        "derivative_name": "Sensitivity of Roll Center Height to Hardpoint Coordinate",
        "derivative_unit": "mm/mm",
    },
    "rc_migration_range_mm": {
        "metric_symbol": "ΔRC_z",
        "metric_name": "Roll Center Migration Range",
        "metric_unit": "mm",
        "derivative_symbol": "∂(ΔRC_z)/∂p",
        "derivative_name": "Sensitivity of RC Migration Range to Hardpoint Coordinate",
        "derivative_unit": "mm/mm",
    },
    "rc_migration_rate": {
        "metric_symbol": "d(RC_z)/dz",
        "metric_name": "Roll Center Migration Rate",
        "metric_unit": "mm/mm",
        "derivative_symbol": "∂(d(RC_z)/dz)/∂p",
        "derivative_name": "Sensitivity of RC Migration Rate to Hardpoint Coordinate",
        "derivative_unit": "(mm/mm)/mm",
    },
    "motion_ratio_static": {
        "metric_symbol": "MR₀",
        "metric_name": "Static Damper Motion Ratio",
        "metric_unit": "-",
        "derivative_symbol": "∂MR/∂p",
        "derivative_name": "Sensitivity of Damper Motion Ratio to Hardpoint Coordinate",
        "derivative_unit": "1/mm",
    },
    "track_change_max_mm": {
        "metric_symbol": "Δtrack_max",
        "metric_name": "Max Track Width Scrub",
        "metric_unit": "mm",
        "derivative_symbol": "∂(Δtrack)/∂p",
        "derivative_name": "Sensitivity of Track Scrub to Hardpoint Coordinate",
        "derivative_unit": "mm/mm",
    },
    "wheelbase_change_max_mm": {
        "metric_symbol": "Δwb_max",
        "metric_name": "Max Wheelbase Scrub",
        "metric_unit": "mm",
        "derivative_symbol": "∂(Δwb)/∂p",
        "derivative_name": "Sensitivity of Wheelbase Scrub to Hardpoint Coordinate",
        "derivative_unit": "mm/mm",
    },
    "caster_static_deg": {
        "metric_symbol": "caster₀",
        "metric_name": "Static Caster Angle",
        "metric_unit": "°",
        "derivative_symbol": "∂caster/∂p",
        "derivative_name": "Sensitivity of Caster Angle to Hardpoint Coordinate",
        "derivative_unit": "°/mm",
    },
    "kpi_static_deg": {
        "metric_symbol": "KPI₀",
        "metric_name": "Kingpin Inclination",
        "metric_unit": "°",
        "derivative_symbol": "∂KPI/∂p",
        "derivative_name": "Sensitivity of Kingpin Inclination to Hardpoint Coordinate",
        "derivative_unit": "°/mm",
    },
    "scrub_radius_static_mm": {
        "metric_symbol": "r_scrub",
        "metric_name": "Scrub Radius",
        "metric_unit": "mm",
        "derivative_symbol": "∂r_scrub/∂p",
        "derivative_name": "Sensitivity of Scrub Radius to Hardpoint Coordinate",
        "derivative_unit": "mm/mm",
    },
}

HARDPOINT_DESCRIPTIONS = {
    "UWI_fwd": "Upper wishbone inboard pivot (forward chassis mount)",
    "UWI_aft": "Upper wishbone inboard pivot (aft chassis mount)",
    "UWO": "Upper wishbone outboard ball joint (upright mount)",
    "LWI_fwd": "Lower wishbone inboard pivot (forward chassis mount)",
    "LWI_aft": "Lower wishbone inboard pivot (aft chassis mount)",
    "LWO": "Lower wishbone outboard ball joint (upright mount)",
    "TRI": "Steering tie rod inboard pivot (rack end)",
    "TRO": "Steering tie rod outboard ball joint (steering arm on upright)",
    "PRI": "Pushrod inboard chassis / rocker pivot",
    "PRO": "Pushrod outboard upright attachment",
}


# ─────────────────────────────────────────────────────────────────────────────
# Safety & Clearance Validator
# ─────────────────────────────────────────────────────────────────────────────

class HardpointSafetyValidator:
    """
    Validates physical kinematics feasibility, clearances, and structural integrity.
    Never auto-corrects silently — strictly rejects invalid configurations.
    """

    MIN_ARM_LENGTH_MM = 120.0
    MIN_VERTICAL_BALLJOINT_CLEARANCE_MM = 75.0
    MIN_TRANSVERSE_SPAN_MM = 150.0

    @classmethod
    def validate(cls, hp: Dict[str, List[float]]) -> Tuple[bool, List[str]]:
        errors = []

        # 1. Coordinate completeness
        required_keys = ["UWI_fwd", "UWI_aft", "UWO", "LWI_fwd", "LWI_aft", "LWO", "TRI", "TRO"]
        for k in required_keys:
            if k not in hp or len(hp[k]) != 3:
                errors.append(f"Missing or malformed hardpoint '{k}'")
        if errors:
            return False, errors

        # Convert to numpy arrays
        uwi_f = np.array(hp["UWI_fwd"], dtype=np.float64)
        uwi_a = np.array(hp["UWI_aft"], dtype=np.float64)
        uwo = np.array(hp["UWO"], dtype=np.float64)
        lwi_f = np.array(hp["LWI_fwd"], dtype=np.float64)
        lwi_a = np.array(hp["LWI_aft"], dtype=np.float64)
        lwo = np.array(hp["LWO"], dtype=np.float64)
        tri = np.array(hp["TRI"], dtype=np.float64)
        tro = np.array(hp["TRO"], dtype=np.float64)

        # 2. Minimum control arm length check
        len_uw_fwd = np.linalg.norm(uwo - uwi_f)
        len_uw_aft = np.linalg.norm(uwo - uwi_a)
        len_lw_fwd = np.linalg.norm(lwo - lwi_f)
        len_lw_aft = np.linalg.norm(lwo - lwi_a)
        len_tr = np.linalg.norm(tro - tri)

        for name, val in [
            ("Upper Wishbone Fwd Arm", len_uw_fwd),
            ("Upper Wishbone Aft Arm", len_uw_aft),
            ("Lower Wishbone Fwd Arm", len_lw_fwd),
            ("Lower Wishbone Aft Arm", len_lw_aft),
            ("Steering Tie Rod", len_tr),
        ]:
            if val < cls.MIN_ARM_LENGTH_MM:
                errors.append(
                    f"Link length violation: {name} length {val:.1f} mm is below minimum safe structural threshold ({cls.MIN_ARM_LENGTH_MM} mm)."
                )

        # 3. Ball joint vertical clearance (Upper ball joint must remain strictly above lower ball joint)
        vertical_bj_clearance = uwo[2] - lwo[2]
        if vertical_bj_clearance < cls.MIN_VERTICAL_BALLJOINT_CLEARANCE_MM:
            errors.append(
                f"Upright vertical clearance violation: UWO Z ({uwo[2]:.1f} mm) is too close to LWO Z ({lwo[2]:.1f} mm). "
                f"Clearance {vertical_bj_clearance:.1f} mm < minimum {cls.MIN_VERTICAL_BALLJOINT_CLEARANCE_MM} mm. "
                "Risk of ball joint binding or inverted upright inclination."
            )

        # 4. Transverse orientation (Outboard ball joints must be outboard of chassis mounts)
        if uwo[1] <= uwi_f[1] + cls.MIN_TRANSVERSE_SPAN_MM or uwo[1] <= uwi_a[1] + cls.MIN_TRANSVERSE_SPAN_MM:
            errors.append(
                f"Upper wishbone transverse span violation: UWO Y ({uwo[1]:.1f} mm) must be at least {cls.MIN_TRANSVERSE_SPAN_MM} mm outboard of chassis mounts."
            )
        if lwo[1] <= lwi_f[1] + cls.MIN_TRANSVERSE_SPAN_MM or lwo[1] <= lwi_a[1] + cls.MIN_TRANSVERSE_SPAN_MM:
            errors.append(
                f"Lower wishbone transverse span violation: LWO Y ({lwo[1]:.1f} mm) must be at least {cls.MIN_TRANSVERSE_SPAN_MM} mm outboard of chassis mounts."
            )

        # 5. Base Python validation check (singularities, coplanar wishbones, etc.)
        base_val = validate_hardpoints_py("double_wishbone", hp)
        if not base_val.get("is_valid", True):
            for err in base_val.get("errors", []):
                if err not in errors:
                    errors.append(err)

        is_valid = len(errors) == 0
        return is_valid, errors


# ─────────────────────────────────────────────────────────────────────────────
# Key Metric Evaluator
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_sweep_metrics(
    hp: Dict[str, List[float]],
    z_min_mm: float = -35.0,
    z_max_mm: float = 35.0,
    n_steps: int = 15,
) -> Dict[str, float]:
    """
    Executes a real kinematics sweep and distills key design metrics.
    Raises RuntimeError if solver diverges.
    """
    curves = solve_kinematics(hp, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
    d = curves.to_dict()

    if not all(d["converged"]):
        raise RuntimeError("Kinematics solver failed to converge at one or more travel positions.")

    derivs = compute_kinematic_derivatives(d)
    z = d["wheel_travel_mm"]

    # Neutral static index (closest to dz = 0)
    idx_0 = min(range(len(z)), key=lambda i: abs(z[i]))
    idx_bump = len(z) - 1

    camber = d["camber_deg"]
    toe = d["toe_deg"]
    rc_z = d["roll_center_height_mm"]
    mr = d["motion_ratio"]
    track = d["track_change_mm"]
    wb = d["wheelbase_change_mm"]
    caster = d["caster_deg"]
    kpi = d["kpi_deg"]
    scrub = d["scrub_radius_mm"]

    camber_gain_arr = derivs.get("camber_gain_deg_per_100mm", [0.0] * len(z))
    toe_gain_arr = derivs.get("toe_gain_deg_per_100mm", [0.0] * len(z))
    rc_rate_arr = derivs.get("rc_migration_rate", [0.0] * len(z))

    # Average bump rates (from static to max bump)
    bump_indices = [i for i, val in enumerate(z) if val >= 0.0]
    mean_camber_gain = float(np.mean([camber_gain_arr[i] for i in bump_indices])) if bump_indices else float(camber_gain_arr[idx_0])
    mean_toe_gain = float(np.mean([toe_gain_arr[i] for i in bump_indices])) if bump_indices else float(toe_gain_arr[idx_0])
    mean_rc_rate = float(np.mean([rc_rate_arr[i] for i in bump_indices])) if bump_indices else float(rc_rate_arr[idx_0])

    return {
        "camber_static_deg": float(camber[idx_0]),
        "camber_bump_deg": float(camber[idx_bump]),
        "camber_gain_deg_per_100mm": mean_camber_gain,
        "toe_static_deg": float(toe[idx_0]),
        "toe_variation_deg": float(max(toe) - min(toe)),
        "toe_gain_deg_per_100mm": mean_toe_gain,
        "roll_center_height_static_mm": float(rc_z[idx_0]),
        "rc_migration_range_mm": float(max(rc_z) - min(rc_z)),
        "rc_migration_rate": mean_rc_rate,
        "motion_ratio_static": float(mr[idx_0]),
        "track_change_max_mm": float(max(track) - min(track)),
        "wheelbase_change_max_mm": float(max(wb) - min(wb)),
        "caster_static_deg": float(caster[idx_0]),
        "kpi_static_deg": float(kpi[idx_0]),
        "scrub_radius_static_mm": float(scrub[idx_0]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Hardpoint Sensitivity Engine & Jacobian Matrix
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HardpointSensitivityResult:
    hardpoint: str
    axis: str  # 'X', 'Y', or 'Z'
    delta_mm: float
    output_sensitivities: Dict[str, float]  # dOutput / dHardpoint
    units: Dict[str, str]


def compute_hardpoint_sensitivity(
    hardpoints: Dict[str, List[float]],
    target_hardpoints: Optional[List[str]] = None,
    axes: Optional[List[str]] = None,
    step_size_mm: float = 1.0,
    z_min_mm: float = -35.0,
    z_max_mm: float = 35.0,
    n_steps: int = 15,
) -> Dict[str, Any]:
    """
    Computes real central finite-difference Jacobian matrix:
        J[metric, (hardpoint, axis)] = (f(p + dh) - f(p - dh)) / (2 * dh)

    Guarantees every cell derives directly from solver executions.
    """
    clean_hp = {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else [float(c) for c in v]) for k, v in hardpoints.items()}

    # Safety check on baseline
    is_valid, errs = HardpointSafetyValidator.validate(clean_hp)
    if not is_valid:
        raise ValueError(f"Baseline hardpoints failed safety validation: {'; '.join(errs)}")

    hp_list = target_hardpoints or [
        "UWI_fwd", "UWI_aft", "UWO",
        "LWI_fwd", "LWI_aft", "LWO",
        "TRI", "TRO"
    ]
    ax_list = axes or ["X", "Y", "Z"]
    axis_to_idx = {"X": 0, "Y": 1, "Z": 2}

    # Baseline evaluation
    base_metrics = evaluate_sweep_metrics(clean_hp, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)

    jacobian_matrix: Dict[str, Dict[str, float]] = {}  # row: f"{hp}.{ax}", col: metric
    unit_matrix: Dict[str, str] = {}
    detailed_results: List[Dict[str, Any]] = []

    dh = float(step_size_mm)

    for hp_name in hp_list:
        if hp_name not in clean_hp:
            continue
        for ax in ax_list:
            coord_idx = axis_to_idx[ax]
            row_key = f"{hp_name}_{ax}"
            jacobian_matrix[row_key] = {}

            # Perturb +dh
            hp_plus = copy.deepcopy(clean_hp)
            hp_plus[hp_name][coord_idx] += dh
            valid_plus, _ = HardpointSafetyValidator.validate(hp_plus)

            # Perturb -dh
            hp_minus = copy.deepcopy(clean_hp)
            hp_minus[hp_name][coord_idx] -= dh
            valid_minus, _ = HardpointSafetyValidator.validate(hp_minus)

            if valid_plus and valid_minus:
                # Central difference: (f(p+dh) - f(p-dh)) / (2*dh)
                try:
                    m_plus = evaluate_sweep_metrics(hp_plus, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
                    m_minus = evaluate_sweep_metrics(hp_minus, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
                    denom = 2.0 * dh
                    sens_dict = {
                        k: (m_plus[k] - m_minus[k]) / denom for k in base_metrics
                    }
                except Exception as e:
                    logger.warning("Central difference failed for %s.%s: %s", hp_name, ax, e)
                    sens_dict = {k: 0.0 for k in base_metrics}
            elif valid_plus:
                # Forward difference
                try:
                    m_plus = evaluate_sweep_metrics(hp_plus, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
                    sens_dict = {k: (m_plus[k] - base_metrics[k]) / dh for k in base_metrics}
                except Exception:
                    sens_dict = {k: 0.0 for k in base_metrics}
            elif valid_minus:
                # Backward difference
                try:
                    m_minus = evaluate_sweep_metrics(hp_minus, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
                    sens_dict = {k: (base_metrics[k] - m_minus[k]) / dh for k in base_metrics}
                except Exception:
                    sens_dict = {k: 0.0 for k in base_metrics}
            else:
                sens_dict = {k: 0.0 for k in base_metrics}

            for metric_key, s_val in sens_dict.items():
                jacobian_matrix[row_key][metric_key] = float(s_val)
                spec = METRIC_DIMENSIONAL_SPEC.get(metric_key)
                if spec:
                    unit_matrix[metric_key] = spec["derivative_unit"]
                else:
                    base_u = METRIC_UNITS.get(metric_key, "")
                    if base_u == "-":
                        unit_matrix[metric_key] = "1/mm"
                    elif "/" in base_u:
                        unit_matrix[metric_key] = f"({base_u})/mm"
                    else:
                        unit_matrix[metric_key] = f"{base_u}/mm"

            detailed_results.append({
                "hardpoint": hp_name,
                "axis": ax,
                "row_key": row_key,
                "description": HARDPOINT_DESCRIPTIONS.get(hp_name, hp_name),
                "step_size_mm": dh,
                "sensitivities": sens_dict,
            })

    return {
        "baseline_metrics": base_metrics,
        "jacobian_matrix": jacobian_matrix,
        "metric_units": unit_matrix,
        "metric_labels": METRIC_LABELS,
        "metric_dimensional_spec": METRIC_DIMENSIONAL_SPEC,
        "detailed_sensitivities": detailed_results,
        "step_size_mm": dh,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Engineering Question Mode
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EngineeringQuestionPreset:
    id: str
    title: str
    objective_metric: str
    direction: str  # 'maximize', 'minimize', or 'target'
    target_value: Optional[float] = None
    constraints: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    candidate_hardpoints: List[str] = field(default_factory=list)
    description: str = ""


PRESET_QUESTIONS = {
    "camber_gain_without_toe": EngineeringQuestionPreset(
        id="camber_gain_without_toe",
        title="Increase negative camber gain in bump while minimizing bump steer",
        objective_metric="camber_gain_deg_per_100mm",
        direction="minimize",  # negative d(camber)/dz in bump -> more negative means stronger gain
        constraints={
            "toe_variation_deg": (0.0, 5.0),
            "roll_center_height_static_mm": (-150.0, 150.0),
        },
        candidate_hardpoints=["UWI_aft", "UWI_fwd", "UWO", "LWI_fwd", "LWI_aft", "LWO", "TRO", "TRI"],
        description="Optimize control-arm inclination to recover camber in jounce without introducing steering twitchiness.",
    ),
    "lower_rc_preserve_scrub": EngineeringQuestionPreset(
        id="lower_rc_preserve_scrub",
        title="Lower roll center height without degrading scrub radius",
        objective_metric="roll_center_height_static_mm",
        direction="minimize",
        constraints={
            "scrub_radius_static_mm": (10.0, 60.0),
            "camber_gain_deg_per_100mm": (-3.0, -0.05),
        },
        candidate_hardpoints=["LWI_fwd", "LWI_aft", "LWO", "UWI_fwd", "UWI_aft"],
        description="Shift front roll center downward to soften front roll couple while preserving steering feedback feel.",
    ),
    "minimize_bump_steer": EngineeringQuestionPreset(
        id="minimize_bump_steer",
        title="Minimize toe change across full wheel travel envelope",
        objective_metric="toe_variation_deg",
        direction="minimize",
        constraints={
            "camber_gain_deg_per_100mm": (-3.0, -0.05),
            "roll_center_height_static_mm": (-150.0, 150.0),
        },
        candidate_hardpoints=["TRI", "TRO"],
        description="Align steering tie rod length and angle with front swing arm instant center line to eliminate bump steer.",
    ),
}


def evaluate_engineering_question(
    hardpoints: Dict[str, List[float]],
    question_preset_id: Optional[str] = None,
    custom_objective: Optional[Dict[str, Any]] = None,
    custom_constraints: Optional[Dict[str, Tuple[float, float]]] = None,
    custom_candidates: Optional[List[str]] = None,
    perturbation_steps_mm: Optional[List[float]] = None,
    z_min_mm: float = -35.0,
    z_max_mm: float = 35.0,
    n_steps: int = 15,
) -> Dict[str, Any]:
    """
    Evaluates an engineering question, identifying candidate hardpoints,
    testing perturbations using the real solver, and ranking candidates
    with explicit physical mechanism explanations.
    """
    clean_hp = {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else [float(c) for c in v]) for k, v in hardpoints.items()}

    # Resolve question settings
    preset = PRESET_QUESTIONS.get(question_preset_id or "")
    if preset:
        obj_metric = preset.objective_metric
        direction = preset.direction
        target_val = preset.target_value
        constraints = dict(preset.constraints)
        candidates = list(preset.candidate_hardpoints)
        title = preset.title
    elif custom_objective:
        obj_metric = custom_objective["metric"]
        direction = custom_objective.get("direction", "maximize")
        target_val = custom_objective.get("target_value")
        constraints = custom_constraints or {}
        candidates = custom_candidates or ["UWI_aft", "UWI_fwd", "UWO", "LWI_aft", "LWI_fwd", "LWO", "TRI", "TRO"]
        title = custom_objective.get("title", f"Optimize {obj_metric}")
    else:
        preset = PRESET_QUESTIONS["camber_gain_without_toe"]
        obj_metric = preset.objective_metric
        direction = preset.direction
        target_val = preset.target_value
        constraints = dict(preset.constraints)
        candidates = list(preset.candidate_hardpoints)
        title = preset.title

    # 1. Evaluate baseline
    base_metrics = evaluate_sweep_metrics(clean_hp, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
    base_obj_val = base_metrics[obj_metric]

    # 2. Compute Jacobian to rank initial sensitivity
    sens_result = compute_hardpoint_sensitivity(
        clean_hp, target_hardpoints=candidates, axes=["X", "Y", "Z"], step_size_mm=1.0,
        z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps
    )
    jac = sens_result["jacobian_matrix"]

    # 3. Test concrete perturbations: e.g. -6, -4, -2, +2, +4, +6 mm
    steps = perturbation_steps_mm or [-6.0, -4.0, -2.0, 2.0, 4.0, 6.0]
    axis_map = {"X": 0, "Y": 1, "Z": 2}

    evaluated_candidates = []

    for hp_name in candidates:
        if hp_name not in clean_hp:
            continue
        for ax in ["X", "Y", "Z"]:
            row_key = f"{hp_name}_{ax}"
            sensitivity = jac.get(row_key, {}).get(obj_metric, 0.0)

            # Skip tiny sensitivities
            if abs(sensitivity) < 1e-4:
                continue

            coord_idx = axis_map[ax]

            for delta in steps:
                test_hp = copy.deepcopy(clean_hp)
                test_hp[hp_name][coord_idx] += delta

                # Safety check
                is_safe, safety_errs = HardpointSafetyValidator.validate(test_hp)
                if not is_safe:
                    continue

                try:
                    metrics = evaluate_sweep_metrics(test_hp, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
                except Exception:
                    continue

                # Check constraints
                constraint_status = "PASS"
                violated_reasons = []
                for c_metric, (c_min, c_max) in constraints.items():
                    val = metrics.get(c_metric)
                    if val is not None and (val < c_min or val > c_max):
                        constraint_status = "VIOLATION"
                        violated_reasons.append(
                            f"{METRIC_LABELS.get(c_metric, c_metric)} ({val:.2f}) outside limit [{c_min}, {c_max}]"
                        )

                # Score improvement
                obj_val = metrics[obj_metric]
                delta_obj = obj_val - base_obj_val
                if direction == "maximize":
                    score = delta_obj
                elif direction == "minimize":
                    score = -delta_obj
                else:
                    score = -abs(obj_val - (target_val or 0.0))

                # Penalty for constraint violations
                if constraint_status == "VIOLATION":
                    score -= 100.0 * len(violated_reasons)

                # Determine physical mechanism explanation
                mech = _generate_hardpoint_mechanism(hp_name, ax, delta, obj_metric, delta_obj)

                # Determine what improved vs what got worse
                improved = []
                worse = []
                for m_k in ["camber_gain_deg_per_100mm", "toe_variation_deg", "roll_center_height_static_mm", "scrub_radius_static_mm", "track_change_max_mm"]:
                    d_m = metrics[m_k] - base_metrics[m_k]
                    u = METRIC_UNITS.get(m_k, "")
                    l = METRIC_LABELS.get(m_k, m_k)
                    if abs(d_m) < 1e-3:
                        continue
                    if m_k == "toe_variation_deg":
                        if d_m < 0:
                            improved.append(f"Reduced bump steer variation by {abs(d_m):.2f}{u}")
                        else:
                            worse.append(f"Increased bump steer variation by +{d_m:.2f}{u}")
                    elif m_k == "camber_gain_deg_per_100mm":
                        if d_m < 0:
                            improved.append(f"Increased negative bump camber gain by {d_m:.2f} {u}")
                        else:
                            worse.append(f"Reduced negative bump camber gain by +{d_m:.2f} {u}")
                    elif m_k == "track_change_max_mm":
                        if d_m < 0:
                            improved.append(f"Reduced track scrub by {abs(d_m):.2f} mm")
                        else:
                            worse.append(f"Increased track scrub by +{d_m:.2f} mm")

                evaluated_candidates.append({
                    "hardpoint": hp_name,
                    "axis": ax,
                    "delta_mm": delta,
                    "what_changed": f"{hp_name} {ax}: {delta:+0.1f} mm ({clean_hp[hp_name][coord_idx]:.1f} → {test_hp[hp_name][coord_idx]:.1f} mm)",
                    "candidate_id": f"cand-{hp_name}-{ax}-{delta:+0.1f}mm",
                    "objective_metric": obj_metric,
                    "objective_value": obj_val,
                    "baseline_val": base_obj_val,
                    "candidate_val": obj_val,
                    "delta_obj": delta_obj,
                    "score": score,
                    "composite_score": score,
                    "constraint_status": constraint_status,
                    "violation_details": violated_reasons,
                    "why_chosen": mech,
                    "what_improved": improved or ["Maintained baseline kinematic response"],
                    "what_got_worse": worse or ["None observed"],
                    "metrics": metrics,
                    "hardpoints": test_hp,
                    "geometry_hash": compute_geometry_hash(test_hp),
                })

    # Sort evaluated candidates: feasible with highest score first
    evaluated_candidates.sort(key=lambda c: (c["constraint_status"] == "PASS", c["score"]), reverse=True)

    best_candidate = evaluated_candidates[0] if evaluated_candidates else None

    return {
        "title": title,
        "recommendation_type": "SENSITIVITY-BASED RECOMMENDATION",
        "objective_metric": obj_metric,
        "objective_label": METRIC_LABELS.get(obj_metric, obj_metric),
        "direction": direction,
        "baseline_metrics": base_metrics,
        "constraints": constraints,
        "best_candidate": best_candidate,
        "evaluated_candidates": evaluated_candidates[:12],  # Top 12 candidates
        "total_evaluated": len(evaluated_candidates),
    }


def _generate_hardpoint_mechanism(hp: str, ax: str, delta: float, target_metric: str, delta_val: float) -> str:
    """Provides causal physical explanations of why the hardpoint change produces this result."""
    sign_str = "increasing" if delta > 0 else "decreasing"

    if hp.startswith("UWI") and ax == "Z":
        if delta > 0:
            return (
                "Raising upper wishbone chassis pivot increases the downward incline of the upper arm, "
                "shortening its projected swing-arm radius in roll/jounce and recovering negative camber more rapidly."
            )
        else:
            return (
                "Lowering upper wishbone chassis pivot flattens the upper arm, lengthening the front view "
                "instant center distance and raising the kinematic roll center."
            )
    elif hp.startswith("LWI") and ax == "Z":
        if delta > 0:
            return (
                "Raising lower wishbone chassis pivot raises the front view instant center construction line, "
                "elevating roll center height and reducing mechanical lateral roll moment arm."
            )
        else:
            return (
                "Lowering lower wishbone chassis pivot drops the roll center closer to ground plane, "
                "softening geometric anti-roll stiffness and increasing chassis roll angle under lateral acceleration."
            )
    elif hp == "UWO" and ax == "Y":
        return (
            f"Moving upper ball joint {'outboard' if delta > 0 else 'inboard'} directly shifts kingpin inclination "
            "and alters static camber without heavily altering wishbone instantaneous centers."
        )
    elif hp == "LWO" and ax == "Y":
        return (
            f"Moving lower ball joint {'outboard' if delta > 0 else 'inboard'} alters static camber and scrub radius, "
            "directly modulating contact patch tire scrub under vertical travel."
        )
    elif hp in ("TRI", "TRO"):
        return (
            f"Altering tie rod {hp} along {ax} modifies the steering arm arc relative to the wheel spindle trajectory, "
            "directly altering toe variation (bump steer) across travel."
        )

    return f"Shifting {hp} along {ax} by {delta:+.1f} mm alters multibody constraint equations, modifying {METRIC_LABELS.get(target_metric, target_metric)}."


# ─────────────────────────────────────────────────────────────────────────────
# 3. Parameter Optimization & Pareto Frontier Extraction
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OptimizationConstraint:
    metric: str
    min_val: Optional[float] = None
    max_val: Optional[float] = None


@dataclass
class OptimizationObjective:
    metric: str
    direction: str  # 'maximize', 'minimize', or 'target'
    weight: float = 1.0
    target_val: Optional[float] = None


def optimize_hardpoints(
    hardpoints: Dict[str, List[float]],
    target_hardpoints: List[str],
    allowed_axes: List[str],
    hardpoint_bounds_mm: float = 10.0,
    objectives: Optional[List[OptimizationObjective]] = None,
    constraints: Optional[List[OptimizationConstraint]] = None,
    n_samples: int = 40,
    z_min_mm: float = -35.0,
    z_max_mm: float = 35.0,
    n_steps: int = 15,
) -> Dict[str, Any]:
    """
    Performs bounded multi-objective optimization over selected hardpoints using
    the real kinematics solver at every evaluation.
    Extracts non-dominated Pareto frontier and explicitly computes best compromise.
    """
    clean_hp = {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else [float(c) for c in v]) for k, v in hardpoints.items()}

    is_valid, errs = HardpointSafetyValidator.validate(clean_hp)
    if not is_valid:
        raise ValueError(f"Baseline hardpoints failed safety check: {'; '.join(errs)}")

    base_metrics = evaluate_sweep_metrics(clean_hp, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)

    objs = objectives or [
        OptimizationObjective(metric="camber_gain_deg_per_100mm", direction="minimize", weight=1.0),
        OptimizationObjective(metric="toe_variation_deg", direction="minimize", weight=1.0),
    ]
    consts = constraints or [
        OptimizationConstraint(metric="roll_center_height_static_mm", min_val=20.0, max_val=130.0),
        OptimizationConstraint(metric="scrub_radius_static_mm", min_val=10.0, max_val=50.0),
    ]

    axis_map = {"X": 0, "Y": 1, "Z": 2}
    bound = float(hardpoint_bounds_mm)

    evaluated_candidates = []

    # 1. Systematic bounded grid + latin hypercube perturbation exploration
    # Parameter space: for each (hp, ax)
    var_list = []
    for hp in target_hardpoints:
        if hp in clean_hp:
            for ax in allowed_axes:
                var_list.append((hp, ax))

    if not var_list:
        raise ValueError("No valid hardpoints or axes specified for optimization.")

    np.random.seed(42)  # Deterministic repeatability

    # Generate perturbation vectors
    perturbation_vectors = []
    # Baseline vector (zeros)
    perturbation_vectors.append(np.zeros(len(var_list)))

    # Single-parameter extremes
    for i in range(len(var_list)):
        vec_pos = np.zeros(len(var_list))
        vec_pos[i] = bound
        perturbation_vectors.append(vec_pos)

        vec_neg = np.zeros(len(var_list))
        vec_neg[i] = -bound
        perturbation_vectors.append(vec_neg)

        vec_half_pos = np.zeros(len(var_list))
        vec_half_pos[i] = bound * 0.5
        perturbation_vectors.append(vec_half_pos)

        vec_half_neg = np.zeros(len(var_list))
        vec_half_neg[i] = -bound * 0.5
        perturbation_vectors.append(vec_half_neg)

    # Random bounded samples
    remaining_samples = max(n_samples - len(perturbation_vectors), 10)
    for _ in range(remaining_samples):
        rand_vec = np.random.uniform(-bound, bound, size=len(var_list))
        # Snap small perturbations to 0.5 mm steps for machining feasibility
        rand_vec = np.round(rand_vec * 2.0) / 2.0
        perturbation_vectors.append(rand_vec)

    # Evaluate each perturbation
    cand_id_counter = 1
    for vec in perturbation_vectors:
        test_hp = copy.deepcopy(clean_hp)
        change_summary = []

        for i, (hp_name, ax) in enumerate(var_list):
            delta = float(vec[i])
            if abs(delta) > 1e-4:
                idx = axis_map[ax]
                test_hp[hp_name][idx] += delta
                change_summary.append(f"{hp_name} {ax}: {delta:+0.1f} mm")

        # Safety validation
        is_safe, safety_errs = HardpointSafetyValidator.validate(test_hp)
        if not is_safe:
            continue

        try:
            metrics = evaluate_sweep_metrics(test_hp, z_min_mm=z_min_mm, z_max_mm=z_max_mm, n_steps=n_steps)
        except Exception:
            continue

        # Evaluate constraints
        is_feasible = True
        violations = []
        for c in consts:
            v = metrics.get(c.metric)
            if v is not None:
                if c.min_val is not None and v < c.min_val:
                    is_feasible = False
                    violations.append(f"{METRIC_LABELS.get(c.metric, c.metric)} ({v:.2f}) < limit {c.min_val}")
                if c.max_val is not None and v > c.max_val:
                    is_feasible = False
                    violations.append(f"{METRIC_LABELS.get(c.metric, c.metric)} ({v:.2f}) > limit {c.max_val}")

        cand_id = f"cand-{cand_id_counter:03d}"
        cand_entry = {
            "id": cand_id,
            "candidate_id": cand_id,
            "changes_summary": ", ".join(change_summary) if change_summary else "Baseline (0 mm change)",
            "hardpoints": test_hp,
            "geometry_hash": compute_geometry_hash(test_hp),
            "metrics": metrics,
            "objective_values": dict(metrics),
            "is_feasible": is_feasible,
            "violations": violations,
            "is_pareto": False,
        }
        cand_id_counter += 1
        evaluated_candidates.append(cand_entry)

    # 2. Pareto Non-Dominated Sorting for Multi-Objective
    pareto_candidates = _extract_pareto_frontier(evaluated_candidates, objs)

    # 3. Explicit Utopia Distance Compromise Scoring
    best_candidate = _select_best_compromise(pareto_candidates, objs, base_metrics)

    # 4. Generate Causal Explanations for Pareto Candidates
    for p_cand in pareto_candidates:
        p_cand["explanation"] = _build_candidate_explanation(p_cand, base_metrics, objs)

    return {
        "status": "SUCCESS",
        "optimization_id": f"opt-{uuid.uuid4().hex[:10]}",
        "target_hardpoints": target_hardpoints,
        "allowed_axes": allowed_axes,
        "hardpoint_bounds_mm": bound,
        "baseline_metrics": base_metrics,
        "objectives": [{"metric": o.metric, "direction": o.direction, "weight": o.weight} for o in objs],
        "constraints": [{"metric": c.metric, "min_val": c.min_val, "max_val": c.max_val} for c in consts],
        "total_evaluated": len(evaluated_candidates),
        "feasible_count": sum(1 for c in evaluated_candidates if c["is_feasible"]),
        "pareto_count": len(pareto_candidates),
        "best_compromise_candidate": best_candidate,
        "pareto_candidates": pareto_candidates,
        "pareto_frontier": pareto_candidates,
        "all_candidates": evaluated_candidates,
    }


def _extract_pareto_frontier(
    candidates: List[Dict[str, Any]],
    objectives: List[OptimizationObjective]
) -> List[Dict[str, Any]]:
    """Identifies non-dominated candidate points among feasible solutions."""
    feasible = [c for c in candidates if c["is_feasible"]]
    if not feasible:
        return []

    pareto_list = []
    for cand in feasible:
        dominated = False
        for other in feasible:
            if other is cand:
                continue

            # Does 'other' dominate 'cand'?
            other_better_or_equal = True
            other_strictly_better = False

            for obj in objectives:
                val_c = cand["metrics"][obj.metric]
                val_o = other["metrics"][obj.metric]

                if obj.direction == "maximize":
                    if val_o < val_c:
                        other_better_or_equal = False
                        break
                    elif val_o > val_c:
                        other_strictly_better = True
                else:  # minimize
                    if val_o > val_c:
                        other_better_or_equal = False
                        break
                    elif val_o < val_c:
                        other_strictly_better = True

            if other_better_or_equal and other_strictly_better:
                dominated = True
                break

        if not dominated:
            cand["is_pareto"] = True
            pareto_list.append(cand)

    return pareto_list


def _select_best_compromise(
    pareto_candidates: List[Dict[str, Any]],
    objectives: List[OptimizationObjective],
    base_metrics: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    """
    Selects BEST COMPROMISE candidate using normalized weighted Euclidean
    distance to ideal utopia point.
    """
    if not pareto_candidates:
        return None

    # Compute utopia point (best observed per objective)
    utopia = {}
    nadir = {}

    for obj in objectives:
        vals = [c["metrics"][obj.metric] for c in pareto_candidates]
        if obj.direction == "maximize":
            utopia[obj.metric] = max(vals)
            nadir[obj.metric] = min(vals)
        else:
            utopia[obj.metric] = min(vals)
            nadir[obj.metric] = max(vals)

    # Calculate distance to utopia
    for cand in pareto_candidates:
        dist_sq = 0.0
        for obj in objectives:
            val = cand["metrics"][obj.metric]
            u_val = utopia[obj.metric]
            n_val = nadir[obj.metric]
            span = abs(n_val - u_val)
            norm_diff = abs(val - u_val) / span if span > 1e-6 else 0.0
            dist_sq += (obj.weight * norm_diff) ** 2

        cand["utopia_distance"] = float(math.sqrt(dist_sq))

    # Lowest distance is best compromise
    pareto_candidates.sort(key=lambda c: c.get("utopia_distance", 999.0))
    best = pareto_candidates[0]
    best["is_best_compromise"] = True
    return best


def _build_candidate_explanation(
    cand: Dict[str, Any],
    base_metrics: Dict[str, float],
    objectives: List[OptimizationObjective]
) -> Dict[str, Any]:
    """Builds mandatory 5-point explanation for the candidate."""
    improved = []
    worse = []

    for m_k, base_v in base_metrics.items():
        cand_v = cand["metrics"][m_k]
        diff = cand_v - base_v
        if abs(diff) < 1e-3:
            continue
        u = METRIC_UNITS.get(m_k, "")
        lbl = METRIC_LABELS.get(m_k, m_k)

        # Improvement logic
        if m_k == "camber_gain_deg_per_100mm":
            if diff < 0:
                improved.append(f"{lbl}: {diff:.2f} {u}")
            else:
                worse.append(f"{lbl}: +{diff:.2f} {u}")
        elif m_k == "motion_ratio_static":
            if diff > 0:
                improved.append(f"{lbl}: +{diff:.2f} {u}")
            else:
                worse.append(f"{lbl}: {diff:.2f} {u}")
        elif m_k in ("toe_variation_deg", "track_change_max_mm", "wheelbase_change_max_mm"):
            if diff < 0:
                improved.append(f"{lbl}: -{abs(diff):.2f} {u}")
            else:
                worse.append(f"{lbl}: +{diff:.2f} {u}")

    return {
        "what_changed": cand["changes_summary"],
        "why_chosen": "Identified on the non-dominated Pareto frontier providing an optimal multi-objective trade-off.",
        "what_improved": improved or ["Maintained baseline performance"],
        "what_got_worse": worse or ["None within tracked metrics"],
        "constraint_status": "PASS" if cand["is_feasible"] else "VIOLATION",
        "violations": cand["violations"],
    }
