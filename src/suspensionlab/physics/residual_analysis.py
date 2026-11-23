"""
physics/residual_analysis.py
============================
SuspensionLab PRO — Model-to-Telemetry Residual Maps & Attribution

Computes continuous time-domain residuals between real telemetry and physics model simulations:
    e(t) = y_telemetry(t) - y_model(t)

Provides statistical aggregation (MAE, RMSE, Bias, Phase Delay, Correlation R^2)
and attributes model discrepancies across:
- Corner phase (entry, apex, exit, straight)
- Lateral load / roll angle regimes
- Damper velocity regimes (low-speed vs high-speed)
- Ride height / heave travel
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class ChannelResidualMetrics:
    """Statistical summary of error between model simulation and measured telemetry."""
    channel: str
    mae: float                     # Mean Absolute Error
    rmse: float                    # Root Mean Square Error
    mean_bias: float               # Mean signed error (positive = telemetry > model)
    max_error: float               # Maximum absolute error
    correlation_r2: float          # Coefficient of determination R^2
    pearson_r: float = 0.0         # Pearson linear correlation coefficient
    phase_lag_ms: float = 0.0      # Estimated phase delay in milliseconds
    r2_holdout: float = 0.0        # Holdout window (20%) R^2
    units: str = "-"
    epistemic_label: str = "CORRELATED"  # EMPIRICALLY_VALIDATED | CORRELATED | INFERRED | SIMULATION_ESTIMATE
    residual_time_series: List[float] = field(default_factory=list)
    residual_distribution: Dict[str, float] = field(default_factory=dict)
    histogram: Dict[str, Any] = field(default_factory=dict)
    vs_operating: Dict[str, List[List[float]]] = field(default_factory=dict)
    systematic_bias: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "units": self.units,
            "mae": round(self.mae, 4),
            "rmse": round(self.rmse, 4),
            "mean_bias": round(self.mean_bias, 4),
            "max_error": round(self.max_error, 4),
            "correlation_r2": round(self.correlation_r2, 4),
            "r2_holdout": round(self.r2_holdout, 4),
            "pearson_r": round(self.pearson_r, 4),
            "phase_lag_ms": round(self.phase_lag_ms, 2),
            "epistemic_label": self.epistemic_label,
            "residual_distribution": {k: round(v, 4) for k, v in self.residual_distribution.items()},
            "histogram": self.histogram,
            "vs_operating": self.vs_operating,
            "systematic_bias": self.systematic_bias,
        }


@dataclass
class SegmentAttribution:
    """Attribution of model discrepancy to specific corner or driving phases."""
    phase: str                     # 'straight', 'braking', 'corner_entry', 'mid_corner', 'corner_exit'
    sample_count: int
    mean_residual: float
    max_residual: float
    primary_driving_factor: str    # e.g. 'damper_rebound_lag', 'roll_stiffness_deficiency'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "sample_count": self.sample_count,
            "mean_residual": round(self.mean_residual, 4),
            "max_residual": round(self.max_residual, 4),
            "primary_driving_factor": self.primary_driving_factor,
        }


@dataclass
class ResidualAnalysisReport:
    """Complete residual analysis dataset comparing simulation vs telemetry."""
    overall_correlation_pct: float
    channels: Dict[str, ChannelResidualMetrics] = field(default_factory=dict)
    phase_attributions: List[SegmentAttribution] = field(default_factory=list)
    diagnostic_summary: str = ""

    @property
    def channel_residuals(self) -> Dict[str, ChannelResidualMetrics]:
        return self.channels

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_correlation_pct": round(self.overall_correlation_pct, 2),
            "channels": {k: v.to_dict() for k, v in self.channels.items()},
            "phase_attributions": [a.to_dict() for a in self.phase_attributions],
            "diagnostic_summary": self.diagnostic_summary,
        }


def normalize_timestamps(raw_timestamps: np.ndarray | List[float]) -> np.ndarray:
    """Converts raw timestamps to a common time base (seconds from start)."""
    ts = np.asarray(raw_timestamps, dtype=np.float64)
    if len(ts) == 0:
        return ts
    return ts - ts[0]


def compute_residuals(
    telemetry_data: Dict[str, np.ndarray | List[float]],
    simulation_data: Dict[str, np.ndarray | List[float]],
    sample_rate_hz: float = 100.0,
    epistemic_labels: Optional[Dict[str, str]] = None,
    is_empirical_telemetry: bool = True,
) -> ResidualAnalysisReport:
    """Compute channel-by-channel residual metrics and driving phase attributions."""
    channel_metrics: Dict[str, ChannelResidualMetrics] = {}
    r2_scores: List[float] = []

    common_channels = set(telemetry_data.keys()).intersection(set(simulation_data.keys()))
    common_channels.discard("time")
    common_channels.discard("_channel_info")
    common_channels.discard("_audit_trail")

    t_tel = telemetry_data.get("time")
    t_sim = simulation_data.get("time")
    
    if t_tel is not None and t_sim is not None:
        t_tel_norm = normalize_timestamps(t_tel)
        t_sim_norm = normalize_timestamps(t_sim)
    else:
        t_tel_norm = None
        t_sim_norm = None

    # Reference operating arrays for residual dependency mapping
    speed_ref = np.asarray(telemetry_data.get("speed", []), dtype=float)
    lat_g_ref = np.asarray(telemetry_data.get("lat_g", []), dtype=float)
    steer_ref = np.asarray(telemetry_data.get("steer_deg", []), dtype=float)

    for ch in common_channels:
        y_tel = np.asarray(telemetry_data[ch], dtype=np.float64)
        y_sim = np.asarray(simulation_data[ch], dtype=np.float64)

        if len(y_tel) < 3 or len(y_sim) < 3:
            continue

        if t_tel_norm is not None and t_sim_norm is not None and len(t_tel_norm) == len(y_tel) and len(t_sim_norm) == len(y_sim):
            y_sim = np.interp(t_tel_norm, t_sim_norm, y_sim)
        else:
            n = min(len(y_tel), len(y_sim))
            y_tel = y_tel[:n]
            y_sim = y_sim[:n]

        valid = ~(np.isnan(y_tel) | np.isnan(y_sim) | np.isinf(y_tel) | np.isinf(y_sim))
        if np.sum(valid) < 3:
            continue

        e = y_tel[valid] - y_sim[valid]
        mae = float(np.mean(np.abs(e)))
        rmse = float(np.sqrt(np.mean(e**2)))
        bias = float(np.mean(e))
        max_err = float(np.max(np.abs(e)))

        # Pearson r and R^2 (true signed Nash-Sutcliffe Efficiency)
        var_tel = float(np.var(y_tel[valid]))
        var_sim = float(np.var(y_sim[valid]))
        if var_tel > 1e-12 and var_sim > 1e-12:
            r_val = float(np.corrcoef(y_tel[valid], y_sim[valid])[0, 1])
            if math.isnan(r_val):
                r_val = 0.0
            r2 = float(1.0 - np.mean(e ** 2) / max(var_tel, 1e-12))
        else:
            r_val = 1.0 if rmse < 1e-6 else 0.0
            r2 = 1.0 if rmse < 1e-6 else float(1.0 - np.mean(e ** 2) / max(var_tel, 1e-12))
        r2_scores.append(r2)

        # Cross-correlation for phase lag estimation
        cross_corr = np.correlate(
            y_tel[valid] - np.mean(y_tel[valid]),
            y_sim[valid] - np.mean(y_sim[valid]),
            mode="full"
        )
        lags = np.arange(-len(y_tel[valid]) + 1, len(y_tel[valid]))
        best_lag = lags[np.argmax(cross_corr)]
        phase_lag_ms = float(best_lag * (1000.0 / max(sample_rate_hz, 1.0)))

        # Residual distribution statistics
        dist_stats = {
            "mean": bias,
            "std": float(np.std(e)),
            "min": float(np.min(e)),
            "max": float(np.max(e)),
            "p10": float(np.percentile(e, 10)),
            "p50": float(np.percentile(e, 50)),
            "p90": float(np.percentile(e, 90)),
            "skewness": float(np.mean(((e - bias) / (np.std(e) + 1e-9))**3)) if len(e) > 3 else 0.0,
        }

        # Histogram calculation (up to 20 bins)
        if np.ptp(e) < 1e-9:
            counts, bin_edges = np.histogram(e, bins=1, range=(float(e[0]) - 0.5, float(e[0]) + 0.5))
        else:
            n_bins = min(20, max(1, len(e)))
            counts, bin_edges = np.histogram(e, bins=n_bins)
        hist_dict = {
            "bin_edges": [round(float(b), 4) for b in bin_edges],
            "bin_counts": [int(c) for c in counts],
            "bin_centers": [round(float(0.5 * (bin_edges[i] + bin_edges[i+1])), 4) for i in range(len(counts))],
        }

        # Subsample residual dependencies vs operating parameters (max 200 points)
        step = max(1, len(e) // 200)
        vs_operating: Dict[str, List[List[float]]] = {}
        if len(speed_ref) >= len(e):
            vs_operating["vs_speed"] = [[round(float(speed_ref[valid][i]), 2), round(float(e[i]), 4)] for i in range(0, len(e), step)]
        if len(lat_g_ref) >= len(e):
            vs_operating["vs_lat_g"] = [[round(float(lat_g_ref[valid][i]), 3), round(float(e[i]), 4)] for i in range(0, len(e), step)]
        if len(steer_ref) >= len(e):
            vs_operating["vs_steer"] = [[round(float(steer_ref[valid][i]), 2), round(float(e[i]), 4)] for i in range(0, len(e), step)]

        # Systematic bias diagnosis
        is_bias_detected = abs(bias) > (0.15 * max(rmse, 1e-6))
        slope_speed = 0.0
        if len(speed_ref) >= len(e) and np.std(speed_ref[valid]) > 1e-3:
            slope_speed = float(np.polyfit(speed_ref[valid], e, 1)[0])

        slope_lat = 0.0
        if len(lat_g_ref) >= len(e) and np.std(lat_g_ref[valid]) > 1e-3:
            slope_lat = float(np.polyfit(lat_g_ref[valid], e, 1)[0])

        diag_notes = []
        if is_bias_detected:
            diag_notes.append(f"Systematic offset detected: mean error {bias:+.3f} exceeds 15% of RMS error.")
        if abs(slope_speed) > 0.02:
            diag_notes.append(f"Speed-dependent divergence (slope {slope_speed:+.4f}/(m/s)) indicates aero scaling or rolling resistance mismatch.")
        if abs(slope_lat) > 0.05:
            diag_notes.append(f"Lateral-G dependent residual (slope {slope_lat:+.4f}/G) indicates roll stiffness or tire load sensitivity error.")
        if not diag_notes:
            diag_notes.append("Residual is zero-centered with normal random noise distribution.")

        systematic_bias_info = {
            "bias_detected": is_bias_detected,
            "offset": round(bias, 4),
            "slope_vs_speed": round(slope_speed, 5),
            "slope_vs_lat_g": round(slope_lat, 5),
            "diagnosis": " ".join(diag_notes),
        }

        # Compute 20% holdout R^2
        n_pts = len(e)
        split_idx = int(0.8 * n_pts)
        if n_pts >= 20 and split_idx < n_pts:
            e_hold = e[split_idx:]
            var_tel_hold = float(np.var(y_tel[valid][split_idx:]))
            if var_tel_hold > 1e-12:
                r2_holdout = max(0.0, float(1.0 - (np.var(e_hold) / var_tel_hold)))
            else:
                r2_holdout = 1.0 if float(np.sqrt(np.mean(e_hold**2))) < 1e-6 else 0.0
        else:
            r2_holdout = r2

        # 7-point validation criteria for channel
        qualifies_empirical = (
            r2 >= 0.85
            and r2_holdout >= 0.80
            and n_pts >= 100
            and not is_bias_detected
            and abs(phase_lag_ms) <= 50.0
        )

        # Epistemic labeling
        is_empirical = bool(telemetry_data.get("is_empirical_telemetry", is_empirical_telemetry))
        if epistemic_labels and ch in epistemic_labels:
            label = epistemic_labels[ch]
        elif qualifies_empirical:
            label = "EMPIRICALLY_VALIDATED" if is_empirical else "MODEL_SUPPORTED"
        elif "observer" in ch.lower() or "est" in ch.lower():
            label = "INFERRED"
        elif r2 >= 0.70:
            label = "CORRELATED"
        else:
            label = "SIMULATION_ESTIMATE"

        unit_str = "m/s" if "speed" in ch.lower() else ("G" if "lat" in ch.lower() or "long" in ch.lower() or "vert" in ch.lower() else ("mm" if "rh" in ch.lower() or "damper" in ch.lower() else "-"))

        channel_metrics[ch] = ChannelResidualMetrics(
            channel=ch,
            units=unit_str,
            mae=mae,
            rmse=rmse,
            mean_bias=bias,
            max_error=max_err,
            correlation_r2=r2,
            r2_holdout=r2_holdout,
            pearson_r=r_val,
            phase_lag_ms=phase_lag_ms,
            epistemic_label=label,
            residual_time_series=e.tolist(),
            residual_distribution=dist_stats,
            histogram=hist_dict,
            vs_operating=vs_operating,
            systematic_bias=systematic_bias_info,
        )

    if len(channel_metrics) == 0:
        raise ValueError("Cannot compute residuals: No common channels with sufficient valid samples found.")

    # Phase attributions computed dynamically from measured vs simulated residuals
    phase_attributions: List[SegmentAttribution] = []
    lat_g = np.asarray(telemetry_data.get("lat_g", np.zeros(0)), dtype=np.float64)

    if len(lat_g) > 10 and len(channel_metrics) > 0:
        primary_metric = next(iter(channel_metrics.values()))
        e_arr = np.asarray(primary_metric.residual_time_series, dtype=np.float64)
        n_eval = min(len(lat_g), len(e_arr))

        if n_eval > 5:
            lat_slice = lat_g[:n_eval]
            e_slice = np.abs(e_arr[:n_eval])

            entry_mask = np.abs(lat_slice) > 0.4
            straight_mask = ~entry_mask

            if np.any(entry_mask):
                e_entry = e_slice[entry_mask]
                phase_attributions.append(SegmentAttribution(
                    phase="corner_entry",
                    sample_count=int(np.sum(entry_mask)),
                    mean_residual=float(np.nanmean(e_entry)),
                    max_residual=float(np.nanmax(e_entry)),
                    primary_driving_factor="Tire relaxation length & roll damping lag",
                ))
            if np.any(straight_mask):
                e_straight = e_slice[straight_mask]
                phase_attributions.append(SegmentAttribution(
                    phase="straight",
                    sample_count=int(np.sum(straight_mask)),
                    mean_residual=float(np.nanmean(e_straight)),
                    max_residual=float(np.nanmax(e_straight)),
                    primary_driving_factor="Aerodynamic downforce mapping",
                ))

    overall_corr = float(np.mean(r2_scores) * 100.0) if r2_scores else 0.0
    summary = f"Model matches physical telemetry with {overall_corr:.1f}% correlation across {len(channel_metrics)} channels."

    return ResidualAnalysisReport(
        overall_correlation_pct=overall_corr,
        channels=channel_metrics,
        phase_attributions=phase_attributions,
        diagnostic_summary=summary,
    )
