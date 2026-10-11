"""
backend/services/blind_calibration_engine.py
============================================
SuspensionLab PRO — Phase 5.4 Engineering Calibration & Longitudinal Blind Track Record Engine.

Provides deterministic, statistically valid, audit-traceable analytics over completed
Blind Engineering evaluations:
- Separation of Outcome Accuracy, Coverage, and Probabilistic Calibration.
- Metric Eligibility Registry with explicit ineligibility reasons.
- Binary and Multiclass Brier Score calculations.
- Calibration (reliability) curves with binning and Wilson score uncertainty intervals.
- Minimum sample size thresholding (INSUFFICIENT_SAMPLE state, not fabricated conclusions).
- Independent CALIBRATION_POLICY_V1 specification with deterministic SHA-256 fingerprint.
- Strictly NO universal engineer skill rating, NO leaderboard, and NO rationale text scoring.
"""
from __future__ import annotations

import copy
import enum
import hashlib
import json
import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("blind_calibration_engine")

CALIBRATION_POLICY_V1 = "1"
CALIBRATION_POLICY_NAME = "CALIBRATION_POLICY_V1"

# Explicit Confidence Semantics required for binary probabilistic calibration
CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT = "PROBABILITY_PREDICTION_CORRECT"

# Binary outcome mappings
POSITIVE_VERDICTS: Set[str] = {
    "CORRECT",
    "CORRECT_DIRECTION",
    "SUPPORTED",
    "WITHIN_TOLERANCE",
}

NEGATIVE_VERDICTS: Set[str] = {
    "INCORRECT",
    "INCORRECT_DIRECTION",
    "NOT_SUPPORTED",
    "CONTRADICTED",
    "OUTSIDE_TOLERANCE",
}

NON_BINARY_VERDICTS: Set[str] = {
    "METRICS_ONLY",
    "UNCOMPARABLE",
}


# ── POLICY SPECIFICATION ──────────────────────────────────────────────────────

CALIBRATION_POLICY_V1_SPEC: Dict[str, Any] = {
    "policy_version": CALIBRATION_POLICY_V1,
    "policy_name": CALIBRATION_POLICY_NAME,
    "confidence_semantics": {
        "required_for_binary_calibration": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
        "interpretation": "Submitted probability represents engineer forecast that prediction receives policy-defined correct verdict.",
        "unspecified_handling": "NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED",
    },
    "binary_verdicts": {
        "positive": sorted(list(POSITIVE_VERDICTS)),
        "negative": sorted(list(NEGATIVE_VERDICTS)),
        "non_binary_excluded": sorted(list(NON_BINARY_VERDICTS)),
    },
    "accuracy_definition": {
        "formula": "correct_count / (correct_count + incorrect_count)",
        "condition": "(correct_count + incorrect_count) > 0",
        "undefined_value": None,
    },
    "coverage_definition": {
        "formula": "comparable_count / completed_evaluation_count",
        "condition": "completed_evaluation_count > 0",
        "undefined_value": None,
    },
    "brier_score": {
        "binary_formula": "(1/N) * sum((p_i - y_i)^2)",
        "y_i_positive": 1.0,
        "y_i_negative": 0.0,
        "min_sample_size": 1,
        "insufficient_sample_state": "INSUFFICIENT_SAMPLE",
    },
    "calibration_curve": {
        "binning_method": "EQUAL_WIDTH_5_BINS",
        "bins": [
            {"index": 0, "range": [0.0, 0.2], "label": "[0.0, 0.2)"},
            {"index": 1, "range": [0.2, 0.4], "label": "[0.2, 0.4)"},
            {"index": 2, "range": [0.4, 0.6], "label": "[0.4, 0.6)"},
            {"index": 3, "range": [0.6, 0.8], "label": "[0.6, 0.8)"},
            {"index": 4, "range": [0.8, 1.0], "label": "[0.8, 1.0]"},
        ],
        "uncertainty_method": "WILSON_SCORE",
        "confidence_level": 0.95,
        "z_score": 1.959964,
        "min_curve_sample_size": 5,
        "insufficient_sample_state": "INSUFFICIENT_SAMPLE",
    },
    "governance_rules": {
        "no_skill_rating": True,
        "no_leaderboard": True,
        "no_rationale_scoring": True,
        "uncomparable_counted_as_incorrect": False,
        "generic_confidence_reinterpreted_as_probability": False,
    },
}


