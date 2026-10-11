"""SuspensionLab PRO — Local Sensitivity & Uncertainty Quantification (Phase 3J).

Requirement 8:
Sensitivity analysis:
For every fitted parameter report:
- local sensitivity
- parameter correlation
- uncertainty (asymptotic covariance, standard errors, 95% CI)
- effect on each observable channel
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

from suspensionlab.calibration.registry import ParameterDefinition, ParameterRegistry


@dataclass
class ChannelElasticity:
    """Normalized impact score of a parameter variation on a specific observable channel."""
    channel_name: str
    parameter_name: str
    elasticity: float          # (dy/y) / (dtheta/theta)
    absolute_sensitivity: float # dy / dtheta
    impact_rank: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_name": self.channel_name,
            "parameter_name": self.parameter_name,
            "elasticity": round(float(self.elasticity), 4),
            "absolute_sensitivity": round(float(self.absolute_sensitivity), 6),
            "impact_rank": self.impact_rank,
        }


@dataclass
class UncertaintySummary:
    """Uncertainty quantification for an individual fitted parameter."""
    parameter_name: str
    nominal_value: float
    fitted_value: float
    std_error: float
    ci_95_lower: float
    ci_95_upper: float
    relative_uncertainty_pct: float
    t_statistic: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "nominal_value": round(float(self.nominal_value), 4),
            "fitted_value": round(float(self.fitted_value), 4),
            "std_error": round(float(self.std_error), 4),
            "ci_95_lower": round(float(self.ci_95_lower), 4),
            "ci_95_upper": round(float(self.ci_95_upper), 4),
            "relative_uncertainty_pct": round(float(self.relative_uncertainty_pct), 2),
            "t_statistic": round(float(self.t_statistic), 2),
        }


@dataclass
class SensitivityAnalysisResult:
    """Complete multi-observable sensitivity and empirical uncertainty report."""
    fitted_parameters: List[str]
    uncertainties: Dict[str, UncertaintySummary]
    covariance_matrix: List[List[float]]
    correlation_matrix: List[List[float]]
    channel_elasticities: Dict[str, List[ChannelElasticity]]
    parameter_sensitivities: Dict[str, Dict[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fitted_parameters": self.fitted_parameters,
            "uncertainties": {k: v.to_dict() for k, v in self.uncertainties.items()},
            "covariance_matrix": [[round(float(x), 6) for x in row] for row in self.covariance_matrix],
            "correlation_matrix": [[round(float(x), 4) for x in row] for row in self.correlation_matrix],
            "channel_elasticities": {
                ch: [e.to_dict() for e in elist] for ch, elist in self.channel_elasticities.items()
            },
            "parameter_sensitivities": {
                p: {ch: round(float(val), 5) for ch, val in d.items()}
                for p, d in self.parameter_sensitivities.items()
            },
        }


class SensitivityAnalyzer:
    """Computes local sensitivity, Fisher covariance, and observable impact mapping."""

    def __init__(
        self,
        registry: ParameterRegistry,
        relative_step: float = 0.015,
        regularization_eps: float = 1e-6,
    ):
        self.registry = registry
        self.relative_step = relative_step
        self.regularization_eps = regularization_eps

    def analyze(
        self,
        fitted_params: Dict[str, float],
        evaluator_fn: Callable[[Dict[str, float]], Dict[str, np.ndarray]],
        residual_variance: float = 1e-4,
    ) -> SensitivityAnalysisResult:
        """Perform sensitivity and uncertainty analysis at converged parameter point."""
        p_names = sorted(list(fitted_params.keys()))
        n_p = len(p_names)

        if n_p == 0:
            return SensitivityAnalysisResult(
                fitted_parameters=[],
                uncertainties={},
                covariance_matrix=[],
                correlation_matrix=[],
                channel_elasticities={},
                parameter_sensitivities={},
            )

        # Baseline evaluation at fitted parameters
        base_channels = evaluator_fn(fitted_params)
        ch_names = sorted(list(base_channels.keys()))

        # Evaluate perturbations for each parameter
        # S_dict[p_name][ch_name] -> array of dy/dtheta
        channel_derivatives: Dict[str, Dict[str, np.ndarray]] = {p: {} for p in p_names}
        channel_elasticities_map: Dict[str, List[ChannelElasticity]] = {ch: [] for ch in ch_names}
        param_sens_map: Dict[str, Dict[str, float]] = {p: {} for p in p_names}

        # Build concatenated Jacobian for overall Fisher Information
        total_samples = sum(len(base_channels[ch]) for ch in ch_names)
        J = np.zeros((total_samples, n_p), dtype=np.float64)

        for j, p_name in enumerate(p_names):
            p_val = fitted_params[p_name]
            step = self.relative_step * max(abs(p_val), 1.0)

            p_plus = dict(fitted_params)
            p_plus[p_name] = p_val + step
            out_plus = evaluator_fn(p_plus)

            p_minus = dict(fitted_params)
            p_minus[p_name] = p_val - step
            out_minus = evaluator_fn(p_minus)

            row_offset = 0
            for ch in ch_names:
                y_0 = np.asarray(base_channels[ch], dtype=np.float64)
                y_p = np.asarray(out_plus[ch], dtype=np.float64)
                y_m = np.asarray(out_minus[ch], dtype=np.float64)

                dy_dp = (y_p - y_m) / (2.0 * step)
                channel_derivatives[p_name][ch] = dy_dp

                # Scale Jacobian row by channel variance to nondimensionalize
                ch_std = float(np.std(y_0))
                scale = max(ch_std, 1e-3)
                J[row_offset : row_offset + len(y_0), j] = dy_dp / scale
                row_offset += len(y_0)

                # Channel elasticity: (mean(dy/dp) * p_val) / mean(|y_0|)
                y_mean_abs = float(np.mean(np.abs(y_0)))
                dy_mean_abs = float(np.mean(np.abs(dy_dp)))
                norm_elasticity = (dy_mean_abs * abs(p_val)) / max(y_mean_abs, 1e-4)

                channel_elasticities_map[ch].append(ChannelElasticity(
                    channel_name=ch,
                    parameter_name=p_name,
                    elasticity=float(norm_elasticity),
                    absolute_sensitivity=float(dy_mean_abs),
                ))

                param_sens_map[p_name][ch] = float(norm_elasticity)

        # Rank elasticities per channel
        for ch in ch_names:
            channel_elasticities_map[ch].sort(key=lambda e: e.elasticity, reverse=True)
            for r_idx, el in enumerate(channel_elasticities_map[ch]):
                el.impact_rank = r_idx + 1

        # Fisher Information Matrix F = J.T @ J
        F = J.T @ J
        reg_lambda = self.regularization_eps * max(float(np.trace(F)), 1.0)
        F_reg = F + reg_lambda * np.eye(n_p)

        sigma_sq = max(residual_variance, 1e-8)
        try:
            cov_mat = sigma_sq * np.linalg.inv(F_reg)
            std_errors = np.sqrt(np.maximum(np.diag(cov_mat), 1e-12))
            corr_mat = cov_mat / np.outer(std_errors, std_errors)
            corr_mat = np.clip(corr_mat, -1.0, 1.0)
        except Exception:
            cov_mat = np.eye(n_p) * 1e-4
            std_errors = np.array([0.05 * abs(fitted_params[p]) for p in p_names])
            corr_mat = np.eye(n_p)

        uncertainties: Dict[str, UncertaintySummary] = {}
        for j, p_name in enumerate(p_names):
            p_val = fitted_params[p_name]
            nom = self.registry.get(p_name).nominal_value if self.registry.has(p_name) else p_val
            se = float(std_errors[j])
            ci_low = p_val - 1.96 * se
            ci_high = p_val + 1.96 * se
            rel_unc_pct = (se / max(abs(p_val), 1e-6)) * 100.0
            t_stat = (p_val - nom) / max(se, 1e-6)

            uncertainties[p_name] = UncertaintySummary(
                parameter_name=p_name,
                nominal_value=nom,
                fitted_value=p_val,
                std_error=se,
                ci_95_lower=ci_low,
                ci_95_upper=ci_high,
                relative_uncertainty_pct=rel_unc_pct,
                t_statistic=t_stat,
            )

        return SensitivityAnalysisResult(
            fitted_parameters=p_names,
            uncertainties=uncertainties,
            covariance_matrix=cov_mat.tolist(),
            correlation_matrix=corr_mat.tolist(),
            channel_elasticities=channel_elasticities_map,
            parameter_sensitivities=param_sens_map,
        )
