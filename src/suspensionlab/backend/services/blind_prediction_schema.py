"""
backend/services/blind_prediction_schema.py
===========================================
SuspensionLab PRO — Phase 5.2 Versioned Blind Engineering Prediction Contract.

Defines the authoritative, versioned, validated engineering prediction schemas:
- PREDICTION_SCHEMA_V1
- Supported prediction types: CATEGORICAL, DIRECTIONAL, QUANTITATIVE, ENGINEERING_DECISION
- Structured target models (entity_type, entity_id, metric, aggregation)
- Strict target visibility enforcement (invisible / hidden targets rejected)
- Deterministic unit validation across physical dimensions
- Strict numeric validation (rejection of NaN, Infinity, -Infinity)
- Bounded confidence validation (0.0 <= confidence <= 1.0)
- Immutable preservation of engineering rationale and assumptions
- Deterministic RFC 8785 canonicalization and context binding
"""
from __future__ import annotations

import copy
import enum
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Set, Union


# ── SCHEMA VERSIONS ───────────────────────────────────────────────────────────

PREDICTION_SCHEMA_V1 = "1"
PREDICTION_SCHEMA_V2 = "2"
SUPPORTED_SCHEMA_VERSIONS: Set[str] = {"1", "2", "PREDICTION_SCHEMA_V1", "PREDICTION_SCHEMA_V2"}

# ── CONFIDENCE & PROBABILITY SEMANTICS ────────────────────────────────────────
CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT = "PROBABILITY_PREDICTION_CORRECT"
SUPPORTED_CONFIDENCE_SEMANTICS: Set[str] = {
    CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
}


# ── PREDICTION TYPES ──────────────────────────────────────────────────────────

class PredictionType(str, enum.Enum):
    CATEGORICAL = "CATEGORICAL"
    DIRECTIONAL = "DIRECTIONAL"
    QUANTITATIVE = "QUANTITATIVE"
    ENGINEERING_DECISION = "ENGINEERING_DECISION"


class ExpectedDirection(str, enum.Enum):
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    NEUTRAL = "NEUTRAL"
    CONSTANT = "CONSTANT"


# ── PHYSICAL UNITS REGISTRY ───────────────────────────────────────────────────

SUPPORTED_UNITS: Set[str] = {
    # Force
    "N", "kN", "mN",
    # Torque
    "Nm", "kNm",
    # Pressure
    "Pa", "kPa", "MPa", "bar", "psi",
    # Temperature
    "°C", "degC", "K",
    # Velocity / Speed
    "m/s", "km/h", "mm/s",
    # Acceleration
    "g", "m/s^2", "m/s²",
    # Time
    "s", "ms", "min",
    # Stiffness
    "N/mm", "N/m", "kN/m", "Nm/deg", "kN/rad", "N/deg",
    # Damping
    "Ns/m", "Ns/mm",
    # Dimensionless / Percentage / Angle / Count
    "%", "deg", "rad", "count", "ratio",
    # Mass
    "kg", "g",
    # Power
    "W", "kW", "hp",
    # Frequency / Rotational Speed
    "Hz", "rpm",
}


# ── EXCEPTIONS ────────────────────────────────────────────────────────────────

class PredictionSchemaError(Exception):
    """Base exception for prediction schema violations."""
    pass


class UnsupportedSchemaVersionError(PredictionSchemaError):
    """Raised when submission schema version is missing or unsupported."""
    pass


class InvalidPredictionTypeError(PredictionSchemaError):
    """Raised when prediction type is unrecognized."""
    pass


class InvalidPredictionTargetError(PredictionSchemaError):
    """Raised when prediction target is malformed or missing required attributes."""
    pass


class InvisibleTargetError(PredictionSchemaError):
    """Raised when target entity or candidate is not in the visible session context."""
    pass


class InvisibleCandidateError(PredictionSchemaError):
    """Raised when a candidate referenced in a decision is not visible in context."""
    pass


class MissingUnitError(PredictionSchemaError):
    """Raised when a quantitative prediction or delta lacks an explicit unit."""
    pass


