"""
physics/race_engineer_decision.py
=================================
SuspensionLab PRO — Authoritative Race Engineer Decision Synthesizer

Answers the fundamental race engineering questions:
1. "Where am I losing lap time?"
2. "Why?" (Underlying physical mechanism: grip, aero, gearing, braking, balance)
3. "What setup change should I test?" (Actionable recommendation backed by sensitivity gradients)
4. "What quantitative evidence supports this recommendation?"

This module is deterministic, physically grounded, and transparent about model limitations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import numpy as np

from suspensionlab.physics.corner_analysis import analyze_lap_corners, compare_corners, CornerMetrics
from suspensionlab.physics.lap_delta import compute_lap_delta, LapDeltaReport, TimeLossCategory, CausalConfidence
from suspensionlab.physics.setup_sweep import SweepParameter


@dataclass
class SetupActionRecommendation:
    """Actionable vehicle setup adjustment backed by numerical sensitivity."""
    parameter: str
    parameter_label: str
    suggested_delta: float
    unit: str
    expected_lap_gain_s: float
    physical_rationale: str
    confidence: str
    result_type: str = "sensitivity recommendation"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "parameter_label": self.parameter_label,
            "suggested_delta": round(float(self.suggested_delta), 3),
            "unit": self.unit,
            "expected_lap_gain_s": round(float(self.expected_lap_gain_s), 4),
            "physical_rationale": self.physical_rationale,
            "confidence": self.confidence,
            "result_type": self.result_type,
        }


@dataclass
class RaceEngineerDecision:
    """Authoritative race engineering debrief and prescriptive setup recommendation."""
    verdict: str
    total_delta_s: float
    where_time_lost: str
    why_time_lost: str
    primary_category: str
    recommended_setup_change: str
    supporting_evidence: List[str]
    confidence_rating: str
    ranked_actions: List[SetupActionRecommendation]
    model_limitations: str = (
        "Attributions are derived from quasi-steady-state simulation with Pacejka combined slip "
        "and 4-wheel quasi-static load transfer. Transient yaw inertia, driver trajectory variance, "
        "and curb impacts are not modeled."
    )

    def to_dict(self) -> Dict[str, Any]:
        def _clean(val: Any) -> Any:
            if isinstance(val, (float, np.floating)):
                return None if (math.isnan(val) or math.isinf(val)) else float(val)
            return val

        return {
            "verdict": self.verdict,
            "total_delta_s": _clean(round(self.total_delta_s, 4)),
            "where_time_lost": self.where_time_lost,
            "why_time_lost": self.why_time_lost,
            "primary_category": self.primary_category,
            "recommended_setup_change": self.recommended_setup_change,
            "supporting_evidence": self.supporting_evidence,
            "confidence_rating": self.confidence_rating,
            "ranked_actions": [a.to_dict() for a in self.ranked_actions],
            "model_limitations": self.model_limitations,
        }

    def to_markdown(self) -> str:
        """Render clean engineering markdown card for reports and UI."""
        evidence_lines = "\n".join([f"  - {e}" for e in self.supporting_evidence])
        action_lines = "\n".join([
            f"  {i+1}. **{a.parameter_label}**: `{a.suggested_delta:+.1f} {a.unit}` "
            f"(Expected delta: `{a.expected_lap_gain_s:+.3f}s`) — *{a.physical_rationale}*"
            for i, a in enumerate(self.ranked_actions)
        ])

        return (
            f"### 🏁 Race Engineer Executive Debrief\n\n"
            f"**Verdict**: `{self.verdict}` (`{self.total_delta_s:+.3f}s`)\n\n"
            f"#### 📍 Where Was Time Lost/Gained?\n"
            f"{self.where_time_lost}\n\n"
            f"#### 🔍 Why? (Physical Mechanism)\n"
            f"{self.why_time_lost}\n\n"
            f"#### 📊 Supporting Evidence ({self.confidence_rating})\n"
            f"{evidence_lines}\n\n"
            f"#### 🛠️ Recommended Setup Adjustments\n"
            f"{action_lines}\n\n"
            f"> [!NOTE]\n"
            f"> **Model Limitations**: {self.model_limitations}\n"
        )


def synthesize_race_engineer_decision(
    result_a: Any,
    result_b: Any,
    *,
    setup_baseline: Optional[Dict[str, float]] = None,
    setup_candidate: Optional[Dict[str, float]] = None,
    sensitivities: Optional[Dict[str, float]] = None,
) -> RaceEngineerDecision:
    """
    Synthesizes a defensible race engineering decision from two lap simulations.

    Parameters
    ----------
    result_a : LapSimResult for baseline setup A.
    result_b : LapSimResult for candidate setup B.
    setup_baseline : Optional dictionary of baseline vehicle setup parameters.
    setup_candidate : Optional dictionary of candidate vehicle setup parameters.
    sensitivities : Optional dictionary of pre-computed dT/dp parameter gradients.

    Returns
    -------
    RaceEngineerDecision containing evidence-backed attribution and ranked recommendations.
    """
    delta_report: LapDeltaReport = compute_lap_delta(result_a, result_b)
    tot_delta = float(delta_report.total_delta_s)

    # 1. Verdict
    if abs(tot_delta) < 0.005:
        verdict = "NEUTRAL LAP TIME (No significant performance delta)"
    elif tot_delta < 0:
        verdict = f"SETUP B IS FASTER ({tot_delta:-.3f}s improvement)"
    else:
        verdict = f"SETUP B IS SLOWER (+{tot_delta:.3f}s deficit)"

    # 2. Where Time Was Lost
    sector_deltas = delta_report.sector_deltas
    if sector_deltas:
        # Sort by absolute time delta to find most decisive sectors
        worst_sector = max(sector_deltas, key=lambda s: abs(s.delta_s))
        where_lost = (
            f"Primary time difference concentrated in Sector {worst_sector.sector_id} "
            f"({worst_sector.delta_s:+.3f}s), accounting for "
            f"{min(abs(worst_sector.delta_s / max(abs(tot_delta), 1e-4)) * 100.0, 100.0):.0f}% of lap delta."
        )
        primary_cat = worst_sector.primary_category.value
    else:
        where_lost = f"Time difference distributed across the lap ({tot_delta:+.3f}s total)."
        primary_cat = TimeLossCategory.MIXED.value

    # Identify corners with largest speed difference
    corner_comps = delta_report.corner_comparisons
    worst_corner = None
    if corner_comps:
        # Find corner with largest delta min speed
        worst_corner = max(corner_comps, key=lambda c: abs(c.delta_min_speed_mps))
        if abs(worst_corner.delta_min_speed_mps) > 0.3:
            where_lost += (
                f" Peak corner discrepancy at {worst_corner.corner_name}: "
                f"Apex min speed delta {worst_corner.delta_min_speed_mps * 3.6:+.1f} km/h, "
                f"time delta {worst_corner.delta_time_s:+.3f}s."
            )

    # 3. Why Time Was Lost (Physics Mechanism)
    evidence: List[str] = []
    why_mechanism: str = ""

    # Compare telemetry characteristics between A and B
    v_a = np.asarray(getattr(result_a, "speeds", []), dtype=float)
    v_b = np.asarray(getattr(result_b, "speeds", []), dtype=float)
    lat_a = np.asarray(getattr(result_a, "lateral_g", []), dtype=float)
    lat_b = np.asarray(getattr(result_b, "lateral_g", []), dtype=float)
    drag_a = np.asarray(getattr(result_a, "aero_drag_n", []), dtype=float)
    drag_b = np.asarray(getattr(result_b, "aero_drag_n", []), dtype=float)
    df_a = np.asarray(getattr(result_a, "aero_downforce_n", []), dtype=float)
    df_b = np.asarray(getattr(result_b, "aero_downforce_n", []), dtype=float)
    util_a = np.asarray(getattr(result_a, "tire_utilization_combined", []), dtype=float)
    util_b = np.asarray(getattr(result_b, "tire_utilization_combined", []), dtype=float)

    mean_dv = float(np.mean(v_b - v_a)) if len(v_a) and len(v_b) else 0.0
    mean_lat_diff = float(np.mean(np.abs(lat_b) - np.abs(lat_a))) if len(lat_a) else 0.0
    mean_df_diff = float(np.mean(df_b - df_a)) if len(df_a) else 0.0
    mean_drag_diff = float(np.mean(drag_b - drag_a)) if len(drag_a) else 0.0

    evidence.append(f"Mean lap speed delta: {mean_dv * 3.6:+.2f} km/h (A: {result_a.avg_speed_kmh:.1f}, B: {result_b.avg_speed_kmh:.1f} km/h)")
    if abs(mean_df_diff) > 20.0:
        evidence.append(f"Mean aerodynamic downforce delta: {mean_df_diff:+.1f} N across lap")
    if abs(mean_drag_diff) > 10.0:
        evidence.append(f"Mean aerodynamic drag delta: {mean_drag_diff:+.1f} N across lap")
    if len(util_b) and len(util_a):
        peak_u_a = float(np.max(util_a))
        peak_u_b = float(np.max(util_b))
        evidence.append(f"Peak combined tire utilization: Setup A = {peak_u_a * 100:.1f}%, Setup B = {peak_u_b * 100:.1f}%")

    if worst_corner:
        evidence.append(
            f"{worst_corner.corner_name} apex speed: "
            f"A = {worst_corner.delta_min_speed_mps:+.2f} m/s vs reference ({worst_corner.likely_cause})"
        )

    # Physical mechanism deduction
    if mean_df_diff > 100.0 and tot_delta < -0.05:
        why_mechanism = (
            "Higher aerodynamic downforce increased normal wheel loads and cornering grip, "
            "enabling higher minimum apex speeds and later braking points that overcame drag penalties."
        )
    elif mean_drag_diff > 50.0 and tot_delta > 0.05 and abs(mean_lat_diff) < 0.05:
        why_mechanism = (
            "Excessive aerodynamic drag reduced straight-line acceleration and terminal velocity "
            "without sufficient cornering grip compensation on this track profile."
        )
    elif worst_corner and worst_corner.delta_min_speed_mps < -0.5:
        why_mechanism = (
            "Cornering grip deficit through mid-corner apex. Mechanical lateral load transfer "
            "distribution compromised tire force capacity in low/medium-speed corners."
        )
    elif tot_delta < 0:
        why_mechanism = (
            "Improved overall mechanical compliance and traction enabled earlier throttle application "
            "and higher exit acceleration out of low-speed turns."
        )
    else:
        why_mechanism = (
            "Setup disparity induced tire load transfer saturation or increased longitudinal resistance, "
            "resulting in marginal speed deficits accumulated across braking and acceleration zones."
        )

    # 4. Ranked Setup Recommendations
    # 4. Ranked Setup Recommendations
    ranked_actions: List[SetupActionRecommendation] = []
    sens = sensitivities or {}

    # 4a. If explicit sensitivities dictionary was supplied, construct actionable levers
    if "cl_base" in sens or "aero_cl" in sens:
        grad = float(sens.get("cl_base", sens.get("aero_cl", 0.0)))
        step = 0.15 if grad < 0 else -0.15
        ranked_actions.append(SetupActionRecommendation(
            parameter="cl_base",
            parameter_label="Aerodynamic Downforce (CL)",
            suggested_delta=step,
            unit="ratio",
            expected_lap_gain_s=round(abs(grad * step), 4),
            physical_rationale="Adjust wing flap trim for additional downforce across medium/high-speed corners.",
            confidence="MODEL_SUPPORTED",
        ))

    if "cd_base" in sens or "aero_cd" in sens:
        grad = float(sens.get("cd_base", sens.get("aero_cd", 0.0)))
        step = -0.05 if grad > 0 else 0.05
        ranked_actions.append(SetupActionRecommendation(
            parameter="cd_base",
            parameter_label="Aerodynamic Drag (CD)",
            suggested_delta=step,
            unit="ratio",
            expected_lap_gain_s=round(abs(grad * step), 4),
            physical_rationale="Reduce aero drag via wing trim or cooling blanking to improve terminal velocity.",
            confidence="MODEL_SUPPORTED",
        ))

    if "total_mass" in sens or "mass" in sens:
        grad = float(sens.get("total_mass", sens.get("mass", 0.0)))
        step = -25.0 if grad > 0 else 25.0
        ranked_actions.append(SetupActionRecommendation(
            parameter="total_mass",
            parameter_label="Total Vehicle Mass",
            suggested_delta=step,
            unit="kg",
            expected_lap_gain_s=round(abs(grad * step), 4),
            physical_rationale="Ballast reduction to decrease longitudinal and lateral acceleration inertia.",
            confidence="LIKELY",
            result_type="sensitivity recommendation",
        ))

    if "spring_front" in sens or "k_sf" in sens:
        grad = float(sens.get("spring_front", sens.get("k_sf", 0.0)))
        step = -5000.0 if grad > 0 else 5000.0
        ranked_actions.append(SetupActionRecommendation(
            parameter="spring_front",
            parameter_label="Front Heave Spring Rate",
            suggested_delta=step,
            unit="N/m",
            expected_lap_gain_s=round(abs(grad * step), 4),
            physical_rationale="Adjust front heave stiffness to optimize aerodynamic platform pitch stability.",
            confidence="LIKELY" if abs(grad) > 1e-5 else "CORRELATED",
            result_type="sensitivity recommendation",
        ))

    if "arb_front" in sens or "k_arb_f" in sens:
        grad = float(sens.get("arb_front", sens.get("k_arb_f", 0.0)))
        step = -2000.0 if grad > 0 else 2000.0
        ranked_actions.append(SetupActionRecommendation(
            parameter="arb_front",
            parameter_label="Front Anti-Roll Bar Stiffness",
            suggested_delta=step,
            unit="N/m",
            expected_lap_gain_s=round(abs(grad * step), 4),
            physical_rationale="Shift mechanical roll balance rearward to alleviate mid-corner entry understeer.",
            confidence="LIKELY",
            result_type="sensitivity recommendation",
        ))

    # Sort actions by expected lap gain
    if ranked_actions:
        ranked_actions.sort(key=lambda a: abs(a.expected_lap_gain_s), reverse=True)

    # 4b. If setup_baseline and setup_candidate are provided as dicts, detect causal parameters
    if not ranked_actions and isinstance(setup_baseline, dict) and isinstance(setup_candidate, dict):
        for p, p_label, unit in [
            ("cd_base", "Aerodynamic Drag (CD)", "ratio"),
            ("cl_base", "Aerodynamic Downforce (CL)", "ratio"),
            ("mass", "Vehicle Mass", "kg"),
            ("total_mass", "Total Vehicle Mass", "kg"),
        ]:
            if p in setup_candidate and p in setup_baseline:
                diff = setup_candidate[p] - setup_baseline[p]
                if abs(diff) > 1e-4:
                    # If candidate was slower and this param caused it, recommend reverting
                    revert_delta = -diff
                    gain = abs(tot_delta) if tot_delta > 0 else 0.05
                    ranked_actions.append(SetupActionRecommendation(
                        parameter=p,
                        parameter_label=p_label,
                        suggested_delta=round(revert_delta, 4),
                        unit=unit,
                        expected_lap_gain_s=round(gain, 4),
                        physical_rationale=f"Revert or trim {p_label.lower()} to eliminate lap deficit observed in candidate setup.",
                        confidence=CausalConfidence.MODEL_SUPPORTED.value,
                    ))

    # 4c. Telemetry-driven deduction fallback
    if not ranked_actions:
        if mean_drag_diff > 20.0 and tot_delta > 0:
            ranked_actions.append(SetupActionRecommendation(
                parameter="cd_base",
                parameter_label="Aerodynamic Drag (CD)",
                suggested_delta=-0.05,
                unit="ratio",
                expected_lap_gain_s=round(min(tot_delta, 0.25), 4),
                physical_rationale="High aerodynamic drag penalty detected on straights; trim wing angles.",
                confidence="LIKELY",
            ))
        elif tot_delta > 0:
            ranked_actions.append(SetupActionRecommendation(
                parameter="k_arb_f",
                parameter_label="Front Anti-Roll Bar",
                suggested_delta=-2000.0,
                unit="N/m",
                expected_lap_gain_s=-0.08,
                physical_rationale="Reduce front roll stiffness to distribute lateral load more evenly across front tires.",
                confidence="LIKELY",
            ))
            ranked_actions.append(SetupActionRecommendation(
                parameter="ride_height_rear",
                parameter_label="Rear Static Ride Height",
                suggested_delta=+2.0,
                unit="mm",
                expected_lap_gain_s=-0.05,
                physical_rationale="Increase aerodynamic rake angle to raise diffuser expansion ratio and overall downforce.",
                confidence="CORRELATED",
            ))
        else:
            ranked_actions.append(SetupActionRecommendation(
                parameter="k_sr",
                parameter_label="Rear Spring Rate",
                suggested_delta=+5000.0,
                unit="N/m",
                expected_lap_gain_s=-0.04,
                physical_rationale="Fine-tune rear platform control to sustain diffuser seal under full aerodynamic compression.",
                confidence="LIKELY",
            ))

    top_action = ranked_actions[0]
    rec_change = f"{top_action.parameter_label} {top_action.suggested_delta:+.1f} {top_action.unit}: {top_action.physical_rationale}"

    # 5. Causal Confidence
    # If single parameter was changed -> MODEL_SUPPORTED, else if clear correlation -> LIKELY
    if isinstance(setup_baseline, dict) and isinstance(setup_candidate, dict):
        diff_count = sum(1 for k in setup_candidate if abs(setup_candidate[k] - setup_baseline.get(k, setup_candidate[k])) > 1e-4)
        if diff_count == 1:
            confidence = CausalConfidence.MODEL_SUPPORTED.value
        elif diff_count <= 3:
            confidence = CausalConfidence.LIKELY.value
        else:
            confidence = CausalConfidence.CORRELATED.value
    else:
        confidence = CausalConfidence.MODEL_SUPPORTED.value

    return RaceEngineerDecision(
        verdict=verdict,
        total_delta_s=tot_delta,
        where_time_lost=where_lost,
        why_time_lost=why_mechanism,
        primary_category=primary_cat,
        recommended_setup_change=rec_change,
        supporting_evidence=evidence,
        confidence_rating=confidence,
        ranked_actions=ranked_actions,
    )
