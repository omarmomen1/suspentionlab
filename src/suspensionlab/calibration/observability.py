"""SuspensionLab PRO — Observability Analysis Engine (Phase 3J).

Requirements:
2. Observability Analysis:
   Determine whether each parameter is:
   IDENTIFIABLE
   PARTIALLY_IDENTIFIABLE
   UNIDENTIFIABLE
   Use:
   - sensitivity matrix
   - parameter correlation
   - excitation coverage
   - condition number / rank
   - confidence intervals where appropriate

3. Refuse impossible calibration:
   If the data cannot identify a parameter:
   return UNIDENTIFIABLE.
   Do not return a fitted value.

11. Hostile tests:
   - flat signal
   - insufficient excitation
   - perfectly correlated parameters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd

from suspensionlab.calibration.registry import ParameterDefinition, ParameterRegistry


class ObservabilityStatus(str, Enum):
    """Rigorous mathematical classification of parameter identifiability."""
    IDENTIFIABLE = "IDENTIFIABLE"
    PARTIALLY_IDENTIFIABLE = "PARTIALLY_IDENTIFIABLE"
    UNIDENTIFIABLE = "UNIDENTIFIABLE"


@dataclass
class ObservabilityRecord:
    """Observability metrics and decision for an individual parameter."""
    parameter_name: str
    status: ObservabilityStatus
    sensitivity_norm: float
    excitation_coverage: float
    condition_number: float
    singular_value: float
    max_correlation_with: Optional[str] = None
    max_correlation_value: float = 0.0
    confidence_interval_95: Tuple[float, float] = (0.0, 0.0)
    std_error: float = 0.0
    is_calibratable: bool = False
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "status": self.status.value,
            "sensitivity_norm": round(float(self.sensitivity_norm), 5),
            "excitation_coverage": round(float(self.excitation_coverage), 4),
            "condition_number": round(float(self.condition_number), 2),
            "singular_value": round(float(self.singular_value), 5),
            "max_correlation_with": self.max_correlation_with,
            "max_correlation_value": round(float(self.max_correlation_value), 4),
            "confidence_interval_95": [round(float(v), 3) for v in self.confidence_interval_95],
            "std_error": round(float(self.std_error), 4),
            "is_calibratable": self.is_calibratable,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class ObservabilitySummary:
    """Full observability audit report over all candidate parameters."""
    records: Dict[str, ObservabilityRecord]
    identifiable_parameters: List[str]
    partially_identifiable_parameters: List[str]
    unidentifiable_parameters: List[str]
    condition_number: float
    numerical_rank: int
    total_candidates: int
    singular_values: List[float] = field(default_factory=list)
    parameter_names: List[str] = field(default_factory=list)
    correlation_matrix: List[List[float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "identifiable_count": len(self.identifiable_parameters),
            "partially_identifiable_count": len(self.partially_identifiable_parameters),
            "unidentifiable_count": len(self.unidentifiable_parameters),
            "identifiable_parameters": self.identifiable_parameters,
            "partially_identifiable_parameters": self.partially_identifiable_parameters,
            "unidentifiable_parameters": self.unidentifiable_parameters,
            "condition_number": round(float(self.condition_number), 2),
            "numerical_rank": self.numerical_rank,
            "singular_values": [round(float(v), 5) for v in self.singular_values],
            "records": {k: v.to_dict() for k, v in self.records.items()},
        }


class ObservabilityAnalyzer:
    """Analyzes mathematical observability and identifiability of physical parameters."""

    def __init__(
        self,
        registry: ParameterRegistry,
        excitation_threshold: float = 0.12,
        sensitivity_threshold: float = 1e-4,
        collinearity_threshold: float = 0.95,
        condition_number_threshold: float = 1.0e5,
    ):
        self.registry = registry
        self.excitation_threshold = excitation_threshold
        self.sensitivity_threshold = sensitivity_threshold
        self.collinearity_threshold = collinearity_threshold
        self.condition_number_threshold = condition_number_threshold

    def compute_excitation_coverage(
        self,
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        parameter: ParameterDefinition,
    ) -> float:
        """Measure dynamical excitation coverage in channels sensitive to this parameter."""
        obs_channels = parameter.observable_channels
        if not obs_channels:
            return 1.0

        scores: List[float] = []

        def get_channel(ch: str) -> Optional[np.ndarray]:
            if isinstance(data, pd.DataFrame):
                for col in data.columns:
                    if col.lower() == ch.lower():
                        return data[col].to_numpy(dtype=np.float64)
            else:
                for k in data.keys():
                    if k.lower() == ch.lower():
                        return np.asarray(data[k], dtype=np.float64)
            return None

        for ch in obs_channels:
            arr = get_channel(ch)
            if arr is None or len(arr) < 5:
                continue

            arr_clean = arr[np.isfinite(arr)]
            if len(arr_clean) < 5:
                continue

            std_val = float(np.std(arr_clean))
            ptp_val = float(np.ptp(arr_clean))

            # Flat signal check
            if std_val < 1e-4 or ptp_val < 1e-3:
                scores.append(0.0)
                continue

            # Scale based on channel physical expected dynamics
            ch_low = ch.lower()
            if "vert" in ch_low or "accel_z" in ch_low or "az" in ch_low:
                # Vertical acceleration: 0.5 G is moderate excitation
                score = min(1.0, std_val / 0.35)
            elif "ay" in ch_low or "lat" in ch_low:
                # Lateral acceleration: 3.0 m/s^2 is solid cornering excitation
                score = min(1.0, std_val / 2.5)
            elif "ax" in ch_low or "long" in ch_low:
                # Longitudinal acceleration: 2.0 m/s^2 is solid braking/accel
                score = min(1.0, std_val / 1.5)
            elif "yaw" in ch_low:
                # Yaw rate: 0.2 rad/s
                score = min(1.0, std_val / 0.15)
            elif "damper" in ch_low or "travel" in ch_low or "rh_" in ch_low:
                # Suspension travel: 5 mm std
                score = min(1.0, std_val / 4.0)
            elif "steer" in ch_low:
                # Steering: 0.05 rad
                score = min(1.0, std_val / 0.03)
            elif "speed" in ch_low or "vx" in ch_low:
                # Speed variation: 10 m/s ptp
                score = min(1.0, ptp_val / 15.0)
            elif "rpm" in ch_low:
                score = min(1.0, ptp_val / 1500.0)
            else:
                score = min(1.0, std_val / (abs(float(np.mean(arr_clean))) + 1e-3))

            scores.append(score)

        if not scores:
            # None of the observable channels were present in the data!
            return 0.0

        # Mean excitation across present channels
        return float(np.mean(scores))

    def analyze_observability(
        self,
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        candidate_params: List[str],
        evaluator_fn: Callable[[Dict[str, float]], Union[np.ndarray, Dict[str, np.ndarray]]],
        nominal_dict: Optional[Dict[str, float]] = None,
        relative_step: float = 0.02,
    ) -> ObservabilitySummary:
        """Run full sensitivity matrix, Fisher Information, and identifiability audit."""
        p_names = list(candidate_params)
        n_p = len(p_names)
        if n_p == 0:
            return ObservabilitySummary(
                records={},
                identifiable_parameters=[],
                partially_identifiable_parameters=[],
                unidentifiable_parameters=[],
                condition_number=1.0,
                numerical_rank=0,
                total_candidates=0,
            )

        # Baseline evaluation
        theta_0 = {}
        for p in p_names:
            if nominal_dict and p in nominal_dict:
                theta_0[p] = float(nominal_dict[p])
            else:
                theta_0[p] = float(self.registry.get(p).nominal_value)

        y_base_raw = evaluator_fn(theta_0)
        if isinstance(y_base_raw, dict):
            # Flatten multi-channel output
            ch_keys = sorted(list(y_base_raw.keys()))
            y_base = np.concatenate([np.asarray(y_base_raw[k], dtype=np.float64) for k in ch_keys])
        else:
            y_base = np.asarray(y_base_raw, dtype=np.float64)

        n_samples = len(y_base)
        scale_y = float(np.std(y_base))
        if scale_y < 1e-6:
            scale_y = 1.0

        # Compute normalized sensitivity matrix: S_ij = (dy_i / dtheta_j) * (theta_j / scale_y)
        S = np.zeros((n_samples, n_p), dtype=np.float64)
        sens_norms: List[float] = []

        for j, p_name in enumerate(p_names):
            p_val = theta_0[p_name]
            step = relative_step * max(abs(p_val), 1.0)

            theta_plus = dict(theta_0)
            theta_plus[p_name] = p_val + step
            y_plus_raw = evaluator_fn(theta_plus)
            if isinstance(y_plus_raw, dict):
                y_plus = np.concatenate([np.asarray(y_plus_raw[k], dtype=np.float64) for k in sorted(list(y_plus_raw.keys()))])
            else:
                y_plus = np.asarray(y_plus_raw, dtype=np.float64)

            theta_minus = dict(theta_0)
            theta_minus[p_name] = p_val - step
            y_minus_raw = evaluator_fn(theta_minus)
            if isinstance(y_minus_raw, dict):
                y_minus = np.concatenate([np.asarray(y_minus_raw[k], dtype=np.float64) for k in sorted(list(y_minus_raw.keys()))])
            else:
                y_minus = np.asarray(y_minus_raw, dtype=np.float64)

            dy_dtheta = (y_plus - y_minus) / (2.0 * step)
            norm_col = (dy_dtheta * (p_val / scale_y))
            S[:, j] = norm_col

            col_norm = float(np.linalg.norm(norm_col) / math.sqrt(max(n_samples, 1)))
            sens_norms.append(col_norm)

        # Fisher Information Matrix F = S.T @ S
        F = S.T @ S

        # SVD of S
        try:
            _, s_vals, Vt = np.linalg.svd(S, full_matrices=False)
            max_s = float(s_vals[0]) if len(s_vals) > 0 else 0.0
            min_s = float(s_vals[-1]) if len(s_vals) > 0 else 0.0
            cond_num = float(max_s / max(min_s, 1e-12)) if max_s > 0 else float("inf")
            # Numerical rank: singular values > 1e-3 * max_s
            rank = int(np.sum(s_vals > (1e-3 * max_s)))
        except Exception:
            s_vals = np.zeros(n_p)
            cond_num = float("inf")
            rank = 0

        # Regularized inverse for parameter correlation
        reg_lambda = 1e-5 * max(float(np.trace(F)), 1.0)
        F_reg = F + reg_lambda * np.eye(n_p)
        try:
            cov_mat = np.linalg.inv(F_reg)
            std_diag = np.sqrt(np.maximum(np.diag(cov_mat), 1e-12))
            corr_mat = cov_mat / np.outer(std_diag, std_diag)
            corr_mat = np.clip(corr_mat, -1.0, 1.0)
        except Exception:
            corr_mat = np.eye(n_p)
            std_diag = np.ones(n_p)

        # Excitation coverage for each parameter
        records: Dict[str, ObservabilityRecord] = {}
        identifiable: List[str] = []
        partially_identifiable: List[str] = []
        unidentifiable: List[str] = []

        for j, p_name in enumerate(p_names):
            defn = self.registry.get(p_name)
            cov = self.compute_excitation_coverage(data, defn)
            s_norm = sens_norms[j]

            # Find max correlation with any other parameter
            max_corr_val = 0.0
            max_corr_partner = None
            for k in range(n_p):
                if k != j:
                    c_val = abs(float(corr_mat[j, k]))
                    if c_val > max_corr_val:
                        max_corr_val = c_val
                        max_corr_partner = p_names[k]

            # Approximate standard error
            p_val = theta_0[p_name]
            se = float(std_diag[j] * abs(p_val) * 0.05)
            ci_95 = (p_val - 1.96 * se, p_val + 1.96 * se)

            # SVD singular value projection
            param_s_val = float(s_vals[min(j, len(s_vals) - 1)]) if len(s_vals) > 0 else 0.0

            # Classification rules:
            status = ObservabilityStatus.IDENTIFIABLE
            rejection_reason = None

            if cov < self.excitation_threshold:
                status = ObservabilityStatus.UNIDENTIFIABLE
                rejection_reason = (
                    f"Insufficient excitation coverage ({cov:.3f} < {self.excitation_threshold:.3f}) "
                    f"in observable channels {defn.observable_channels}"
                )
            elif s_norm < self.sensitivity_threshold:
                status = ObservabilityStatus.UNIDENTIFIABLE
                rejection_reason = (
                    f"Zero/negligible sensitivity ({s_norm:.2e} < {self.sensitivity_threshold:.2e}); "
                    "telemetry dynamics do not respond to this parameter"
                )
            elif max_corr_val > self.collinearity_threshold:
                # Severe collinearity: cannot uniquely resolve
                if s_norm > 0.01 and cov > 0.25:
                    status = ObservabilityStatus.PARTIALLY_IDENTIFIABLE
                    rejection_reason = (
                        f"Severe collinearity ({max_corr_val:.3f}) with '{max_corr_partner}'; "
                        "parameters are linearly dependent and cannot be uniquely uncoupled"
                    )
                else:
                    status = ObservabilityStatus.UNIDENTIFIABLE
                    rejection_reason = (
                        f"Degenerate collinearity ({max_corr_val:.3f}) with '{max_corr_partner}' "
                        "under low excitation"
                    )
            elif cond_num > self.condition_number_threshold and param_s_val < 1e-4:
                status = ObservabilityStatus.PARTIALLY_IDENTIFIABLE
                rejection_reason = f"Ill-conditioned Fisher matrix (kappa={cond_num:.1e}) with near-zero singular value"

            is_cal = (status == ObservabilityStatus.IDENTIFIABLE)
            rec = ObservabilityRecord(
                parameter_name=p_name,
                status=status,
                sensitivity_norm=s_norm,
                excitation_coverage=cov,
                condition_number=cond_num,
                singular_value=param_s_val,
                max_correlation_with=max_corr_partner,
                max_correlation_value=max_corr_val,
                confidence_interval_95=ci_95,
                std_error=se,
                is_calibratable=is_cal,
                rejection_reason=rejection_reason,
            )
            records[p_name] = rec

            if status == ObservabilityStatus.IDENTIFIABLE:
                identifiable.append(p_name)
            elif status == ObservabilityStatus.PARTIALLY_IDENTIFIABLE:
                partially_identifiable.append(p_name)
            else:
                unidentifiable.append(p_name)

        return ObservabilitySummary(
            records=records,
            identifiable_parameters=identifiable,
            partially_identifiable_parameters=partially_identifiable,
            unidentifiable_parameters=unidentifiable,
            condition_number=cond_num,
            numerical_rank=rank,
            total_candidates=n_p,
            singular_values=[float(v) for v in s_vals],
            parameter_names=p_names,
            correlation_matrix=corr_mat.tolist(),
        )
