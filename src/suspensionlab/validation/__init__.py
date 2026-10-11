"""SuspensionLab PRO — Phase 3I Independent Vehicle Validation Platform.

Production-grade validation framework providing:
- Dataset Registry with cryptographic provenance and licensing metadata
- Universal Channel Schema with no fabrication of missing channels
- Timebase Audit (duplicate, missing, jitter, discontinuity, unit, offset, dropouts)
- Signal Quality and Synthetic Telemetry Detection
- Blind Prediction Mode with causal isolation and zero-leakage firewall
- Comprehensive Residual Engine (RMSE, MAE, bias, peak, normalized, R2, dependencies)
- Epistemic Validity Classification with strict anti-upgrade governance
- Cryptographically Sequestered Holdout Architecture
- End-to-End Independent Validation Pipeline
"""

from suspensionlab.validation.schema import (
    ChannelDefinition,
    ChannelRole,
    ChannelSchema,
    CoordinateConvention,
    MissingChannelError,
    ProvenanceClassification,
    StandardChannels,
    UNIVERSAL_CHANNEL_DEFINITIONS,
)
from suspensionlab.validation.registry import (
    DatasetRecord,
    DatasetRegistry,
    InvalidDatasetMetadataError,
    ProvenanceVerificationError,
)
from suspensionlab.validation.timebase import (
    TimebaseAnomaly,
    TimebaseAnomalyType,
    TimebaseAuditReport,
    TimebaseAuditor,
)
from suspensionlab.validation.signal_quality import (
    SignalQualityAuditor,
    SignalQualityReport,
    SyntheticTelemetryDetector,
)
from suspensionlab.validation.blind_prediction import (
    BlindPredictionEnvironment,
    BlindSimulationResult,
    DriverBoundaryConditions,
    InitialConditionVector,
    TelemetryLeakageError,
)
from suspensionlab.validation.residual_engine import (
    ChannelResidualSummary,
    ComprehensiveResidualReport,
    ManeuverResidualSummary,
    OperatingDependency,
    ResidualEngine,
)
from suspensionlab.validation.classification import (
    EpistemicValidityStatus,
    ValidityClassificationEngine,
    ValidityClassificationRecord,
    ValidityPromotionError,
)
from suspensionlab.validation.holdout import (
    HoldoutContaminationError,
    HoldoutManager,
    HoldoutPartition,
    HoldoutSplit,
)
from suspensionlab.validation.pipeline import (
    IndependentValidationPipeline,
    ValidationPipelineResult,
)

__all__ = [
    # Schema
    "ChannelDefinition",
    "ChannelRole",
    "ChannelSchema",
    "CoordinateConvention",
    "MissingChannelError",
    "ProvenanceClassification",
    "StandardChannels",
    "UNIVERSAL_CHANNEL_DEFINITIONS",
    # Registry
    "DatasetRecord",
    "DatasetRegistry",
    "InvalidDatasetMetadataError",
    "ProvenanceVerificationError",
    # Timebase
    "TimebaseAnomaly",
    "TimebaseAnomalyType",
    "TimebaseAuditReport",
    "TimebaseAuditor",
    # Signal Quality
    "SignalQualityAuditor",
    "SignalQualityReport",
    "SyntheticTelemetryDetector",
    # Blind Prediction
    "BlindPredictionEnvironment",
    "BlindSimulationResult",
    "DriverBoundaryConditions",
    "InitialConditionVector",
    "TelemetryLeakageError",
    # Residuals
    "ChannelResidualSummary",
    "ComprehensiveResidualReport",
    "ManeuverResidualSummary",
    "OperatingDependency",
    "ResidualEngine",
    # Classification
    "EpistemicValidityStatus",
    "ValidityClassificationEngine",
    "ValidityClassificationRecord",
    "ValidityPromotionError",
    # Holdout
    "HoldoutContaminationError",
    "HoldoutManager",
    "HoldoutPartition",
    "HoldoutSplit",
    # Pipeline
    "IndependentValidationPipeline",
    "ValidationPipelineResult",
]
