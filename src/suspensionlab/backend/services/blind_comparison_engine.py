"""
backend/services/blind_comparison_engine.py
===========================================
SuspensionLab PRO — Phase 5.3 Controlled Reveal & Prediction-vs-Outcome Comparison Engine.

Provides authoritative, deterministic, mathematically rigorous comparison logic
for versioned predictions (PREDICTION_SCHEMA_V1) evaluated under COMPARISON_POLICY_V1.

Core principles:
- Predict vs Actual comparison is derived data and NEVER overwrites prediction or outcome.
- Supports CATEGORICAL, DIRECTIONAL, QUANTITATIVE, and ENGINEERING_DECISION.
- Strict dimensional compatibility validation.
- Domain-specific tolerance evaluation only when explicitly declared (NO manufactured pass/fail).
- UNCOMPARABLE is an explicit first-class verdict.
- Undefined relative error when actual is zero is represented as None (never Infinity).
- Deterministic RFC 8785 canonical JSON comparison hashing.
- Strictly NO AI judging and NO engineer ranking.
"""
from __future__ import annotations

import copy
import enum
import hashlib
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("blind_comparison_engine")

COMPARISON_POLICY_V1 = "1"
DIRECTIONAL_ZERO_EPSILON: float = 1e-9

# Metrics representing authoritative structured engineering identifiers (Case A)
STRUCTURED_IDENTITY_METRICS: Set[str] = {
    "candidate",
    "candidate_id",
    "setup",
    "setup_id",
    "selected_option",
    "selected_candidate_id",
    "entity_id",
    "variant_id",
    "component_id",
    "configuration_id",
    "proposal_id",
    "candidate_choice",
}


def is_structured_identity_target(metric_name: str, entity_type: str = "") -> bool:
    """
    Determines whether a metric target represents a structured engineering identifier (Case A)
    or a free categorical label (Case B).
    """
    clean = (metric_name or "").strip().lower()
    if clean in STRUCTURED_IDENTITY_METRICS:
        return True
    if clean.endswith("_id") or clean.endswith("_code"):
        return True
    return False


def normalize_structured_identity(value: Any) -> Tuple[bool, Optional[str]]:
    """
    Normalizes a candidate/entity/setup identity value to its canonical string representation.
    Handles:
    - string / int (trimmed, exact string)
    - dict: {"id": ...} or {"candidate_id": ...} or {"setup_id": ...}
    Returns (success, canonical_id_str).
    If malformed or empty, returns (False, None).
    """
    if value is None:
        return False, None
    if isinstance(value, (str, int)):
        clean = str(value).strip()
        if not clean:
            return False, None
        return True, clean
    if isinstance(value, dict):
        cand = value.get("id") or value.get("candidate_id") or value.get("setup_id")
        if cand is not None and str(cand).strip():
            return True, str(cand).strip()
        return False, None
    return False, None


COMPARISON_POLICY_V1_SPEC: Dict[str, Any] = {
    "version": COMPARISON_POLICY_V1,
    "directional_zero_epsilon": DIRECTIONAL_ZERO_EPSILON,
    "structured_identity_metrics": sorted(list(STRUCTURED_IDENTITY_METRICS)),
    "rules": {
        "categorical_identity": {
            "case_a_structured_identity": "Exact case-sensitive match against authoritative entity identifier. Object {'id': '...'} normalized to canonical string.",
            "case_b_free_categorical": "Trimmed case-insensitive normalized string match.",
            "malformed_identity": "Yields UNCOMPARABLE when identifier structure cannot be resolved.",
        },
        "directional": {
            "zero_deadband": f"|delta| <= {DIRECTIONAL_ZERO_EPSILON} => CONSTANT (matches CONSTANT or NEUTRAL)",
            "positive_delta": f"delta > {DIRECTIONAL_ZERO_EPSILON} => INCREASE",
            "negative_delta": f"delta < -{DIRECTIONAL_ZERO_EPSILON} => DECREASE",
        },
        "quantitative": {
            "signed_error": "predicted - actual (in normalized base physical units)",
            "absolute_error": "|predicted - actual|",
            "relative_error": "|predicted - actual| / |actual| if |actual| > 1e-12 else None",
            "zero_denominator": "None (never Infinity or NaN)",
            "tolerances": "Evaluated only if explicitly configured; otherwise METRICS_ONLY (no synthetic binary verdict).",
        },
        "engineering_decision": {
            "candidate_identity": "Exact case-sensitive match against authoritative candidate ID. Dict {'id': '...'} normalized to canonical string.",
            "verdicts": "SUPPORTED if exact match, NOT_SUPPORTED otherwise.",
        },
        "uncomparable": "Emitted when target metric is missing, unit dimensions are incompatible, or identity structure is malformed.",
    },
}


