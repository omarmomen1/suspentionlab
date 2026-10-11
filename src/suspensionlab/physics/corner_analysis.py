from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any
import numpy as np


class TrackZone(enum.Enum):
    """Enumeration of track zones for lap analysis."""
    STRAIGHT = 1
    BRAKING_ZONE = 2
    CORNER_ENTRY = 3
    APEX = 4
    CORNER_EXIT = 5
    ACCELERATION_ZONE = 6


def classify_zones(
    distances: np.ndarray,
    speeds: np.ndarray,
    curvatures: np.ndarray,
    longitudinal_g: np.ndarray,
    *,
    curvature_threshold: float = 0.005,
    braking_g_threshold: float = -0.3
) -> np.ndarray:
    """
    Classify each station into a TrackZone.

    Args:
        distances: Cumulative distance array [m].
        speeds: Speed array [m/s].
        curvatures: Absolute curvature |κ| array [1/m].
        longitudinal_g: Longitudinal acceleration array [g].
        curvature_threshold: Threshold above which track is considered a corner [1/m].
        braking_g_threshold: Threshold below which track is considered braking [g].

    Returns:
        Integer array where values map to TrackZone enum values.
    """
    if not all(isinstance(a, np.ndarray) for a in (distances, speeds, curvatures, longitudinal_g)):
        raise TypeError("Inputs must be numpy arrays.")

    n = len(distances)
    zones = np.full(n, TrackZone.STRAIGHT.value, dtype=int)

    if n == 0:
        return zones

    # 1. Straight or Acceleration Zone
    straight_mask = (curvatures < curvature_threshold) & (longitudinal_g > braking_g_threshold)
    accel_mask = (longitudinal_g > 0.1) & (curvatures < curvature_threshold)

    # 2. Braking Zone
    braking_mask = (curvatures < curvature_threshold) & (longitudinal_g <= braking_g_threshold)

    zones[straight_mask] = TrackZone.STRAIGHT.value
    zones[accel_mask] = TrackZone.ACCELERATION_ZONE.value
    zones[braking_mask] = TrackZone.BRAKING_ZONE.value

    # 3. Corner phases
    corner_mask = curvatures >= curvature_threshold

    in_corner = False
    corner_start = 0

    for i in range(n):
        if corner_mask[i]:
            if not in_corner:
                in_corner = True
                corner_start = i
        else:
            if in_corner:
                _process_corner_region_zones(zones, speeds, corner_start, i)
                in_corner = False
                
    if in_corner:
        _process_corner_region_zones(zones, speeds, corner_start, n)

    return zones


def _process_corner_region_zones(zones: np.ndarray, speeds: np.ndarray, start: int, end: int) -> None:
    """Helper to classify stations within a contiguous corner region."""
    region_speeds = speeds[start:end]
    if len(region_speeds) == 0:
        return

    min_speed = np.min(region_speeds)
    min_speed_idx = np.argmin(region_speeds) + start
    apex_threshold = min_speed * 1.02

    for i in range(start, end):
        if speeds[i] <= apex_threshold:
            zones[i] = TrackZone.APEX.value
        elif i < min_speed_idx:
            zones[i] = TrackZone.CORNER_ENTRY.value
        else:
            zones[i] = TrackZone.CORNER_EXIT.value


