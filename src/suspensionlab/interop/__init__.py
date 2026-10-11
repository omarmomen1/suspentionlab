"""
src/suspensionlab/interop/__init__.py
=====================================
SuspensionLab PRO — Solver Interoperability Subsystem.

Exposes:
- Canonical exchange manifest, versioning, and hashing contracts.
- Parameter mapping contracts with authoritative validation.
- Physical dimensions, unit compatibility, and conversion records.
- Vehicle dynamics coordinate frames (ISO 8855, SAE J670) and transformations.
- Adapter protocol, capability reporting, and deterministic registry.
- Import/export safety guardrails and provenance preservation.
"""
from suspensionlab.interop.units import (
    ConversionRecord,
    IncompatibleDimensionError,
    UnresolvedUnitError,
    UnitCompatibilityStatus,
    check_unit_compatibility,
    convert_unit_value,
    get_physical_dimension,
    are_units_dimensionally_compatible,
)
from suspensionlab.interop.frames import (
    CoordinateFrameDefinition,
    CoordinateStandard,
    FrameValidationStatus,
    Handedness,
    ISO_8855_FRAME,
    SAE_J670_FRAME,
    validate_coordinate_frame,
    compute_frame_transformation,
)
from suspensionlab.interop.mapping import (
    MappingProvenance,
    MappingStatus,
    ParameterMapping,
    is_authoritative_internal_parameter,
    validate_parameter_mapping,
)
from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
    ExchangeMode,
    ExchangeValidationStatus,
    ExecutionMetadata,
    ParameterValue,
    ResultProvenanceOrigin,
    SUPPORTED_EXCHANGE_SCHEMA_VERSIONS,
    compute_canonical_manifest_hash,
    validate_canonical_manifest,
)
from suspensionlab.interop.adapter import (
    AdapterCapability,
    BaseSolverAdapter,
    DataCategory,
    DependencyRequirement,
    SupportLevel,
    VerificationStatus,
)
from suspensionlab.interop.registry import (
    AdapterRegistry,
    get_adapter_registry,
    reset_adapter_registry,
)
from suspensionlab.interop.security import (
    MAX_PAYLOAD_BYTES,
    MAX_ARRAY_ELEMENTS,
    MAX_DICT_KEYS,
    InteropSecurityError,
    PathTraversalSecurityError,
    ExecutableContentSecurityError,
    ResourceExhaustionSecurityError,
    MalformedPayloadSecurityError,
    MalformedNumericSecurityError,
    TenantIsolationError,
    sanitize_artifact_filename,
    verify_safe_path,
    safe_parse_json,
    safe_parse_csv,
    safe_extract_archive,
    enforce_tenant_isolation,
)
from suspensionlab.interop.service import SolverInteropService

__all__ = [
    # Units
    "ConversionRecord",
    "IncompatibleDimensionError",
    "UnresolvedUnitError",
    "UnitCompatibilityStatus",
    "check_unit_compatibility",
    "convert_unit_value",
    "get_physical_dimension",
    "are_units_dimensionally_compatible",
    # Frames
    "CoordinateFrameDefinition",
    "CoordinateStandard",
    "FrameValidationStatus",
    "Handedness",
    "ISO_8855_FRAME",
    "SAE_J670_FRAME",
    "validate_coordinate_frame",
    "compute_frame_transformation",
    # Mapping
    "MappingProvenance",
    "MappingStatus",
    "ParameterMapping",
    "is_authoritative_internal_parameter",
    "validate_parameter_mapping",
    # Manifest
    "ArtifactReference",
    "CanonicalExchangeManifest",
    "ExchangeMode",
    "ExchangeValidationStatus",
    "ExecutionMetadata",
    "ParameterValue",
    "ResultProvenanceOrigin",
    "SUPPORTED_EXCHANGE_SCHEMA_VERSIONS",
    "compute_canonical_manifest_hash",
    "validate_canonical_manifest",
    # Adapter
    "AdapterCapability",
    "BaseSolverAdapter",
    "DataCategory",
    "DependencyRequirement",
    "SupportLevel",
    "VerificationStatus",
    # Registry
    "AdapterRegistry",
    "get_adapter_registry",
    "reset_adapter_registry",
    # Security
    "MAX_PAYLOAD_BYTES",
    "MAX_ARRAY_ELEMENTS",
    "MAX_DICT_KEYS",
    "InteropSecurityError",
    "PathTraversalSecurityError",
    "ExecutableContentSecurityError",
    "ResourceExhaustionSecurityError",
    "MalformedPayloadSecurityError",
    "MalformedNumericSecurityError",
    "TenantIsolationError",
    "sanitize_artifact_filename",
    "verify_safe_path",
    "safe_parse_json",
    "safe_parse_csv",
    "safe_extract_archive",
    "enforce_tenant_isolation",
    # Service
    "SolverInteropService",
]
