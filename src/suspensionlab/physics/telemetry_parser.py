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
# Channel Alias Map — maps raw column names (lower-case, stripped) to
# standardised channel keys
# ─────────────────────────────────────────────────────────────────────────────

# Format: {alias_substring: (standard_key, inferred_unit)}
# Matching is case-insensitive, substring. First match wins.
_CHANNEL_ALIAS_MAP: list[tuple[str, str, str]] = [
    # Time / Distance
    ("time",          "time",         "s"),
    ("sec",           "time",         "s"),
    ("timestamp",     "time",         "s"),
    ("t_abs",         "time",         "s"),
    ("distance",      "distance",     "m"),
    ("dist",          "distance",     "m"),
    ("odometer",      "distance",     "m"),
    # Speed
    ("speed",         "speed",        "m/s"),
    ("v_x",           "speed",        "m/s"),
    ("vx",            "speed",        "m/s"),
    ("gps speed",     "speed",        "m/s"),
    ("ground speed",  "speed",        "m/s"),
    ("wheel speed fl","wsp_fl",       "m/s"),
    ("wheel speed fr","wsp_fr",       "m/s"),
    ("wheel speed rl","wsp_rl",       "m/s"),
    ("wheel speed rr","wsp_rr",       "m/s"),
    ("wsp_fl",        "wsp_fl",       "m/s"),
    ("wsp_fr",        "wsp_fr",       "m/s"),
    ("wsp_rl",        "wsp_rl",       "m/s"),
    ("wsp_rr",        "wsp_rr",       "m/s"),
    # Lateral / Longitudinal G
    ("latg",          "lat_g",        "G"),
    ("lat_g",         "lat_g",        "G"),
    ("lateral acc",   "lat_g",        "G"),
    ("lateral g",     "lat_g",        "G"),
    ("a_y",           "lat_g",        "G"),
    ("ay",            "lat_g",        "G"),
    ("g force lat",   "lat_g",        "G"),
    ("longg",         "long_g",       "G"),
    ("long_g",        "long_g",       "G"),
    ("longitudinal",  "long_g",       "G"),
    ("a_x",           "long_g",       "G"),
    ("ax",            "long_g",       "G"),
    ("g force long",  "long_g",       "G"),
    # Vertical G
    ("vert g",        "vert_g",       "G"),
    ("vertical acc",  "vert_g",       "G"),
    ("a_z",           "vert_g",       "G"),
    ("az",            "vert_g",       "G"),
    # Steering
    ("steering",      "steer_deg",    "deg"),
    ("steer",         "steer_deg",    "deg"),
    ("steer angle",   "steer_deg",    "deg"),
    # Yaw / Roll / Pitch rates
    ("yaw",           "yaw_rate",     "deg/s"),
    ("omega_z",       "yaw_rate",     "rad/s"),
    ("gyro z",        "yaw_rate",     "deg/s"),
    ("roll rate",     "roll_rate",    "deg/s"),
    ("pitch rate",    "pitch_rate",   "deg/s"),
    # Throttle / Brake
    ("throttle",      "throttle_pct", "%"),
    ("tps",           "throttle_pct", "%"),
    ("brake",         "brake_bar",    "bar"),
    ("brake pres",    "brake_bar",    "bar"),
    # Ride heights
    ("ride height fl","rh_fl",        "mm"),
    ("ride height fr","rh_fr",        "mm"),
    ("ride height rl","rh_rl",        "mm"),
    ("ride height rr","rh_rr",        "mm"),
    ("rh_fl",         "rh_fl",        "mm"),
    ("rh_fr",         "rh_fr",        "mm"),
    ("rh_rl",         "rh_rl",        "mm"),
    ("rh_rr",         "rh_rr",        "mm"),
    # Damper positions
    ("damper fl",     "damper_fl",    "mm"),
    ("damper fr",     "damper_fr",    "mm"),
    ("damper rl",     "damper_rl",    "mm"),
    ("damper rr",     "damper_rr",    "mm"),
    ("susp fl",       "damper_fl",    "mm"),
    ("susp fr",       "damper_fr",    "mm"),
    ("susp rl",       "damper_rl",    "mm"),
    ("susp rr",       "damper_rr",    "mm"),
    # GPS
    ("latitude",      "gps_lat",      "deg"),
    ("gps lat",       "gps_lat",      "deg"),
    ("longitude",     "gps_lon",      "deg"),
    ("gps lon",       "gps_lon",      "deg"),
    ("gps alt",       "gps_alt",      "m"),
    # Tire temperatures (FL/FR/RL/RR)
    ("tire temp fl",  "t_tire_fl",    "°C"),
    ("tire temp fr",  "t_tire_fr",    "°C"),
    ("tire temp rl",  "t_tire_rl",    "°C"),
    ("tire temp rr",  "t_tire_rr",    "°C"),
    ("tyre temp fl",  "t_tire_fl",    "°C"),
    ("tyre temp fr",  "t_tire_fr",    "°C"),
    ("tyre temp rl",  "t_tire_rl",    "°C"),
    ("tyre temp rr",  "t_tire_rr",    "°C"),
    # Tire pressures
    ("tire pres fl",  "p_tire_fl",    "bar"),
    ("tire pres fr",  "p_tire_fr",    "bar"),
    ("tire pres rl",  "p_tire_rl",    "bar"),
    ("tire pres rr",  "p_tire_rr",    "bar"),
    # Gear
    ("gear",          "gear",         "-"),
    ("n gear",        "gear",         "-"),
    # RPM / Engine
    ("rpm",           "rpm",          "rpm"),
    ("engine speed",  "rpm",          "rpm"),
    # Lap / Sector
    ("lap",           "lap_number",   "-"),
    ("sector",        "sector",       "-"),
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

    Parameters
    ----------
    content : str  Raw CSV file content.

    Returns
    -------
    dict with keys matching standardised channel names → list[float].
    Also includes '_channel_info': dict[str, ChannelInfo]
    """
    lines = content.splitlines()

    # Find header row
    header_idx = 0
    for i, line in enumerate(lines[:30]):
        line_lower = line.lower()
        if 'time' in line_lower or 'sec' in line_lower or 'speed' in line_lower:
            header_idx = i
            break

    headers = [h.strip() for h in lines[header_idx].split(',')]
    channel_map = identify_channels(headers)

    # Initialise data arrays
    data: dict[str, list[float]] = {k: [] for k in channel_map}
    col_to_key = {info.column_index: key for key, info in channel_map.items()}

    skipped_counts: dict[str, int] = {}
    reader = csv.reader(lines[header_idx + 1:])
    for row in reader:
        if not row or row[0].strip().startswith('#'):
            continue
        for col_idx, key in col_to_key.items():
            try:
                if col_idx < len(row):
                    val_str = row[col_idx].strip()
                    data[key].append(float(val_str))
            except (ValueError, IndexError):
                skipped_counts[key] = skipped_counts.get(key, 0) + 1

    total_skipped = sum(skipped_counts.values())
    if total_skipped:
        worst = dict(sorted(skipped_counts.items(), key=lambda kv: -kv[1])[:10])
        logger.warning(
            "Telemetry CSV parse: %d non-numeric/unreadable sample(s) skipped across %d channel(s). "
            "Worst channels: %s. Downstream QA may report gaps or dead channels.",
            total_skipped, len(skipped_counts), worst,
        )

    data['_channel_info'] = channel_map  # type: ignore[assignment]
    return data


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
    long_g_arr= np.asarray(data.get("long_g", []), dtype=float)

    n = min(len(time_arr), len(speed_arr), len(lat_g_arr), len(long_g_arr))
    if n < 10:
        return []

    time_arr  = time_arr[:n]
    speed_arr = speed_arr[:n]
    lat_g_arr = lat_g_arr[:n]
    long_g_arr= long_g_arr[:n]

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