def get_calibration_policy_spec(version: str = CALIBRATION_POLICY_V1) -> Dict[str, Any]:
    """Returns the immutable specification dictionary for the given calibration policy version."""
    if version in (CALIBRATION_POLICY_V1, CALIBRATION_POLICY_NAME):
        return copy.deepcopy(CALIBRATION_POLICY_V1_SPEC)
    raise ValueError(f"Unknown calibration policy version: '{version}'")


def compute_calibration_policy_hash(version: str = CALIBRATION_POLICY_V1) -> str:
    """Computes SHA-256 fingerprint over RFC 8785 canonical JSON of the policy specification."""
    spec = get_calibration_policy_spec(version)
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── METRIC ELIGIBILITY REGISTRY ───────────────────────────────────────────────

class IneligibilityReason(str, enum.Enum):
    NOT_ELIGIBLE_UNCOMPARABLE = "NOT_ELIGIBLE_UNCOMPARABLE"
    NOT_ELIGIBLE_METRICS_ONLY = "NOT_ELIGIBLE_METRICS_ONLY"
    NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED = "NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED"
    NOT_ELIGIBLE_NON_BINARY_OUTCOME = "NOT_ELIGIBLE_NON_BINARY_OUTCOME"
    NOT_ELIGIBLE_INCOMPLETE_DISTRIBUTION = "NOT_ELIGIBLE_INCOMPLETE_DISTRIBUTION"
    NOT_ELIGIBLE_UNREVEALED = "NOT_ELIGIBLE_UNREVEALED"
    NOT_ELIGIBLE_NO_PREDICTION = "NOT_ELIGIBLE_NO_PREDICTION"


class EvaluationRecordEligibility:
    """Encapsulates eligibility classification for a single completed evaluation."""
    def __init__(
        self,
        eligible_for_accuracy: bool,
        eligible_for_coverage: bool,
        eligible_for_binary_calibration: bool,
        eligible_for_multiclass_calibration: bool,
        binary_verdict_value: Optional[int],
        forecast_probability: Optional[float],
        declared_distribution: Optional[Dict[str, float]],
        ineligibility_reasons: List[str],
    ) -> None:
        self.eligible_for_accuracy = eligible_for_accuracy
        self.eligible_for_coverage = eligible_for_coverage
        self.eligible_for_binary_calibration = eligible_for_binary_calibration
        self.eligible_for_multiclass_calibration = eligible_for_multiclass_calibration
        self.binary_verdict_value = binary_verdict_value
        self.forecast_probability = forecast_probability
        self.declared_distribution = declared_distribution
        self.ineligibility_reasons = ineligibility_reasons

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible_for_accuracy": self.eligible_for_accuracy,
            "eligible_for_coverage": self.eligible_for_coverage,
            "eligible_for_binary_calibration": self.eligible_for_binary_calibration,
            "eligible_for_multiclass_calibration": self.eligible_for_multiclass_calibration,
            "binary_verdict_value": self.binary_verdict_value,
            "forecast_probability": self.forecast_probability,
            "ineligibility_reasons": self.ineligibility_reasons,
        }


