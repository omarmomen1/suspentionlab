"""
physics/telemetry_parser.py
============================
SuspensionLab PRO — Motorsport Telemetry Parser

Parses generic telemetry CSV files from common DAQ systems:
    - AiM (RaceStudio 3 / RS3Analysis CSV export)
    - MoTeC i2 Pro (CSV export)
    - Pi System / Cosworth ICD / Bosch
    - Generic CSV (column-header based)

Channel Identification
----------------------
Automatically maps 40+ common channel aliases to standardised keys.
For each identified channel reports:
    - Standardised key
    - Raw column name
    - Confidence score (0–1)
    - Inferred units
    - Data quality warnings

Lap Segmentation
----------------
Identifies lap phases using speed and G thresholds:
    - Straight (high speed, low lat G)
    - Braking zone (negative long G, decelerating)
    - Corner entry (lat G rising)
    - Mid-corner (lat G peak)
    - Corner exit (lat G falling, throttle applied)
    - Kerb (high-frequency wheel load variation)

References
----------
- Segers, J. "Analysis Techniques for Racecar Data Acquisition", SAE.
- MoTeC i2 Pro Documentation, MoTeC Pty Ltd.
- AiM RaceStudio 3 User Manual.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Channel Alias Map — routed directly to canonical telemetry dataset ontology
# (Rule 21 & Step 3 Single Source of Truth)
# ─────────────────────────────────────────────────────────────────────────────
from suspensionlab.physics.telemetry_dataset import (
    _UNIVERSAL_ONTOLOGY_MAP,
    resolve_channel_mapping,
)

# Format: {alias_substring: (standard_key, inferred_unit)}
# Derived directly from canonical telemetry dataset ontology rules
_CHANNEL_ALIAS_MAP: list[tuple[str, str, str]] = [
    (entry[0], entry[1], entry[2]) for entry in _UNIVERSAL_ONTOLOGY_MAP
]


@dataclass
class ChannelInfo:
    """Metadata for an identified telemetry channel."""
    standard_key: str     # Standardised key (e.g. 'lat_g')
    raw_name:     str     # Original column name as-found in file
    column_index: int     # 0-based column index in the CSV
    inferred_unit: str    # Inferred physical unit
    confidence:   float   # 0.0–1.0 match confidence
    warnings:     list[str] = field(default_factory=list)


@dataclass
class TelemetryChannel:
    """Canonical channel ontology for motorsport & automotive data acquisition."""
    canonical_name: str          # e.g. "steering_angle", "damper_pos_fl", "speed"
    source_name: str             # Raw name from MoTeC / AiM / CSV column
    unit: str                    # e.g. "deg", "mm", "m/s"
    scale: float = 1.0           # Conversion multiplier
    offset: float = 0.0          # Conversion offset
    sampling_rate_hz: float = 100.0
    quality_score: float = 1.0   # 0-1 based on noise and dropouts
    data: np.ndarray = field(default_factory=lambda: np.zeros(0))


@dataclass
class VehicleSessionMetadata:
    """Vehicle-engineering aware session metadata."""
    vehicle_id: str = "Unknown"
    driver: str = "Unknown"
    track: str = "Unknown"
    session_type: str = "Practice"
    date_iso: str = ""
    timezone: str = "UTC"
    tire_compound: str = "Slick"
    setup_identifier: str = "Base"
    weather_ambient_c: float = 20.0
    track_temp_c: float = 30.0
    coordinate_convention: str = "ISO 8855 (X-Forward, Y-Left, Z-Up)"



@dataclass
class TelemetryQA:
    """Data quality metrics for a parsed telemetry session."""
    n_samples:          int
    duration_s:         float
    sample_rate_hz:     float
    channels_found:     list[str]       # Standard keys of identified channels
    channels_missing:   list[str]       # Standard keys NOT found
    dead_channels:      list[str]       # Channels with near-zero variance
    dropout_intervals:  list[tuple[float, float]]  # (t_start, t_end) [s]
    rate_mismatch_pct:  float           # % deviation from median sample rate
    total_warnings:     int


@dataclass
class LapSegment:
    """A classified phase of a lap."""
    label:    str    # 'straight', 'braking', 'corner_entry', 'mid_corner', 'corner_exit', 'kerb'
    t_start:  float  # [s]
    t_end:    float  # [s]
    i_start:  int    # sample index
    i_end:    int    # sample index
    peak_lat_g:   float = 0.0
    peak_long_g:  float = 0.0
    peak_speed:   float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Channel identification
# ─────────────────────────────────────────────────────────────────────────────

def identify_channels(headers: list[str]) -> dict[str, ChannelInfo]:
    """Map raw CSV header names to standardised channel keys.

    Parameters
    ----------
    headers : list[str]
        Raw column headers from the CSV file.

    Returns
    -------
    dict[str, ChannelInfo]
        Keys are standardised channel keys; values are ChannelInfo.
        Only one column is mapped per standard key (first/best match wins).
    """
    identified: dict[str, ChannelInfo] = {}

    for col_idx, raw_name in enumerate(headers):
        h_lower = raw_name.strip().lower()
        for alias, std_key, unit in _CHANNEL_ALIAS_MAP:
            if alias in h_lower:
                if std_key not in identified:  # first match wins
                    # Confidence: 1.0 for exact match, 0.75 for substring
                    confidence = 1.0 if h_lower == alias else 0.75
                    identified[std_key] = ChannelInfo(
                        standard_key=std_key,
                        raw_name=raw_name.strip(),
                        column_index=col_idx,
                        inferred_unit=unit,
                        confidence=confidence,
                    )
                break

    return identified


@dataclass
class IngestionAuditTrail:
    """Complete audit record of the ingestion pipeline."""
    raw_lines_count: int
    header_line_index: int
    raw_headers: list[str]
    identified_channels: list[str]
    rejected_channels: list[str]
    total_parsed_rows: int
    rejected_rows_count: int
    duplicate_timestamps_count: int
    non_monotonic_timestamps_count: int
    sample_rate_hz: float
    modifications: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    missing_channels: list[str] = field(default_factory=list)
    unit_mappings: dict[str, str] = field(default_factory=dict)
    alignment_operations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_lines_count": self.raw_lines_count,
            "header_line_index": self.header_line_index,
            "raw_headers": self.raw_headers,
            "identified_channels": self.identified_channels,
            "rejected_channels": self.rejected_channels,
            "total_parsed_rows": self.total_parsed_rows,
            "rejected_rows_count": self.rejected_rows_count,
            "duplicate_timestamps_count": self.duplicate_timestamps_count,
            "non_monotonic_timestamps_count": self.non_monotonic_timestamps_count,
            "sample_rate_hz": round(self.sample_rate_hz, 2),
            "modifications": self.modifications,
            "rejections": self.rejections,
            "missing_channels": self.missing_channels,
            "unit_mappings": self.unit_mappings,
            "alignment_operations": self.alignment_operations,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Core CSV parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_telemetry_csv(content: str) -> dict:
    """
    Parse generic telemetry CSV files (AiM, MoTeC, Pi, generic).

    Attempts to:
    1. Find the header row (first row containing 'time' or 'sec' within first 30 lines)
    2. Identify all known channels
    3. Parse numeric data for all identified channels
    4. Audit all ingested rows, non-numeric values, duplicates, and unit transformations.
       Never silently repair corrupt data or convert missing telemetry to zero.

    Parameters
    ----------
    content : str  Raw CSV file content.

    Returns
    -------
    dict with keys matching standardised channel names → list[float].
    Also includes:
      - '_channel_info': dict[str, ChannelInfo]
      - '_audit_trail': dict (IngestionAuditTrail serialized)
    """
    lines = content.splitlines()
    if not lines or all(not l.strip() for l in lines):
        raise ValueError("Telemetry CSV content cannot be empty.")

    # Find header row
    header_idx = 0
    header_found = False
    for i, line in enumerate(lines[:30]):
        line_lower = line.lower()
        if 'time' in line_lower or 'sec' in line_lower or 'speed' in line_lower or 'lat' in line_lower:
            header_idx = i
            header_found = True
            break

    raw_header_line = lines[header_idx] if header_found else lines[0]
    headers = [h.strip() for h in raw_header_line.split(',')]
    channel_map = identify_channels(headers)

    identified_keys = [info.standard_key for info in channel_map.values()]
    identified_raw_names = set(info.raw_name for info in channel_map.values())
    rejected_raw_headers = [h for h in headers if h and h not in identified_raw_names]

    # Initialise data arrays
    data: dict[str, list[float]] = {k: [] for k in channel_map}
    col_to_key = {info.column_index: key for key, info in channel_map.items()}

    skipped_counts: dict[str, int] = {}
    rejections_log: list[str] = []
    modifications_log: list[str] = []
    unit_mappings = {info.standard_key: info.inferred_unit for info in channel_map.values()}

    duplicate_ts_count = 0
    non_monotonic_ts_count = 0
    prev_time = None
    row_num = header_idx + 1
    total_parsed = 0

    reader = csv.reader(lines[header_idx + 1:])
    for row in reader:
        row_num += 1
        if not row or all(not c.strip() for c in row) or row[0].strip().startswith('#'):
            continue
        total_parsed += 1

        for col_idx, key in col_to_key.items():
            if col_idx < len(row):
                val_str = row[col_idx].strip()
                try:
                    num_val = float(val_str)
                    data[key].append(num_val)
                except (ValueError, IndexError):
                    data[key].append(float('nan'))
                    skipped_counts[key] = skipped_counts.get(key, 0) + 1
                    if len(rejections_log) < 50:
                        rejections_log.append(f"Row {row_num}: non-numeric value '{val_str}' in channel '{key}' preserved as NaN (not zeroed).")
            else:
                data[key].append(float('nan'))
                skipped_counts[key] = skipped_counts.get(key, 0) + 1
                if len(rejections_log) < 50:
                    rejections_log.append(f"Row {row_num}: missing column for channel '{key}' preserved as NaN.")

        # Timestamp audit
        if "time" in data and len(data["time"]) > 0:
            curr_t = data["time"][-1]
            if math.isfinite(curr_t):
                if prev_time is not None:
                    if curr_t == prev_time:
                        duplicate_ts_count += 1
                        if len(rejections_log) < 50:
                            rejections_log.append(f"Row {row_num}: duplicate timestamp t={curr_t:.4f}s detected.")
                    elif curr_t < prev_time:
                        non_monotonic_ts_count += 1
                        if len(rejections_log) < 50:
                            rejections_log.append(f"Row {row_num}: non-monotonic timestamp reversal t={curr_t:.4f}s < {prev_time:.4f}s.")
                prev_time = curr_t

    # Sample rate estimation
    sample_rate_hz = 0.0
    if "time" in data and len(data["time"]) > 1:
        t_arr = np.asarray([t for t in data["time"] if math.isfinite(t)], dtype=float)
        if len(t_arr) > 1:
            dt = np.diff(t_arr)
            pos_dt = dt[dt > 1e-7]
            if len(pos_dt) > 0:
                sample_rate_hz = float(1.0 / np.median(pos_dt))

    # Unit transformations documentation
    for key, info in channel_map.items():
        if info.inferred_unit:
            modifications_log.append(f"Channel '{key}' mapped from raw '{info.raw_name}' with unit '{info.inferred_unit}' (confidence: {info.confidence:.2f}).")

    missing_core = [c for c in ["time", "speed", "lat_g", "long_g"] if c not in data]
    total_skipped = sum(skipped_counts.values())

    audit = IngestionAuditTrail(
        raw_lines_count=len(lines),
        header_line_index=header_idx,
        raw_headers=headers,
        identified_channels=identified_keys,
        rejected_channels=rejected_raw_headers,
        total_parsed_rows=total_parsed,
        rejected_rows_count=total_skipped,
        duplicate_timestamps_count=duplicate_ts_count,
        non_monotonic_timestamps_count=non_monotonic_ts_count,
        sample_rate_hz=sample_rate_hz,
        modifications=modifications_log,
        rejections=rejections_log,
        missing_channels=missing_core,
        unit_mappings=unit_mappings,
        alignment_operations=[],
    )

    data['_channel_info'] = channel_map  # type: ignore[assignment]
    data['_audit_trail'] = audit.to_dict()  # type: ignore[assignment]
    return data


def normalize_to_100hz(data: dict[str, list[float]]) -> dict[str, list[float]]:
    """
    Resample all continuous telemetry channels onto a strictly uniform 100 Hz time grid (dt = 0.01s).
    Preserves NaN handling and row alignment across all channels.
    Documents resampling and alignment transformations in _audit_trail.
    """
    if "time" not in data or len(data["time"]) < 2:
        return data

    t_raw = np.asarray(data["time"], dtype=np.float64)
    valid_t_mask = np.isfinite(t_raw)
    if np.sum(valid_t_mask) < 2:
        return data

    # Strictly filter monotonic unique timestamps for interpolation
    t_valid_indices = np.where(valid_t_mask)[0]
    t_valid = t_raw[t_valid_indices]
    
    # Filter duplicate timestamps
    strict_monotonic_mask = np.diff(t_valid, prepend=t_valid[0] - 1.0) > 1e-7
    t_clean = t_valid[strict_monotonic_mask]
    clean_indices = t_valid_indices[strict_monotonic_mask]

    if len(t_clean) < 2:
        return data

    t_start, t_end = t_clean[0], t_clean[-1]
    if t_end <= t_start:
        return data

    # Strict 100 Hz grid
    t_100hz = np.arange(t_start, t_end + 1e-7, 0.01)
    resampled: dict[str, list[float]] = {"time": t_100hz.tolist()}

    for k, v in data.items():
        if k == "time" or k.startswith("_"):
            continue
        v_arr = np.asarray(v, dtype=np.float64)
        if len(v_arr) != len(t_raw):
            continue

        v_clean = v_arr[clean_indices]
        valid_val_mask = np.isfinite(v_clean)

        if np.sum(valid_val_mask) >= 2:
            interpolated = np.interp(t_100hz, t_clean[valid_val_mask], v_clean[valid_val_mask])
            resampled[k] = interpolated.tolist()
        else:
            resampled[k] = np.full(len(t_100hz), np.nan).tolist()

    if "_channel_info" in data:
        resampled["_channel_info"] = data["_channel_info"]
    if "_audit_trail" in data:
        resampled["_audit_trail"] = dict(data["_audit_trail"])
        resampled["_audit_trail"].setdefault("alignment_operations", []).append(
            f"Resampled channels to uniform 100 Hz grid ({len(t_100hz)} points, t=[{t_start:.2f}s, {t_end:.2f}s])"
        )

    return resampled



# ─────────────────────────────────────────────────────────────────────────────
# Data Quality Assessment
# ─────────────────────────────────────────────────────────────────────────────

def validate_channels(
    data: dict,
    expected_channels: list[str] | None = None,
) -> TelemetryQA:
    """Assess data quality for a parsed telemetry session.

    Detects:
    - Dead channels (variance < 1% of mean absolute)
    - Dropout intervals (gaps > 5 × median dt)
    - Sample-rate mismatch
    - Missing expected channels

    Parameters
    ----------
    data : dict                Parsed data from parse_telemetry_csv()
    expected_channels : list   Keys expected to be present (default: core set)

    Returns
    -------
    TelemetryQA
    """
    if expected_channels is None:
        expected_channels = ["time", "speed", "lat_g", "long_g", "yaw_rate"]

    time_arr = np.asarray(data.get("time", []), dtype=float)
    n_samples = len(time_arr)
    duration_s = float(time_arr[-1] - time_arr[0]) if n_samples > 1 else 0.0

    # Sample rate
    if n_samples > 1:
        dt_arr = np.diff(time_arr)
        median_dt = float(np.median(dt_arr))
        sample_rate_hz = 1.0 / median_dt if median_dt > 1e-9 else 0.0
        dt_std = float(np.std(dt_arr))
        rate_mismatch_pct = 100.0 * dt_std / median_dt if median_dt > 1e-9 else 0.0
    else:
        sample_rate_hz = 0.0
        rate_mismatch_pct = 0.0
        median_dt = 0.0

    channels_found = [k for k in data if not k.startswith('_') and len(data[k]) > 0]
    channels_missing = [k for k in expected_channels if k not in channels_found]

    # Dead channel detection
    dead_channels = []
    for key in channels_found:
        arr = np.asarray(data[key], dtype=float)
        if len(arr) < 2:
            continue
        mean_abs = float(np.mean(np.abs(arr)))
        std_val  = float(np.std(arr))
        # Dead if std < 1% of mean absolute (or constant)
        if mean_abs > 1e-6 and std_val / mean_abs < 0.01:
            dead_channels.append(key)
        elif std_val < 1e-9:
            dead_channels.append(key)

    # Dropout detection (gaps > 5 × median_dt)
    dropout_intervals: list[tuple[float, float]] = []
    if n_samples > 1 and median_dt > 0:
        gap_threshold = 5.0 * median_dt
        gap_indices = np.where(dt_arr > gap_threshold)[0]
        for gi in gap_indices:
            dropout_intervals.append((float(time_arr[gi]), float(time_arr[gi + 1])))

    total_warnings = len(dead_channels) + len(dropout_intervals) + len(channels_missing)

    return TelemetryQA(
        n_samples=n_samples,
        duration_s=duration_s,
        sample_rate_hz=round(sample_rate_hz, 1),
        channels_found=channels_found,
        channels_missing=channels_missing,
        dead_channels=dead_channels,
        dropout_intervals=dropout_intervals,
        rate_mismatch_pct=round(rate_mismatch_pct, 2),
        total_warnings=total_warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Lap Segmentation
# ─────────────────────────────────────────────────────────────────────────────

def segment_lap(
    data: dict,
    speed_straight_thresh: float = 15.0,   # m/s
    lat_g_corner_thresh:   float = 0.4,    # G
    long_g_brake_thresh:   float = -0.3,   # G (negative = deceleration)
    min_segment_duration:  float = 0.3,    # s
) -> list[LapSegment]:
    """Segment a telemetry session into lap phases.

    Classification rules (in priority order):
    1. lat_g > threshold AND speed > threshold → corner
       - Within corner: rising lat_g → entry; peak → mid; falling → exit
    2. long_g < brake_threshold AND speed > threshold → braking zone
    3. Otherwise → straight

    Parameters
    ----------
    data : dict  Parsed telemetry data
    speed_straight_thresh : float  Speed above which we're not in a corner [m/s]
    lat_g_corner_thresh   : float  |lat_g| above which we're cornering [G]
    long_g_brake_thresh   : float  long_g below which we're braking [G]
    min_segment_duration  : float  Minimum segment duration to keep [s]

    Returns
    -------
    list[LapSegment]
    """
    time_arr  = np.asarray(data.get("time",   []), dtype=float)
    speed_arr = np.asarray(data.get("speed",  []), dtype=float)
    lat_g_arr = np.asarray(data.get("lat_g",  []), dtype=float)

    if len(time_arr) < 10 or len(speed_arr) < 10 or len(lat_g_arr) < 10:
        return []

    n = min(len(time_arr), len(speed_arr), len(lat_g_arr))
    time_arr  = time_arr[:n]
    speed_arr = speed_arr[:n]
    lat_g_arr = lat_g_arr[:n]

    long_g_raw = data.get("long_g")
    if long_g_raw is not None and len(long_g_raw) >= n:
        long_g_arr = np.asarray(long_g_raw[:n], dtype=float)
    elif len(speed_arr) > 1:
        dt = np.diff(time_arr)
        valid_dt = np.where(dt > 1e-4, dt, 0.01)
        long_g_arr = np.zeros(n)
        long_g_arr[:-1] = np.diff(speed_arr) / (valid_dt * 9.81)
        long_g_arr[-1] = long_g_arr[-2] if n > 1 else 0.0
    else:
        long_g_arr = np.zeros(n)

    abs_lat_g = np.abs(lat_g_arr)

    # State classification per sample
    # 0=straight, 1=braking, 2=corner_entry, 3=mid_corner, 4=corner_exit
    labels = np.full(n, "straight", dtype=object)

    in_corner = abs_lat_g > lat_g_corner_thresh
    braking   = (long_g_arr < long_g_brake_thresh) & ~in_corner

    labels[braking] = "braking"
    labels[in_corner] = "mid_corner"  # default; refine below

    # Refine corner phases using gradient of lat_g
    d_lat_g = np.gradient(abs_lat_g)
    labels[in_corner & (d_lat_g > 0.01)]  = "corner_entry"
    labels[in_corner & (d_lat_g < -0.01)] = "corner_exit"

    # Build segments from run-length encoding
    segments: list[LapSegment] = []
    i = 0
    while i < n:
        current_label = labels[i]
        j = i + 1
        while j < n and labels[j] == current_label:
            j += 1
        t_start = float(time_arr[i])
        t_end   = float(time_arr[j - 1])
        if (t_end - t_start) >= min_segment_duration:
            segments.append(LapSegment(
                label=str(current_label),
                t_start=t_start,
                t_end=t_end,
                i_start=i,
                i_end=j - 1,
                peak_lat_g=float(np.max(abs_lat_g[i:j])),
                peak_long_g=float(np.min(long_g_arr[i:j])),
                peak_speed=float(np.max(speed_arr[i:j])),
            ))
        i = j

    return segments
