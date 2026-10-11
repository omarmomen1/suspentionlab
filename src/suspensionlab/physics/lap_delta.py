from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TimeLossCategory(Enum):
    """
    Categorizes the primary physical reason for a difference in lap time.
    """
    STRAIGHT_SPEED = "STRAIGHT_SPEED"
    CORNER_SPEED = "CORNER_SPEED"
    BRAKING = "BRAKING"
    ACCELERATION = "ACCELERATION"
    AERO_DOWNFORCE = "AERO_DOWNFORCE"
    AERO_DRAG = "AERO_DRAG"
    TIRE_GRIP = "TIRE_GRIP"
    MIXED = "MIXED"


class CausalConfidence(Enum):
    """
    Indicates the epistemic confidence level of the attribution for a time difference.

    Tiers:
    - EMPIRICALLY_VALIDATED: Verified by physical telemetry evidence across holdout windows.
    - MODEL_SUPPORTED: Isolated simulation parameter perturbation in verified physics model.
    - LIKELY: Consistent physics mechanism with 2-3 interacting parameter variations.
    - CORRELATED: Statistical or directional correlation across multi-parameter differences.
    - UNCERTAIN: Conflicting evidence or unconstrained degrees of freedom.
    """
    EMPIRICALLY_VALIDATED = "EMPIRICALLY_VALIDATED"
    MODEL_SUPPORTED = "MODEL_SUPPORTED"
    LIKELY = "LIKELY"
    CORRELATED = "CORRELATED"
    UNCERTAIN = "UNCERTAIN"
    # Backward compatibility alias
    PROVEN = "MODEL_SUPPORTED"


@dataclass
class SectorDelta:
    """
    Represents the time delta and engineering analysis for a specific track sector.
    """
    sector_id: int
    time_a_s: float
    time_b_s: float
    delta_s: float  # B - A (negative = B is faster)
    primary_category: TimeLossCategory
    contributing_factors: List[str]
    confidence: CausalConfidence
    evidence: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector_id": self.sector_id,
            "time_a_s": self.time_a_s,
            "time_b_s": self.time_b_s,
            "delta_s": self.delta_s,
            "primary_category": self.primary_category.value,
            "contributing_factors": self.contributing_factors,
            "confidence": self.confidence.value,
            "evidence": self.evidence,
        }


@dataclass
class ZoneDelta:
    """
    Finer-grained distance-based analysis for specific contiguous track zones.
    """
    zone_type: str  # 'corner', 'straight', 'braking', 'acceleration'
    start_distance_m: float
    end_distance_m: float
    delta_time_s: float
    delta_speed_mean_mps: float
    primary_category: TimeLossCategory
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_type": self.zone_type,
            "start_distance_m": self.start_distance_m,
            "end_distance_m": self.end_distance_m,
            "delta_time_s": self.delta_time_s,
            "delta_speed_mean_mps": self.delta_speed_mean_mps,
            "primary_category": self.primary_category.value,
            "detail": self.detail,
        }


@dataclass
class LapDeltaReport:
    """
    Complete analysis of WHERE and WHY lap time changed between two vehicle setups.
    """
    total_delta_s: float
    sector_deltas: List[SectorDelta]
    zone_deltas: List[ZoneDelta]
    corner_comparisons: List[Any]
    cumulative_delta_distance: np.ndarray
    cumulative_delta_time: np.ndarray
    speed_diff: np.ndarray
    summary: str
    model_assumptions_caveat: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_delta_s": self.total_delta_s,
            "sector_deltas": [s.to_dict() for s in self.sector_deltas],
            "zone_deltas": [z.to_dict() for z in self.zone_deltas],
            "corner_comparisons": [
                c.to_dict() if hasattr(c, "to_dict") else str(c)
                for c in self.corner_comparisons
            ],
            "cumulative_delta_distance": self.cumulative_delta_distance.tolist(),
            "cumulative_delta_time": self.cumulative_delta_time.tolist(),
            "speed_diff": self.speed_diff.tolist(),
            "summary": self.summary,
            "model_assumptions_caveat": self.model_assumptions_caveat,
        }