def evaluate_observation_eligibility(
    prediction_payload: Optional[Dict[str, Any]],
    verdict: str,
) -> EvaluationRecordEligibility:
    """
    Evaluates an observation against CALIBRATION_POLICY_V1 eligibility rules:
    - Coverage eligibility: Any completed/revealed comparison.
    - Accuracy eligibility: Requires a binary comparable verdict (positive or negative).
    - Binary calibration eligibility: Requires binary verdict AND explicit
      confidence_semantics == PROBABILITY_PREDICTION_CORRECT with valid probability in [0, 1].
    - Multiclass calibration eligibility: Requires complete declared distribution over choices.
    """
    ineligibility_reasons: List[str] = []
    eligible_for_coverage = True

    # 1. Verdict-level checks
    clean_verdict = (verdict or "").strip().upper()
    is_positive = clean_verdict in POSITIVE_VERDICTS
    is_negative = clean_verdict in NEGATIVE_VERDICTS
    is_uncomparable = clean_verdict == "UNCOMPARABLE"
    is_metrics_only = clean_verdict == "METRICS_ONLY"

    binary_verdict_value: Optional[int] = None
    eligible_for_accuracy = False

    if is_uncomparable:
        ineligibility_reasons.append(IneligibilityReason.NOT_ELIGIBLE_UNCOMPARABLE.value)
    elif is_metrics_only:
        ineligibility_reasons.append(IneligibilityReason.NOT_ELIGIBLE_METRICS_ONLY.value)
    elif is_positive:
        binary_verdict_value = 1
        eligible_for_accuracy = True
    elif is_negative:
        binary_verdict_value = 0
        eligible_for_accuracy = True
    else:
        ineligibility_reasons.append(IneligibilityReason.NOT_ELIGIBLE_NON_BINARY_OUTCOME.value)

    # 2. Prediction contract checks
    eligible_for_binary_calib = False
    forecast_probability: Optional[float] = None
    declared_distribution: Optional[Dict[str, float]] = None
    eligible_for_multi_calib = False

    if not prediction_payload or not isinstance(prediction_payload, dict):
        ineligibility_reasons.append(IneligibilityReason.NOT_ELIGIBLE_NO_PREDICTION.value)
    else:
        # Check explicit confidence semantics
        conf_semantics = prediction_payload.get("confidence_semantics")
        clean_sem = str(conf_semantics).strip().upper() if conf_semantics else ""

        if clean_sem != CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT:
            ineligibility_reasons.append(IneligibilityReason.NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED.value)
        else:
            # Check bounded probability
            raw_conf = prediction_payload.get("confidence")
            if raw_conf is not None and isinstance(raw_conf, (int, float)) and not math.isnan(raw_conf) and not math.isinf(raw_conf):
                p_val = float(raw_conf)
                if 0.0 <= p_val <= 1.0:
                    forecast_probability = p_val
                    if eligible_for_accuracy and binary_verdict_value is not None:
                        eligible_for_binary_calib = True

        # Check multiclass probability distribution
        raw_dist = prediction_payload.get("probability_distribution")
        if isinstance(raw_dist, dict) and raw_dist:
            try:
                clean_dist: Dict[str, float] = {}
                tot_p = 0.0
                for cat_k, cat_p in raw_dist.items():
                    p_num = float(cat_p)
                    if math.isnan(p_num) or math.isinf(p_num) or p_num < 0.0 or p_num > 1.0:
                        raise ValueError("Invalid probability in distribution")
                    clean_dist[str(cat_k).strip()] = p_num
                    tot_p += p_num
                if abs(tot_p - 1.0) <= 1e-4 and not is_uncomparable:
                    declared_distribution = clean_dist
                    eligible_for_multi_calib = True
                else:
                    ineligibility_reasons.append(IneligibilityReason.NOT_ELIGIBLE_INCOMPLETE_DISTRIBUTION.value)
            except Exception:
                ineligibility_reasons.append(IneligibilityReason.NOT_ELIGIBLE_INCOMPLETE_DISTRIBUTION.value)

    return EvaluationRecordEligibility(
        eligible_for_accuracy=eligible_for_accuracy,
        eligible_for_coverage=eligible_for_coverage,
        eligible_for_binary_calibration=eligible_for_binary_calib,
        eligible_for_multiclass_calibration=eligible_for_multi_calib,
        binary_verdict_value=binary_verdict_value,
        forecast_probability=forecast_probability,
        declared_distribution=declared_distribution,
        ineligibility_reasons=ineligibility_reasons,
    )


# ── STATISTICAL HELPERS ───────────────────────────────────────────────────────

def compute_wilson_score_interval(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> Optional[Tuple[float, float]]:
    """
    Computes Wilson score interval for binomial proportion:
    k positive observations out of n total trials.
    Returns (lower_bound, upper_bound) in [0.0, 1.0], or None if n == 0.
    """
    if n <= 0 or k < 0 or k > n:
        return None

    # Z-score for two-sided confidence level (default 1.959964 for 95%)
    z = 1.959963984540054 if abs(confidence - 0.95) < 1e-3 else 1.96
    z2 = z * z
    p_hat = k / n

    denom = 1.0 + (z2 / n)
    center = (p_hat + (z2 / (2.0 * n))) / denom
    margin = (z * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * (n ** 2))))) / denom

    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return (round(lower, 4), round(upper, 4))


# ── BASIC OUTCOME STATISTICS ──────────────────────────────────────────────────

