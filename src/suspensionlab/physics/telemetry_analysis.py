"""
physics/telemetry_analysis.py
==============================
SuspensionLab PRO — Telemetry Session Analysis

Orchestrates the full telemetry pipeline:
    1. Parse → 2. Validate → 3. Segment → 4. Compare vs simulation

The comparison table quantifies the gap between the quarter-car simulation
and the real measured data for each available channel pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from suspensionlab.physics.telemetry_parser import (
    parse_telemetry_csv,
    validate_channels,
    segment_lap,
    TelemetryQA,
    LapSegment,
    ChannelInfo,
)


@dataclass
class ComparisonRow:
    """One row in the simulation vs. telemetry comparison table."""
    channel:     str    # Standard channel key
    description: str    # Human-readable label
    unit:        str    # Physical unit
    sim_value:   float | None  # Simulation prediction (scalar metric)
    telem_value: float | None  # Measured value from telemetry
    error_abs:   float | None  # Absolute error (sim - telem)
    error_pct:   float | None  # Relative error (%)
    status:      str    # 'good' | 'warning' | 'error' | 'missing'


@dataclass
class TelemetryAnalysisResult:
    """Complete result from a telemetry analysis session."""
    # Raw channel data
    channels:       dict[str, list[float]] = field(default_factory=dict)
    channel_info:   dict[str, Any]         = field(default_factory=dict)

    # Quality
    qa:             TelemetryQA | None = None

    # Segmentation
    segments:       list[LapSegment]       = field(default_factory=list)

    # Simulation comparison
    comparison:     list[ComparisonRow]    = field(default_factory=list)
    model_note:     str = ""

    # Summary statistics
    n_samples:      int   = 0
    duration_s:     float = 0.0
    sample_rate_hz: float = 0.0
    mean_speed_ms:  float = 0.0
    peak_lat_g:     float = 0.0
    peak_long_g:    float = 0.0
    peak_vert_g:    float = 0.0


def _stat(arr: list[float] | None, fn) -> float | None:
    """Safe statistical function on a list."""
    if not arr or len(arr) == 0:
        return None
    try:
        return float(fn(np.asarray(arr, dtype=float)))
    except Exception:
        return None


def analyse_session(
    csv_content: str,
    model_params: dict | None = None,
) -> TelemetryAnalysisResult:
    """
    Run the full telemetry analysis pipeline on a raw CSV string.

    Pipeline
    --------
    1. Parse CSV → identify channels
    2. Validate data quality (dropouts, dead sensors, rate mismatch)
    3. Segment lap into phases
    4. Build simulation vs. telemetry comparison table

    Parameters
    ----------
    csv_content  : str   Raw CSV file content.
    model_params : dict  Optional quarter-car model parameters for comparison.
                         Keys: 'm_s', 'm_u', 'k_s', 'c', 'k_t', 'MR', etc.

    Returns
    -------
    TelemetryAnalysisResult
    """
    # Step 1 — Parse
    data = parse_telemetry_csv(csv_content)
    channel_info_raw = data.pop('_channel_info', {})

    # Step 2 — Quality assessment
    qa = validate_channels(data)

    # Step 3 — Segmentation
    segments = segment_lap(data)

    # Step 4 — Summary stats
    time_arr  = np.asarray(data.get("time",   [0.0]), dtype=float)
    speed_arr = np.asarray(data.get("speed",  [0.0]), dtype=float)
    lat_g_arr = np.asarray(data.get("lat_g",  [0.0]), dtype=float)
    long_g_arr= np.asarray(data.get("long_g", [0.0]), dtype=float)
    vert_g_arr= np.asarray(data.get("vert_g", [0.0]), dtype=float)

    n_samples = qa.n_samples
    duration_s = qa.duration_s
    sample_rate_hz = qa.sample_rate_hz
    mean_speed = float(np.mean(speed_arr)) if len(speed_arr) > 0 else 0.0
    peak_lat   = float(np.max(np.abs(lat_g_arr))) if len(lat_g_arr) > 0 else 0.0
    peak_long  = float(np.min(long_g_arr)) if len(long_g_arr) > 0 else 0.0
    peak_vert  = float(np.max(np.abs(vert_g_arr))) if len(vert_g_arr) > 0 else 0.0

    # Step 5 — Build comparison table (simulation vs. telemetry)
    comparison: list[ComparisonRow] = []
    model_note = ""

    if model_params:
        try:
            from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis

            p = QuarterCarParams(**{k: v for k, v in model_params.items()
                                   if k in QuarterCarParams.__dataclass_fields__})
            profile = RoadProfile(profile_type="random", amplitude=0.03, duration=min(duration_s, 10.0))
            result = run_quarter_car_analysis(p, profile)

            # Helper to build a row
            def make_row(channel, description, unit, sim_val, telem_val):
                if sim_val is None or telem_val is None:
                    return ComparisonRow(channel, description, unit, sim_val, telem_val, None, None, "missing")
                err_abs = sim_val - telem_val
                err_pct = 100.0 * err_abs / telem_val if abs(telem_val) > 1e-6 else None
                status = "good"
                if err_pct is not None:
                    if abs(err_pct) > 20:
                        status = "error"
                    elif abs(err_pct) > 10:
                        status = "warning"
                return ComparisonRow(channel, description, unit,
                                    round(sim_val, 4), round(telem_val, 4),
                                    round(err_abs, 4), round(err_pct, 1) if err_pct is not None else None,
                                    status)

            # Ride frequency
            comparison.append(make_row(
                "f_n_s", "Sprung Natural Freq.", "Hz",
                result.f_n_s, None,  # no direct telemetry equivalent without modal analysis
            ))

            # RMS body acceleration vs. telemetry vert_g
            telem_rms_vert = float(np.sqrt(np.mean(vert_g_arr**2))) * 9.81 if len(vert_g_arr) > 1 else None
            comparison.append(make_row(
                "rms_body_accel", "RMS Body Acceleration", "m/s²",
                result.rms_body_accel, telem_rms_vert,
            ))

            # Peak suspension travel vs. ride height differential
            rh_fl = np.asarray(data.get("rh_fl", []), dtype=float)
            rh_fr = np.asarray(data.get("rh_fr", []), dtype=float)
            if len(rh_fl) > 1 and len(rh_fr) > 1:
                telem_travel = float(np.ptp((rh_fl + rh_fr) / 2)) / 1000.0  # mm → m
            else:
                telem_travel = None
            comparison.append(make_row(
                "peak_susp_travel", "Peak Suspension Travel", "m",
                result.peak_susp_travel, telem_travel,
            ))

            # Peak lat G: model (from tire friction) vs. telemetry
            comparison.append(make_row(
                "peak_lat_g", "Peak Lateral G", "G",
                None, peak_lat,  # model doesn't directly predict peak lat G in quarter car
            ))

            model_note = (
                f"Model: m_s={p.m_s} kg, k_s={p.k_s/1000:.1f} kN/m, "
                f"MR={p.MR}, f_n_s={result.f_n_s:.2f} Hz. "
                f"Frequency-domain note: {result.damper_linearisation_note}"
            )
        except Exception as exc:
            model_note = f"Model comparison failed: {exc}"

    # Serialise channel_info to plain dicts for JSON
    channel_info_dict = {}
    for key, info in channel_info_raw.items():
        channel_info_dict[key] = {
            "standard_key":  info.standard_key,
            "raw_name":      info.raw_name,
            "column_index":  info.column_index,
            "inferred_unit": info.inferred_unit,
            "confidence":    info.confidence,
            "warnings":      info.warnings,
        }

    return TelemetryAnalysisResult(
        channels=data,
        channel_info=channel_info_dict,
        qa=qa,
        segments=segments,
        comparison=comparison,
        model_note=model_note,
        n_samples=n_samples,
        duration_s=round(duration_s, 2),
        sample_rate_hz=sample_rate_hz,
        mean_speed_ms=round(mean_speed, 2),
        peak_lat_g=round(peak_lat, 3),
        peak_long_g=round(peak_long, 3),
        peak_vert_g=round(peak_vert, 3),
    )
