"""SuspensionLab PRO — Signal Quality Audit & Synthetic Telemetry Detection.

Provides:
1. Signal Quality Audit: physical range bounds, derivative spike limits, dead-band detection.
2. Synthetic Telemetry Detector: identifies artificially generated or fabricated signals
   (e.g., zero sensor noise, mathematical zero-slip, identical synthetic noise seeds, polynomial splines).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

from suspensionlab.validation.schema import UNIVERSAL_CHANNEL_DEFINITIONS, ChannelDefinition


@dataclass
class SignalQualityReport:
    """Report summarizing signal health, physical boundary compliance, and spikes."""
    is_valid: bool
    total_samples: int
    out_of_range_channels: Dict[str, int] = field(default_factory=dict)
    derivative_spike_channels: Dict[str, int] = field(default_factory=dict)
    noise_floor_estimates: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    verdict: str = "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "verdict": self.verdict,
            "total_samples": self.total_samples,
            "out_of_range_channels": self.out_of_range_channels,
            "derivative_spike_channels": self.derivative_spike_channels,
            "noise_floor_estimates": {k: round(v, 6) for k, v in self.noise_floor_estimates.items()},
            "warnings": self.warnings,
        }


@dataclass
class SyntheticTelemetryCheckResult:
    """Result of synthetic / fabricated telemetry audit."""
    is_authentic: bool
    synthetic_probability: float  # 0.0 (authentic physical DAQ) to 1.0 (pure synthetic)
    detected_artifacts: List[str] = field(default_factory=list)
    channel_evaluations: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_authentic": self.is_authentic,
            "synthetic_probability": round(self.synthetic_probability, 4),
            "detected_artifacts": self.detected_artifacts,
            "channel_evaluations": self.channel_evaluations,
        }


class SignalQualityAuditor:
    """Audits signal ranges and physical rate of change limits."""

    def __init__(self, definitions: Optional[Dict[str, ChannelDefinition]] = None):
        self.definitions = definitions or UNIVERSAL_CHANNEL_DEFINITIONS

    def audit(
        self,
        channels: Dict[str, np.ndarray],
        dt_s: float = 0.005,
    ) -> SignalQualityReport:
        out_of_range: Dict[str, int] = {}
        spikes: Dict[str, int] = {}
        noise_floors: Dict[str, float] = {}
        warnings: List[str] = []

        n_samples = len(next(iter(channels.values()))) if channels else 0

        for ch_name, values in channels.items():
            arr = np.asarray(values, dtype=np.float64)
            if len(arr) == 0:
                continue

            valid = ~(np.isnan(arr) | np.isinf(arr))
            if np.sum(valid) == 0:
                warnings.append(f"Channel '{ch_name}' contains all NaN or Inf values.")
                continue

            v_clean = arr[valid]
            defn = self.definitions.get(ch_name)

            # Range bounds check
            if defn:
                oor = np.sum((v_clean < defn.physical_min) | (v_clean > defn.physical_max))
                if oor > 0:
                    out_of_range[ch_name] = int(oor)
                    warnings.append(
                        f"Channel '{ch_name}' has {oor} samples outside physical bounds [{defn.physical_min}, {defn.physical_max}]."
                    )

            # Derivative spike check
            if len(v_clean) > 2 and dt_s > 0:
                rates = np.abs(np.diff(v_clean)) / dt_s
                if defn:
                    spike_count = int(np.sum(rates > defn.max_rate_of_change))
                    if spike_count > 0:
                        spikes[ch_name] = spike_count
                        warnings.append(
                            f"Channel '{ch_name}' has {spike_count} derivative spikes exceeding limit {defn.max_rate_of_change}/s."
                        )

                # High-frequency noise floor (high-pass filter / second difference)
                d2 = np.diff(rates)
                noise_floors[ch_name] = float(np.median(np.abs(d2))) if len(d2) > 0 else 0.0

        total_samples_eval = max(n_samples, 1)
        severe_spikes = sum(cnt for cnt in spikes.values() if cnt > 0.05 * total_samples_eval)
        is_valid = len(out_of_range) == 0 and severe_spikes == 0
        if not is_valid:
            verdict = "FAIL"
        elif len(spikes) > 0 or len(warnings) > 0:
            verdict = "WARN"
        else:
            verdict = "PASS"

        return SignalQualityReport(
            is_valid=is_valid,
            total_samples=n_samples,
            out_of_range_channels=out_of_range,
            derivative_spike_channels=spikes,
            noise_floor_estimates=noise_floors,
            warnings=warnings,
            verdict=verdict,
        )


class SyntheticTelemetryDetector:
    """Detects artificial, simulated, or fabricated telemetry passed off as real sensor data."""

    def __init__(self, min_noise_floor: float = 1e-6):
        self.min_noise_floor = min_noise_floor

    def analyze(
        self,
        channels: Dict[str, np.ndarray],
        dt_s: float = 0.005,
        wheel_radius_m: float = 0.3198,
    ) -> SyntheticTelemetryCheckResult:
        artifacts: List[str] = []
        evals: Dict[str, Dict[str, Any]] = {}
        synthetic_points = 0.0
        total_tests = 0.0

        # Test 1: Zero sensor noise floor on dynamic analog channels
        analog_channels = [c for c in ["Vx", "Vy", "yaw_rate", "ax", "ay", "wheelspeed_fl"] if c in channels]
        for ch in analog_channels:
            arr = np.asarray(channels[ch], dtype=np.float64)
            valid = ~(np.isnan(arr) | np.isinf(arr))
            if np.sum(valid) > 50:
                v = arr[valid]
                # High-pass filter via 2nd discrete difference
                d2 = np.diff(np.diff(v))
                noise_std = float(np.std(d2))
                evals[ch] = {"noise_std": noise_std}
                total_tests += 1.0

                if noise_std < 0.001:  # Authentic vehicle sensors on moving chassis have noise_std > 0.01
                    artifacts.append(
                        f"Channel '{ch}' has unnaturally zero sensor noise (std = {noise_std:.2e}), indicating mathematical spline or simulation output."
                    )
                    synthetic_points += 1.0

        # Test 2: Exact kinematic zero-slip wheel speed identity
        # Authentic vehicle tires ALWAYS exhibit transient slip (kappa != 0) during acceleration/braking
        if "Vx" in channels and "wheelspeed_fl" in channels:
            vx = np.asarray(channels["Vx"], dtype=np.float64)
            wsp = np.asarray(channels["wheelspeed_fl"], dtype=np.float64)
            valid = (vx > 5.0) & ~(np.isnan(vx) | np.isnan(wsp))
            if np.sum(valid) > 50:
                total_tests += 1.0
                vx_sub = vx[valid]
                wsp_sub = wsp[valid]
                # Check if wsp is in rad/s or m/s
                if np.nanmean(wsp_sub) > 1.5 * np.nanmean(vx_sub):
                    # wsp is in rad/s
                    v_wheel = wsp_sub * wheel_radius_m
                else:
                    v_wheel = wsp_sub

                diff = np.abs(vx_sub - v_wheel)
                max_diff = float(np.max(diff))
                mean_diff = float(np.mean(diff))

                evals["slip_identity"] = {"max_diff": max_diff, "mean_diff": mean_diff}
                if max_diff < 1e-8:
                    artifacts.append(
                        "Wheel speed matches vehicle velocity with zero kinematic slip (max diff < 1e-8 m/s), proving synthetic telemetry."
                    )
                    synthetic_points += 2.0

        # Test 3: Perfectly identical noise across independent sensors
        # Authentic sensors (e.g. left vs right wheel speed, or IMU vs GPS) have uncorrelated analog noise
        if "wheelspeed_fl" in channels and "wheelspeed_fr" in channels:
            w_fl = np.asarray(channels["wheelspeed_fl"], dtype=np.float64)
            w_fr = np.asarray(channels["wheelspeed_fr"], dtype=np.float64)
            valid = ~(np.isnan(w_fl) | np.isnan(w_fr))
            if np.sum(valid) > 50:
                total_tests += 1.0
                d_fl = np.diff(w_fl[valid])
                d_fr = np.diff(w_fr[valid])
                corr = np.corrcoef(d_fl, d_fr)[0, 1] if np.std(d_fl) > 1e-8 and np.std(d_fr) > 1e-8 else 0.0
                evals["sensor_noise_correlation"] = {"corr": float(corr)}
                # If correlation is exactly 1.000000000000, signals were duplicated or synthesized
                if abs(corr - 1.0) < 1e-9:
                    artifacts.append(
                        "Wheel speed sensors exhibit exact identical derivative noise (r = 1.00000000), proving artificial signal generation."
                    )
                    synthetic_points += 2.0

        raw_prob = synthetic_points / max(1.0, total_tests)
        prob = min(1.0, max(raw_prob, 0.75 if len(artifacts) >= 2 else (0.55 if len(artifacts) == 1 else 0.0)))
        is_auth = prob < 0.35 and len(artifacts) == 0

        return SyntheticTelemetryCheckResult(
            is_authentic=is_auth,
            synthetic_probability=prob,
            detected_artifacts=artifacts,
            channel_evaluations=evals,
        )