def compute_lap_delta(
    result_a: Any,
    result_b: Any,
    *,
    corners_a: Optional[List[Any]] = None,
    corners_b: Optional[List[Any]] = None,
    sectors_a: Optional[List[Any]] = None,
    sectors_b: Optional[List[Any]] = None,
) -> LapDeltaReport:
    """
    Analyzes the differences between two LapSimResult objects to determine where
    and why time was gained or lost.

    Args:
        result_a: Baseline LapSimResult.
        result_b: Modified LapSimResult.
        corners_a: Optional list of corner metrics for baseline.
        corners_b: Optional list of corner metrics for modified setup.
        sectors_a: Optional explicit sector boundaries for A.
        sectors_b: Optional explicit sector boundaries for B.

    Returns:
        A LapDeltaReport containing the delta analysis.
    """
    # 1. Align traces to result_a's distance array
    dist_a = result_a.distances
    dist_b = result_b.distances

    speed_b_interp = np.interp(dist_a, dist_b, result_b.speeds)
    long_g_b_interp = np.interp(dist_a, dist_b, result_b.longitudinal_g)
    
    # Calculate time at each station
    ds_a = np.zeros_like(dist_a)
    ds_a[1:] = np.diff(dist_a)
    
    v_a_safe = np.maximum(result_a.speeds, 1e-3)
    v_b_safe = np.maximum(speed_b_interp, 1e-3)
    
    dt_a = ds_a / v_a_safe
    dt_b = ds_a / v_b_safe
    
    time_a = np.cumsum(dt_a)
    time_b = np.cumsum(dt_b)

    # 2. Cumulative delta and 3. Speed difference
    cumulative_delta_time = time_b - time_a
    speed_diff = speed_b_interp - result_a.speeds

    # 4. Sector analysis
    sector_deltas: List[SectorDelta] = []
    num_sectors = len(result_a.sector_times) if hasattr(result_a, "sector_times") else 1
    
    sector_length_m = dist_a[-1] / max(1, num_sectors)
    
    summary_lines = [
        f"Lap Time Delta: {result_b.total_time - result_a.total_time:+.3f}s "
        f"({'Setup B faster' if result_b.total_time < result_a.total_time else 'Setup A faster'})\n"
    ]

    for i in range(num_sectors):
        start_dist = i * sector_length_m
        end_dist = (i + 1) * sector_length_m if i < num_sectors - 1 else dist_a[-1]
        mask = (dist_a >= start_dist) & (dist_a <= end_dist)
        
        t_a = result_a.sector_times[i] if hasattr(result_a, "sector_times") else result_a.total_time
        t_b = result_b.sector_times[i] if hasattr(result_b, "sector_times") else result_b.total_time
        delta_s = t_b - t_a
        
        mean_speed_diff = np.mean(speed_diff[mask]) if np.any(mask) else 0.0
        mean_curv = np.mean(np.abs(result_a.curvatures[mask])) if np.any(mask) else 0.0
        min_long_g = np.min(result_a.longitudinal_g[mask]) if np.any(mask) else 0.0
        max_long_g = np.max(result_a.longitudinal_g[mask]) if np.any(mask) else 0.0
        
        category = TimeLossCategory.MIXED
        confidence = CausalConfidence.UNCERTAIN
        evidence = [f"Mean speed diff: {mean_speed_diff * 3.6:+.1f} km/h"]
        
        if mean_curv > 0.015:
            category = TimeLossCategory.CORNER_SPEED
            confidence = CausalConfidence.LIKELY
            evidence.append("High average curvature indicates corner-dominated sector")
        elif min_long_g < -1.0 and abs(np.min(long_g_b_interp[mask]) - min_long_g) > 0.1:
            category = TimeLossCategory.BRAKING
            confidence = CausalConfidence.LIKELY
            evidence.append(f"Peak decel diff: {np.min(long_g_b_interp[mask]) - min_long_g:+.2f}g")
        elif max_long_g > 0.5:
            category = TimeLossCategory.ACCELERATION
            confidence = CausalConfidence.CORRELATED
            evidence.append("Acceleration-heavy sector")
        else:
            category = TimeLossCategory.STRAIGHT_SPEED
            confidence = CausalConfidence.LIKELY
            evidence.append("Low curvature indicates straight-line dominance")

        sector_deltas.append(
            SectorDelta(
                sector_id=i + 1,
                time_a_s=t_a,
                time_b_s=t_b,
                delta_s=delta_s,
                primary_category=category,
                contributing_factors=[],
                confidence=confidence,
                evidence=evidence
            )
        )
        
        summary_lines.append(
            f"Sector {i + 1}: {delta_s:+.2f}s — Main driver: {category.name} ({confidence.name})"
        )
        for ev in evidence:
            summary_lines.append(f"  Evidence: {ev}")
        summary_lines.append("")

    # 5. Zone analysis
    zone_deltas: List[ZoneDelta] = []
    significant_diff = np.abs(speed_diff) > 0.5
    zone_starts = np.where(significant_diff & ~np.roll(significant_diff, 1))[0]
    zone_ends = np.where(significant_diff & ~np.roll(significant_diff, -1))[0]
    
    for start_idx, end_idx in zip(zone_starts, zone_ends):
        if end_idx <= start_idx:
            continue
            
        z_mask = slice(start_idx, end_idx + 1)
        z_dist_start = dist_a[start_idx]
        z_dist_end = dist_a[end_idx]
        
        if (z_dist_end - z_dist_start) < 10.0:
            continue
            
        z_delta_time = cumulative_delta_time[end_idx] - cumulative_delta_time[start_idx]
        z_mean_speed_diff = np.mean(speed_diff[z_mask])
        z_mean_curv = np.mean(np.abs(result_a.curvatures[z_mask]))
        z_mean_long_g = np.mean(result_a.longitudinal_g[z_mask])
        
        z_type = "straight"
        z_cat = TimeLossCategory.STRAIGHT_SPEED
        if z_mean_curv > 0.01:
            z_type = "corner"
            z_cat = TimeLossCategory.CORNER_SPEED
        elif z_mean_long_g < -0.3:
            z_type = "braking"
            z_cat = TimeLossCategory.BRAKING
        elif z_mean_long_g > 0.3:
            z_type = "acceleration"
            z_cat = TimeLossCategory.ACCELERATION
            
        zone_deltas.append(
            ZoneDelta(
                zone_type=z_type,
                start_distance_m=z_dist_start,
                end_distance_m=z_dist_end,
                delta_time_s=z_delta_time,
                delta_speed_mean_mps=z_mean_speed_diff,
                primary_category=z_cat,
                detail=f"Mean speed difference of {z_mean_speed_diff*3.6:+.1f} km/h in {z_type} zone"
            )
        )

    # 6. Corner comparison
    corner_comparisons = []
    if corners_a is not None and corners_b is not None:
        try:
            from suspensionlab.physics.corner_analysis import compare_corners
            corner_comparisons = compare_corners(corners_a, corners_b)
        except ImportError:
            pass

    model_assumptions_caveat = (
        'This analysis is based on a quasi-steady-state vehicle model. '
        'Attributions reflect model-supported sensitivity mechanisms, not real-vehicle causal proof. '
        'A single-parameter change with MODEL-SUPPORTED confidence is the strongest isolated simulation attribution. '
        'Multi-parameter interactions reduce attribution confidence to LIKELY or CORRELATED. '
        'Empirical validation requires qualifying on-track telemetry.'
    )

    return LapDeltaReport(
        total_delta_s=result_b.total_time - result_a.total_time,
        sector_deltas=sector_deltas,
        zone_deltas=zone_deltas,
        corner_comparisons=corner_comparisons,
        cumulative_delta_distance=dist_a,
        cumulative_delta_time=cumulative_delta_time,
        speed_diff=speed_diff,
        summary="\n".join(summary_lines).strip(),
        model_assumptions_caveat=model_assumptions_caveat,
    )


