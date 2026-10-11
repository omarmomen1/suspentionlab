"""SuspensionLab PRO — Phase 3J Physical Parameter Identification & Observability.

Production-grade parameter identification system providing:
- Parameter Registry covering 11 physical parameter families already represented by the model
- Observability Analysis via sensitivity matrix, Fisher Information, singular value decomposition, condition number, and excitation coverage
- Strict Refusal of Impossible Calibration (unidentifiable parameters are never fitted)
- Cryptographic Dataset Isolation separating calibration and sequestered blind holdout data
- Derivative-Free Regularized Optimization (Powell / Nelder-Mead)
- Physical Invariant Regularization preventing unphysical parameter combinations
- Multi-Start Calibration demonstrating regional convergence vs local minima
- Sensitivity & Uncertainty Analysis (local sensitivity, covariance, standard error, 95% CI)
- Blind Holdout Evaluation with frozen parameters and zero retuning
- Epistemic Validity Classification with anti-upgrade enforcement (never report 'validated' unless criteria pass)
"""

from suspensionlab.calibration.registry import (
    ParameterFamily,
    PriorDistribution,
    GaussianPrior,
    UniformPrior,
    LogNormalPrior,
    ValidityDomain,
    ParameterDefinition,
    ParameterRegistry,
    STANDARD_PARAMETER_REGISTRY,
)
from suspensionlab.calibration.observability import (
    ObservabilityStatus,
    ObservabilityRecord,
    ObservabilityAnalyzer,
    ObservabilitySummary,
)
from suspensionlab.calibration.isolation import (
    CalibrationSplitType,
    CalibrationLeakageError,
    CryptographicDatasetIsolation,
    IsolatedDatasetPartition,
)
from suspensionlab.calibration.regularization import (
    PhysicalInvariants,
    PhysicalRegularizer,
    RegularizationPenalty,
)
from suspensionlab.calibration.optimizer import (
    DerivativeFreeSolver,
    MultiStartConvergenceStatus,
    MultiStartConvergenceSummary,
    MultiStartOptimizer,
    OptimizationTrajectory,
)
from suspensionlab.calibration.sensitivity import (
    ChannelElasticity,
    SensitivityAnalysisResult,
    SensitivityAnalyzer,
    UncertaintySummary,
)
from suspensionlab.calibration.report import (
    HoldoutPerformanceRecord,
    ParameterResult,
    PhysicalCalibrationReport,
    ResidualEvolutionRecord,
)
from suspensionlab.calibration.engine import (
    ParameterIdentificationEngine,
    IdentificationConfig,
)

__all__ = [
    # Registry
    "ParameterFamily",
    "PriorDistribution",
    "GaussianPrior",
    "UniformPrior",
    "LogNormalPrior",
    "ValidityDomain",
    "ParameterDefinition",
    "ParameterRegistry",
    "STANDARD_PARAMETER_REGISTRY",
    # Observability
    "ObservabilityStatus",
    "ObservabilityRecord",
    "ObservabilityAnalyzer",
    "ObservabilitySummary",
    # Isolation
    "CalibrationSplitType",
    "CalibrationLeakageError",
    "CryptographicDatasetIsolation",
    "IsolatedDatasetPartition",
    # Regularization
    "PhysicalInvariants",
    "PhysicalRegularizer",
    "RegularizationPenalty",
    # Optimizer
    "DerivativeFreeSolver",
    "MultiStartConvergenceStatus",
    "MultiStartConvergenceSummary",
    "MultiStartOptimizer",
    "OptimizationTrajectory",
    # Sensitivity
    "ChannelElasticity",
    "SensitivityAnalysisResult",
    "SensitivityAnalyzer",
    "UncertaintySummary",
    # Report
    "HoldoutPerformanceRecord",
    "ParameterResult",
    "PhysicalCalibrationReport",
    "ResidualEvolutionRecord",
    # Engine
    "ParameterIdentificationEngine",
    "IdentificationConfig",
]
