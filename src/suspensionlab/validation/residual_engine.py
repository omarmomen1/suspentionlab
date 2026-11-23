"""SuspensionLab PRO — Validation Residual Engine.

Implements Requirement 5:
Calculate:
- RMSE
- MAE
- bias
- peak error
- normalized error
- correlation (Pearson r, R^2)
- phase/time alignment (cross-correlation lag)
- residual versus speed
- residual versus throttle
- residual versus steering
- residual versus lateral acceleration
- residual versus gear
- residual versus maneuver
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


@dataclass
class OperatingDependency:
    """Dependency analysis of residual error against an operating condition variable."""
    variable_name: str
    linear_slope: float            # de / d(variable)
    intercept: float
    correlation_r: float
    binned_means: Dict[str, float] = field(default_factory=dict)
    binned_stds: Dict[str, float] = field(default_factory=dict)
    binned_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variable_name": self.variable_name,
            "linear_slope": round(self.linear_slope, 5),
            "intercept": round(self.intercept, 4),
            "correlation_r": round(self.correlation_r, 4),
            "binned_means": {k: round(v, 4) for k, v in self.binned_means.items()},
            "binned_stds": {k: round(v, 4) for k, v in self.binned_stds.items()},
            "binned_counts": self.binned_counts,
        }


@dataclass
class ChannelResidualSummary:
    """Complete statistical residual analysis for a single vehicle channel."""
    channel: str
    units: str
    n_samples: int
    rmse: float
    mae: float
    bias: float
    peak_error: float
    normalized_rmse_pct: float     # NRMSE = RMSE / range * 100%
    normalized_peak_pct: float     # Peak Error / range * 100%
    pearson_r: float
    correlation_r2: float
    phase_lag_ms: float
    residuals: List[float] = field(default_factory=list)
    # Operating dependencies
    vs_speed: Optional[OperatingDependency] = None
    vs_throttle: Optional[OperatingDependency] = None
    vs_steering: Optional[OperatingDependency] = None
    vs_lat_g: Optional[OperatingDependency] = None
    vs_gear: Dict[int, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "channel": self.channel,
            "units": self.units,
            "n_samples": self.n_samples,
            "rmse": round(self.rmse, 4),
            "mae": round(self.mae, 4),
            "bias": round(self.bias, 4),
            "peak_error": round(self.peak_error, 4),
            "normalized_rmse_pct": round(self.normalized_rmse_pct, 2),
            "normalized_peak_pct": round(self.normalized_peak_pct, 2),
            "pearson_r": round(self.pearson_r, 4),
            "correlation_r2": round(self.correlation_r2, 4),
            "phase_lag_ms": round(self.phase_lag_ms, 2),
            "vs_gear": {
                int(g): {k: round(v, 4) for k, v in metrics.items()}
                for g, metrics in self.vs_gear.items()
            },
        }
        if self.vs_speed:
            res["vs_speed"] = self.vs_speed.to_dict()
        if self.vs_throttle:
            res["vs_throttle"] = self.vs_throttle.to_dict()
        if self.vs_steering:
            res["vs_steering"] = self.vs_steering.to_dict()
        if self.vs_lat_g:
            res["vs_lat_g"] = self.vs_lat_g.to_dict()
        return res


@dataclass
class ManeuverResidualSummary:
    """Residual summary segmented across a distinct vehicle driving maneuver."""
    maneuver_name: str
    t_start_s: float
    t_end_s: float
    sample_count: int
    channel_rmse: Dict[str, float] = field(default_factory=dict)
    channel_peak: Dict[str, float] = field(default_factory=dict)
    exit_error: Dict[str, float] = field(default_factory=dict)
    operating_envelope: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "maneuver_name": self.maneuver_name,
            "t_start_s": round(self.t_start_s, 3),
            "t_end_s": round(self.t_end_s, 3),
            "sample_count": self.sample_count,
            "channel_rmse": {k: round(v, 4) for k, v in self.channel_rmse.items()},
            "channel_peak": {k: round(v, 4) for k, v in self.channel_peak.items()},
            "exit_error": {k: round(v, 4) for k, v in self.exit_error.items()},
            "operating_envelope": {k: round(v, 4) for k, v in self.operating_envelope.items()},
        }


@dataclass
class ComprehensiveResidualReport:
    """Top-level validation report encompassing all evaluated channels and maneuvers."""
    channels: Dict[str, ChannelResidualSummary] = field(default_factory=dict)
    maneuvers: List[ManeuverResidualSummary] = field(default_factory=list)
    overall_mean_r2: float = 0.0
    overall_mean_nrmse_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_mean_r2": round(self.overall_mean_r2, 4),
            "overall_mean_nrmse_pct": round(self.overall_mean_nrmse_pct, 2),
            "channels": {k: v.to_dict() for k, v in self.channels.items()},
            "maneuvers": [m.to_dict() for m in self.maneuvers],
        }


class ResidualEngine:
    """Calculates multidimensional residual metrics and dependency maps between measured and predicted states."""

    @staticmethod
    def _compute_operating_dependency(
        e: np.ndarray,
        x: np.ndarray,
        var_name: str,
        bins: Sequence[Tuple[str, float, float]],
    ) -> OperatingDependency:
        """Computes regression slope and binned metrics for residual against variable x."""
        valid = ~(np.isnan(e) | np.isnan(x) | np.isinf(e) | np.isinf(x))
        if np.sum(valid) < 5 or np.std(x[valid]) < 1e-6:
            return OperatingDependency(
                variable_name=var_name,
                linear_slope=0.0,
                intercept=float(np.nanmean(e)),
                correlation_r=0.0,
            )

        e_v = e[valid]
        x_v = x[valid]

        slope, intercept = np.polyfit(x_v, e_v, 1)
        r = float(np.corrcoef(x_v, e_v)[0, 1]) if np.std(e_v) > 1e-6 else 0.0

        b_means = {}
        b_stds = {}
        b_counts = {}

        for label, low, high in bins:
            mask = (x_v >= low) & (x_v < high)
            cnt = int(np.sum(mask))
            b_counts[label] = cnt
            if cnt > 0:
                b_means[label] = float(np.mean(e_v[mask]))
                b_stds[label] = float(np.std(e_v[mask]))
            else:
                b_means[label] = 0.0
                b_stds[label] = 0.0

        return OperatingDependency(
            variable_name=var_name,
            linear_slope=float(slope),
            intercept=float(intercept),
            correlation_r=r,
            binned_means=b_means,
            binned_stds=b_stds,
            binned_counts=b_counts,
        )

    @classmethod
    def evaluate(
        cls,
        measured: Dict[str, np.ndarray],
        predicted: Dict[str, np.ndarray],
        dt_s: float = 0.005,
        maneuver_definitions: Optional[List[Dict[str, Any]]] = None,
        units: Optional[Dict[str, str]] = None,
    ) -> ComprehensiveResidualReport:
        """Computes complete residual statistics for all mutual channels and defined maneuvers."""
        common = set(measured.keys()).intersection(set(predicted.keys()))
        common.discard("time")
        common.discard("t_s")

        units_map = units or {}
        channel_summaries: Dict[str, ChannelResidualSummary] = {}
        r2_list = []
        nrmse_list = []

        # Operating reference vectors for dependency regressions
        vx_ref = np.asarray(measured.get("Vx", measured.get("speed", np.zeros(0))), dtype=np.float64)
        thr_ref = np.asarray(measured.get("throttle", np.zeros(0)), dtype=np.float64)
        steer_ref = np.asarray(measured.get("steering", np.zeros(0)), dtype=np.float64)
        ay_ref = np.asarray(measured.get("ay", measured.get("lat_g", np.zeros(0))), dtype=np.float64)
        gear_ref = np.asarray(measured.get("gear", np.zeros(0)), dtype=np.float64)

        for ch in sorted(list(common)):
            y_meas = np.asarray(measured[ch], dtype=np.float64)
            y_pred = np.asarray(predicted[ch], dtype=np.float64)

            n = min(len(y_meas), len(y_pred))
            if n < 3:
                continue

            y_m = y_meas[:n]
            y_p = y_pred[:n]

            valid = ~(np.isnan(y_m) | np.isnan(y_p) | np.isinf(y_m) | np.isinf(y_p))
            if np.sum(valid) < 3:
                continue

            e = y_m[valid] - y_p[valid]
            y_m_v = y_m[valid]
            y_p_v = y_p[valid]

            rmse = float(np.sqrt(np.mean(e ** 2)))
            mae = float(np.mean(np.abs(e)))
            bias = float(np.mean(e))
            peak_err = float(np.max(np.abs(e)))

            # Normalized error calculation
            data_range = float(np.ptp(y_m_v))
            if data_range > 1e-4:
                nrmse_pct = (rmse / data_range) * 100.0
                peak_pct = (peak_err / data_range) * 100.0
            else:
                rms_val = float(np.sqrt(np.mean(y_m_v ** 2)))
                nrmse_pct = (rmse / max(rms_val, 1e-4)) * 100.0
                peak_pct = (peak_err / max(rms_val, 1e-4)) * 100.0

            # Correlation metrics (Pearson r & true signed Nash-Sutcliffe Efficiency)
            var_m = float(np.var(y_m_v))
            var_p = float(np.var(y_p_v))
            if var_m > 1e-9 and var_p > 1e-9:
                r_val = float(np.corrcoef(y_m_v, y_p_v)[0, 1])
                if math.isnan(r_val):
                    r_val = 0.0
                r2 = float(1.0 - np.mean(e ** 2) / max(var_m, 1e-12))
            else:
                r_val = 1.0 if rmse < 1e-5 else 0.0
                r2 = 1.0 if rmse < 1e-5 else float(1.0 - np.mean(e ** 2) / max(var_m, 1e-12))

            r2_list.append(r2)
            nrmse_list.append(nrmse_pct)

            # Phase / time alignment via cross-correlation peak
            if len(y_m_v) > 20 and var_m > 1e-8 and var_p > 1e-8:
                cross = np.correlate(y_m_v - np.mean(y_m_v), y_p_v - np.mean(y_p_v), mode="full")
                lags = np.arange(-len(y_m_v) + 1, len(y_m_v))
                best_lag = lags[np.argmax(cross)]
                phase_lag_ms = float(best_lag * dt_s * 1000.0)
            else:
                phase_lag_ms = 0.0

            # Operating dependencies
            # 1. Residual vs speed
            speed_bins = [
                ("low_speed_0_15mps", 0.0, 15.0),
                ("mid_speed_15_30mps", 15.0, 30.0),
                ("high_speed_30_45mps", 30.0, 45.0),
                ("very_high_speed_gt_45mps", 45.0, 150.0),
            ]
            dep_speed = (
                cls._compute_operating_dependency(e, vx_ref[:n][valid], "speed_mps", speed_bins)
                if len(vx_ref) >= n
                else None
            )

            # 2. Residual vs throttle
            thr_bins = [
                ("idle_0_5pct", 0.0, 0.05),
                ("part_throttle_5_50pct", 0.05, 0.50),
                ("heavy_throttle_50_85pct", 0.50, 0.85),
                ("wot_gt_85pct", 0.85, 1.05),
            ]
            dep_thr = (
                cls._compute_operating_dependency(e, thr_ref[:n][valid], "throttle_norm", thr_bins)
                if len(thr_ref) >= n
                else None
            )

            # 3. Residual vs steering
            steer_bins = [
                ("straight_abs_lt_0.02rad", -0.02, 0.02),
                ("left_turn_gt_0.02rad", 0.02, 1.50),
                ("right_turn_lt_neg_0.02rad", -1.50, -0.02),
            ]
            dep_steer = (
                cls._compute_operating_dependency(e, steer_ref[:n][valid], "steering_rad", steer_bins)
                if len(steer_ref) >= n
                else None
            )

            # 4. Residual vs lateral acceleration
            lat_bins = [
                ("low_lat_lt_3mps2", -3.0, 3.0),
                ("mid_lat_3_8mps2", 3.0, 8.0),
                ("high_lat_gt_8mps2", 8.0, 35.0),
            ]
            dep_lat = (
                cls._compute_operating_dependency(e, ay_ref[:n][valid], "ay_mps2", lat_bins)
                if len(ay_ref) >= n
                else None
            )

            # 5. Residual vs gear
            vs_gear: Dict[int, Dict[str, float]] = {}
            if len(gear_ref) >= n:
                g_arr = np.round(gear_ref[:n][valid]).astype(int)
                for g_idx in range(1, 8):
                    g_mask = g_arr == g_idx
                    if np.any(g_mask):
                        vs_gear[g_idx] = {
                            "mean_residual": float(np.mean(e[g_mask])),
                            "std_residual": float(np.std(e[g_mask])),
                            "count": int(np.sum(g_mask)),
                        }

            unit_str = units_map.get(ch, "m/s" if "speed" in ch.lower() or "vx" in ch.lower() or "vy" in ch.lower() else "-")

            channel_summaries[ch] = ChannelResidualSummary(
                channel=ch,
                units=unit_str,
                n_samples=len(e),
                rmse=rmse,
                mae=mae,
                bias=bias,
                peak_error=peak_err,
                normalized_rmse_pct=nrmse_pct,
                normalized_peak_pct=peak_pct,
                pearson_r=r_val,
                correlation_r2=r2,
                phase_lag_ms=phase_lag_ms,
                residuals=e.tolist(),
                vs_speed=dep_speed,
                vs_throttle=dep_thr,
                vs_steering=dep_steer,
                vs_lat_g=dep_lat,
                vs_gear=vs_gear,
            )

        # Maneuver-level residual analysis
        maneuver_summaries: List[ManeuverResidualSummary] = []
        if maneuver_definitions and "time" in measured:
            t_meas = np.asarray(measured["time"], dtype=np.float64)
            for m_def in maneuver_definitions:
                m_name = m_def.get("name", "Unknown Maneuver")
                t0 = float(m_def.get("t_start_s", 0.0))
                t1 = float(m_def.get("t_end_s", 0.0))

                m_mask = (t_meas >= t0) & (t_meas <= t1)
                m_count = int(np.sum(m_mask))
                if m_count < 2:
                    continue

                m_rmse: Dict[str, float] = {}
                m_peak: Dict[str, float] = {}
                m_exit: Dict[str, float] = {}

                for ch in common:
                    if ch in channel_summaries:
                        ym_sub = np.asarray(measured[ch], dtype=np.float64)[m_mask]
                        yp_sub = np.asarray(predicted[ch], dtype=np.float64)[m_mask]
                        val_m = ~(np.isnan(ym_sub) | np.isnan(yp_sub))
                        if np.sum(val_m) > 1:
                            err_sub = ym_sub[val_m] - yp_sub[val_m]
                            m_rmse[ch] = float(np.sqrt(np.mean(err_sub ** 2)))
                            m_peak[ch] = float(np.max(np.abs(err_sub)))
                            m_exit[ch] = float(err_sub[-1])

                env = {
                    "max_speed_mps": float(np.nanmax(vx_ref[m_mask])) if len(vx_ref) > 0 else 0.0,
                    "max_throttle": float(np.nanmax(thr_ref[m_mask])) if len(thr_ref) > 0 else 0.0,
                    "max_lat_g": float(np.nanmax(np.abs(ay_ref[m_mask])) / 9.80665) if len(ay_ref) > 0 else 0.0,
                }

                maneuver_summaries.append(
                    ManeuverResidualSummary(
                        maneuver_name=m_name,
                        t_start_s=t0,
                        t_end_s=t1,
                        sample_count=m_count,
                        channel_rmse=m_rmse,
                        channel_peak=m_peak,
                        exit_error=m_exit,
                        operating_envelope=env,
                    )
                )

        mean_r2 = float(np.mean(r2_list)) if r2_list else 0.0
        mean_nrmse = float(np.mean(nrmse_list)) if nrmse_list else 0.0

        return ComprehensiveResidualReport(
            channels=channel_summaries,
            maneuvers=maneuver_summaries,
            overall_mean_r2=mean_r2,
            overall_mean_nrmse_pct=mean_nrmse,
        )