def format_engineering_report(delta: LapDeltaReport) -> str:
    """
    Formats the LapDeltaReport into a clean engineering text report.

    Args:
        delta: The computed lap delta report.

    Returns:
        A formatted multi-line string suitable for a race debrief.
    """
    lines = [
        "==================================================",
        "          LAP DELTA ENGINEERING REPORT            ",
        "==================================================",
        f"Lap Time Delta: {delta.total_delta_s:+.3f}s",
        "--------------------------------------------------",
        "SECTOR BREAKDOWN:",
    ]

    for sd in delta.sector_deltas:
        lines.append(
            f"Sector {sd.sector_id}: {sd.delta_s:+.3f}s — "
            f"Primary Driver: {sd.primary_category.value} ({sd.confidence.value})"
        )
        for ev in sd.evidence:
            lines.append(f"  * {ev}")
        lines.append("")

    lines.append("--------------------------------------------------")
    lines.append("NOTABLE PERFORMANCE ZONES:")
    
    sorted_zones = sorted(delta.zone_deltas, key=lambda z: abs(z.delta_time_s), reverse=True)
    for i, zd in enumerate(sorted_zones[:5]):
        lines.append(
            f"Zone {i+1} ({zd.zone_type.capitalize()}): {zd.start_distance_m:.1f}m - {zd.end_distance_m:.1f}m"
        )
        lines.append(f"  Time Impact: {zd.delta_time_s:+.3f}s")
        lines.append(f"  Speed Diff:  {zd.delta_speed_mean_mps * 3.6:+.1f} km/h")
        lines.append(f"  Analysis:    {zd.detail}")
        lines.append("")

    lines.append("==================================================")
    lines.append("CAVEATS & ASSUMPTIONS:")
    lines.append(delta.model_assumptions_caveat)
    lines.append("==================================================")

    return "\n".join(lines)