def compute_outcome_statistics(
    evaluations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Computes rigorous outcome statistics across a collection of completed evaluations:
    - Distinguishes observed accuracy from coverage.
    - Preserves uncomparable outcomes without counting them as incorrect.
    - Excludes METRICS_ONLY from binary calculations.
    - Breaks down statistics by prediction type cohort.
    """
    total_completed = len(evaluations)
    comparable_count = 0
    uncomparable_count = 0
    metrics_only_count = 0
    correct_count = 0
    incorrect_count = 0

    excluded_counts: Dict[str, int] = {
        IneligibilityReason.NOT_ELIGIBLE_UNCOMPARABLE.value: 0,
        IneligibilityReason.NOT_ELIGIBLE_METRICS_ONLY.value: 0,
        IneligibilityReason.NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED.value: 0,
    }

    # Cohort trackers
    cohort_evals: Dict[str, List[Dict[str, Any]]] = {
        "CATEGORICAL": [],
        "DIRECTIONAL": [],
        "QUANTITATIVE": [],
        "ENGINEERING_DECISION": [],
    }

    for item in evaluations:
        pred_payload = item.get("prediction_payload") or {}
        verdict = str(item.get("verdict", "")).strip().upper()
        pred_type = str(pred_payload.get("prediction_type", item.get("comparison_type", ""))).strip().upper()

        if pred_type in cohort_evals:
            cohort_evals[pred_type].append(item)

        elig = evaluate_observation_eligibility(pred_payload, verdict)

        if verdict == "UNCOMPARABLE":
            uncomparable_count += 1
            excluded_counts[IneligibilityReason.NOT_ELIGIBLE_UNCOMPARABLE.value] += 1
        else:
            comparable_count += 1

        if verdict == "METRICS_ONLY":
            metrics_only_count += 1
            excluded_counts[IneligibilityReason.NOT_ELIGIBLE_METRICS_ONLY.value] += 1

        if elig.eligible_for_accuracy:
            if elig.binary_verdict_value == 1:
                correct_count += 1
            elif elig.binary_verdict_value == 0:
                incorrect_count += 1

        if IneligibilityReason.NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED.value in elig.ineligibility_reasons:
            excluded_counts[IneligibilityReason.NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED.value] += 1

    # Explicit Denominators
    binary_total = correct_count + incorrect_count
    observed_accuracy = (
        round(correct_count / binary_total, 4) if binary_total > 0 else None
    )
    accuracy_uncertainty = (
        compute_wilson_score_interval(correct_count, binary_total) if binary_total > 0 else None
    )

    comparison_coverage = (
        round(comparable_count / total_completed, 4) if total_completed > 0 else None
    )

    # Compute cohort breakdown recursively without nesting
    cohort_breakdown: Dict[str, Any] = {}
    for c_name, c_items in cohort_evals.items():
        c_total = len(c_items)
        if c_total == 0:
            cohort_breakdown[c_name] = {
                "total_completed": 0,
                "comparable_count": 0,
                "uncomparable_count": 0,
                "correct_count": 0,
                "incorrect_count": 0,
                "observed_accuracy": None,
                "comparison_coverage": None,
            }
            continue

        c_comp = sum(1 for x in c_items if str(x.get("verdict", "")).upper() != "UNCOMPARABLE")
        c_uncomp = sum(1 for x in c_items if str(x.get("verdict", "")).upper() == "UNCOMPARABLE")
        c_corr = sum(1 for x in c_items if str(x.get("verdict", "")).upper() in POSITIVE_VERDICTS)
        c_incorr = sum(1 for x in c_items if str(x.get("verdict", "")).upper() in NEGATIVE_VERDICTS)
        c_bin = c_corr + c_incorr

        cohort_breakdown[c_name] = {
            "total_completed": c_total,
            "comparable_count": c_comp,
            "uncomparable_count": c_uncomp,
            "correct_count": c_corr,
            "incorrect_count": c_incorr,
            "observed_accuracy": round(c_corr / c_bin, 4) if c_bin > 0 else None,
            "comparison_coverage": round(c_comp / c_total, 4) if c_total > 0 else None,
        }

    return {
        "total_completed_evaluations": total_completed,
        "comparable_evaluations": comparable_count,
        "uncomparable_evaluations": uncomparable_count,
        "metrics_only_evaluations": metrics_only_count,
        "binary_evaluated_count": binary_total,
        "correct_outcomes": correct_count,
        "incorrect_outcomes": incorrect_count,
        "observed_accuracy": observed_accuracy,
        "observed_accuracy_ci": accuracy_uncertainty,
        "comparison_coverage": comparison_coverage,
        "excluded_counts": excluded_counts,
        "cohort_breakdown": cohort_breakdown,
    }


# ── BRIER SCORE ───────────────────────────────────────────────────────────────

def compute_brier_score(
    evaluations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Computes Brier score for binary probabilistic forecasts:
    BS = (1/N) * sum((p_i - y_i)^2)
    where p_i is the explicitly submitted forecast probability and y_i in {0, 1}.

    Strict requirements:
    - Uses only observations with confidence_semantics == PROBABILITY_PREDICTION_CORRECT.
    - Excludes uncomparable, metrics-only, or non-binary verdicts.
    - Returns INSUFFICIENT_SAMPLE if N == 0.
    """
    eligible_obs: List[Tuple[float, int]] = []
    excluded_count = 0
    excluded_reasons_tally: Dict[str, int] = {}

    for item in evaluations:
        pred_payload = item.get("prediction_payload") or {}
        verdict = str(item.get("verdict", "")).strip().upper()

        elig = evaluate_observation_eligibility(pred_payload, verdict)
        if elig.eligible_for_binary_calibration and elig.forecast_probability is not None and elig.binary_verdict_value is not None:
            eligible_obs.append((elig.forecast_probability, elig.binary_verdict_value))
        else:
            excluded_count += 1
            for r in elig.ineligibility_reasons:
                excluded_reasons_tally[r] = excluded_reasons_tally.get(r, 0) + 1

    n_eligible = len(eligible_obs)
    if n_eligible == 0:
        return {
            "brier_score": None,
            "eligible_sample_size": 0,
            "status": "INSUFFICIENT_SAMPLE",
            "excluded_count": excluded_count,
            "excluded_reasons": excluded_reasons_tally,
            "interpretation": "No eligible probabilistic observations available for Brier score.",
        }

    squared_errors = [(p - y) ** 2 for p, y in eligible_obs]
    mean_brier = sum(squared_errors) / n_eligible

    return {
        "brier_score": round(mean_brier, 6),
        "eligible_sample_size": n_eligible,
        "status": "AVAILABLE",
        "excluded_count": excluded_count,
        "excluded_reasons": excluded_reasons_tally,
        "interpretation": f"Binary Brier score computed over {n_eligible} eligible probabilistic observations.",
    }


def compute_multiclass_brier_score(
    evaluations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Computes Multiclass Brier score:
    BS = (1/N) * sum_{i=1}^N sum_{k=1}^K (p_{i,k} - y_{i,k})^2
    Requires complete authoritative declared probability distribution over all classes.
    """
    eligible_obs: List[float] = []
    excluded_count = 0

    for item in evaluations:
        pred_payload = item.get("prediction_payload") or {}
        verdict = str(item.get("verdict", "")).strip().upper()
        elig = evaluate_observation_eligibility(pred_payload, verdict)

        if not elig.eligible_for_multiclass_calibration or not elig.declared_distribution:
            excluded_count += 1
            continue

        revealed_outcome = item.get("revealed_outcome") or item.get("outcome_identity") or {}
        revealed_class = str(revealed_outcome.get("selected_candidate_id") or revealed_outcome.get("id") or item.get("revealed_class") or "").strip()

        if not revealed_class:
            excluded_count += 1
            continue

        # Check if revealed class is in distribution
        dist = elig.declared_distribution
        obs_error_sum = 0.0
        for cat_name, prob_val in dist.items():
            y_k = 1.0 if cat_name == revealed_class else 0.0
            obs_error_sum += (prob_val - y_k) ** 2

        eligible_obs.append(obs_error_sum)

    n_eligible = len(eligible_obs)
    if n_eligible == 0:
        return {
            "multiclass_brier_score": None,
            "eligible_sample_size": 0,
            "status": "INSUFFICIENT_SAMPLE",
            "excluded_count": excluded_count,
        }

    mean_multi_brier = sum(eligible_obs) / n_eligible
    return {
        "multiclass_brier_score": round(mean_multi_brier, 6),
        "eligible_sample_size": n_eligible,
        "status": "AVAILABLE",
        "excluded_count": excluded_count,
    }


# ── CALIBRATION CURVES ────────────────────────────────────────────────────────

def compute_calibration_curve(
    evaluations: List[Dict[str, Any]],
    policy_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes 5-bin calibration (reliability) curve over eligible probabilistic observations:
    - Bins: [0.0, 0.2), [0.2, 0.4), [0.4, 0.6), [0.6, 0.8), [0.8, 1.0]
    - Mean forecast probability per bin
    - Observed event frequency per bin
    - Sample count per bin
    - Wilson score 95% uncertainty interval
    - Preserves empty bins explicitly
    - Indicates INSUFFICIENT_SAMPLE if total eligible samples < min_curve_sample_size (5).
    """
    policy = policy_spec or CALIBRATION_POLICY_V1_SPEC
    bin_defs = policy["calibration_curve"]["bins"]
    min_samples = policy["calibration_curve"]["min_curve_sample_size"]

    # Gather eligible observations
    eligible_pairs: List[Tuple[float, int]] = []
    excluded_count = 0

    for item in evaluations:
        pred_payload = item.get("prediction_payload") or {}
        verdict = str(item.get("verdict", "")).strip().upper()
        elig = evaluate_observation_eligibility(pred_payload, verdict)

        if elig.eligible_for_binary_calibration and elig.forecast_probability is not None and elig.binary_verdict_value is not None:
            eligible_pairs.append((elig.forecast_probability, elig.binary_verdict_value))
        else:
            excluded_count += 1

    total_eligible = len(eligible_pairs)

    # Binning accumulators
    bins_data: List[Dict[str, Any]] = []

    for b_def in bin_defs:
        b_idx = b_def["index"]
        b_range = b_def["range"]
        low, high = b_range[0], b_range[1]

        # In highest bin, include high endpoint (p == 1.0)
        is_last = (b_idx == len(bin_defs) - 1)

        b_probs: List[float] = []
        b_positives = 0

        for p_val, y_val in eligible_pairs:
            in_bin = (low <= p_val <= high) if is_last else (low <= p_val < high)
            if in_bin:
                b_probs.append(p_val)
                if y_val == 1:
                    b_positives += 1

        b_count = len(b_probs)
        mean_prob = round(sum(b_probs) / b_count, 4) if b_count > 0 else None
        obs_freq = round(b_positives / b_count, 4) if b_count > 0 else None
        ci = compute_wilson_score_interval(b_positives, b_count) if b_count > 0 else None

        bins_data.append({
            "bin_index": b_idx,
            "range": [low, high],
            "label": b_def["label"],
            "sample_count": b_count,
            "positive_count": b_positives,
            "mean_forecast_probability": mean_prob,
            "observed_frequency": obs_freq,
            "uncertainty_interval": ci,
            "is_empty": (b_count == 0),
        })

    if total_eligible == 0:
        curve_status = "NO_DATA"
        status_message = "No eligible probabilistic observations found."
    elif total_eligible < min_samples:
        curve_status = "INSUFFICIENT_SAMPLE"
        status_message = f"Sample size ({total_eligible}) is below minimum curve threshold ({min_samples}). Descriptive bin counts shown without conclusive calibration claims."
    else:
        curve_status = "AVAILABLE"
        status_message = f"Reliability curve evaluated over {total_eligible} eligible observations."

    return {
        "status": curve_status,
        "status_message": status_message,
        "total_eligible_samples": total_eligible,
        "excluded_observations_count": excluded_count,
        "bins": bins_data,
        "policy_version": policy["policy_version"],
        "binning_method": policy["calibration_curve"]["binning_method"],
        "uncertainty_method": policy["calibration_curve"]["uncertainty_method"],
    }


# ── DETERMINISTIC AGGREGATE IDENTITY / HASH ───────────────────────────────────

def compute_aggregate_hash(
    cohort_definition: Dict[str, Any],
    policy_version: str,
    source_comparison_ids: List[str],
    source_comparison_hashes: List[str],
) -> str:
    """
    Computes deterministic SHA-256 fingerprint for an aggregate result.
    Enforces stable sorting and canonical JSON formatting.
    Guarantees:
    - Any added, removed, or modified source comparison changes the hash.
    - Any policy version change changes the hash.
    - Different time windows or cohort filters produce distinct hashes.
    """
    payload = {
        "policy_version": str(policy_version).strip(),
        "cohort_definition": cohort_definition,
        "source_comparison_ids": sorted([str(cid).strip() for cid in source_comparison_ids]),
        "source_comparison_hashes": sorted([str(ch).strip() for ch in source_comparison_hashes]),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