@dataclass
class CornerMetrics:
    """Per-corner analysis metrics."""
    corner_id: int
    name: str
    sector_id: int
    entry_station: int
    apex_station: int
    exit_station: int
    entry_distance_m: float
    apex_distance_m: float
    exit_distance_m: float
    entry_speed_mps: float
    min_speed_mps: float
    exit_speed_mps: float
    braking_distance_m: float
    peak_lateral_g: float
    mean_lateral_g: float
    peak_longitudinal_g: float
    time_in_corner_s: float
    tire_utilization_peak: float
    tire_utilization_mean: float
    aero_downforce_at_entry_n: float
    aero_downforce_at_apex_n: float

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary representation with JSON-compliant nulls for NaN/inf."""
        def _clean(val: Any) -> Any:
            if isinstance(val, (float, np.floating)):
                if math.isnan(val) or math.isinf(val):
                    return None
                return float(val)
            return val

        return {
            "corner_id": self.corner_id,
            "name": self.name,
            "sector_id": self.sector_id,
            "entry_station": self.entry_station,
            "apex_station": self.apex_station,
            "exit_station": self.exit_station,
            "entry_distance_m": _clean(self.entry_distance_m),
            "apex_distance_m": _clean(self.apex_distance_m),
            "exit_distance_m": _clean(self.exit_distance_m),
            "entry_speed_mps": _clean(self.entry_speed_mps),
            "min_speed_mps": _clean(self.min_speed_mps),
            "exit_speed_mps": _clean(self.exit_speed_mps),
            "braking_distance_m": _clean(self.braking_distance_m),
            "peak_lateral_g": _clean(self.peak_lateral_g),
            "mean_lateral_g": _clean(self.mean_lateral_g),
            "peak_longitudinal_g": _clean(self.peak_longitudinal_g),
            "time_in_corner_s": _clean(self.time_in_corner_s),
            "tire_utilization_peak": _clean(self.tire_utilization_peak),
            "tire_utilization_mean": _clean(self.tire_utilization_mean),
            "aero_downforce_at_entry_n": _clean(self.aero_downforce_at_entry_n),
            "aero_downforce_at_apex_n": _clean(self.aero_downforce_at_apex_n),
        }


def detect_corners(
    distances: np.ndarray,
    speeds: np.ndarray,
    curvatures: np.ndarray,
    lateral_g: np.ndarray,
    longitudinal_g: np.ndarray,
    *,
    curvature_threshold: float = 0.005,
    min_corner_length_m: float = 10.0,
    sectors: np.ndarray | None = None,
    aero_downforce_n: np.ndarray | None = None,
    tire_utilization_combined: np.ndarray | None = None,
    dt: np.ndarray | None = None
) -> list[CornerMetrics]:
    """
    Detect corners from curvature and speed profiles.

    Args:
        distances: Cumulative distance array [m].
        speeds: Speed array [m/s].
        curvatures: Absolute curvature |κ| array [1/m].
        lateral_g: Lateral acceleration array [g].
        longitudinal_g: Longitudinal acceleration array [g].
        curvature_threshold: Minimum curvature to trigger corner detection [1/m].
        min_corner_length_m: Minimum length to qualify as a corner [m].
        sectors: Optional array mapping station to sector ID.
        aero_downforce_n: Optional aero downforce array [N].
        tire_utilization_combined: Optional tire utilization array [0-1].
        dt: Optional time step array for time calculation [s].

    Returns:
        List of CornerMetrics for each detected corner.
    """
    n = len(distances)
    if n == 0:
        return []

    # 1. Find contiguous regions where |κ| > curvature_threshold
    corner_mask = curvatures > curvature_threshold
    
    regions = []
    in_corner = False
    start_idx = 0

    for i in range(n):
        if corner_mask[i]:
            if not in_corner:
                in_corner = True
                start_idx = i
        else:
            if in_corner:
                regions.append([start_idx, i - 1])
                in_corner = False
                
    if in_corner:
        regions.append([start_idx, n - 1])

    if not regions:
        return []

    # 2. Merge regions separated by < 5m
    merged_regions = []
    current_region = regions[0]

    for i in range(1, len(regions)):
        next_region = regions[i]
        dist_between = distances[next_region[0]] - distances[current_region[1]]
        if dist_between < 5.0:
            # Merge
            current_region[1] = next_region[1]
        else:
            merged_regions.append(current_region)
            current_region = next_region
    merged_regions.append(current_region)

    corners = []
    corner_id = 1

    # 3. Process regions
    for entry, exit_station in merged_regions:
        length = distances[exit_station] - distances[entry]
        if length < min_corner_length_m:
            continue

        # 4. Find apex
        region_speeds = speeds[entry:exit_station + 1]
        apex_offset = int(np.argmin(region_speeds))
        apex_station = entry + apex_offset

        # Find braking initiation point (where long_g first goes negative before the corner)
        braking_start = entry
        for j in range(entry, -1, -1):
            if longitudinal_g[j] >= 0:
                braking_start = min(j + 1, entry)
                break
            if j == 0:
                braking_start = 0

        braking_distance_m = float(distances[entry] - distances[braking_start])

        # Sector ID
        sector_id = int(sectors[apex_station]) if sectors is not None else 1

        # Peak and mean lateral G
        region_lat_g = np.abs(lateral_g[entry:exit_station + 1])
        peak_lateral_g = float(np.max(region_lat_g))
        mean_lateral_g = float(np.mean(region_lat_g))

        # Peak longitudinal G (braking)
        region_long_g = longitudinal_g[braking_start:exit_station + 1]
        peak_longitudinal_g = float(np.min(region_long_g)) if len(region_long_g) > 0 else 0.0

        # Time in corner
        if dt is not None:
            time_in_corner_s = float(np.sum(dt[entry:exit_station + 1]))
        else:
            # Approximation if dt not provided
            mean_speed = np.mean(region_speeds)
            time_in_corner_s = float(length / mean_speed) if mean_speed > 0 else 0.0

        # Tire utilization
        tire_utilization_peak = float('nan')
        tire_utilization_mean = float('nan')
        if tire_utilization_combined is not None:
            region_tire = tire_utilization_combined[entry:exit_station + 1]
            tire_utilization_peak = float(np.max(region_tire))
            tire_utilization_mean = float(np.mean(region_tire))

        # Aero downforce
        aero_downforce_at_entry_n = float('nan')
        aero_downforce_at_apex_n = float('nan')
        if aero_downforce_n is not None:
            aero_downforce_at_entry_n = float(aero_downforce_n[entry])
            aero_downforce_at_apex_n = float(aero_downforce_n[apex_station])

        metric = CornerMetrics(
            corner_id=corner_id,
            name=f"Turn {corner_id}",
            sector_id=sector_id,
            entry_station=entry,
            apex_station=apex_station,
            exit_station=exit_station,
            entry_distance_m=float(distances[entry]),
            apex_distance_m=float(distances[apex_station]),
            exit_distance_m=float(distances[exit_station]),
            entry_speed_mps=float(speeds[entry]),
            min_speed_mps=float(speeds[apex_station]),
            exit_speed_mps=float(speeds[exit_station]),
            braking_distance_m=braking_distance_m,
            peak_lateral_g=peak_lateral_g,
            mean_lateral_g=mean_lateral_g,
            peak_longitudinal_g=peak_longitudinal_g,
            time_in_corner_s=time_in_corner_s,
            tire_utilization_peak=tire_utilization_peak,
            tire_utilization_mean=tire_utilization_mean,
            aero_downforce_at_entry_n=aero_downforce_at_entry_n,
            aero_downforce_at_apex_n=aero_downforce_at_apex_n
        )
        corners.append(metric)
        corner_id += 1

    return corners


@dataclass
class CornerComparison:
    """Result of comparing a corner between two laps or setups."""
    corner_id: int
    corner_name: str
    delta_entry_speed_mps: float
    delta_min_speed_mps: float
    delta_exit_speed_mps: float
    delta_braking_distance_m: float
    delta_time_s: float
    delta_peak_lateral_g: float
    likely_cause: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        """Convert comparison to dictionary representation with JSON-compliant nulls."""
        def _clean(val: Any) -> Any:
            if isinstance(val, (float, np.floating)):
                if math.isnan(val) or math.isinf(val):
                    return None
                return float(val)
            return val

        return {
            "corner_id": self.corner_id,
            "corner_name": self.corner_name,
            "delta_entry_speed_mps": _clean(self.delta_entry_speed_mps),
            "delta_min_speed_mps": _clean(self.delta_min_speed_mps),
            "delta_exit_speed_mps": _clean(self.delta_exit_speed_mps),
            "delta_braking_distance_m": _clean(self.delta_braking_distance_m),
            "delta_time_s": _clean(self.delta_time_s),
            "delta_peak_lateral_g": _clean(self.delta_peak_lateral_g),
            "likely_cause": self.likely_cause,
            "confidence": self.confidence,
        }


def compare_corners(corners_a: list[CornerMetrics], corners_b: list[CornerMetrics]) -> list[CornerComparison]:
    """
    Pairwise comparison between matched corners (by corner_id).
    
    Args:
        corners_a: Baseline corners.
        corners_b: Comparison corners (B - A).
        
    Returns:
        List of CornerComparison results.
    """
    comparisons = []
    
    # Create dictionary for quick lookup by ID
    dict_b = {c.corner_id: c for c in corners_b}
    
    for c_a in corners_a:
        if c_a.corner_id not in dict_b:
            continue
            
        c_b = dict_b[c_a.corner_id]
        
        # Calculate deltas (B - A)
        d_entry = c_b.entry_speed_mps - c_a.entry_speed_mps
        d_min = c_b.min_speed_mps - c_a.min_speed_mps
        d_exit = c_b.exit_speed_mps - c_a.exit_speed_mps
        d_brake_dist = c_b.braking_distance_m - c_a.braking_distance_m
        d_time = c_b.time_in_corner_s - c_a.time_in_corner_s
        d_lat_g = c_b.peak_lateral_g - c_a.peak_lateral_g
        
        # Heuristics for likely cause
        causes = []
        if d_min > 0.5:
            causes.append("Higher apex speed (more grip or lower entry speed)")
        if d_exit > 0.5:
            causes.append("Better corner exit traction")
        if d_brake_dist < -2.0:
            causes.append("Later braking point")
        if d_entry > 1.0:
            causes.append("Higher approach speed")
            
        likely_cause = " / ".join(causes) if causes else "Similar performance"
        
        # Confidence
        abs_d_time = abs(d_time)
        if abs_d_time > 0.1:
            confidence = "HIGH"
        elif abs_d_time > 0.02:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
            
        comp = CornerComparison(
            corner_id=c_a.corner_id,
            corner_name=c_a.name,
            delta_entry_speed_mps=d_entry,
            delta_min_speed_mps=d_min,
            delta_exit_speed_mps=d_exit,
            delta_braking_distance_m=d_brake_dist,
            delta_time_s=d_time,
            delta_peak_lateral_g=d_lat_g,
            likely_cause=likely_cause,
            confidence=confidence
        )
        comparisons.append(comp)
        
    return comparisons


def analyze_lap_corners(
    distances: np.ndarray,
    speeds: np.ndarray,
    curvatures: np.ndarray,
    lateral_g: np.ndarray,
    longitudinal_g: np.ndarray,
    dt: np.ndarray,
    aero_downforce_n: np.ndarray | None = None,
    tire_utilization_combined: np.ndarray | None = None,
    sectors: np.ndarray | None = None
) -> list[CornerMetrics]:
    """
    Convenience function that runs detect_corners with time computation.

    Args:
        distances: Cumulative distance array [m].
        speeds: Speed array [m/s].
        curvatures: Absolute curvature |κ| array [1/m].
        lateral_g: Lateral acceleration array [g].
        longitudinal_g: Longitudinal acceleration array [g].
        dt: Time step array [s].
        aero_downforce_n: Optional aero downforce array [N].
        tire_utilization_combined: Optional tire utilization array [0-1].
        sectors: Optional array mapping station to sector ID.

    Returns:
        List of CornerMetrics for the lap.
    """
    return detect_corners(
        distances=distances,
        speeds=speeds,
        curvatures=curvatures,
        lateral_g=lateral_g,
        longitudinal_g=longitudinal_g,
        dt=dt,
        aero_downforce_n=aero_downforce_n,
        tire_utilization_combined=tire_utilization_combined,
        sectors=sectors
    )
