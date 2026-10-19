"""
src/suspensionlab/interop/reconciliation/engine.py
==================================================
SuspensionLab PRO — Engineering Result Reconciliation Engine (Phase 7.3 & 7.4).

Provides rigorous, unit-aware, mathematically verified comparison between external CAE solver
simulation results and independent reference vehicle dynamics models.

Features:
- Time-base alignment and uniform interpolation (zero time-base extrapolation).
- Peak error, RMS error, Normalized RMS error (NRMSE), and phase/delay analysis.
- Absolute threshold gating to eliminate division-by-near-zero distortion on quiescent signals.
- Pre-registered physical channel tolerance provenance (ISO 2631, sensor resolutions).
- Energy and dynamic envelope consistency diagnostics.
- Strict Epistemic Invariants:
  * NUMERICAL AGREEMENT != PHYSICAL VALIDATION
  * EXECUTED != VERIFIED CORRECT
"""
from __future__ import annotations

import csv
import io
import math
import pathlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np


@dataclass
class ChannelToleranceProvenance:
    """Documented tolerance provenance and physical sensor thresholds for a signal channel."""
    signal_name: str
    unit: str
    dimension: str
    nrmse_threshold: float
    absolute_threshold: float
    provenance_rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SignalMetricResult:
    signal_name: str
    unit: str
    dimension: str
    peak_external: float
    peak_reference: float
    peak_error: float
    rms_error: float
    nrmse: float
    phase_delay_seconds: float
    energy_ratio: float
    tolerance_threshold: float
    is_within_tolerance: bool
    status: str  # "PASS" or "FAIL"
    absolute_threshold: float = 0.0
    denominator_mode: str = "PEAK_TO_PEAK_RANGE"  # "PEAK_TO_PEAK_RANGE" or "ABSOLUTE_THRESHOLD"
    provenance_rationale: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReconciliationReport:
    reconciliation_id: str
    solver_name: str
    reference_model: str
    overall_status: str  # "PASS" or "FAIL"
    alignment_samples: int
    time_span_seconds: float
    metrics: Dict[str, SignalMetricResult]
    summary: Dict[str, Any]
    epistemic_notice: str
    created_at: str
    epistemic_invariants: Dict[str, Any] = field(default_factory=lambda: {
        "numerical_agreement_is_not_physical_validation": True,
        "executed_is_not_verified_correct": True,
        "physical_proving_ground_validation": False,
    })

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["metrics"] = {k: v.to_dict() for k, v in self.metrics.items()}
        return d