def get_comparison_policy_spec(version: str = COMPARISON_POLICY_V1) -> Dict[str, Any]:
    """Returns the immutable specification dictionary for the given policy version."""
    if version == COMPARISON_POLICY_V1:
        return copy.deepcopy(COMPARISON_POLICY_V1_SPEC)
    raise ValueError(f"Unknown comparison policy version: '{version}'")



# ── VERDICTS ──────────────────────────────────────────────────────────────────

class ComparisonVerdict(str, enum.Enum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    CORRECT_DIRECTION = "CORRECT_DIRECTION"
    INCORRECT_DIRECTION = "INCORRECT_DIRECTION"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    OUTSIDE_TOLERANCE = "OUTSIDE_TOLERANCE"
    METRICS_ONLY = "METRICS_ONLY"
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNCOMPARABLE = "UNCOMPARABLE"


# ── DIMENSIONAL UNITS REGISTRY & CONVERSIONS ──────────────────────────────────

# Map units to standard base dimensions and linear conversion factors (val * factor = base_val)
UNIT_DIMENSIONS: Dict[str, Tuple[str, float]] = {
    # Force (Base: N)
    "N": ("FORCE", 1.0),
    "kN": ("FORCE", 1000.0),

    # Torque (Base: Nm)
    "Nm": ("TORQUE", 1.0),

    # Pressure (Base: Pa)
    "Pa": ("PRESSURE", 1.0),
    "kPa": ("PRESSURE", 1000.0),
    "MPa": ("PRESSURE", 1000000.0),
    "bar": ("PRESSURE", 100000.0),
    "psi": ("PRESSURE", 6894.757),

    # Temperature (Base: K, handled specially if degC)
    "K": ("TEMPERATURE", 1.0),
    "°C": ("TEMPERATURE", 1.0),
    "degC": ("TEMPERATURE", 1.0),

    # Velocity (Base: m/s)
    "m/s": ("VELOCITY", 1.0),
    "km/h": ("VELOCITY", 1.0 / 3.6),
    "mph": ("VELOCITY", 0.44704),

    # Acceleration (Base: m/s²)
    "m/s²": ("ACCELERATION", 1.0),
    "m/s2": ("ACCELERATION", 1.0),
    "g": ("ACCELERATION", 9.80665),

    # Time (Base: s)
    "s": ("TIME", 1.0),
    "ms": ("TIME", 0.001),
    "min": ("TIME", 60.0),
    "h": ("TIME", 3600.0),

    # Angle (Base: rad)
    "rad": ("ANGLE", 1.0),
    "deg": ("ANGLE", math.pi / 180.0),
    "°": ("ANGLE", math.pi / 180.0),

    # Stiffness / Rate (Base: N/m)
    "N/m": ("STIFFNESS", 1.0),
    "kN/m": ("STIFFNESS", 1000.0),
    "N/mm": ("STIFFNESS", 1000.0),

    # Angular Stiffness (Base: Nm/rad)
    "Nm/rad": ("ANGULAR_STIFFNESS", 1.0),
    "kNm/rad": ("ANGULAR_STIFFNESS", 1000.0),
    "Nm/deg": ("ANGULAR_STIFFNESS", 180.0 / math.pi),

    # Damping (Base: Ns/m)
    "Ns/m": ("DAMPING", 1.0),
    "N/(m/s)": ("DAMPING", 1.0),

    # Mass (Base: kg)
    "kg": ("MASS", 1.0),
    "g_mass": ("MASS", 0.001),

    # Dimensionless / Ratio / Percent (Base: ratio)
    "ratio": ("RATIO", 1.0),
    "dimensionless": ("RATIO", 1.0),
    "unitless": ("RATIO", 1.0),
    "%": ("RATIO", 0.01),
}


def normalize_unit_value(value: float, unit: str) -> Tuple[bool, Optional[str], Optional[float], Optional[str]]:
    """
    Normalizes a numeric value to its base physical dimension.
    Returns: (success, dimension_name, base_normalized_value, base_unit_name)
    """
    clean_u = unit.strip()
    if clean_u not in UNIT_DIMENSIONS:
        return False, None, None, None

    dim, factor = UNIT_DIMENSIONS[clean_u]
    if dim == "TEMPERATURE":
        # Convert C to K if needed, or maintain delta
        return True, dim, value, "K"
    return True, dim, value * factor, dim.lower()


def check_dimensional_compatibility(unit1: str, unit2: str) -> bool:
    """Verifies that two units represent the same physical dimension."""
    u1_clean = unit1.strip()
    u2_clean = unit2.strip()
    if u1_clean == u2_clean:
        return True
    dim1 = UNIT_DIMENSIONS.get(u1_clean, (None, 0))[0]
    dim2 = UNIT_DIMENSIONS.get(u2_clean, (None, 0))[0]
    return dim1 is not None and dim1 == dim2


# ── DETERMINISTIC COMPARISON HASH ─────────────────────────────────────────────

def compute_canonical_comparison_hash(
    session_id: Union[str, Any],
    submission_id: Union[str, Any],
    submission_hash: str,
    outcome_identity: Dict[str, Any],
    comparison_policy_version: str,
    prediction_schema_version: str,
    comparison_type: str,
    verdict: str,
    comparison_metrics: Dict[str, Any],
    tolerance_applied: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Computes deterministic SHA-256 hash of a completed comparison result.
    Applies RFC 8785 canonical JSON formatting over stable domain properties.
    """
    payload = {
        "session_id": str(session_id),
        "submission_id": str(submission_id),
        "submission_hash": str(submission_hash),
        "outcome_identity": outcome_identity,
        "comparison_policy_version": str(comparison_policy_version),
        "prediction_schema_version": str(prediction_schema_version),
        "comparison_type": str(comparison_type),
        "verdict": str(verdict),
        "comparison_metrics": comparison_metrics,
        "tolerance_applied": tolerance_applied,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_canonical_outcome_identity(
    entity_type: str,
    entity_id: str,
    record: Any,
    artifact_hash: Optional[str] = None,
    reveal_policy_version: str = "1",
    comparison_policy_version: str = COMPARISON_POLICY_V1,
) -> Tuple[Dict[str, Any], str]:
    """
    Constructs deterministic outcome identity snapshot and canonical outcome hash.
    Reuses existing authoritative artifact hash if available; otherwise computes
    deterministic SHA-256 hash from canonical outcome fields.
    """
    effective_hash = str(artifact_hash).strip() if artifact_hash else ""
    if not effective_hash:
        attrs: Dict[str, Any] = {
            "entity_type": str(entity_type),
            "entity_id": str(entity_id),
        }
        for attr in ("holdout_r2", "holdout_rmse", "gate_verdict", "selected_option", "status", "summary_metrics", "metrics"):
            if hasattr(record, attr):
                val = getattr(record, attr)
                if val is not None:
                    attrs[attr] = val
        canon_json = json.dumps(attrs, sort_keys=True, separators=(",", ":"), default=str)
        effective_hash = hashlib.sha256(canon_json.encode("utf-8")).hexdigest()

    outcome_identity = {
        "entity_type": str(entity_type),
        "entity_id": str(entity_id),
        "canonical_id": str(getattr(record, "id", entity_id)),
        "artifact_hash": effective_hash,
        "reveal_policy_version": str(reveal_policy_version),
        "comparison_policy_version": str(comparison_policy_version),
    }
    return outcome_identity, effective_hash


# ── OUTCOME VALUE RESOLUTION ──────────────────────────────────────────────────

METRIC_DEFAULT_UNITS: Dict[str, str] = {
    "bar_rate": "N/m",
    "spring_rate": "N/m",
    "front_roll_stiffness": "N/m",
    "rear_roll_stiffness": "N/m",
    "roll_stiffness": "Nm/rad",
    "holdout_r2": "ratio",
    "r2": "ratio",
    "r2_score": "ratio",
    "holdout_rmse": "ratio",
    "rmse": "ratio",
    "peak_lat_g": "g",
    "lat_g": "g",
    "speed_kmh": "km/h",
    "mean_speed": "km/h",
    "lap_time": "s",
}


def extract_actual_metric_from_record(
    record: Any,
    metric_name: str,
    entity_type: str,
) -> Tuple[bool, Any, Optional[str]]:
    """
    Extracts authoritative value and unit from an engineering outcome DB record.
    Returns: (found, value, unit)
    """
    clean_metric = metric_name.strip()

    # 1. Check entity-specific semantic mappings first
    if entity_type in ("BlindValidationRecord", "BlindValidation"):
        if clean_metric in ("holdout_r2", "r2", "r2_score"):
            return True, getattr(record, "holdout_r2", None), "ratio"
        if clean_metric in ("holdout_rmse", "rmse"):
            return True, getattr(record, "holdout_rmse", None), "ratio"
        if clean_metric in ("verdict", "gate_verdict", "status"):
            return True, getattr(record, "gate_verdict", None), None
        if clean_metric in ("setup_id", "setup", "candidate"):
            return True, getattr(record, "setup_id", None), None

    elif entity_type == "EngineeringDecision":
        if clean_metric in ("selected_option", "setup_selection", "candidate_choice", "setup_id"):
            opt = getattr(record, "selected_option", None)
            if isinstance(opt, dict):
                return True, opt.get("id") or opt.get("candidate_id") or opt.get("setup_id") or str(opt), None
            if isinstance(opt, str):
                return True, opt, None
        if clean_metric in ("bar_rate", "front_roll_stiffness", "roll_stiffness"):
            opt = getattr(record, "selected_option", None)
            if isinstance(opt, dict) and "bar_rate" in opt:
                return True, opt["bar_rate"], "N/m"

    elif entity_type == "SimulationRun":
        metrics = getattr(record, "metrics", {}) or {}
        if isinstance(metrics, dict) and clean_metric in metrics:
            return True, metrics[clean_metric], METRIC_DEFAULT_UNITS.get(clean_metric)
        if clean_metric in ("status", "run_status"):
            return True, getattr(record, "status", None), None

    elif entity_type in ("InvestigationRecord", "Investigation"):
        if clean_metric in ("residual", "evidence_residual"):
            snap = getattr(record, "evidence_snapshot", {}) or {}
            if "residual" in snap:
                return True, snap["residual"], snap.get("channel_unit") or METRIC_DEFAULT_UNITS.get(clean_metric)

    # 2. Direct model attribute check
    if hasattr(record, clean_metric):
        val = getattr(record, clean_metric)
        if val is not None:
            unit = getattr(record, f"{clean_metric}_unit", getattr(record, "unit", None)) or METRIC_DEFAULT_UNITS.get(clean_metric)
            if isinstance(val, dict) and clean_metric in ("selected_option", "candidate", "setup", "candidate_choice"):
                val = val.get("id") or val.get("candidate_id") or val.get("setup_id") or str(val)
            return True, val, unit

    # 3. Check structured dictionaries commonly present on engineering records
    for dict_attr in ("summary_metrics", "metrics", "evidence_snapshot", "validation_evidence", "parameters", "tradeoffs"):
        if hasattr(record, dict_attr):
            d = getattr(record, dict_attr)
            if isinstance(d, dict) and clean_metric in d:
                unit = METRIC_DEFAULT_UNITS.get(clean_metric)
                return True, d[clean_metric], unit

    return False, None, None


# ── COMPARISON EVALUATOR ──────────────────────────────────────────────────────

def evaluate_prediction_comparison(
    submission_payload: Dict[str, Any],
    outcome_record: Any,
    outcome_entity_type: str,
    outcome_entity_id: str,
    session_config: Optional[Dict[str, Any]] = None,
    policy_version: str = COMPARISON_POLICY_V1,
) -> Dict[str, Any]:
    """
    Main comparative evaluation function under COMPARISON_POLICY_V1.
    Strictly deterministic and explainable from structured evidence.
    """
    cfg = session_config or {}
    pred_type = submission_payload.get("prediction_type", "QUANTITATIVE")
    target = submission_payload.get("target", {})
    metric_name = target.get("metric", "")

    # Extract tolerance from session config or submission payload if declared
    tolerance_cfg = cfg.get("tolerance") or submission_payload.get("tolerance")

    # ── 1. CATEGORICAL COMPARISON ─────────────────────────────────────────────
    if pred_type == "CATEGORICAL":
        predicted_raw = (
            submission_payload.get("predicted_category")
            if "predicted_category" in submission_payload
            else submission_payload.get("predicted_value")
        )

        found, actual_raw, _ = extract_actual_metric_from_record(outcome_record, metric_name, outcome_entity_type)
        if not found or actual_raw is None:
            return {
                "comparison_type": "CATEGORICAL",
                "verdict": ComparisonVerdict.UNCOMPARABLE.value,
                "comparison_metrics": {
                    "predicted_category": str(predicted_raw or "").strip(),
                    "actual_category": None,
                },
                "tolerance_applied": None,
                "interpretation": f"Authoritative outcome metric '{metric_name}' could not be resolved from {outcome_entity_type}:{outcome_entity_id}.",
            }

        is_structured_id = is_structured_identity_target(metric_name, outcome_entity_type)

        if is_structured_id:
            # CASE A: Structured entity/candidate/setup IDs -> Authoritative identity comparison
            ok_pred, norm_pred = normalize_structured_identity(predicted_raw)
            ok_act, norm_act = normalize_structured_identity(actual_raw)

            if not ok_pred or not ok_act:
                return {
                    "comparison_type": "CATEGORICAL",
                    "verdict": ComparisonVerdict.UNCOMPARABLE.value,
                    "comparison_metrics": {
                        "predicted_category": str(predicted_raw or "").strip(),
                        "actual_category": str(actual_raw or "").strip(),
                        "error": "MALFORMED_STRUCTURED_IDENTITY",
                    },
                    "tolerance_applied": None,
                    "interpretation": f"Malformed structured identity in comparison for target metric '{metric_name}'.",
                }

            # Exact case-sensitive match for authoritative structured identities (Case A)
            is_match = (norm_pred == norm_act)
            verdict = ComparisonVerdict.CORRECT.value if is_match else ComparisonVerdict.INCORRECT.value
            interpretation = (
                f"Authoritative identity match: predicted '{norm_pred}' matches actual '{norm_act}'."
                if is_match
                else f"Authoritative identity mismatch: predicted '{norm_pred}' does not match actual '{norm_act}'."
            )
            return {
                "comparison_type": "CATEGORICAL",
                "verdict": verdict,
                "comparison_metrics": {
                    "predicted_category": norm_pred,
                    "actual_category": norm_act,
                    "match": is_match,
                    "identity_mode": "STRUCTURED_AUTHORITATIVE",
                },
                "tolerance_applied": None,
                "interpretation": interpretation,
            }
        else:
            # CASE B: Free categorical labels (gate_verdict, status, qualitative assessment, etc.)
            predicted_cat = str(predicted_raw or "").strip()
            actual_cat = str(actual_raw or "").strip()
            is_match = predicted_cat.lower() == actual_cat.lower()
            verdict = ComparisonVerdict.CORRECT.value if is_match else ComparisonVerdict.INCORRECT.value
            interpretation = (
                f"Predicted category '{predicted_cat}' matches authoritative outcome category '{actual_cat}'."
                if is_match
                else f"Predicted category '{predicted_cat}' does not match authoritative outcome category '{actual_cat}'."
            )
            return {
                "comparison_type": "CATEGORICAL",
                "verdict": verdict,
                "comparison_metrics": {
                    "predicted_category": predicted_cat,
                    "actual_category": actual_cat,
                    "match": is_match,
                    "identity_mode": "NORMALIZED_STRING",
                },
                "tolerance_applied": None,
                "interpretation": interpretation,
            }

    # ── 2. DIRECTIONAL COMPARISON ─────────────────────────────────────────────
    elif pred_type == "DIRECTIONAL":
        pred_dir = str(submission_payload.get("expected_direction", "")).strip().upper()

        found, actual_delta, _ = extract_actual_metric_from_record(outcome_record, metric_name, outcome_entity_type)
        if not found or actual_delta is None or not isinstance(actual_delta, (int, float)):
            return {
                "comparison_type": "DIRECTIONAL",
                "verdict": ComparisonVerdict.UNCOMPARABLE.value,
                "comparison_metrics": {
                    "predicted_direction": pred_dir,
                    "actual_delta": None,
                },
                "tolerance_applied": None,
                "interpretation": f"Authoritative delta for metric '{metric_name}' could not be resolved numerically.",
            }

        delta_val = float(actual_delta)
        # Deterministic zero deadband comparison rule under COMPARISON_POLICY_V1:
        if abs(delta_val) <= DIRECTIONAL_ZERO_EPSILON:
            actual_dir = "CONSTANT"
        elif delta_val > DIRECTIONAL_ZERO_EPSILON:
            actual_dir = "INCREASE"
        else:
            actual_dir = "DECREASE"

        # Direction match check (NEUTRAL matches CONSTANT)
        is_dir_match = (pred_dir == actual_dir) or (pred_dir in ("NEUTRAL", "CONSTANT") and actual_dir in ("NEUTRAL", "CONSTANT"))
        verdict = ComparisonVerdict.CORRECT_DIRECTION.value if is_dir_match else ComparisonVerdict.INCORRECT_DIRECTION.value

        interpretation = (
            f"Predicted direction '{pred_dir}' corresponds with observed delta of {delta_val:+g} ({actual_dir})."
            if is_dir_match
            else f"Predicted direction '{pred_dir}' contradicts observed delta of {delta_val:+g} ({actual_dir})."
        )

        return {
            "comparison_type": "DIRECTIONAL",
            "verdict": verdict,
            "comparison_metrics": {
                "predicted_direction": pred_dir,
                "actual_direction": actual_dir,
                "actual_delta": delta_val,
                "direction_match": is_dir_match,
            },
            "tolerance_applied": None,
            "interpretation": interpretation,
        }

    # ── 3. QUANTITATIVE COMPARISON ────────────────────────────────────────────
    elif pred_type == "QUANTITATIVE":
        pred_val = float(submission_payload.get("predicted_value", 0.0))
        pred_unit = str(submission_payload.get("unit", "")).strip()

        found, actual_raw, outcome_unit_hint = extract_actual_metric_from_record(outcome_record, metric_name, outcome_entity_type)
        if not found or actual_raw is None or not isinstance(actual_raw, (int, float)):
            return {
                "comparison_type": "QUANTITATIVE",
                "verdict": ComparisonVerdict.UNCOMPARABLE.value,
                "comparison_metrics": {
                    "predicted_value": pred_val,
                    "predicted_unit": pred_unit,
                    "actual_value": None,
                },
                "tolerance_applied": None,
                "interpretation": f"Authoritative metric '{metric_name}' could not be resolved numerically from {outcome_entity_type}:{outcome_entity_id}.",
            }

        actual_val = float(actual_raw)
        actual_unit = str(outcome_unit_hint or pred_unit).strip()

        # Check dimensional compatibility
        if pred_unit and actual_unit and not check_dimensional_compatibility(pred_unit, actual_unit):
            return {
                "comparison_type": "QUANTITATIVE",
                "verdict": ComparisonVerdict.UNCOMPARABLE.value,
                "comparison_metrics": {
                    "predicted_value": pred_val,
                    "predicted_unit": pred_unit,
                    "actual_value": actual_val,
                    "actual_unit": actual_unit,
                    "error": "DIMENSIONAL_INCOMPATIBILITY",
                },
                "tolerance_applied": None,
                "interpretation": f"Dimensional incompatibility: unit '{pred_unit}' cannot be compared with '{actual_unit}'.",
            }

        # Normalize to common base units if valid units exist
        ok_p, _, norm_p, base_u_p = normalize_unit_value(pred_val, pred_unit) if pred_unit else (True, None, pred_val, pred_unit)
        ok_a, _, norm_a, base_u_a = normalize_unit_value(actual_val, actual_unit) if actual_unit else (True, None, actual_val, actual_unit)

        eval_pred = norm_p if ok_p and norm_p is not None else pred_val
        eval_actual = norm_a if ok_a and norm_a is not None else actual_val
        base_unit = base_u_p or pred_unit

        signed_error = eval_pred - eval_actual
        abs_error = abs(signed_error)

        # Relative error undefined when actual is zero
        EPSILON = 1e-12
        if abs(eval_actual) > EPSILON:
            rel_error = abs_error / abs(eval_actual)
        else:
            rel_error = None

        comparison_metrics: Dict[str, Any] = {
            "predicted_value": pred_val,
            "predicted_unit": pred_unit,
            "actual_value": actual_val,
            "actual_unit": actual_unit,
            "normalized_predicted": eval_pred,
            "normalized_actual": eval_actual,
            "base_unit": base_unit,
            "signed_error": signed_error,
            "absolute_error": abs_error,
            "relative_error": rel_error,
        }

        # Tolerance evaluation: Domain-specific only when declared
        if tolerance_cfg and isinstance(tolerance_cfg, dict):
            abs_tol = tolerance_cfg.get("absolute_tolerance")
            rel_tol = tolerance_cfg.get("relative_tolerance")

            passes = []
            reasons = []

            if abs_tol is not None:
                abs_tol_f = float(abs_tol)
                p_abs = abs_error <= abs_tol_f
                passes.append(p_abs)
                reasons.append(f"absolute_error ({abs_error:.4g} {base_unit}) <= tol ({abs_tol_f:.4g}) [{p_abs}]")

            if rel_tol is not None:
                rel_tol_f = float(rel_tol)
                if rel_error is not None:
                    p_rel = rel_error <= rel_tol_f
                    passes.append(p_rel)
                    reasons.append(f"relative_error ({rel_error:.4%}) <= tol ({rel_tol_f:.4%}) [{p_rel}]")
                else:
                    passes.append(False)
                    reasons.append("relative error undefined (actual value is 0)")

            overall_pass = all(passes) if passes else False
            verdict = ComparisonVerdict.WITHIN_TOLERANCE.value if overall_pass else ComparisonVerdict.OUTSIDE_TOLERANCE.value
            interpretation = (
                f"Prediction is {verdict.replace('_', ' ').lower()} based on configured tolerances: {'; '.join(reasons)}."
            )
            tolerance_applied = tolerance_cfg
        else:
            # NO tolerance declared: Return raw error metrics only. DO NOT manufacture PASS/FAIL.
            verdict = ComparisonVerdict.METRICS_ONLY.value
            rel_str = f"{rel_error:.4%}" if rel_error is not None else "undefined (zero denominator)"
            interpretation = (
                f"Raw quantitative error metrics computed: signed error = {signed_error:+.4g} {base_unit}, "
                f"absolute error = {abs_error:.4g} {base_unit}, relative error = {rel_str}. "
                "No binary verdict generated because no comparison tolerance was configured."
            )
            tolerance_applied = None

        return {
            "comparison_type": "QUANTITATIVE",
            "verdict": verdict,
            "comparison_metrics": comparison_metrics,
            "tolerance_applied": tolerance_applied,
            "interpretation": interpretation,
        }

    # ── 4. ENGINEERING DECISION COMPARISON ────────────────────────────────────
    elif pred_type == "ENGINEERING_DECISION":
        selected_cand_raw = submission_payload.get("selected_candidate_id") or submission_payload.get("predicted_value")

        found, actual_choice_raw, _ = extract_actual_metric_from_record(outcome_record, "selected_option", outcome_entity_type)
        if not found or not actual_choice_raw:
            # Try setup_id or candidate
            found, actual_choice_raw, _ = extract_actual_metric_from_record(outcome_record, "setup_id", outcome_entity_type)

        if not found or not actual_choice_raw:
            return {
                "comparison_type": "ENGINEERING_DECISION",
                "verdict": ComparisonVerdict.UNCOMPARABLE.value,
                "comparison_metrics": {
                    "selected_candidate_id": str(selected_cand_raw or "").strip(),
                    "authoritative_choice": None,
                },
                "tolerance_applied": None,
                "interpretation": f"Authoritative decision option could not be extracted from {outcome_entity_type}:{outcome_entity_id}.",
            }

        ok_pred, norm_pred = normalize_structured_identity(selected_cand_raw)
        ok_act, norm_act = normalize_structured_identity(actual_choice_raw)

        if not ok_pred or not ok_act:
            return {
                "comparison_type": "ENGINEERING_DECISION",
                "verdict": ComparisonVerdict.UNCOMPARABLE.value,
                "comparison_metrics": {
                    "selected_candidate_id": str(selected_cand_raw or "").strip(),
                    "authoritative_choice": str(actual_choice_raw or "").strip(),
                    "error": "MALFORMED_STRUCTURED_IDENTITY",
                },
                "tolerance_applied": None,
                "interpretation": "Malformed candidate identity in engineering decision comparison.",
            }

        # Exact case-sensitive match for authoritative candidate identity (Case A)
        is_supported = (norm_pred == norm_act)
        verdict = ComparisonVerdict.SUPPORTED.value if is_supported else ComparisonVerdict.NOT_SUPPORTED.value

        interpretation = (
            f"Selected engineering candidate '{norm_pred}' is supported by authoritative outcome '{norm_act}'."
            if is_supported
            else f"Selected engineering candidate '{norm_pred}' was not chosen; authoritative outcome was '{norm_act}'."
        )

        return {
            "comparison_type": "ENGINEERING_DECISION",
            "verdict": verdict,
            "comparison_metrics": {
                "selected_candidate_id": norm_pred,
                "authoritative_choice": norm_act,
                "supported": is_supported,
                "identity_mode": "STRUCTURED_AUTHORITATIVE",
            },
            "tolerance_applied": None,
            "interpretation": interpretation,
        }

    else:
        return {
            "comparison_type": pred_type,
            "verdict": ComparisonVerdict.UNCOMPARABLE.value,
            "comparison_metrics": {},
            "tolerance_applied": None,
            "interpretation": f"Unrecognized prediction type '{pred_type}'.",
        }
