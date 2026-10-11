"""
physics/semantic_overlays.py
============================
SuspensionLab PRO — Engineering Chart Semantic Overlays

Generates semantic contextual bands and quadrant classifications for vehicle dynamics charts:
1. Damper Velocity Quadrants:
   - Low-speed compression  (0 to +50 mm/s)
   - High-speed compression (> +50 mm/s)
   - Low-speed rebound      (-50 to 0 mm/s)
   - High-speed rebound      (< -50 mm/s)

2. Cornering Phase Segmentation:
   - Straight
   - Braking zone
   - Turn-in / Entry
   - Apex / Mid-corner
   - Corner exit / Acceleration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class DamperQuadrant(str, Enum):
    LOW_SPEED_COMPRESSION = "Low-Speed Compression (0-50 mm/s)"
    HIGH_SPEED_COMPRESSION = "High-Speed Compression (>50 mm/s)"
    LOW_SPEED_REBOUND = "Low-Speed Rebound (-50-0 mm/s)"
    HIGH_SPEED_REBOUND = "High-Speed Rebound (<-50 mm/s)"


class CornerPhase(str, Enum):
    STRAIGHT = "Straight"
    BRAKING = "Braking"
    ENTRY = "Corner Entry / Turn-In"
    APEX = "Mid-Corner / Apex"
    EXIT = "Corner Exit / Traction"


@dataclass
class DamperQuadrantDistribution:
    """Statistical distribution of damper velocities across 4 operational quadrants."""
    low_speed_comp_pct: float
    high_speed_comp_pct: float
    low_speed_reb_pct: float
    high_speed_reb_pct: float
    knee_velocity_m_s: float = 0.050   # 50 mm/s standard blow-off knee

    def to_dict(self) -> Dict[str, float]:
        return {
            "low_speed_compression_pct": round(self.low_speed_comp_pct, 1),
            "high_speed_compression_pct": round(self.high_speed_comp_pct, 1),
            "low_speed_rebound_pct": round(self.low_speed_reb_pct, 1),
            "high_speed_rebound_pct": round(self.high_speed_reb_pct, 1),
            "knee_velocity_mm_s": self.knee_velocity_m_s * 1000.0,
        }


@dataclass
class PhaseOverlayBand:
    """Continuous track segment tagged with its dynamic cornering phase."""
    phase: CornerPhase
    start_distance_m: float
    end_distance_m: float
    start_time_s: float
    end_time_s: float
    mean_speed_kmh: float
    peak_lat_g: float
    color_hex: str


def compute_damper_distribution(
    damper_velocities_m_s: np.ndarray | List[float],
    knee_velocity_m_s: float = 0.050,
) -> DamperQuadrantDistribution:
    """Compute percentage of operating time spent in each damper quadrant."""
    v = np.asarray(damper_velocities_m_s, dtype=np.float64)
    total = len(v)
    if total == 0:
        return DamperQuadrantDistribution(25.0, 25.0, 25.0, 25.0, knee_velocity_m_s)

    v_knee = knee_velocity_m_s

    ls_comp = np.sum((v > 0.0) & (v <= v_knee)) / total * 100.0
    hs_comp = np.sum(v > v_knee) / total * 100.0
    ls_reb = np.sum((v < 0.0) & (v >= -v_knee)) / total * 100.0
    hs_reb = np.sum(v < -v_knee) / total * 100.0

    return DamperQuadrantDistribution(
        low_speed_comp_pct=float(ls_comp),
        high_speed_comp_pct=float(hs_comp),
        low_speed_reb_pct=float(ls_reb),
        high_speed_reb_pct=float(hs_reb),
        knee_velocity_m_s=knee_velocity_m_s,
    )


def segment_corner_phases(
    distances: np.ndarray | List[float],
    speeds_m_s: np.ndarray | List[float],
    ax_g: np.ndarray | List[float],
    ay_g: np.ndarray | List[float],
    dt: float = 0.01,
) -> List[PhaseOverlayBand]:
    """Segment a lap into semantic driving phase overlay bands."""
    dist = np.asarray(distances, dtype=np.float64)
    spd = np.asarray(speeds_m_s, dtype=np.float64)
    ax = np.asarray(ax_g, dtype=np.float64)
    ay = np.asarray(ay_g, dtype=np.float64)
    n = len(dist)

    if n < 2:
        return []

    # Assign phase per sample
    raw_phases: List[CornerPhase] = []
    for i in range(n):
        a_x = ax[i]
        a_y_mag = abs(ay[i])

        if a_x < -0.35 and a_y_mag < 0.5:
            raw_phases.append(CornerPhase.BRAKING)
        elif a_y_mag > 0.8:
            if a_x < -0.1:
                raw_phases.append(CornerPhase.ENTRY)
            elif a_x > 0.15:
                raw_phases.append(CornerPhase.EXIT)
            else:
                raw_phases.append(CornerPhase.APEX)
        elif a_x > 0.25 and a_y_mag < 0.6:
            raw_phases.append(CornerPhase.EXIT)
        else:
            raw_phases.append(CornerPhase.STRAIGHT)

    # Group contiguous blocks
    colors = {
        CornerPhase.STRAIGHT: "#4B5563",
        CornerPhase.BRAKING: "#EF4444",
        CornerPhase.ENTRY: "#F59E0B",
        CornerPhase.APEX: "#8B5CF6",
        CornerPhase.EXIT: "#10B981",
    }

    bands: List[PhaseOverlayBand] = []
    current_phase = raw_phases[0]
    start_idx = 0

    for i in range(1, n):
        if raw_phases[i] != current_phase or i == n - 1:
            end_idx = i
            sub_spd = spd[start_idx:end_idx + 1]
            sub_ay = ay[start_idx:end_idx + 1]

            bands.append(
                PhaseOverlayBand(
                    phase=current_phase,
                    start_distance_m=float(dist[start_idx]),
                    end_distance_m=float(dist[end_idx]),
                    start_time_s=float(start_idx * dt),
                    end_time_s=float(end_idx * dt),
                    mean_speed_kmh=float(np.mean(sub_spd) * 3.6),
                    peak_lat_g=float(np.max(np.abs(sub_ay))),
                    color_hex=colors[current_phase],
                )
            )
            current_phase = raw_phases[i]
            start_idx = i

    return bands
