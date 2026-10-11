"""SuspensionLab PRO — Timebase Audit & Signal Synchronization Engine.

Implements Requirement 3:
Detect:
- duplicate timestamps
- missing samples
- jitter
- discontinuities
- resampling
- unit mismatch
- channel offset
- sensor dropouts
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


class TimebaseAnomalyType(str, Enum):
    """Classification of timebase defects."""
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    MISSING_SAMPLE = "MISSING_SAMPLE"
    JITTER = "JITTER"
    DISCONTINUITY = "DISCONTINUITY"
    RESAMPLING_ARTIFACT = "RESAMPLING_ARTIFACT"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    CHANNEL_OFFSET = "CHANNEL_OFFSET"
    SENSOR_DROPOUT = "SENSOR_DROPOUT"


@dataclass
class TimebaseAnomaly:
    """Detailed record of a single timebase defect."""
    anomaly_type: TimebaseAnomalyType
    sample_index: int
    timestamp_s: float
    description: str
    severity: str  # "BLOCKING", "WARNING", "INFO"
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class TimebaseAuditReport:
    """Comprehensive diagnostic report from the timebase audit."""
    is_valid: bool
    nominal_dt_s: float
    nominal_rate_hz: float
    actual_mean_dt_s: float
    dt_std_s: float
    jitter_pct: float
    total_samples: int
    duplicate_count: int
    missing_sample_count: int
    discontinuity_count: int
    sensor_dropout_count: int
    detected_channel_offsets_ms: Dict[str, float] = field(default_factory=dict)
    anomalies: List[TimebaseAnomaly] = field(default_factory=list)
    verdict: str = "PASS"  # "PASS", "WARN", "FAIL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "verdict": self.verdict,
            "nominal_dt_s": round(self.nominal_dt_s, 6),
            "nominal_rate_hz": round(self.nominal_rate_hz, 2),
            "actual_mean_dt_s": round(self.actual_mean_dt_s, 6),
            "dt_std_s": round(self.dt_std_s, 8),
            "jitter_pct": round(self.jitter_pct, 4),
            "total_samples": self.total_samples,
            "duplicate_count": self.duplicate_count,
            "missing_sample_count": self.missing_sample_count,
            "discontinuity_count": self.discontinuity_count,
            "sensor_dropout_count": self.sensor_dropout_count,
            "detected_channel_offsets_ms": {
                k: round(v, 2) for k, v in self.detected_channel_offsets_ms.items()
            },
            "anomaly_count": len(self.anomalies),
            "anomalies": [
                {
                    "type": a.anomaly_type.value,
                    "index": a.sample_index,
                    "timestamp": round(a.timestamp_s, 4),
                    "description": a.description,
                    "severity": a.severity,
                    "metrics": a.metrics,
                }
                for a in self.anomalies[:50]  # Cap summary at 50 entries
            ],
        }


class TimebaseAuditor:
    """Forensic auditor evaluating timebase integrity, clock drift, jitter, and cross-channel sync."""

    def __init__(
        self,
        max_jitter_pct: float = 15.0,
        missing_sample_threshold_factor: float = 1.5,
        discontinuity_threshold_factor: float = 5.0,
        max_channel_offset_ms: float = 30.0,
        min_dropout_consecutive_samples: int = 15,
    ):
        self.max_jitter_pct = max_jitter_pct
        self.missing_sample_threshold_factor = missing_sample_threshold_factor
        self.discontinuity_threshold_factor = discontinuity_threshold_factor
        self.max_channel_offset_ms = max_channel_offset_ms
        self.min_dropout_consecutive_samples = min_dropout_consecutive_samples

    def audit(
        self,
        timestamps: Union[np.ndarray, Sequence[float]],
        channels: Optional[Dict[str, Union[np.ndarray, Sequence[float]]]] = None,
        expected_rate_hz: Optional[float] = None,
    ) -> TimebaseAuditReport:
        """Runs the 8-point timebase audit across the timestamp vector and synchronized channels."""
        t = np.asarray(timestamps, dtype=np.float64)
        n = len(t)
        anomalies: List[TimebaseAnomaly] = []

        if n < 3:
            return TimebaseAuditReport(
                is_valid=False,
                nominal_dt_s=0.0,
                nominal_rate_hz=0.0,
                actual_mean_dt_s=0.0,
                dt_std_s=0.0,
                jitter_pct=0.0,
                total_samples=n,
                duplicate_count=0,
                missing_sample_count=0,
                discontinuity_count=1,
                sensor_dropout_count=0,
                anomalies=[
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.DISCONTINUITY,
                        sample_index=0,
                        timestamp_s=float(t[0]) if n > 0 else 0.0,
                        description=f"Insufficient sample count for timebase audit: {n} < 3",
                        severity="BLOCKING",
                    )
                ],
                verdict="FAIL",
            )

        # 1. Unit mismatch detection
        # Check if timestamps look like milliseconds (e.g. dt is on order of 1.0 to 10.0 for 100-1000Hz, or span is enormous)
        span = float(t[-1] - t[0])
        dt_raw = np.diff(t)
        median_dt = float(np.median(dt_raw))

        unit_mismatch_detected = False
        if expected_rate_hz is not None and expected_rate_hz > 0:
            expected_nominal_dt = 1.0 / expected_rate_hz
            ratio = median_dt / expected_nominal_dt if expected_nominal_dt > 0 else 1.0
            if ratio > 5.0 or ratio < 0.2:
                unit_mismatch_detected = True
                anomalies.append(
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.UNIT_MISMATCH,
                        sample_index=0,
                        timestamp_s=float(t[0]),
                        description=f"Timestamp median dt ({median_dt:.4f} s) differs by factor {ratio:.1f}x from expected nominal dt ({expected_nominal_dt:.4f} s), indicating unit mismatch (e.g. ms vs s).",
                        severity="BLOCKING",
                        metrics={"median_dt": median_dt, "expected_dt": expected_nominal_dt, "ratio": ratio},
                    )
                )

        if not unit_mismatch_detected and median_dt > 50.0:  # dt > 50s between consecutive samples is abnormal for telemetry
            unit_mismatch_detected = True
            anomalies.append(
                TimebaseAnomaly(
                    anomaly_type=TimebaseAnomalyType.UNIT_MISMATCH,
                    sample_index=0,
                    timestamp_s=float(t[0]),
                    description=f"Timestamp median dt ({median_dt:.3f} s) indicates possible timestamp scale or unit mismatch (e.g. minutes/hours).",
                    severity="BLOCKING",
                    metrics={"median_dt": median_dt},
                )
            )
        elif not unit_mismatch_detected and median_dt < 1e-6 and median_dt > 0:
            unit_mismatch_detected = True
            anomalies.append(
                TimebaseAnomaly(
                    anomaly_type=TimebaseAnomalyType.UNIT_MISMATCH,
                    sample_index=0,
                    timestamp_s=float(t[0]),
                    description=f"Timestamp median dt ({median_dt:.2e} s) indicates microsecond or nanosecond units mislabeled as seconds.",
                    severity="BLOCKING",
                    metrics={"median_dt": median_dt},
                )
            )
        elif not unit_mismatch_detected and float(t[0]) > 1e11:  # Unix epoch in milliseconds (> 1.7e12) or microseconds
            unit_mismatch_detected = True
            anomalies.append(
                TimebaseAnomaly(
                    anomaly_type=TimebaseAnomalyType.UNIT_MISMATCH,
                    sample_index=0,
                    timestamp_s=float(t[0]),
                    description="Timestamps appear to be raw Unix epoch milliseconds or microseconds; should be normalized seconds from start.",
                    severity="BLOCKING",
                    metrics={"t0": float(t[0])},
                )
            )

        # Establish nominal dt
        if expected_rate_hz is not None and expected_rate_hz > 0:
            nominal_dt = 1.0 / expected_rate_hz
        else:
            # Filter non-positive dts to compute robust median
            positive_dts = dt_raw[dt_raw > 1e-9]
            nominal_dt = float(np.median(positive_dts)) if len(positive_dts) > 0 else 0.01

        nominal_hz = 1.0 / nominal_dt if nominal_dt > 0 else 0.0

        # 2. Duplicate timestamps & Discontinuities (Non-monotonicity)
        duplicate_count = 0
        discontinuity_count = 0

        for i in range(len(dt_raw)):
            dt_i = dt_raw[i]
            # Exact duplicate or near-zero step
            if abs(dt_i) < 1e-9:
                duplicate_count += 1
                anomalies.append(
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.DUPLICATE_TIMESTAMP,
                        sample_index=i + 1,
                        timestamp_s=float(t[i + 1]),
                        description=f"Duplicate timestamp detected at index {i+1}: t = {t[i+1]:.6f} s.",
                        severity="BLOCKING",
                        metrics={"dt": dt_i},
                    )
                )
            # Reversal / negative jump
            elif dt_i < -1e-9:
                discontinuity_count += 1
                anomalies.append(
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.DISCONTINUITY,
                        sample_index=i + 1,
                        timestamp_s=float(t[i + 1]),
                        description=f"Negative time step (timestamp reversal / shuffled) at index {i+1}: dt = {dt_i:.6f} s.",
                        severity="BLOCKING",
                        metrics={"dt": dt_i},
                    )
                )
            # Large step discontinuity
            elif dt_i > self.discontinuity_threshold_factor * nominal_dt:
                discontinuity_count += 1
                anomalies.append(
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.DISCONTINUITY,
                        sample_index=i + 1,
                        timestamp_s=float(t[i + 1]),
                        description=f"Severe time discontinuity at index {i+1}: dt = {dt_i:.4f} s (> {self.discontinuity_threshold_factor}x nominal {nominal_dt:.4f} s).",
                        severity="BLOCKING",
                        metrics={"dt": dt_i, "ratio": dt_i / max(nominal_dt, 1e-6)},
                    )
                )

        # 3. Missing samples (gaps between 1.5x and 5.0x nominal)
        missing_sample_count = 0
        for i in range(len(dt_raw)):
            dt_i = dt_raw[i]
            if dt_i > self.missing_sample_threshold_factor * nominal_dt and dt_i <= self.discontinuity_threshold_factor * nominal_dt:
                est_lost = int(round(dt_i / nominal_dt)) - 1
                missing_sample_count += max(1, est_lost)
                anomalies.append(
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.MISSING_SAMPLE,
                        sample_index=i + 1,
                        timestamp_s=float(t[i + 1]),
                        description=f"Missing sample gap at index {i+1}: dt = {dt_i:.4f} s (~{est_lost} dropped frames).",
                        severity="WARNING",
                        metrics={"dt": dt_i, "estimated_lost_frames": float(est_lost)},
                    )
                )

        # 4. Jitter statistics
        valid_dts = dt_raw[dt_raw > 1e-9]
        if len(valid_dts) > 0:
            actual_mean_dt = float(np.mean(valid_dts))
            dt_std = float(np.std(valid_dts))
            jitter_pct = float((dt_std / nominal_dt) * 100.0) if nominal_dt > 0 else 0.0
        else:
            actual_mean_dt = 0.0
            dt_std = 0.0
            jitter_pct = 0.0

        if jitter_pct > self.max_jitter_pct:
            anomalies.append(
                TimebaseAnomaly(
                    anomaly_type=TimebaseAnomalyType.JITTER,
                    sample_index=0,
                    timestamp_s=float(t[0]),
                    description=f"Timestamp jitter {jitter_pct:.2f}% exceeds tolerance threshold of {self.max_jitter_pct}%.",
                    severity="WARNING",
                    metrics={"jitter_pct": jitter_pct, "std_dt": dt_std},
                )
            )

        # 5. Resampling artifact detection
        # Check if timestamps have unnaturally zero variance (exact constant step synthetic grid)
        # or fractional step harmonics indicative of post-acquisition resampling
        if len(valid_dts) > 20:
            if dt_std < 1e-12:
                anomalies.append(
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.RESAMPLING_ARTIFACT,
                        sample_index=0,
                        timestamp_s=float(t[0]),
                        description="Identical floating-point timestamps across entire dataset indicate synthetic grid or post-hoc resampling.",
                        severity="INFO",
                        metrics={"dt_std": dt_std},
                    )
                )
            # Check for dual-rate interleaving (e.g. 10ms then 0ms, or alternating 4ms/6ms)
            step_diffs = np.abs(np.diff(valid_dts))
            if len(step_diffs) > 10 and np.mean(step_diffs) > 0.3 * nominal_dt:
                anomalies.append(
                    TimebaseAnomaly(
                        anomaly_type=TimebaseAnomalyType.RESAMPLING_ARTIFACT,
                        sample_index=0,
                        timestamp_s=float(t[0]),
                        description="Periodic step fluctuations indicate software rate-conversion or asynchronous DAQ multiplexing.",
                        severity="WARNING",
                        metrics={"mean_step_diff": float(np.mean(step_diffs))},
                    )
                )

        # 6. Sensor Dropouts & 7. Channel Offset Audit (if channels provided)
        detected_offsets: Dict[str, float] = {}
        sensor_dropout_count = 0

        if channels:
            # Check for NaN / Inf / sensor freeze dropouts
            speed = channels.get("Vx") if "Vx" in channels else channels.get("speed")
            speed_arr = np.asarray(speed, dtype=np.float64) if speed is not None else np.ones(n) * 10.0

            for ch_name, ch_vals in channels.items():
                if ch_name == "time":
                    continue
                arr = np.asarray(ch_vals, dtype=np.float64)
                if len(arr) != n:
                    continue

                # Check NaNs or Infs
                nan_mask = np.isnan(arr) | np.isinf(arr)
                nan_count = int(np.sum(nan_mask))
                if nan_count > 0:
                    sensor_dropout_count += nan_count
                    anomalies.append(
                        TimebaseAnomaly(
                            anomaly_type=TimebaseAnomalyType.SENSOR_DROPOUT,
                            sample_index=int(np.where(nan_mask)[0][0]),
                            timestamp_s=float(t[np.where(nan_mask)[0][0]]),
                            description=f"Channel '{ch_name}' contains {nan_count} NaN or Inf dropout samples.",
                            severity="BLOCKING",
                            metrics={"nan_count": float(nan_count)},
                        )
                    )

                # Check flatline sensor freeze (constant value for N steps while speed > 5 m/s)
                # Ignore discrete channels like gear
                if ch_name not in ("gear", "lap_number", "sector") and not np.all(nan_mask):
                    diffs = np.abs(np.diff(arr))
                    is_flat = (diffs < 1e-12) & (speed_arr[1:] > 5.0)
                    consecutive_flat = 0
                    max_flat = 0
                    flat_start_idx = 0
                    for k in range(len(is_flat)):
                        if is_flat[k]:
                            if consecutive_flat == 0:
                                flat_start_idx = k
                            consecutive_flat += 1
                            if consecutive_flat > max_flat:
                                max_flat = consecutive_flat
                        else:
                            if consecutive_flat >= self.min_dropout_consecutive_samples:
                                sensor_dropout_count += 1
                                anomalies.append(
                                    TimebaseAnomaly(
                                        anomaly_type=TimebaseAnomalyType.SENSOR_DROPOUT,
                                        sample_index=flat_start_idx,
                                        timestamp_s=float(t[flat_start_idx]),
                                        description=f"Channel '{ch_name}' flatlined for {consecutive_flat} frames while vehicle was in motion.",
                                        severity="WARNING",
                                        metrics={"consecutive_flat_samples": float(consecutive_flat)},
                                    )
                                )
                            consecutive_flat = 0

            # Cross-channel offset detection (e.g. wheel speeds vs Vx, or steering rate vs yaw rate)
            if "Vx" in channels and "wheelspeed_fl" in channels:
                vx = np.asarray(channels["Vx"], dtype=np.float64)
                wsp = np.asarray(channels["wheelspeed_fl"], dtype=np.float64)
                valid = ~(np.isnan(vx) | np.isnan(wsp))
                if np.sum(valid) > 100:
                    vx_v = vx[valid] - np.mean(vx[valid])
                    wsp_v = wsp[valid] - np.mean(wsp[valid])
                    if np.std(vx_v) > 0.1 and np.std(wsp_v) > 0.1:
                        corr = np.correlate(vx_v, wsp_v, mode="full")
                        lags = np.arange(-len(vx_v) + 1, len(vx_v))
                        best_lag = lags[np.argmax(corr)]
                        offset_ms = float(best_lag * nominal_dt * 1000.0)
                        detected_offsets["wheelspeed_fl_vs_Vx"] = offset_ms
                        if abs(offset_ms) > self.max_channel_offset_ms:
                            anomalies.append(
                                TimebaseAnomaly(
                                    anomaly_type=TimebaseAnomalyType.CHANNEL_OFFSET,
                                    sample_index=0,
                                    timestamp_s=float(t[0]),
                                    description=f"Cross-channel offset between wheelspeed_fl and Vx is {offset_ms:+.1f} ms (> {self.max_channel_offset_ms} ms).",
                                    severity="WARNING",
                                    metrics={"offset_ms": offset_ms},
                                )
                            )

        # Verdict calculation
        blocking_count = sum(1 for a in anomalies if a.severity == "BLOCKING")
        warning_count = sum(1 for a in anomalies if a.severity == "WARNING")

        if blocking_count > 0:
            verdict = "FAIL"
            is_valid = False
        elif warning_count > 0:
            verdict = "WARN"
            is_valid = True
        else:
            verdict = "PASS"
            is_valid = True

        return TimebaseAuditReport(
            is_valid=is_valid,
            nominal_dt_s=nominal_dt,
            nominal_rate_hz=nominal_hz,
            actual_mean_dt_s=actual_mean_dt,
            dt_std_s=dt_std,
            jitter_pct=jitter_pct,
            total_samples=n,
            duplicate_count=duplicate_count,
            missing_sample_count=missing_sample_count,
            discontinuity_count=discontinuity_count,
            sensor_dropout_count=sensor_dropout_count,
            detected_channel_offsets_ms=detected_offsets,
            anomalies=anomalies,
            verdict=verdict,
        )
