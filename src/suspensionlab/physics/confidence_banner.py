"""
physics/confidence_banner.py
============================
SuspensionLab PRO — Simulation Confidence Banner & Model Validity Breakdown

Generates the quantitative engineering confidence badge and subsystem checklist
displayed at the top of every simulation and optimization report:

┌──────────────────────────────────────────────┐
│  MODEL VALIDITY: CONDITIONAL                 │
│  Confidence Score: 82%                       │
├──────────────────────────────────────────────┤
│  ✔ Tire data calibrated:       YES           │
│  ✖ Aero map calibrated:       NO (Default)  │
│  ✔ Telemetry correlation:      91.4%         │
│  ✔ Kinematics continuation:    PASS          │
│  ⚠ Operating range exceeded:   YES (2 pts)   │
└──────────────────────────────────────────────┘
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


import time
from datetime import datetime, timezone


class EpistemicTier(str, Enum):
    """
    Four distinct epistemic tiers for simulation model outputs and engineering claims:
    1. SIMULATION_ESTIMATE: Forward simulation with nominal/default parameters and no qualifying physical telemetry.
    2. MODEL_SUPPORTED: Forward simulation verified by isolated first-principles parameter perturbations and sensitivity gradients.
    3. CORRELATED: Statistical association with measured telemetry (R² ≥ 0.70) but failing one or more strict empirical validation criteria.
    4. EMPIRICALLY_VALIDATED: Model predictions verified against qualifying physical telemetry satisfying all 7 scientific criteria.
    """
    SIMULATION_ESTIMATE = "SIMULATION_ESTIMATE"
    MODEL_SUPPORTED = "MODEL_SUPPORTED"
    CORRELATED = "CORRELATED"
    EMPIRICALLY_VALIDATED = "EMPIRICALLY_VALIDATED"


class ValidityStatus(str, Enum):
    EMPIRICALLY_VALIDATED = "EMPIRICALLY_VALIDATED"
    VALIDATED = "VALIDATED"         # Synonym for EMPIRICALLY_VALIDATED (maintains backward compatibility)
    PASS = "PASS"                   # Synonym for VALIDATED in verification/certification tests
    CONDITIONAL = "CONDITIONAL"     # 60% - 84% confidence or default aero/tire maps
    DEGRADED = "DEGRADED"           # Significant warnings, high residuals, or partial subsystem failures
    INCONCLUSIVE = "INCONCLUSIVE"   # Insufficient empirical sample size (<100 pts) or wide confidence interval
    UNVALIDATED = "UNVALIDATED"     # No verification data provided or unverified parameters (0.0% score)
    DATA_MISSING = "DATA_MISSING"   # Required validation channels or telemetry sessions absent
    NOT_EVALUATED = "NOT_EVALUATED" # Calculation skipped or solver not verified
    FAIL = "FAIL"                   # Correlation < 50%, solver divergence, or physical bounds violated
    FAILED = "FAILED"               # Synonym for FAIL


@dataclass
class ConfidenceProvenance:
    """Traceable evidence chain for quantitative engineering confidence claims."""
    data_source: str = "NONE"
    sample_count: int = 0
    metric_name: str = "none"
    calculation_method: str = "none"
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_version: str = "quarter-car-v2"
    validation_protocol: str = "NONE"
    is_synthetic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_source": self.data_source,
            "sample_count": self.sample_count,
            "metric_name": self.metric_name,
            "calculation_method": self.calculation_method,
            "timestamp_iso": self.timestamp_iso,
            "model_version": self.model_version,
            "validation_protocol": self.validation_protocol,
            "is_synthetic": self.is_synthetic,
        }


@dataclass
class SimulationConfidenceBanner:
    """Quantitative confidence and validation status banner for simulation outputs."""
    validity_status: ValidityStatus
    confidence_score_pct: float
    tire_calibrated: bool
    aero_calibrated: bool
    epistemic_tier: EpistemicTier = EpistemicTier.SIMULATION_ESTIMATE
    telemetry_correlation_pct: Optional[float] = None
    kinematics_validation: str = "NOT_EVALUATED"
    operating_range_exceeded: bool = False
    out_of_envelope_points: int = 0
    validation_criteria: Dict[str, Any] = field(default_factory=dict)
    provenance: ConfidenceProvenance = field(default_factory=ConfidenceProvenance)

    @classmethod
    def evaluate(
        cls,
        tire_calibrated: bool = False,
        aero_calibrated: bool = False,
        correlation_pct: Optional[float] = None,
        kinematics_valid: str = "NOT_EVALUATED",
        out_of_envelope_count: int = 0,
        data_source: str = "NONE",
        sample_count: int = 0,
        is_synthetic: bool = False,
        validation_protocol: str = "NONE",
        model_version: str = "quarter-car-v2",
        holdout_r2: Optional[float] = None,
        rmse: Optional[float] = None,
        mean_bias: Optional[float] = None,
        phase_lag_ms: Optional[float] = None,
        operating_domain_coverage_pct: Optional[float] = None,
    ) -> SimulationConfidenceBanner:
        """
        Evaluate subsystem validation states and compute overall quantitative confidence.
        Core Principle: NO DATA = NO CLAIM.
        When no validation evidence is supplied, score is strictly 0.0% and status is UNVALIDATED.
        """
        # 1. Zero evidence or empty/missing data strictly evaluates as UNVALIDATED with 0.0% score
        if (
            correlation_pct is None
            and not tire_calibrated
            and not aero_calibrated
            and kinematics_valid in ("NOT_EVALUATED", "UNKNOWN")
        ):
            prov = ConfidenceProvenance(
                data_source="UNVALIDATED_ZERO_DATA",
                sample_count=0,
                metric_name="none",
                calculation_method="none",
                model_version=model_version,
                validation_protocol="NONE",
                is_synthetic=False,
            )
            return cls(
                validity_status=ValidityStatus.UNVALIDATED,
                confidence_score_pct=0.0,
                tire_calibrated=False,
                aero_calibrated=False,
                epistemic_tier=EpistemicTier.SIMULATION_ESTIMATE,
                telemetry_correlation_pct=None,
                kinematics_validation=kinematics_valid,
                operating_range_exceeded=(out_of_envelope_count > 0),
                out_of_envelope_points=out_of_envelope_count,
                provenance=prov,
            )

        # 2. Synthetic telemetry can NEVER grant PASS/VALIDATED certification
        if is_synthetic:
            prov = ConfidenceProvenance(
                data_source="SYNTHETIC_DATASET",
                sample_count=sample_count,
                metric_name="synthetic_cross_correlation",
                calculation_method="simulation_vs_synthetic",
                model_version=model_version,
                validation_protocol=validation_protocol or "SYNTHETIC_SMOKE_TEST",
                is_synthetic=True,
            )
            return cls(
                validity_status=ValidityStatus.DEGRADED,
                confidence_score_pct=0.0,
                tire_calibrated=tire_calibrated,
                aero_calibrated=aero_calibrated,
                epistemic_tier=EpistemicTier.SIMULATION_ESTIMATE,
                telemetry_correlation_pct=None,
                kinematics_validation=kinematics_valid,
                operating_range_exceeded=(out_of_envelope_count > 0),
                out_of_envelope_points=out_of_envelope_count,
                provenance=prov,
            )

        # 3. Objective weighted scoring
        score = 0.0
        score += 25.0 if tire_calibrated else 0.0
        score += 25.0 if aero_calibrated else 0.0

        corr_val = 0.0
        if correlation_pct is not None:
            try:
                corr_val = max(0.0, min(float(correlation_pct), 100.0))
                score += min(corr_val * 0.35, 35.0)
            except (ValueError, TypeError):
                correlation_pct = None

        if kinematics_valid == "PASS":
            score += 15.0
        elif kinematics_valid == "WARNING":
            score += 8.0

        if out_of_envelope_count > 0:
            score = max(score - min(out_of_envelope_count * 2.5, 20.0), 0.0)

        # Check strict empirical criteria
        criteria_checks = {
            "non_synthetic": (not is_synthetic and data_source != "SYNTHETIC_DATASET"),
            "sample_coverage": (sample_count >= 100) if sample_count > 0 else True,
            "r2_overall": (corr_val >= 85.0) if correlation_pct is not None else False,
            "holdout_r2": (holdout_r2 >= 0.80) if holdout_r2 is not None else True,
            "systematic_bias": (abs(mean_bias) <= 0.15 * rmse) if (mean_bias is not None and rmse is not None and rmse > 0) else True,
            "phase_alignment": (abs(phase_lag_ms) <= 50.0) if phase_lag_ms is not None else True,
            "operating_domain": (operating_domain_coverage_pct >= 50.0) if operating_domain_coverage_pct is not None else (out_of_envelope_count == 0),
        }
        all_criteria_met = all(criteria_checks.values())

        # 4. Objective state transitions & Epistemic Tier assignment
        if kinematics_valid == "FAIL" or (correlation_pct is not None and corr_val < 50.0):
            status = ValidityStatus.FAIL
            score = 0.0
            tier = EpistemicTier.SIMULATION_ESTIMATE
        elif correlation_pct is not None and sample_count > 0 and sample_count < 100:
            status = ValidityStatus.INCONCLUSIVE
            tier = EpistemicTier.CORRELATED
        elif correlation_pct is None:
            status = ValidityStatus.DATA_MISSING if (tire_calibrated or aero_calibrated) else ValidityStatus.UNVALIDATED
            score = 0.0  # NO DATA = NO CLAIM
            tier = EpistemicTier.MODEL_SUPPORTED if (tire_calibrated or aero_calibrated) else EpistemicTier.SIMULATION_ESTIMATE
        elif score >= 85.0 and tire_calibrated and aero_calibrated and kinematics_valid == "PASS" and corr_val >= 85.0 and all_criteria_met:
            status = ValidityStatus.VALIDATED
            tier = EpistemicTier.EMPIRICALLY_VALIDATED
        elif score >= 60.0 and corr_val >= 60.0:
            status = ValidityStatus.CONDITIONAL
            tier = EpistemicTier.CORRELATED
        elif score > 0.0:
            status = ValidityStatus.DEGRADED
            tier = EpistemicTier.MODEL_SUPPORTED if (tire_calibrated or aero_calibrated) else EpistemicTier.CORRELATED
        else:
            status = ValidityStatus.UNVALIDATED
            tier = EpistemicTier.SIMULATION_ESTIMATE

        prov = ConfidenceProvenance(
            data_source=data_source if data_source != "NONE" else ("MEASURED_TELEMETRY" if correlation_pct is not None else "UNVALIDATED_ZERO_DATA"),
            sample_count=sample_count,
            metric_name="cross_correlation_r2" if correlation_pct is not None else "none",
            calculation_method="pearson_and_rms_residuals" if correlation_pct is not None else "none",
            model_version=model_version,
            validation_protocol=validation_protocol if validation_protocol != "NONE" else ("ISO_15037_RIDE_VALIDATION" if correlation_pct is not None else "NONE"),
            is_synthetic=False,
        )

        return cls(
            validity_status=status,
            confidence_score_pct=round(score, 1),
            tire_calibrated=tire_calibrated,
            aero_calibrated=aero_calibrated,
            epistemic_tier=tier,
            telemetry_correlation_pct=round(corr_val, 1) if correlation_pct is not None else None,
            kinematics_validation=kinematics_valid,
            operating_range_exceeded=(out_of_envelope_count > 0),
            out_of_envelope_points=out_of_envelope_count,
            validation_criteria=criteria_checks,
            provenance=prov,
        )

    def to_markdown_badge(self) -> str:
        """Render markdown confidence banner card."""
        status_icons = {
            ValidityStatus.VALIDATED: "🟢 VALIDATED",
            ValidityStatus.PASS: "🟢 PASS",
            ValidityStatus.CONDITIONAL: "🟡 CONDITIONAL",
            ValidityStatus.DEGRADED: "🟠 DEGRADED",
            ValidityStatus.INCONCLUSIVE: "🟡 INCONCLUSIVE",
            ValidityStatus.UNVALIDATED: "🔴 UNVALIDATED",
            ValidityStatus.DATA_MISSING: "⚪ DATA_MISSING",
            ValidityStatus.NOT_EVALUATED: "⚪ NOT_EVALUATED",
            ValidityStatus.FAIL: "❌ FAIL",
            ValidityStatus.FAILED: "❌ FAILED",
        }

        icon = status_icons.get(self.validity_status, "🔴 UNVALIDATED")
        tire_check = "✅ YES" if self.tire_calibrated else "❌ NO (Default)"
        aero_check = "✅ YES" if self.aero_calibrated else "❌ NO (Default)"
        range_check = f"⚠️ YES ({self.out_of_envelope_points} pts)" if self.operating_range_exceeded else "✅ NO (Within Envelope)"
        corr_str = f"{self.telemetry_correlation_pct:.1f}%" if self.telemetry_correlation_pct is not None else "N/A (Uncorrelated)"

        return (
            f"```text\n"
            f"┌────────────────────────────────────────────────────────┐\n"
            f"│ MODEL VALIDITY: {icon:<37}│\n"
            f"│ Epistemic Tier: {self.epistemic_tier.value:<38}│\n"
            f"│ Overall Confidence Score: {self.confidence_score_pct:.1f}%                        │\n"
            f"├────────────────────────────────────────────────────────┤\n"
            f"│  • Tire parameters calibrated:    {tire_check:<20} │\n"
            f"│  • Aero map calibrated:           {aero_check:<20} │\n"
            f"│  • Telemetry correlation:         {corr_str:<20} │\n"
            f"│  • Kinematics consistency:        {self.kinematics_validation:<20} │\n"
            f"│  • Operating envelope exceeded:   {range_check:<20} │\n"
            f"└────────────────────────────────────────────────────────┘\n"
            f"```\n"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validity_status": self.validity_status.value,
            "confidence_score_pct": self.confidence_score_pct,
            "tire_calibrated": self.tire_calibrated,
            "aero_calibrated": self.aero_calibrated,
            "epistemic_tier": self.epistemic_tier.value,
            "telemetry_correlation_pct": self.telemetry_correlation_pct,
            "kinematics_validation": self.kinematics_validation,
            "operating_range_exceeded": self.operating_range_exceeded,
            "out_of_envelope_points": self.out_of_envelope_points,
            "validation_criteria": self.validation_criteria,
            "provenance": self.provenance.to_dict(),
        }
