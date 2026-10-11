"""SuspensionLab PRO — Epistemic Validity Classification Engine.

Implements Requirement 6:
Use authoritative statuses:
- DISCOVERY
- MODEL_SUPPORTED
- CORRELATED
- EMPIRICALLY_VALIDATED
- EXTRAPOLATED
- UNSUPPORTED
- NUMERICALLY_FAILED
- UNIDENTIFIABLE

Governance Directive:
- "Do not upgrade epistemic status automatically."
- Calibration / discovery sets can never be certified as EMPIRICALLY_VALIDATED.
- Degraded states strictly propagate downstream.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


class EpistemicValidityStatus(str, Enum):
    """Authoritative physical and empirical validity status per Requirement 6."""
    DISCOVERY = "DISCOVERY"                          # Calibration/discovery partition (never external confirmation)
    MODEL_SUPPORTED = "MODEL_SUPPORTED"              # Operating within theoretical physical assumptions
    CORRELATED = "CORRELATED"                        # Moderately correlated with measured telemetry (R2 >= 0.70)
    EMPIRICALLY_VALIDATED = "EMPIRICALLY_VALIDATED"  # Confirmed on unseen validation/holdout data (R2 >= 0.85, bias pass)
    EXTRAPOLATED = "EXTRAPOLATED"                    # Operating outside calibrated envelope
    UNSUPPORTED = "UNSUPPORTED"                      # Physical domain or structural model assumptions violated
    NUMERICALLY_FAILED = "NUMERICALLY_FAILED"        # Solver divergence, NaN, Inf, integration instability
    UNIDENTIFIABLE = "UNIDENTIFIABLE"                # Telemetry lacks excitation/observability to evaluate states


# Degradation hierarchy: higher rank = more degraded validity
_STATUS_HIERARCHY: Dict[EpistemicValidityStatus, int] = {
    EpistemicValidityStatus.EMPIRICALLY_VALIDATED: 0,
    EpistemicValidityStatus.CORRELATED: 1,
    EpistemicValidityStatus.MODEL_SUPPORTED: 2,
    EpistemicValidityStatus.DISCOVERY: 3,
    EpistemicValidityStatus.EXTRAPOLATED: 4,
    EpistemicValidityStatus.UNIDENTIFIABLE: 5,
    EpistemicValidityStatus.UNSUPPORTED: 6,
    EpistemicValidityStatus.NUMERICALLY_FAILED: 7,
}


class ValidityPromotionError(RuntimeError):
    """Raised when an attempt is made to illegally upgrade a degraded epistemic status."""
    pass


@dataclass
class ValidityClassificationRecord:
    """Authoritative record certifying epistemic status for a validation trial."""
    status: EpistemicValidityStatus
    target_channel_or_maneuver: str
    is_unseen_data: bool
    r2_score: float
    rmse: float
    max_error: float
    mean_bias: float
    phase_lag_ms: float
    operating_envelope_within_bounds: bool
    leak_free_guarantee: bool
    timebase_audit_passed: bool
    evidence_rationale: str
    upstream_status: Optional[EpistemicValidityStatus] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "target": self.target_channel_or_maneuver,
            "is_unseen_data": self.is_unseen_data,
            "r2_score": round(self.r2_score, 4),
            "rmse": round(self.rmse, 4),
            "max_error": round(self.max_error, 4),
            "mean_bias": round(self.mean_bias, 4),
            "phase_lag_ms": round(self.phase_lag_ms, 2),
            "operating_envelope_within_bounds": self.operating_envelope_within_bounds,
            "leak_free_guarantee": self.leak_free_guarantee,
            "timebase_audit_passed": self.timebase_audit_passed,
            "evidence_rationale": self.evidence_rationale,
            "upstream_status": self.upstream_status.value if self.upstream_status else None,
            "warnings": self.warnings,
        }


class ValidityClassificationEngine:
    """Classifies validation outcomes according to strict epistemic laws."""

    @classmethod
    def classify(
        cls,
        r2_score: float,
        rmse: float,
        mean_bias: float,
        phase_lag_ms: float,
        is_unseen_data: bool,
        is_discovery_partition: bool,
        operating_envelope_within_bounds: bool,
        leak_free_guarantee: bool,
        timebase_audit_passed: bool,
        signal_has_excitation: bool = True,
        numerical_diverged: bool = False,
        physical_assumptions_violated: bool = False,
        upstream_status: Optional[EpistemicValidityStatus] = None,
        target_name: str = "simulation",
    ) -> ValidityClassificationRecord:
        """Determines the exact epistemic validity classification under non-upgrade governance."""
        warnings: List[str] = []

        # 1. Catastrophic numerical or physical failure
        if numerical_diverged or math.isnan(r2_score) or math.isnan(rmse) or math.isinf(rmse):
            status = EpistemicValidityStatus.NUMERICALLY_FAILED
            rationale = "Numerical divergence, NaN/Inf values, or integrator breakdown detected."
            return ValidityClassificationRecord(
                status=status,
                target_channel_or_maneuver=target_name,
                is_unseen_data=is_unseen_data,
                r2_score=0.0,
                rmse=float("inf") if math.isnan(rmse) else rmse,
                max_error=float("inf"),
                mean_bias=0.0,
                phase_lag_ms=0.0,
                operating_envelope_within_bounds=operating_envelope_within_bounds,
                leak_free_guarantee=leak_free_guarantee,
                timebase_audit_passed=timebase_audit_passed,
                evidence_rationale=rationale,
                warnings=["Numerical integrator failure."],
            )

        # 2. Physics domain violation
        if physical_assumptions_violated or not leak_free_guarantee:
            status = EpistemicValidityStatus.UNSUPPORTED
            rationale = (
                "Physical model assumptions violated or telemetry firewall breach detected."
                if not leak_free_guarantee
                else "Physical parameter boundaries or kinematic constraints violated."
            )
            warnings.append("Simulation operates outside physical admissibility domain.")
            return ValidityClassificationRecord(
                status=status,
                target_channel_or_maneuver=target_name,
                is_unseen_data=is_unseen_data,
                r2_score=r2_score,
                rmse=rmse,
                max_error=0.0,
                mean_bias=mean_bias,
                phase_lag_ms=phase_lag_ms,
                operating_envelope_within_bounds=operating_envelope_within_bounds,
                leak_free_guarantee=leak_free_guarantee,
                timebase_audit_passed=timebase_audit_passed,
                evidence_rationale=rationale,
                warnings=warnings,
            )

        # 3. Observability / Dynamic Excitation
        if not signal_has_excitation:
            status = EpistemicValidityStatus.UNIDENTIFIABLE
            rationale = "Telemetry lacks dynamic excitation or observability to identify model validity."
            warnings.append("Insufficient dynamic excitation in channel/window.")
            return ValidityClassificationRecord(
                status=status,
                target_channel_or_maneuver=target_name,
                is_unseen_data=is_unseen_data,
                r2_score=r2_score,
                rmse=rmse,
                max_error=0.0,
                mean_bias=mean_bias,
                phase_lag_ms=phase_lag_ms,
                operating_envelope_within_bounds=operating_envelope_within_bounds,
                leak_free_guarantee=leak_free_guarantee,
                timebase_audit_passed=timebase_audit_passed,
                evidence_rationale=rationale,
                warnings=warnings,
            )

        # 4. Out of calibrated operating envelope
        if not operating_envelope_within_bounds:
            status = EpistemicValidityStatus.EXTRAPOLATED
            rationale = "Operating outside calibrated parameter envelope (e.g. high-throttle or extreme load)."
            warnings.append("Operating in extrapolated regime; empirical validity cannot be claimed.")
        # 5. Discovery / Calibration set (NEVER upgrade to EMPIRICALLY_VALIDATED)
        elif is_discovery_partition:
            status = EpistemicValidityStatus.DISCOVERY
            rationale = "Evaluated on discovery/calibration partition; strictly reserved for hypothesis generation."
            warnings.append("Discovery dataset partition cannot be claimed as empirical confirmation.")
        # 6. Empirical Validation Criteria on UNSEEN Data
        elif (
            is_unseen_data
            and r2_score >= 0.85
            and abs(phase_lag_ms) <= 50.0
            and abs(mean_bias) <= (0.20 * max(rmse, 1e-4))
            and timebase_audit_passed
            and leak_free_guarantee
        ):
            status = EpistemicValidityStatus.EMPIRICALLY_VALIDATED
            rationale = f"Statistically confirmed on unseen validation data (R2={r2_score:.3f} >= 0.85, bias within tolerance)."
        # 7. Correlated
        elif r2_score >= 0.70:
            status = EpistemicValidityStatus.CORRELATED
            rationale = f"Moderately correlated with external data (R2={r2_score:.3f} >= 0.70)."
        # 8. Model Supported
        else:
            status = EpistemicValidityStatus.MODEL_SUPPORTED
            rationale = f"Forward physical model prediction within valid bounds (R2={r2_score:.3f} < 0.70)."

        # Upstream degradation enforcement: Never upgrade upstream degraded status
        if upstream_status is not None:
            up_rank = _STATUS_HIERARCHY.get(upstream_status, 2)
            curr_rank = _STATUS_HIERARCHY.get(status, 2)
            if up_rank >= 4 and curr_rank < up_rank:
                warnings.append(
                    f"Blocked automatic upgrade from degraded upstream status '{upstream_status.value}' to '{status.value}'."
                )
                status = upstream_status
                rationale = f"Inherited upstream degraded status '{upstream_status.value}'."

        return ValidityClassificationRecord(
            status=status,
            target_channel_or_maneuver=target_name,
            is_unseen_data=is_unseen_data,
            r2_score=r2_score,
            rmse=rmse,
            max_error=0.0,
            mean_bias=mean_bias,
            phase_lag_ms=phase_lag_ms,
            operating_envelope_within_bounds=operating_envelope_within_bounds,
            leak_free_guarantee=leak_free_guarantee,
            timebase_audit_passed=timebase_audit_passed,
            evidence_rationale=rationale,
            upstream_status=upstream_status,
            warnings=warnings,
        )

    @classmethod
    def assert_no_illegal_promotion(
        cls,
        original_status: EpistemicValidityStatus,
        proposed_status: EpistemicValidityStatus,
    ) -> None:
        """Enforces that a degraded status is never silently upgraded to a higher status."""
        orig_rank = _STATUS_HIERARCHY[original_status]
        prop_rank = _STATUS_HIERARCHY[proposed_status]
        if orig_rank > prop_rank:
            raise ValidityPromotionError(
                f"ILLEGAL EPISTEMIC PROMOTION: Cannot promote status from '{original_status.value}' "
                f"(rank {orig_rank}) to '{proposed_status.value}' (rank {prop_rank}). "
                "Automatic promotion of degraded epistemic states is prohibited."
            )