class InvalidUnitError(PredictionSchemaError):
    """Raised when an unapproved or invalid physical unit is provided."""
    pass


class InvalidNumericValueError(PredictionSchemaError):
    """Raised when a numeric value is non-finite, NaN, or Infinity."""
    pass


class InvalidConfidenceError(PredictionSchemaError):
    """Raised when confidence score is not a finite number in [0.0, 1.0]."""
    pass


class ContextBindingMismatchError(PredictionSchemaError):
    """Raised when submission context hash does not match active session context."""
    pass


# ── VALIDATION FUNCTIONS ──────────────────────────────────────────────────────

def _assert_finite_number(value: Any, field_name: str) -> float:
    """Verifies that value is an int or float, and strictly not NaN or Infinity."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidNumericValueError(f"Field '{field_name}' must be a numeric value, got {type(value).__name__}.")
    val_float = float(value)
    if math.isnan(val_float) or math.isinf(val_float):
        raise InvalidNumericValueError(f"Field '{field_name}' must be finite (NaN and Infinity prohibited).")
    return val_float


def validate_unit(unit: Any, field_name: str = "unit") -> str:
    """Validates that unit is non-empty and belongs to supported physical dimensions."""
    if not isinstance(unit, str) or not unit.strip():
        raise MissingUnitError(f"Field '{field_name}' requires an explicit physical unit.")
    clean_unit = unit.strip()
    if clean_unit not in SUPPORTED_UNITS:
        raise InvalidUnitError(f"Unsupported unit '{clean_unit}'. Must be a recognized engineering unit.")
    return clean_unit


def validate_confidence(confidence: Any) -> float:
    """Validates bounded confidence: 0.0 <= confidence <= 1.0."""
    try:
        conf = _assert_finite_number(confidence, "confidence")
    except InvalidNumericValueError as e:
        raise InvalidConfidenceError(f"Invalid confidence value: {e}") from e
    if conf < 0.0 or conf > 1.0:
        raise InvalidConfidenceError(f"Confidence must be between 0.0 and 1.0 inclusive (got {conf}).")
    return conf


def validate_target_structure(target: Any) -> Dict[str, Any]:
    """Validates that target dictionary contains required entity_type, entity_id, and metric."""
    if not isinstance(target, dict) or not target:
        raise InvalidPredictionTargetError("Target must be a non-empty structured dictionary.")

    entity_type = target.get("entity_type")
    if not isinstance(entity_type, str) or not entity_type.strip():
        raise InvalidPredictionTargetError("Target requires a non-empty 'entity_type'.")

    entity_id = target.get("entity_id")
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise InvalidPredictionTargetError("Target requires a non-empty 'entity_id'.")

    metric = target.get("metric")
    if not isinstance(metric, str) or not metric.strip():
        raise InvalidPredictionTargetError("Target requires a non-empty 'metric'.")

    clean_target: Dict[str, Any] = {
        "entity_type": entity_type.strip(),
        "entity_id": entity_id.strip(),
        "metric": metric.strip(),
    }
    if "aggregation" in target and target["aggregation"] is not None:
        agg = str(target["aggregation"]).strip()
        if agg:
            clean_target["aggregation"] = agg

    return clean_target


def validate_target_visibility(
    target: Dict[str, Any],
    visible_context: Dict[str, Any],
    hidden_outcome_type: Optional[str] = None,
    hidden_outcome_id: Optional[str] = None,
) -> None:
    """
    Guarantees target is accessible in the evaluator's visible context.
    Strictly forbids targets pointing to hidden outcomes or unrevealed entities.
    Error messages NEVER disclose hidden entity identity.
    """
    target_type = target["entity_type"]
    target_id = target["entity_id"]

    # 1. Anti-leakage: if target directly references hidden outcome, reject with generic not-available
    if hidden_outcome_type and hidden_outcome_id:
        if target_type == hidden_outcome_type and target_id == hidden_outcome_id:
            raise InvisibleTargetError("Target is not available in the active session context.")

    # 2. Extract all authorized visible entity identifiers from context
    allowed_entities: Set[Tuple[str, str]] = set()

    root = visible_context.get("root_entity", {})
    if root.get("entity_type") and root.get("entity_id"):
        allowed_entities.add((str(root["entity_type"]), str(root["entity_id"])))

    for ent in visible_context.get("visible_entities", []):
        if ent.get("entity_type") and ent.get("entity_id"):
            allowed_entities.add((str(ent["entity_type"]), str(ent["entity_id"])))

    # Also check edges for valid visible nodes
    for edge in visible_context.get("visible_edges", []):
        if edge.get("source_type") and edge.get("source_id"):
            allowed_entities.add((str(edge["source_type"]), str(edge["source_id"])))
        if edge.get("target_type") and edge.get("target_id"):
            allowed_entities.add((str(edge["target_type"]), str(edge["target_id"])))

    if (target_type, target_id) not in allowed_entities:
        raise InvisibleTargetError("Target is not available in the active session context.")


def validate_candidate_visibility(
    candidate_id: str,
    visible_context: Dict[str, Any],
) -> None:
    """
    Validates that a candidate selected in an ENGINEERING_DECISION prediction
    is present among the visible candidates in root entity context.
    """
    clean_cand_id = str(candidate_id).strip()
    root = visible_context.get("root_entity", {})
    candidates = root.get("candidates", [])

    allowed_cand_ids: Set[str] = set()
    if isinstance(candidates, list):
        for c in candidates:
            if isinstance(c, dict) and "id" in c:
                allowed_cand_ids.add(str(c["id"]).strip())
            elif isinstance(c, str):
                allowed_cand_ids.add(c.strip())

    # Also check visible entities if candidate was modeled as a SetupCandidate record
    for ent in visible_context.get("visible_entities", []):
        if ent.get("entity_type") in ("SetupCandidate", "SetupProposal") and ent.get("entity_id"):
            allowed_cand_ids.add(str(ent["entity_id"]).strip())

    if allowed_cand_ids and clean_cand_id not in allowed_cand_ids:
        raise InvisibleCandidateError("Target candidate is not available in the active session context.")


def validate_expected_effect(expected_effect: Any) -> Dict[str, Any]:
    """Validates structured expected_effect block if provided."""
    if not isinstance(expected_effect, dict):
        raise PredictionSchemaError("expected_effect must be a structured dictionary.")

    metric = expected_effect.get("metric")
    if not isinstance(metric, str) or not metric.strip():
        raise PredictionSchemaError("expected_effect requires a non-empty 'metric'.")

    direction = expected_effect.get("direction")
    if not isinstance(direction, str) or direction.upper() not in [d.value for d in ExpectedDirection]:
        raise PredictionSchemaError(f"expected_effect direction must be one of {[d.value for d in ExpectedDirection]}.")

    clean_effect: Dict[str, Any] = {
        "metric": metric.strip(),
        "direction": direction.upper(),
    }

    if "expected_delta" in expected_effect and expected_effect["expected_delta"] is not None:
        delta = _assert_finite_number(expected_effect["expected_delta"], "expected_delta")
        clean_effect["expected_delta"] = delta
        clean_effect["unit"] = validate_unit(expected_effect.get("unit"), "expected_effect.unit")
    elif "unit" in expected_effect and expected_effect["unit"]:
        clean_effect["unit"] = validate_unit(expected_effect["unit"], "expected_effect.unit")

    return clean_effect


def validate_prediction_contract(
    payload: Dict[str, Any],
    visible_context: Dict[str, Any],
    hidden_outcome_type: Optional[str] = None,
    hidden_outcome_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Authoritative server-side validation pipeline for Blind Engineering Prediction payloads.
    Returns normalized, canonicalized payload dictionary ready for deterministic hashing.
    """
    if not isinstance(payload, dict) or not payload:
        raise PredictionSchemaError("Submission payload must be a non-empty JSON object.")

    # 1. Schema version validation
    raw_version = str(payload.get("schema_version", "")).strip()
    if not raw_version or raw_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(
            f"Unsupported schema_version '{raw_version}'. Must be one of: {sorted(SUPPORTED_SCHEMA_VERSIONS)}."
        )
    target_schema_version = (
        PREDICTION_SCHEMA_V2 if raw_version in {"2", "PREDICTION_SCHEMA_V2"} else PREDICTION_SCHEMA_V1
    )

    # 2. Prediction type validation
    raw_type = payload.get("prediction_type")
    if not isinstance(raw_type, str) or raw_type.upper() not in [pt.value for pt in PredictionType]:
        raise InvalidPredictionTypeError(
            f"Unsupported prediction_type '{raw_type}'. Must be one of: {[pt.value for pt in PredictionType]}."
        )
    pred_type = PredictionType(raw_type.upper())

    # 3. Target validation & visibility check
    target_dict = validate_target_structure(payload.get("target"))
    validate_target_visibility(
        target=target_dict,
        visible_context=visible_context,
        hidden_outcome_type=hidden_outcome_type,
        hidden_outcome_id=hidden_outcome_id,
    )

    # 4. Context binding check (if provided in payload)
    if "visible_context_hash" in payload and payload["visible_context_hash"]:
        provided_hash = str(payload["visible_context_hash"]).strip()
        expected_hash = str(visible_context.get("visible_context_hash", "")).strip()
        if expected_hash and provided_hash != expected_hash:
            raise ContextBindingMismatchError(
                "Submission context hash does not match active session context."
            )

    # 5. Confidence validation
    confidence_val = validate_confidence(payload.get("confidence", 1.0))

    # 6. Type-specific validation
    clean_contract: Dict[str, Any] = {
        "schema_version": target_schema_version,
        "prediction_type": pred_type.value,
        "target": target_dict,
        "confidence": confidence_val,
    }

    if "confidence_semantics" in payload and payload["confidence_semantics"] is not None:
        raw_sem = str(payload["confidence_semantics"]).strip().upper()
        if raw_sem not in SUPPORTED_CONFIDENCE_SEMANTICS:
            raise PredictionSchemaError(
                f"Unsupported confidence_semantics '{raw_sem}'. Must be one of: {sorted(list(SUPPORTED_CONFIDENCE_SEMANTICS))}."
            )
        clean_contract["confidence_semantics"] = raw_sem

    if "probability_distribution" in payload and payload["probability_distribution"] is not None:
        raw_dist = payload["probability_distribution"]
        if not isinstance(raw_dist, dict) or not raw_dist:
            raise PredictionSchemaError("probability_distribution must be a non-empty dictionary mapping categories to probabilities.")
        clean_dist: Dict[str, float] = {}
        total_p = 0.0
        for cat_k, p_v in raw_dist.items():
            k_clean = str(cat_k).strip()
            p_val = _assert_finite_number(p_v, f"probability_distribution['{k_clean}']")
            if p_val < 0.0 or p_val > 1.0:
                raise PredictionSchemaError(f"Probability for '{k_clean}' must be in [0.0, 1.0], got {p_val}.")
            clean_dist[k_clean] = p_val
            total_p += p_val
        if abs(total_p - 1.0) > 1e-4:
            raise PredictionSchemaError(f"probability_distribution values must sum to 1.0 (got {total_p:.6f}).")
        clean_contract["probability_distribution"] = clean_dist

    if pred_type == PredictionType.QUANTITATIVE:
        if "predicted_value" not in payload:
            raise PredictionSchemaError("QUANTITATIVE prediction requires 'predicted_value'.")
        val = _assert_finite_number(payload["predicted_value"], "predicted_value")
        unit = validate_unit(payload.get("unit"), "unit")
        clean_contract["predicted_value"] = val
        clean_contract["unit"] = unit

        if "expected_direction" in payload and payload["expected_direction"]:
            dir_str = str(payload["expected_direction"]).upper()
            if dir_str not in [d.value for d in ExpectedDirection]:
                raise PredictionSchemaError(f"Invalid expected_direction '{dir_str}'.")
            clean_contract["expected_direction"] = dir_str

        if "expected_delta" in payload and payload["expected_delta"] is not None:
            clean_contract["expected_delta"] = _assert_finite_number(payload["expected_delta"], "expected_delta")

    elif pred_type == PredictionType.CATEGORICAL:
        val = payload.get("predicted_category") if "predicted_category" in payload else payload.get("predicted_value")
        if val is None:
            raise PredictionSchemaError("CATEGORICAL prediction requires 'predicted_value' or 'predicted_category'.")
        if not isinstance(val, (str, int, bool)):
            raise PredictionSchemaError("CATEGORICAL predicted_value must be a string, integer, or boolean.")
        clean_val = str(val).strip()
        clean_contract["predicted_value"] = clean_val
        clean_contract["predicted_category"] = clean_val

        raw_choices = payload.get("allowed_choices") if "allowed_choices" in payload else payload.get("allowed_categories")
        if raw_choices is not None and isinstance(raw_choices, list):
            choices = [str(c).strip() for c in raw_choices]
            clean_contract["allowed_choices"] = choices
            clean_contract["allowed_categories"] = choices
            if clean_val not in choices:
                raise PredictionSchemaError(
                    f"Predicted value '{clean_val}' is not in allowed choices {choices}."
                )

    elif pred_type == PredictionType.DIRECTIONAL:
        if "expected_direction" not in payload:
            raise PredictionSchemaError("DIRECTIONAL prediction requires 'expected_direction'.")
        dir_str = str(payload["expected_direction"]).upper()
        if dir_str not in [d.value for d in ExpectedDirection]:
            raise PredictionSchemaError(f"Invalid expected_direction '{dir_str}'.")
        clean_contract["expected_direction"] = dir_str

        if "expected_delta" in payload and payload["expected_delta"] is not None:
            clean_contract["expected_delta"] = _assert_finite_number(payload["expected_delta"], "expected_delta")
            clean_contract["unit"] = validate_unit(payload.get("unit"), "unit")
        elif "unit" in payload and payload["unit"]:
            clean_contract["unit"] = validate_unit(payload["unit"], "unit")

    elif pred_type == PredictionType.ENGINEERING_DECISION:
        candidate_id = payload.get("selected_candidate_id") or payload.get("predicted_value")
        if not candidate_id or not isinstance(candidate_id, str):
            raise PredictionSchemaError("ENGINEERING_DECISION requires 'selected_candidate_id'.")
        cand_str = candidate_id.strip()
        validate_candidate_visibility(cand_str, visible_context)
        clean_contract["selected_candidate_id"] = cand_str
        clean_contract["predicted_value"] = cand_str

    # 7. Optional engineering rationale and assumptions
    if "rationale" in payload and payload["rationale"] is not None:
        clean_contract["rationale"] = str(payload["rationale"]).strip()

    if "assumptions" in payload and payload["assumptions"] is not None:
        if not isinstance(payload["assumptions"], list):
            raise PredictionSchemaError("Assumptions must be a list of strings.")
        clean_assumptions = [str(a).strip() for a in payload["assumptions"] if str(a).strip()]
        clean_contract["assumptions"] = clean_assumptions

    if "expected_effect" in payload and payload["expected_effect"] is not None:
        clean_contract["expected_effect"] = validate_expected_effect(payload["expected_effect"])

    return clean_contract


# ── CANONICALIZATION & HASHING ────────────────────────────────────────────────

def canonicalize_prediction_payload(payload: Dict[str, Any]) -> str:
    """
    RFC 8785 canonical JSON serialization of prediction payload:
    Deterministic sorting of keys, compact separators, UTF-8.
    """
    cleaned = copy.deepcopy(payload)
    # Strip any volatile metadata if accidentally injected
    cleaned.pop("request_id", None)
    cleaned.pop("timestamp", None)
    cleaned.pop("submitted_at", None)
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)


def compute_prediction_content_hash(payload: Dict[str, Any]) -> str:
    """Computes SHA-256 hash over canonical prediction payload bytes."""
    canonical_str = canonicalize_prediction_payload(payload)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
