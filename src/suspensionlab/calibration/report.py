"""SuspensionLab PRO — Physical Calibration Report (Phase 3J).

Requirement 10:
Required outputs:
Calibration report:
- fitted parameters
- prior
- bounds
- observability
- objective
- convergence
- holdout performance
- residual changes
- uncertainty
- validity classification

Requirement 12:
Never report "validated" unless independent physical holdout criteria are actually satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class ParameterResult:
    """Detailed result for an individual parameter."""
    name: str
    family: str
    nominal_value: float
    calibrated_value: float
    delta_pct: float
    is_fitted: bool
    observability_status: str
    units: str
    bounds: Tuple[float, float]
    prior: Dict[str, Any]
    std_error: float = 0.0
    ci_95: Tuple[float, float] = (0.0, 0.0)
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "nominal_value": round(float(self.nominal_value), 4),
            "calibrated_value": round(float(self.calibrated_value), 4),
            "delta_pct": round(float(self.delta_pct), 2),
            "is_fitted": self.is_fitted,
            "observability_status": self.observability_status,
            "units": self.units,
            "bounds": [round(float(b), 4) for b in self.bounds],
            "prior": self.prior,
            "std_error": round(float(self.std_error), 4),
            "ci_95": [round(float(x), 4) for x in self.ci_95],
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class HoldoutPerformanceRecord:
    """Out-of-sample sequestered holdout validation performance metrics."""
    train_rmse: float
    train_mae: float
    train_r2: float
    holdout_rmse: float
    holdout_mae: float
    holdout_r2: float
    holdout_bias: float
    holdout_peak: float
    generalization_gap_rmse: float
    generalization_gap_pct: float
    criteria_satisfied: bool
    verdict: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "train_rmse": round(float(self.train_rmse), 4),
            "train_mae": round(float(self.train_mae), 4),
            "train_r2": round(float(self.train_r2), 4),
            "holdout_rmse": round(float(self.holdout_rmse), 4),
            "holdout_mae": round(float(self.holdout_mae), 4),
            "holdout_r2": round(float(self.holdout_r2), 4),
            "holdout_bias": round(float(self.holdout_bias), 4),
            "holdout_peak": round(float(self.holdout_peak), 4),
            "generalization_gap_rmse": round(float(self.generalization_gap_rmse), 4),
            "generalization_gap_pct": round(float(self.generalization_gap_pct), 2),
            "criteria_satisfied": self.criteria_satisfied,
            "verdict": self.verdict,
        }


@dataclass
class ResidualEvolutionRecord:
    """Residual improvements achieved from prior to calibration."""
    initial_train_rmse: float
    final_train_rmse: float
    rmse_reduction_pct: float
    initial_train_mae: float
    final_train_mae: float
    mae_reduction_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_train_rmse": round(float(self.initial_train_rmse), 4),
            "final_train_rmse": round(float(self.final_train_rmse), 4),
            "rmse_reduction_pct": round(float(self.rmse_reduction_pct), 2),
            "initial_train_mae": round(float(self.initial_train_mae), 4),
            "final_train_mae": round(float(self.final_train_mae), 4),
            "mae_reduction_pct": round(float(self.mae_reduction_pct), 2),
        }


@dataclass
class PhysicalCalibrationReport:
    """Authoritative Phase 3J physical parameter identification report."""
    fitted_parameters: Dict[str, ParameterResult]
    priors: Dict[str, Dict[str, Any]]
    bounds: Dict[str, Tuple[float, float]]
    observability: Dict[str, Any]
    objective_summary: Dict[str, float]
    convergence: Dict[str, Any]
    holdout_performance: HoldoutPerformanceRecord
    residual_changes: ResidualEvolutionRecord
    uncertainty: Dict[str, Any]
    validity_classification: str
    is_validated: bool
    unidentifiable_parameters: List[str]
    partially_identifiable_parameters: List[str]
    refusal_summary: Dict[str, str]
    dataset_metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_iso": self.timestamp_iso,
            "validity_classification": self.validity_classification,
            "is_validated": self.is_validated,
            "total_parameters": len(self.fitted_parameters),
            "calibrated_count": len([p for p in self.fitted_parameters.values() if p.is_fitted]),
            "unidentifiable_count": len(self.unidentifiable_parameters),
            "partially_identifiable_count": len(self.partially_identifiable_parameters),
            "fitted_parameters": {k: v.to_dict() for k, v in self.fitted_parameters.items()},
            "unidentifiable_parameters": self.unidentifiable_parameters,
            "partially_identifiable_parameters": self.partially_identifiable_parameters,
            "refusal_summary": self.refusal_summary,
            "priors": self.priors,
            "bounds": {k: list(v) for k, v in self.bounds.items()},
            "observability": self.observability,
            "objective_summary": self.objective_summary,
            "convergence": self.convergence,
            "holdout_performance": self.holdout_performance.to_dict(),
            "residual_changes": self.residual_changes.to_dict(),
            "uncertainty": self.uncertainty,
            "dataset_metadata": self.dataset_metadata,
        }

    def export_json(self, file_path: Union[str, Path]) -> None:
        """Export report to JSON manifest."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(self.to_dict(), fp, indent=2)
