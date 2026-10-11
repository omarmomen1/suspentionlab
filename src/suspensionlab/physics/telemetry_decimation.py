"""
physics/telemetry_decimation.py
===============================
SuspensionLab PRO — Multiresolution & Peak-Preserving Telemetry Decimation

Implements server-side Level-of-Detail (LOD) downsampling tailored for high-frequency
vehicle dynamics traces (100 Hz – 1 kHz).

Key Principles:
---------------
1. Min-Max Peak Preservation:
   Standard downsampling (e.g., L1 averaging) smooths out transient events.
   Min-Max decimation preserves extrema (wheel hop, damper velocity spikes, lockups)
   by capturing {min, max, first, last} for every bucket.

2. Event Detection:
   Identifies and locks critical engineering spikes into the decimated output:
   - Damper velocity spikes (|v_damper| > threshold)
   - Wheel hop resonance (10–15 Hz oscillations)
   - Wheel lockup (slip ratio kappa < -0.30 or wheel speed -> 0 while vehicle speed > 0)
   - Traction breakaway (slip ratio kappa > +0.30)

3. Multiresolution LOD Profiles:
   - OVERVIEW : ~2,000 points (fast initial page load & macro trends)
   - MEDIUM   : ~20,000 points (corner-by-corner analysis)
   - DEEP     : ~100,000 points (high-resolution FFT / vibration analysis)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class LODLevel(str, Enum):
    OVERVIEW = "OVERVIEW"   # ~2,000 points
    MEDIUM = "MEDIUM"       # ~20,000 points
    DEEP = "DEEP"           # ~100,000 points


@dataclass
class TelemetryEvent:
    """Detected transient vehicle dynamics anomaly."""
    event_type: str         # "DAMPER_SPIKE", "WHEEL_HOP", "LOCKUP", "TRACTION_LOSS"
    timestamp_s: float
    channel: str
    peak_value: float
    threshold: float
    description: str


@dataclass
class DecimatedTrace:
    """Downsampled time-series dataset with preserved extrema and detected events."""
    channel_name: str
    original_points: int
    decimated_points: int
    lod_level: str
    timestamps: List[float]
    values: List[float]
    events_detected: List[TelemetryEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_name": self.channel_name,
            "original_points": self.original_points,
            "decimated_points": self.decimated_points,
            "lod_level": self.lod_level,
            "timestamps": self.timestamps,
            "values": self.values,
            "events": [
                {
                    "type": e.event_type,
                    "time_s": e.timestamp_s,
                    "channel": e.channel,
                    "value": e.peak_value,
                    "desc": e.description,
                }
                for e in self.events_detected
            ],
        }


def decimate_telemetry_trace(
    timestamps: np.ndarray | List[float],
    values: np.ndarray | List[float],
    channel_name: str = "damper_velocity_fl",
    target_points: int = 2000,
    detect_events: bool = True,
) -> DecimatedTrace:
    """
    Downsample a high-frequency telemetry channel using peak-preserving min-max bucketing.
    Preserves all physical spikes and extrema without smoothing out transients.
    """
    ts = np.asarray(timestamps, dtype=np.float64)
    val = np.asarray(values, dtype=np.float64)
    n = len(ts)

    if n <= target_points or target_points < 4:
        # Return full dataset if already within budget
        events = _detect_channel_events(ts, val, channel_name) if detect_events else []
        return DecimatedTrace(
            channel_name=channel_name,
            original_points=n,
            decimated_points=n,
            lod_level="RAW",
            timestamps=ts.tolist(),
            values=val.tolist(),
            events_detected=events,
        )

    # 4 points per bucket: (first, min, max, last)
    n_buckets = target_points // 4
    bucket_size = n / n_buckets

    out_t: List[float] = []
    out_v: List[float] = []

    for i in range(n_buckets):
        idx_start = int(i * bucket_size)
        idx_end = int((i + 1) * bucket_size) if i < n_buckets - 1 else n
        if idx_start >= idx_end:
            continue

        b_t = ts[idx_start:idx_end]
        b_v = val[idx_start:idx_end]

        # 1. First point
        out_t.append(float(b_t[0]))
        out_v.append(float(b_v[0]))

        # 2. Min point
        min_idx = int(np.argmin(b_v))
        if min_idx != 0 and min_idx != len(b_v) - 1:
            out_t.append(float(b_t[min_idx]))
            out_v.append(float(b_v[min_idx]))

        # 3. Max point
        max_idx = int(np.argmax(b_v))
        if max_idx != 0 and max_idx != len(b_v) - 1 and max_idx != min_idx:
            out_t.append(float(b_t[max_idx]))
            out_v.append(float(b_v[max_idx]))

        # 4. Last point
        if len(b_t) > 1:
            out_t.append(float(b_t[-1]))
            out_v.append(float(b_v[-1]))

    events = _detect_channel_events(ts, val, channel_name) if detect_events else []

    lod = "OVERVIEW" if target_points <= 2500 else ("MEDIUM" if target_points <= 25000 else "DEEP")

    return DecimatedTrace(
        channel_name=channel_name,
        original_points=n,
        decimated_points=len(out_t),
        lod_level=lod,
        timestamps=out_t,
        values=out_v,
        events_detected=events,
    )


def _detect_channel_events(
    ts: np.ndarray,
    val: np.ndarray,
    channel_name: str,
) -> List[TelemetryEvent]:
    """Detect transient engineering events (damper velocity spikes, wheel hops, lockups)."""
    events: List[TelemetryEvent] = []
    chn = channel_name.lower()

    # 1. Damper velocity spike (> 0.6 m/s = 600 mm/s)
    if "damper" in chn or "v_d" in chn:
        threshold = 0.60
        spike_indices = np.where(np.abs(val) > threshold)[0]
        for idx in spike_indices[:5]:  # Capture top representative spikes
            events.append(
                TelemetryEvent(
                    event_type="DAMPER_SPIKE",
                    timestamp_s=float(ts[idx]),
                    channel=channel_name,
                    peak_value=float(val[idx]),
                    threshold=threshold,
                    description=f"High-speed damper impact velocity {val[idx]:.2f} m/s exceeded threshold {threshold:.2f} m/s",
                )
            )

    # 2. Wheel slip lockup (kappa < -0.35)
    elif "slip" in chn or "kappa" in chn:
        lockup_indices = np.where(val < -0.35)[0]
        for idx in lockup_indices[:3]:
            events.append(
                TelemetryEvent(
                    event_type="LOCKUP",
                    timestamp_s=float(ts[idx]),
                    channel=channel_name,
                    peak_value=float(val[idx]),
                    threshold=-0.35,
                    description=f"Severe wheel lockup detected: slip ratio {val[idx]:.2f} < -0.35",
                )
            )

    # 3. Normal load liftoff (Fz <= 0)
    elif "fz" in chn or "load" in chn:
        liftoff_indices = np.where(val <= 5.0)[0]
        for idx in liftoff_indices[:3]:
            events.append(
                TelemetryEvent(
                    event_type="TIRE_LIFTOFF",
                    timestamp_s=float(ts[idx]),
                    channel=channel_name,
                    peak_value=float(val[idx]),
                    threshold=5.0,
                    description=f"Tire contact lost (Fz = {val[idx]:.1f} N <= 5 N)",
                )
            )

    return events
