"""SuspensionLab PRO — Parameter Identification Engine (Phase 3J).

Orchestrates the complete 9-step parameter identification pipeline:
1. Candidate parameter registration & domain validation
2. Cryptographic calibration / blind holdout isolation
3. Mathematical observability analysis (sensitivities, Fisher rank, excitation coverage)
4. Refusal of impossible calibration (unidentifiable parameters are strictly frozen)
5. Multi-start derivative-free optimization with physical regularization
6. Local minima detection & convergence trajectory analysis
7. Local sensitivity & empirical uncertainty quantification
8. Blind holdout evaluation with frozen parameters and zero retuning
9. Epistemic validity gating (never reports 'validated' unless holdout passes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd

from suspensionlab.calibration.registry import (
    ParameterDefinition,
    ParameterRegistry,
    STANDARD_PARAMETER_REGISTRY,
)
from suspensionlab.calibration.isolation import (
    CalibrationLeakageError,
    CalibrationSplitType,
    CryptographicDatasetIsolation,
)
from suspensionlab.calibration.regularization import (
    PhysicalInvariants,
    PhysicalRegularizer,
)
from suspensionlab.calibration.observability import (
    ObservabilityAnalyzer,
    ObservabilityRecord,
    ObservabilityStatus,
    ObservabilitySummary,
)
from suspensionlab.calibration.optimizer import (
    DerivativeFreeSolver,
    MultiStartConvergenceStatus,
    MultiStartConvergenceSummary,
    MultiStartOptimizer,
)
from suspensionlab.calibration.sensitivity import (
    SensitivityAnalysisResult,
    SensitivityAnalyzer,
)
from suspensionlab.calibration.report import (
    HoldoutPerformanceRecord,
    ParameterResult,
    PhysicalCalibrationReport,
    ResidualEvolutionRecord,
)


@dataclass
class IdentificationConfig:
    """Configuration options for parameter identification."""
    candidate_parameters: List[str]
    target_channels: List[str]
    nominal_overrides: Dict[str, float] = field(default_factory=dict)
    holdout_ratio: float = 0.25
    holdout_window: Optional[Tuple[float, float]] = None
    solver: DerivativeFreeSolver = DerivativeFreeSolver.POWELL
    num_starts: int = 3
    max_iter: int = 35
    ftol: float = 1e-4
    guard_band_s: float = 0.50
    holdout_r2_threshold: float = 0.50
    generalization_gap_threshold_pct: float = 35.0
    lambda_prior: float = 1e-3


class ParameterIdentificationEngine:
    """Production physical parameter identification engine."""

    def __init__(
        self,
        registry: Optional[ParameterRegistry] = None,
        regularizer: Optional[PhysicalRegularizer] = None,
    ):
        self.registry = registry if registry is not None else STANDARD_PARAMETER_REGISTRY
        self.regularizer = (
            regularizer
            if regularizer is not None
            else PhysicalRegularizer(registry=self.registry)
        )
        self.observability_analyzer = ObservabilityAnalyzer(registry=self.registry)

    def identify_parameters(
        self,
        telemetry: Union[pd.DataFrame, Dict[str, np.ndarray]],
        config: IdentificationConfig,
        model_evaluator: Callable[[Dict[str, float], Union[pd.DataFrame, Dict[str, np.ndarray]]], Dict[str, np.ndarray]],
        dataset_metadata: Optional[Dict[str, Any]] = None,
    ) -> PhysicalCalibrationReport:
        """Execute full end-to-end parameter identification with observability gating and blind holdout."""
        # 1. Parameter Registry Validation
        for p_name in config.candidate_parameters:
            if not self.registry.has(p_name):
                raise KeyError(
                    f"Parameter '{p_name}' is not in the parameter registry! "
                    "Do NOT invent parameters simply because they improve optimization."
                )

        # 2. Verify target channels exist in telemetry
        def get_channel_names(data_src) -> List[str]:
            if isinstance(data_src, pd.DataFrame):
                return list(data_src.columns)
            return list(data_src.keys())

        available_channels = get_channel_names(telemetry)
        for target_ch in config.target_channels:
            matched = any(target_ch.lower() == c.lower() for c in available_channels)
            if not matched:
                raise ValueError(
                    f"Required target channel '{target_ch}' is missing from telemetry dataset! "
                    f"Available channels: {available_channels[:10]}..."
                )

        # 3. Missingness check
        for target_ch in config.target_channels:
            arr = None
            if isinstance(telemetry, pd.DataFrame):
                for col in telemetry.columns:
                    if col.lower() == target_ch.lower():
                        arr = telemetry[col].to_numpy()
                        break
            else:
                for k, v in telemetry.items():
                    if k.lower() == target_ch.lower():
                        arr = np.asarray(v)
                        break
            if arr is not None and len(arr) > 0:
                missing_mask = np.isnan(arr) | np.isinf(arr)
                missing_pct = (np.sum(missing_mask) / len(arr)) * 100.0
                if missing_pct > 5.0:
                    raise ValueError(
                        f"Target channel '{target_ch}' has {missing_pct:.1f}% missing/corrupt samples "
                        "(maximum allowable threshold is 5.0%)."
                    )

        # 4. Cryptographic dataset isolation
        isolation = CryptographicDatasetIsolation(guard_band_s=config.guard_band_s)
        cal_partition, holdout_partition = isolation.partition_dataset(
            telemetry,
            holdout_ratio=config.holdout_ratio,
            holdout_window=config.holdout_window,
        )
        cal_data = isolation.get_calibration_data(caller="ParameterIdentificationEngine")

        # Build nominal parameter dictionary
        nominal_dict = {}
        for p in config.candidate_parameters:
            if p in config.nominal_overrides:
                nominal_dict[p] = float(config.nominal_overrides[p])
            else:
                nominal_dict[p] = float(self.registry.get(p).nominal_value)

        # 5. Observability Analysis on calibration partition
        def cal_evaluator_dict(param_dict: Dict[str, float]) -> Dict[str, np.ndarray]:
            # Evaluator wrapped to pass calibration partition
            return model_evaluator(param_dict, cal_data)

        try:
            observability_summary = self.observability_analyzer.analyze_observability(
                data=cal_data,
                candidate_params=config.candidate_parameters,
                evaluator_fn=cal_evaluator_dict,
                nominal_dict=config.nominal_overrides,
            )
            # Baseline evaluation at nominal parameters
            y_nom_dict = cal_evaluator_dict(nominal_dict)
            identifiable_params = observability_summary.identifiable_parameters
            unidentifiable_params = observability_summary.unidentifiable_parameters
            partially_identifiable_params = observability_summary.partially_identifiable_parameters
        except Exception as exc:
            # Model simulation or numerical solver failed
            refusal_summary = {p: f"Numerical solver failure: {exc}" for p in config.candidate_parameters}
            param_results = {}
            for p in config.candidate_parameters:
                defn = self.registry.get(p)
                nom = nominal_dict[p]
                param_results[p] = ParameterResult(
                    name=p,
                    family=defn.family.value,
                    nominal_value=nom,
                    calibrated_value=nom,
                    delta_pct=0.0,
                    is_fitted=False,
                    observability_status=ObservabilityStatus.UNIDENTIFIABLE.value,
                    units=defn.units,
                    bounds=defn.bounds,
                    prior=defn.prior.to_dict(),
                    rejection_reason=f"Numerical solver failure: {exc}",
                )
            holdout_rec = HoldoutPerformanceRecord(
                train_rmse=0.0, train_mae=0.0, train_r2=0.0,
                holdout_rmse=0.0, holdout_mae=0.0, holdout_r2=0.0,
                holdout_bias=0.0, holdout_peak=0.0,
                generalization_gap_rmse=0.0, generalization_gap_pct=0.0,
                criteria_satisfied=False, verdict="SOLVER_FAILED_UNIDENTIFIABLE",
            )
            res_changes = ResidualEvolutionRecord(
                initial_train_rmse=0.0, final_train_rmse=0.0, rmse_reduction_pct=0.0,
                initial_train_mae=0.0, final_train_mae=0.0, mae_reduction_pct=0.0,
            )
            return PhysicalCalibrationReport(
                fitted_parameters=param_results,
                priors={p: self.registry.get(p).prior.to_dict() for p in config.candidate_parameters},
                bounds={p: self.registry.get(p).bounds for p in config.candidate_parameters},
                observability={},
                objective_summary={"initial_train_loss": 0.0, "final_train_loss": 0.0, "best_optimizer_loss": 0.0},
                convergence={"status": "SOLVER_FAILED", "error": str(exc)},
                holdout_performance=holdout_rec,
                residual_changes=res_changes,
                uncertainty={},
                validity_classification="UNIDENTIFIABLE",
                is_validated=False,
                unidentifiable_parameters=config.candidate_parameters,
                partially_identifiable_parameters=[],
                refusal_summary=refusal_summary,
                dataset_metadata=dataset_metadata or {},
            )
        y_meas_dict = {}
        for ch in config.target_channels:
            if isinstance(cal_data, pd.DataFrame):
                for col in cal_data.columns:
                    if col.lower() == ch.lower():
                        y_meas_dict[ch] = cal_data[col].to_numpy(dtype=np.float64)
                        break
            else:
                for k, v in cal_data.items():
                    if k.lower() == ch.lower():
                        y_meas_dict[ch] = np.asarray(v, dtype=np.float64)
                        break

        # Compute initial training metrics
        def compute_channel_metrics(meas_d: Dict[str, np.ndarray], sim_d: Dict[str, np.ndarray]) -> Tuple[float, float, float]:
            mses, maes, r2s = [], [], []
            for ch in meas_d:
                if ch in sim_d:
                    m = meas_d[ch]
                    s = sim_d[ch]
                    n = min(len(m), len(s))
                    m_cut = m[:n]
                    s_cut = s[:n]
                    mse = float(np.mean((m_cut - s_cut) ** 2))
                    mae = float(np.mean(np.abs(m_cut - s_cut)))
                    ss_tot = float(np.sum((m_cut - np.mean(m_cut)) ** 2))
                    r2 = float(max(0.0, 1.0 - (np.sum((m_cut - s_cut) ** 2) / max(ss_tot, 1e-12))))
                    mses.append(mse)
                    maes.append(mae)
                    r2s.append(r2)
            rmse_tot = float(np.sqrt(np.mean(mses))) if mses else 0.0
            mae_tot = float(np.mean(maes)) if maes else 0.0
            r2_tot = float(np.mean(r2s)) if r2s else 0.0
            return rmse_tot, mae_tot, r2_tot

        initial_train_rmse, initial_train_mae, initial_train_r2 = compute_channel_metrics(y_meas_dict, y_nom_dict)

        # 6. Requirement 3: Refuse impossible calibration
        # Unidentifiable parameters MUST NOT be fitted.
        fitted_params_dict = dict(nominal_dict)
        convergence_summary: Optional[MultiStartConvergenceSummary] = None

        if len(identifiable_params) == 0:
            # Entire calibration refused!
            refusal_summary = {
                p: observability_summary.records[p].rejection_reason or "Unidentifiable"
                for p in unidentifiable_params + partially_identifiable_params
            }
            # Freeze all parameters at nominal
            param_results: Dict[str, ParameterResult] = {}
            for p in config.candidate_parameters:
                defn = self.registry.get(p)
                param_results[p] = ParameterResult(
                    name=p,
                    family=defn.family.value,
                    nominal_value=nominal_dict[p],
                    calibrated_value=nominal_dict[p],
                    delta_pct=0.0,
                    is_fitted=False,
                    observability_status=observability_summary.records[p].status.value,
                    units=defn.units,
                    bounds=defn.bounds,
                    prior=defn.prior.to_dict(),
                    rejection_reason=observability_summary.records[p].rejection_reason,
                )

            # Holdout evaluated with nominal parameters
            holdout_data = isolation.get_holdout_data(token=isolation.unlock_token, caller="holdout_evaluator")
            y_hold_meas = {}
            for ch in config.target_channels:
                if isinstance(holdout_data, pd.DataFrame):
                    for col in holdout_data.columns:
                        if col.lower() == ch.lower():
                            y_hold_meas[ch] = holdout_data[col].to_numpy(dtype=np.float64)
                            break
                else:
                    for k, v in holdout_data.items():
                        if k.lower() == ch.lower():
                            y_hold_meas[ch] = np.asarray(v, dtype=np.float64)
                            break

            y_hold_sim = model_evaluator(nominal_dict, holdout_data)
            h_rmse, h_mae, h_r2 = compute_channel_metrics(y_hold_meas, y_hold_sim)

            holdout_rec = HoldoutPerformanceRecord(
                train_rmse=initial_train_rmse,
                train_mae=initial_train_mae,
                train_r2=initial_train_r2,
                holdout_rmse=h_rmse,
                holdout_mae=h_mae,
                holdout_r2=h_r2,
                holdout_bias=0.0,
                holdout_peak=0.0,
                generalization_gap_rmse=h_rmse - initial_train_rmse,
                generalization_gap_pct=((h_rmse - initial_train_rmse) / max(initial_train_rmse, 1e-6)) * 100.0,
                criteria_satisfied=False,
                verdict="CALIBRATION_REFUSED_UNIDENTIFIABLE",
            )

            res_changes = ResidualEvolutionRecord(
                initial_train_rmse=initial_train_rmse,
                final_train_rmse=initial_train_rmse,
                rmse_reduction_pct=0.0,
                initial_train_mae=initial_train_mae,
                final_train_mae=initial_train_mae,
                mae_reduction_pct=0.0,
            )

            return PhysicalCalibrationReport(
                fitted_parameters=param_results,
                priors={p: self.registry.get(p).prior.to_dict() for p in config.candidate_parameters},
                bounds={p: self.registry.get(p).bounds for p in config.candidate_parameters},
                observability=observability_summary.to_dict(),
                objective_summary={"initial_loss": initial_train_rmse ** 2, "final_loss": initial_train_rmse ** 2},
                convergence={"status": "REFUSED_NO_IDENTIFIABLE_PARAMETERS"},
                holdout_performance=holdout_rec,
                residual_changes=res_changes,
                uncertainty={},
                validity_classification="UNIDENTIFIABLE",
                is_validated=False,
                unidentifiable_parameters=unidentifiable_params,
                partially_identifiable_parameters=partially_identifiable_params,
                refusal_summary=refusal_summary,
                dataset_metadata=dataset_metadata or {},
            )

        # 7. Derivative-Free Multi-Start Optimization on IDENTIFIABLE parameters only
        # Scale variances for multi-channel objective
        ch_variances = {
            ch: max(float(np.var(y_meas_dict[ch])), 1e-4) for ch in config.target_channels if ch in y_meas_dict
        }

        def objective_fn(free_param_dict: Dict[str, float]) -> float:
            full_params = dict(nominal_dict)
            full_params.update(free_param_dict)
            sim_dict = cal_evaluator_dict(full_params)

            total_loss = 0.0
            for ch in config.target_channels:
                if ch in y_meas_dict and ch in sim_dict:
                    m = y_meas_dict[ch]
                    s = sim_dict[ch]
                    n = min(len(m), len(s))
                    mse = np.mean((m[:n] - s[:n]) ** 2)
                    total_loss += mse / ch_variances[ch]
            return float(total_loss)

        optimizer = MultiStartOptimizer(
            registry=self.registry,
            regularizer=self.regularizer,
            solver=config.solver,
            num_starts=config.num_starts,
            max_iter=config.max_iter,
            ftol=config.ftol,
        )

        convergence_summary = optimizer.optimize(
            param_names=identifiable_params,
            objective_evaluator=objective_fn,
            nominal_dict=nominal_dict,
        )

        # Merge optimized parameters
        fitted_params_dict.update(convergence_summary.best_parameters)

        # Evaluate training metrics after calibration
        y_opt_train_dict = cal_evaluator_dict(fitted_params_dict)
        final_train_rmse, final_train_mae, final_train_r2 = compute_channel_metrics(y_meas_dict, y_opt_train_dict)

        rmse_red_pct = max(0.0, ((initial_train_rmse - final_train_rmse) / max(initial_train_rmse, 1e-6)) * 100.0)
        mae_red_pct = max(0.0, ((initial_train_mae - final_train_mae) / max(initial_train_mae, 1e-6)) * 100.0)

        # 8. Local Sensitivity & Uncertainty Quantification on fitted parameters
        sensitivity_analyzer = SensitivityAnalyzer(registry=self.registry)
        only_fitted_dict = {p: fitted_params_dict[p] for p in identifiable_params}
        sensitivity_res = sensitivity_analyzer.analyze(
            fitted_params=only_fitted_dict,
            evaluator_fn=cal_evaluator_dict,
            residual_variance=final_train_rmse ** 2,
        )

        # 9. Requirement 9: Blind Holdout Evaluation
        # Parameters are frozen. Holdout partition is unlocked with cryptographic token.
        holdout_data = isolation.get_holdout_data(token=isolation.unlock_token, caller="holdout_evaluator")

        y_hold_meas = {}
        for ch in config.target_channels:
            if isinstance(holdout_data, pd.DataFrame):
                for col in holdout_data.columns:
                    if col.lower() == ch.lower():
                        y_hold_meas[ch] = holdout_data[col].to_numpy(dtype=np.float64)
                        break
            else:
                for k, v in holdout_data.items():
                    if k.lower() == ch.lower():
                        y_hold_meas[ch] = np.asarray(v, dtype=np.float64)
                        break

        # Simulate holdout data with frozen calibrated parameters (NO retuning)
        y_hold_sim = model_evaluator(fitted_params_dict, holdout_data)
        h_rmse, h_mae, h_r2 = compute_channel_metrics(y_hold_meas, y_hold_sim)

        # Compute holdout bias and peak residual
        biases, peaks = [], []
        for ch in y_hold_meas:
            if ch in y_hold_sim:
                m = y_hold_meas[ch]
                s = y_hold_sim[ch]
                n = min(len(m), len(s))
                res = m[:n] - s[:n]
                biases.append(float(np.mean(res)))
                peaks.append(float(np.max(np.abs(res))))
        holdout_bias = float(np.mean(biases)) if biases else 0.0
        holdout_peak = float(np.max(peaks)) if peaks else 0.0

        gen_gap_rmse = h_rmse - final_train_rmse
        gen_gap_pct = (gen_gap_rmse / max(final_train_rmse, 1e-6)) * 100.0

        # Requirement 12: Epistemic validity gating
        # Never report "validated" unless independent physical holdout criteria are actually satisfied!
        gen_gap_acceptable = (
            (gen_gap_pct <= config.generalization_gap_threshold_pct)
            or (h_r2 >= 0.85 and gen_gap_rmse <= 0.03)
        )
        holdout_criteria_passed = (
            (h_r2 >= config.holdout_r2_threshold)
            and gen_gap_acceptable
            and (convergence_summary.status != MultiStartConvergenceStatus.OPTIMIZER_FAILED)
            and (len(identifiable_params) > 0)
        )

        if holdout_criteria_passed:
            validity_classification = "MODEL_SUPPORTED" if h_r2 >= 0.70 else "CORRELATED"
            verdict = "INDEPENDENT_PHYSICAL_HOLDOUT_SATISFIED"
            is_validated = True
        else:
            if not gen_gap_acceptable and final_train_r2 > 0.80 and h_r2 < config.holdout_r2_threshold:
                validity_classification = "OVERFIT"
            elif h_r2 < 0.20:
                validity_classification = "UNIDENTIFIABLE"
            else:
                validity_classification = "EXTRAPOLATED"
            verdict = "HOLDOUT_CRITERIA_FAILED_NOT_VALIDATED"
            is_validated = False

        holdout_record = HoldoutPerformanceRecord(
            train_rmse=final_train_rmse,
            train_mae=final_train_mae,
            train_r2=final_train_r2,
            holdout_rmse=h_rmse,
            holdout_mae=h_mae,
            holdout_r2=h_r2,
            holdout_bias=holdout_bias,
            holdout_peak=holdout_peak,
            generalization_gap_rmse=gen_gap_rmse,
            generalization_gap_pct=gen_gap_pct,
            criteria_satisfied=holdout_criteria_passed,
            verdict=verdict,
        )

        residual_changes = ResidualEvolutionRecord(
            initial_train_rmse=initial_train_rmse,
            final_train_rmse=final_train_rmse,
            rmse_reduction_pct=rmse_red_pct,
            initial_train_mae=initial_train_mae,
            final_train_mae=final_train_mae,
            mae_reduction_pct=mae_red_pct,
        )

        # Build ParameterResult records
        param_results: Dict[str, ParameterResult] = {}
        refusal_summary: Dict[str, str] = {}

        for p in config.candidate_parameters:
            defn = self.registry.get(p)
            nom = nominal_dict[p]
            obs_rec = observability_summary.records[p]

            if p in identifiable_params:
                cal_val = fitted_params_dict[p]
                delta_pct = ((cal_val - nom) / max(abs(nom), 1e-6)) * 100.0
                unc = sensitivity_res.uncertainties.get(p)
                se = unc.std_error if unc else 0.0
                ci_95 = (unc.ci_95_lower, unc.ci_95_upper) if unc else (nom, nom)
                param_results[p] = ParameterResult(
                    name=p,
                    family=defn.family.value,
                    nominal_value=nom,
                    calibrated_value=cal_val,
                    delta_pct=delta_pct,
                    is_fitted=True,
                    observability_status=obs_rec.status.value,
                    units=defn.units,
                    bounds=defn.bounds,
                    prior=defn.prior.to_dict(),
                    std_error=se,
                    ci_95=ci_95,
                    rejection_reason=None,
                )
            else:
                # UNIDENTIFIABLE / PARTIALLY_IDENTIFIABLE parameter: calibration refused
                rej_msg = obs_rec.rejection_reason or f"Calibration refused: parameter classified as {obs_rec.status.value}"
                refusal_summary[p] = rej_msg
                param_results[p] = ParameterResult(
                    name=p,
                    family=defn.family.value,
                    nominal_value=nom,
                    calibrated_value=nom,
                    delta_pct=0.0,
                    is_fitted=False,
                    observability_status=obs_rec.status.value,
                    units=defn.units,
                    bounds=defn.bounds,
                    prior=defn.prior.to_dict(),
                    std_error=0.0,
                    ci_95=(nom, nom),
                    rejection_reason=rej_msg,
                )

        return PhysicalCalibrationReport(
            fitted_parameters=param_results,
            priors={p: self.registry.get(p).prior.to_dict() for p in config.candidate_parameters},
            bounds={p: self.registry.get(p).bounds for p in config.candidate_parameters},
            observability=observability_summary.to_dict(),
            objective_summary={
                "initial_train_loss": initial_train_rmse ** 2,
                "final_train_loss": final_train_rmse ** 2,
                "best_optimizer_loss": convergence_summary.best_loss,
            },
            convergence=convergence_summary.to_dict(),
            holdout_performance=holdout_record,
            residual_changes=residual_changes,
            uncertainty=sensitivity_res.to_dict(),
            validity_classification=validity_classification,
            is_validated=is_validated,
            unidentifiable_parameters=unidentifiable_params,
            partially_identifiable_parameters=partially_identifiable_params,
            refusal_summary=refusal_summary,
            dataset_metadata=dataset_metadata or {},
        )