class ResultReconciliationEngine:
    """
    Compares external time-series simulation outputs against independent reference dynamics.
    """

    CHANNEL_PROVENANCE: Dict[str, ChannelToleranceProvenance] = {
        "z_s": ChannelToleranceProvenance(
            signal_name="z_s",
            unit="m",
            dimension="length",
            nrmse_threshold=0.05,
            absolute_threshold=0.002,  # 2 mm
            provenance_rationale="Chassis ride height sensor resolution and primary body heave motion tolerance.",
        ),
        "z_u": ChannelToleranceProvenance(
            signal_name="z_u",
            unit="m",
            dimension="length",
            nrmse_threshold=0.08,
            absolute_threshold=0.003,  # 3 mm
            provenance_rationale="Wheel center hop vertical displacement measurement uncertainty and hub accelerometer integration.",
        ),
        "susp_travel": ChannelToleranceProvenance(
            signal_name="susp_travel",
            unit="m",
            dimension="length",
            nrmse_threshold=0.05,
            absolute_threshold=0.002,  # 2 mm
            provenance_rationale="Damper linear potentiometer stroke accuracy and bump stop engagement threshold.",
        ),
        "tire_load_dynamic": ChannelToleranceProvenance(
            signal_name="tire_load_dynamic",
            unit="N",
            dimension="force",
            nrmse_threshold=0.08,
            absolute_threshold=50.0,  # 50 N
            provenance_rationale="Dynamic wheel force transducer load cell calibration noise floor and contact patch compliance.",
        ),
        "body_accel": ChannelToleranceProvenance(
            signal_name="body_accel",
            unit="m/s2",
            dimension="acceleration",
            nrmse_threshold=0.10,
            absolute_threshold=0.2,  # 0.2 m/s²
            provenance_rationale="ISO 2631-1 whole-body vibration sensor sensitivity and road input spectral noise floor.",
        ),
    }

    SIGNAL_UNITS: Dict[str, Tuple[str, str]] = {
        k: (v.unit, v.dimension) for k, v in CHANNEL_PROVENANCE.items()
    }

    DEFAULT_TOLERANCES: Dict[str, float] = {
        k: v.nrmse_threshold for k, v in CHANNEL_PROVENANCE.items()
    }

    DEFAULT_ABSOLUTE_TOLERANCES: Dict[str, float] = {
        k: v.absolute_threshold for k, v in CHANNEL_PROVENANCE.items()
    }

    MIN_OVERLAP_RATIO: float = 0.90

    EPISTEMIC_NOTICE: str = (
        "Strict Epistemic Governance: Numerical result reconciliation verifies mathematical consistency "
        "and numerical convergence between external solver outputs and independent reference models under specified "
        "operating conditions. It does NOT claim or imply physical vehicle validation, road correlation, or deployment safety."
    )

    @classmethod
    def parse_time_series_csv(cls, content: Union[str, bytes, pathlib.Path]) -> Dict[str, np.ndarray]:
        """
        Parses simulation CSV output into a dictionary of numpy arrays keyed by column name.
        """
        if isinstance(content, pathlib.Path):
            text = content.read_text(encoding="utf-8", errors="replace")
        elif isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
        else:
            text = content

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise ValueError("CSV simulation output is empty.")

        raw_headers = [h.strip().strip("'\"").lower() for h in rows[0]]
        header_map: Dict[str, int] = {h: idx for idx, h in enumerate(raw_headers)}

        if "time" not in header_map:
            raise ValueError("Simulation CSV must contain a 'time' column.")

        data_rows = rows[1:]
        if not data_rows:
            raise ValueError("Simulation CSV contains no data rows.")

        result: Dict[str, List[float]] = {h: [] for h in raw_headers}

        for row in data_rows:
            if not row or not any(row):
                continue
            for h, idx in header_map.items():
                if idx < len(row):
                    try:
                        result[h].append(float(row[idx].strip()))
                    except ValueError:
                        result[h].append(0.0)

        return {k: np.array(v, dtype=np.float64) for k, v in result.items()}

    @classmethod
    def reconcile(
        cls,
        external_data: Dict[str, np.ndarray],
        reference_data: Dict[str, np.ndarray],
        solver_name: str = "EXTERNAL_SOLVER",
        reference_model: str = "QuarterCarReference_2DOF",
        custom_tolerances: Optional[Dict[str, float]] = None,
        custom_absolute_tolerances: Optional[Dict[str, float]] = None,
        required_signals: Optional[List[str]] = None,
    ) -> ReconciliationReport:
        """
        Reconciles external simulation series against independent reference series.
        """
        tolerances = dict(cls.DEFAULT_TOLERANCES)
        if custom_tolerances:
            tolerances.update(custom_tolerances)

        abs_tolerances = dict(cls.DEFAULT_ABSOLUTE_TOLERANCES)
        if custom_absolute_tolerances:
            abs_tolerances.update(custom_absolute_tolerances)

        if "time" not in external_data or "time" not in reference_data:
            raise ValueError("Both datasets must provide a 'time' series.")

        t_ext = external_data["time"]
        t_ref = reference_data["time"]

        if len(t_ext) < 2 or len(t_ref) < 2:
            raise ValueError("Insufficient time points for reconciliation (minimum 2 required).")

        t_common_min = max(float(t_ext[0]), float(t_ref[0]))
        t_common_max = min(float(t_ext[-1]), float(t_ref[-1]))

        if t_common_max <= t_common_min:
            raise ValueError(f"No overlapping time range between external [{t_ext[0]}, {t_ext[-1]}] and reference [{t_ref[0]}, {t_ref[-1]}].")

        # Guard against insufficient overlap and time-base extrapolation
        t_ext_span = float(t_ext[-1] - t_ext[0])
        t_ref_span = float(t_ref[-1] - t_ref[0])
        overlap_span = float(t_common_max - t_common_min)
        max_span = max(t_ext_span, t_ref_span)

        overlap_ratio = overlap_span / max_span if max_span > 0 else 0.0
        if overlap_ratio < cls.MIN_OVERLAP_RATIO:
            raise ValueError(
                f"Insufficient time overlap ({overlap_ratio * 100:.1f}% < {cls.MIN_OVERLAP_RATIO * 100:.0f}% required). "
                "Reconciliation policy prohibits time-base extrapolation."
            )

        # Check required signals guard if specified
        if required_signals is not None:
            missing_ext = [s for s in required_signals if s not in external_data]
            missing_ref = [s for s in required_signals if s not in reference_data]
            if missing_ext or missing_ref:
                raise ValueError(
                    f"Required signals missing: external missing {missing_ext}, reference missing {missing_ref}."
                )

        # Create uniform evaluation grid strictly within common intersection [t_common_min, t_common_max]
        dt = min(float(np.mean(np.diff(t_ext))), float(np.mean(np.diff(t_ref))))
        if dt <= 0:
            dt = 0.002
        t_grid = np.arange(t_common_min, t_common_max + 1e-9, dt)

        metrics_map: Dict[str, SignalMetricResult] = {}
        all_passed = True
        nrmse_values: List[float] = []

        # Determine common signals to evaluate
        common_signals = [s for s in cls.CHANNEL_PROVENANCE if s in external_data and s in reference_data]
        if not common_signals:
            common_signals = [s for s in external_data if s in reference_data and s != "time"]

        for sig in common_signals:
            y_ext_raw = external_data[sig]
            y_ref_raw = reference_data[sig]

            # Interpolate strictly onto common grid
            y_ext = np.interp(t_grid, t_ext, y_ext_raw)
            y_ref = np.interp(t_grid, t_ref, y_ref_raw)

            diff = y_ext - y_ref
            peak_ext = float(np.max(np.abs(y_ext)))
            peak_ref = float(np.max(np.abs(y_ref)))
            peak_err = float(np.max(np.abs(diff)))
            rms_err = float(np.sqrt(np.mean(diff ** 2)))

            ref_range = float(np.ptp(y_ref))
            abs_tol = abs_tolerances.get(sig, 1e-3)
            tol = tolerances.get(sig, 0.05)

            # Division-by-near-zero hardening:
            # If reference signal is near-zero / quiescent (range < abs_tol):
            if ref_range < abs_tol:
                # Quiescent signal: evaluate against absolute RMS error directly
                is_pass = bool(rms_err <= abs_tol)
                nrmse = float(rms_err / abs_tol) if abs_tol > 0 else 0.0
                denominator_mode = "ABSOLUTE_THRESHOLD"
            else:
                nrmse = float(rms_err / ref_range)
                is_pass = bool(nrmse <= tol)
                denominator_mode = "PEAK_TO_PEAK_RANGE"

            nrmse_values.append(nrmse)

            # Phase delay via peak location
            idx_ext_peak = int(np.argmax(np.abs(y_ext)))
            idx_ref_peak = int(np.argmax(np.abs(y_ref)))
            delay = float(t_grid[idx_ext_peak] - t_grid[idx_ref_peak])

            # Energy ratio
            e_ext = float(np.sum(y_ext ** 2) * dt)
            e_ref = float(np.sum(y_ref ** 2) * dt)
            energy_ratio = float(e_ext / (e_ref + 1e-12)) if e_ref > 1e-12 else 1.0

            if not is_pass:
                all_passed = False

            prov = cls.CHANNEL_PROVENANCE.get(sig)
            unit, dim = (prov.unit, prov.dimension) if prov else ("-", "dimensionless")
            rationale = prov.provenance_rationale if prov else None

            metrics_map[sig] = SignalMetricResult(
                signal_name=sig,
                unit=unit,
                dimension=dim,
                peak_external=round(peak_ext, 6),
                peak_reference=round(peak_ref, 6),
                peak_error=round(peak_err, 6),
                rms_error=round(rms_err, 6),
                nrmse=round(nrmse, 6),
                phase_delay_seconds=round(delay, 6),
                energy_ratio=round(energy_ratio, 4),
                tolerance_threshold=tol,
                is_within_tolerance=is_pass,
                status="PASS" if is_pass else "FAIL",
                absolute_threshold=abs_tol,
                denominator_mode=denominator_mode,
                provenance_rationale=rationale,
            )

        summary = {
            "max_nrmse": round(float(np.max(nrmse_values)), 6) if nrmse_values else 0.0,
            "mean_nrmse": round(float(np.mean(nrmse_values)), 6) if nrmse_values else 0.0,
            "total_signals_evaluated": len(metrics_map),
            "signals_passed": sum(1 for m in metrics_map.values() if m.is_within_tolerance),
            "signals_failed": sum(1 for m in metrics_map.values() if not m.is_within_tolerance),
            "overlap_ratio": round(overlap_ratio, 4),
        }

        return ReconciliationReport(
            reconciliation_id=f"REC-{uuid.uuid4().hex[:12].upper()}",
            solver_name=solver_name,
            reference_model=reference_model,
            overall_status="PASS" if all_passed else "FAIL",
            alignment_samples=len(t_grid),
            time_span_seconds=round(t_common_max - t_common_min, 4),
            metrics=metrics_map,
            summary=summary,
            epistemic_notice=cls.EPISTEMIC_NOTICE,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
