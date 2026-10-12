"""
src/suspensionlab/interop/reconciliation/engine.py
==================================================
SuspensionLab PRO — Engineering Result Reconciliation Engine (Phase 7.3).

Provides rigorous, unit-aware, mathematically verified comparison between external CAE solver
simulation results and analytical / reference vehicle dynamics models.

Features:
- Time-base alignment and uniform interpolation.
- Peak error, RMS error, Normalized RMS error (NRMSE), and phase/delay analysis.
- Energy and dynamic envelope consistency diagnostics.
- Preregistered engineering tolerance verification.
- Epistemic invariants: Mathematical consistency != Physical proving-ground validation.
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

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["metrics"] = {k: v.to_dict() for k, v in self.metrics.items()}
        return d


class ResultReconciliationEngine:
    """
    Compares external time-series simulation outputs against independent reference dynamics.
    """

    SIGNAL_UNITS: Dict[str, Tuple[str, str]] = {
        "z_s": ("m", "length"),
        "z_u": ("m", "length"),
        "susp_travel": ("m", "length"),
        "tire_load_dynamic": ("N", "force"),
        "body_accel": ("m/s2", "acceleration"),
    }

    DEFAULT_TOLERANCES: Dict[str, float] = {
        "z_s": 0.05,            # Max 5% NRMSE
        "z_u": 0.08,            # Max 8% NRMSE
        "susp_travel": 0.05,    # Max 5% NRMSE
        "tire_load_dynamic": 0.08,  # Max 8% NRMSE
        "body_accel": 0.10,     # Max 10% NRMSE
    }

    EPISTEMIC_NOTICE: str = (
        "Strict Epistemic Governance: Numerical result reconciliation verifies mathematical consistency "
        "and numerical convergence between external solver outputs and internal reference models under specified "
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
    ) -> ReconciliationReport:
        """
        Reconciles external simulation series against reference series.
        """
        tolerances = dict(cls.DEFAULT_TOLERANCES)
        if custom_tolerances:
            tolerances.update(custom_tolerances)

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

        # Create uniform evaluation grid using finer of the two resolutions
        dt = min(float(np.mean(np.diff(t_ext))), float(np.mean(np.diff(t_ref))))
        if dt <= 0:
            dt = 0.002
        t_grid = np.arange(t_common_min, t_common_max + 1e-9, dt)

        metrics_map: Dict[str, SignalMetricResult] = {}
        all_passed = True
        nrmse_values: List[float] = []

        # Compare signals present in both
        common_signals = [s for s in cls.SIGNAL_UNITS if s in external_data and s in reference_data]
        if not common_signals:
            # Fallback to any common column except time
            common_signals = [s for s in external_data if s in reference_data and s != "time"]

        for sig in common_signals:
            y_ext_raw = external_data[sig]
            y_ref_raw = reference_data[sig]

            # Interpolate onto common grid
            y_ext = np.interp(t_grid, t_ext, y_ext_raw)
            y_ref = np.interp(t_grid, t_ref, y_ref_raw)

            diff = y_ext - y_ref
            peak_ext = float(np.max(np.abs(y_ext)))
            peak_ref = float(np.max(np.abs(y_ref)))
            peak_err = float(np.max(np.abs(diff)))
            rms_err = float(np.sqrt(np.mean(diff ** 2)))

            ref_range = float(np.ptp(y_ref))
            if ref_range < 1e-6:
                ref_range = peak_ref if peak_ref > 1e-6 else 1.0

            nrmse = float(rms_err / ref_range)
            nrmse_values.append(nrmse)

            # Phase delay via peak location
            idx_ext_peak = int(np.argmax(np.abs(y_ext)))
            idx_ref_peak = int(np.argmax(np.abs(y_ref)))
            delay = float(t_grid[idx_ext_peak] - t_grid[idx_ref_peak])

            # Energy ratio
            e_ext = float(np.sum(y_ext ** 2) * dt)
            e_ref = float(np.sum(y_ref ** 2) * dt)
            energy_ratio = float(e_ext / (e_ref + 1e-12)) if e_ref > 1e-12 else 1.0

            tol = tolerances.get(sig, 0.05)
            is_pass = bool(nrmse <= tol)
            if not is_pass:
                all_passed = False

            unit, dim = cls.SIGNAL_UNITS.get(sig, ("-", "dimensionless"))

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
            )

        summary = {
            "max_nrmse": round(float(np.max(nrmse_values)), 6) if nrmse_values else 0.0,
            "mean_nrmse": round(float(np.mean(nrmse_values)), 6) if nrmse_values else 0.0,
            "total_signals_evaluated": len(metrics_map),
            "signals_passed": sum(1 for m in metrics_map.values() if m.is_within_tolerance),
            "signals_failed": sum(1 for m in metrics_map.values() if not m.is_within_tolerance),
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
