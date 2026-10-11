"""
src/suspensionlab/interop/manifest.py
=====================================
SuspensionLab PRO — Canonical Exchange Manifest Contract.

Defines the versioned, typed exchange manifest representing engineering inputs,
configurations, simulation results, and artifacts exchanged between SuspensionLab
and external engineering solvers.

Invariants & Guarantees:
1. Versioned Schema: Supported schema is "1.0.0". Unsupported versions are strictly rejected.
2. Deterministic Hash: Canonical manifest identity is computed via RFC 8785 canonical JSON
   serialization and SHA-256 hashing.
3. Material Sensitivity: Any change in parameters, units, frames, or artifact hashes changes
   the manifest identity.
4. Epistemic Humility:
   - Imported results are marked with ResultProvenanceOrigin.IMPORTED_EXTERNAL.
   - Parsing success does NOT establish physical accuracy (is_physically_validated=False).
   - Import success does NOT establish validation (validation_status != VALIDATED).
   - Export success does NOT prove an external solver executed the model (is_executed=False).
5. Numerical Safety: NaN and Infinity are rejected with validation errors.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from suspensionlab.interop.units import (
    ConversionRecord,
    UnitCompatibilityStatus,
    check_unit_compatibility,
    get_physical_dimension,
)
from suspensionlab.interop.frames import (
    CoordinateFrameDefinition,
    FrameValidationStatus,
    validate_coordinate_frame,
)
from suspensionlab.interop.mapping import (
    ParameterMapping,
    validate_parameter_mapping,
)


SUPPORTED_EXCHANGE_SCHEMA_VERSIONS: Set[str] = {"1.0.0"}
DEFAULT_EXCHANGE_SCHEMA_VERSION = "1.0.0"


class ExchangeMode(str, Enum):
    """Direction of the engineering exchange."""
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class ExchangeValidationStatus(str, Enum):
    """Overall validation verdict of the exchange manifest."""
    VALIDATED = "VALIDATED"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"
    UNRESOLVED = "UNRESOLVED"


class ResultProvenanceOrigin(str, Enum):
    """Authoritative origin of the engineering results contained in or linked to manifest."""
    NATIVE_SOLVER = "NATIVE_SOLVER"            # Computed by certified native SuspensionLab solver
    IMPORTED_EXTERNAL = "IMPORTED_EXTERNAL"    # Ingested from external solver or third-party CAE tool


class ArtifactReference(BaseModel):
    """Cryptographic reference to an associated file, model, or dataset artifact."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    artifact_id: str = Field(..., description="Unique identifier of the artifact (e.g. ART-001 or UUID).")
    name: str = Field(..., description="Filename or resource name.")
    artifact_type: str = Field(..., description="MIME type or category (e.g. adams_adm, fmu_zip, csv_telemetry).")
    sha256: str = Field(..., min_length=64, max_length=64, description="Hex-encoded SHA-256 content digest.")
    size_bytes: int = Field(..., ge=0, description="Exact size of the artifact in bytes.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Supplementary artifact metadata.")


class ParameterValue(BaseModel):
    """Strongly typed parameter representation with unit and dimensional traceability."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    name: str = Field(..., description="Parameter key or identifier.")
    value: Union[float, int, str, bool, List[float]] = Field(..., description="Engineering value.")
    unit: Optional[str] = Field(default=None, description="Authoritative unit expression.")
    dimension: Optional[str] = Field(default=None, description="Physical dimension (e.g. stiffness, mass).")
    description: Optional[str] = Field(default=None, description="Physical interpretation.")

    @field_validator("value")
    @classmethod
    def reject_nan_and_inf(cls, v: Any) -> Any:
        """Enforces that numeric values are finite and non-NaN."""
        if isinstance(v, float):
            if math.isnan(v):
                raise ValueError("Parameter value cannot be NaN.")
            if math.isinf(v):
                raise ValueError("Parameter value cannot be Infinity.")
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, float):
                    if math.isnan(item):
                        raise ValueError("Array element cannot be NaN.")
                    if math.isinf(item):
                        raise ValueError("Array element cannot be Infinity.")
        return v


class ExecutionMetadata(BaseModel):
    """Metadata regarding simulation solver execution and provenance."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    is_executed: bool = Field(
        default=False,
        description="True ONLY if an actual solver execution run was verified."
    )
    execution_id: Optional[str] = Field(
        default=None,
        description="Execution run ID if executed."
    )
    execution_timestamp_utc: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp of execution."
    )
    is_physically_validated: bool = Field(
        default=False,
        description="True ONLY if certified physical validation criteria passed. NEVER True upon raw import."
    )
    provenance_origin: ResultProvenanceOrigin = Field(
        default=ResultProvenanceOrigin.NATIVE_SOLVER,
        description="Origin of the underlying calculations."
    )
    execution_environment: Optional[str] = Field(
        default=None,
        description="Operating environment or platform details."
    )


class CanonicalExchangeManifest(BaseModel):
    """
    Authoritative Canonical Exchange Manifest for SuspensionLab PRO Solver Interoperability.
    """
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    schema_version: str = Field(
        default=DEFAULT_EXCHANGE_SCHEMA_VERSION,
        description="Schema version (e.g. '1.0.0')."
    )
    manifest_id: Optional[str] = Field(
        default=None,
        description="Deterministic manifest digest or unique identifier."
    )
    source_application: str = Field(
        default="SuspensionLab PRO",
        description="Application that generated the exchange package."
    )
    source_solver: str = Field(
        default="SuspensionLab",
        description="Origin solver name (e.g. SuspensionLab, MSC_ADAMS, MATLAB_SIMULINK)."
    )
    solver_version: Optional[str] = Field(
        default="1.0.0",
        description="Solver software release or engine version."
    )
    model_version: Optional[str] = Field(
        default="v1.0",
        description="Engineering model formulation version."
    )
    engineering_model_id: str = Field(
        ...,
        description="Model family identifier (e.g. quarter_car, half_car, full_car, kinematics, tire_mf52)."
    )
    exchange_mode: ExchangeMode = Field(
        default=ExchangeMode.EXPORT,
        description="Exchange mode: EXPORT, IMPORT, or BIDIRECTIONAL."
    )
    parameters: Dict[str, ParameterValue] = Field(
        default_factory=dict,
        description="Mapped parameter values with units and dimensions."
    )
    coordinate_frame: Optional[CoordinateFrameDefinition] = Field(
        default=None,
        description="Active coordinate frame definition and engineering conventions."
    )
    operating_conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Operating environment conditions (e.g. ambient_temp_c, track_friction)."
    )
    input_artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="Input engineering files, geometry, or telemetry artifacts."
    )
    result_artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="Simulation output or result artifacts."
    )
    parameter_mappings: List[ParameterMapping] = Field(
        default_factory=list,
        description="Explicit mappings applied during the exchange."
    )
    conversions_applied: List[ConversionRecord] = Field(
        default_factory=list,
        description="Auditable log of unit and coordinate conversions performed."
    )
    unsupported_fields: List[str] = Field(
        default_factory=list,
        description="Fields present in external source that could not be mapped or represented."
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Exchange warnings or non-fatal limitations."
    )
    validation_status: ExchangeValidationStatus = Field(
        default=ExchangeValidationStatus.VALIDATED,
        description="Validation outcome."
    )
    created_at_utc: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        description="ISO-8601 UTC creation timestamp."
    )
    exported_at_utc: Optional[str] = Field(
        default=None,
        description="Timestamp of export operation."
    )
    imported_at_utc: Optional[str] = Field(
        default=None,
        description="Timestamp of import operation."
    )
    execution_metadata: ExecutionMetadata = Field(
        default_factory=ExecutionMetadata,
        description="Execution status and provenance."
    )

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        """Rejects unsupported exchange schema versions."""
        if v not in SUPPORTED_EXCHANGE_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported exchange schema version '{v}'. Supported versions: {sorted(SUPPORTED_EXCHANGE_SCHEMA_VERSIONS)}"
            )
        return v

    @model_validator(mode="after")
    def validate_manifest_semantics(self) -> "CanonicalExchangeManifest":
        """Performs semantic checks on manifest completeness and provenance."""
        # 1. Coordinate frame check
        if self.coordinate_frame is not None:
            c_status, c_reasons = validate_coordinate_frame(self.coordinate_frame)
            if c_status != FrameValidationStatus.VALID:
                for r in c_reasons:
                    if r not in self.warnings:
                        self.warnings.append(r)
                if self.validation_status == ExchangeValidationStatus.VALIDATED:
                    self.validation_status = ExchangeValidationStatus.VALID_WITH_WARNINGS

        # 2. Check for missing units on parameters
        for p_name, p_val in self.parameters.items():
            if p_val.unit is None or not p_val.unit.strip():
                warn = f"Parameter '{p_name}' has missing or empty unit specification."
                if warn not in self.warnings:
                    self.warnings.append(warn)
                if self.validation_status == ExchangeValidationStatus.VALIDATED:
                    self.validation_status = ExchangeValidationStatus.VALID_WITH_WARNINGS

        # 3. Provenance rules:
        # If exchange_mode is IMPORT, ensure provenance_origin is IMPORTED_EXTERNAL
        # and physical validation is False
        if self.exchange_mode == ExchangeMode.IMPORT:
            self.execution_metadata.provenance_origin = ResultProvenanceOrigin.IMPORTED_EXTERNAL
            self.execution_metadata.is_physically_validated = False
            # Raw import success does not equal validation success
            if self.validation_status == ExchangeValidationStatus.VALIDATED:
                self.validation_status = ExchangeValidationStatus.VALID_WITH_WARNINGS
                self.warnings.append("Imported artifact parsed successfully but is NOT physically validated.")

        # 4. If manifest_id is not set, compute it deterministically
        if not self.manifest_id:
            self.manifest_id = compute_canonical_manifest_hash(self)

        return self


def compute_canonical_manifest_hash(manifest: CanonicalExchangeManifest) -> str:
    """
    Computes a deterministic SHA-256 hash across canonical manifest contents using
    RFC 8785 canonical JSON sorting and formatting.

    Excludes transient non-semantic fields (e.g. self.manifest_id) to avoid circularity.
    """
    # Build dictionary of canonical semantic fields
    raw_dict = manifest.model_dump(mode="json")
    # Exclude manifest_id itself to prevent circular hash dependencies
    raw_dict.pop("manifest_id", None)

    # Convert to canonical deterministic JSON string (sorted keys, compact separators)
    canonical_json_str = json.dumps(raw_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json_str.encode("utf-8")).hexdigest()


def validate_canonical_manifest(
    data: Union[CanonicalExchangeManifest, Dict[str, Any]],
) -> Tuple[bool, List[str], Optional[CanonicalExchangeManifest]]:
    """
    Validates a canonical exchange manifest dictionary or object.

    Returns:
        (is_valid, error_or_warning_messages, parsed_manifest_or_None)
    """
    errors: List[str] = []

    if isinstance(data, CanonicalExchangeManifest):
        manifest = data
    elif isinstance(data, dict):
        # 1. Check schema version before full validation
        ver = data.get("schema_version", DEFAULT_EXCHANGE_SCHEMA_VERSION)
        if ver not in SUPPORTED_EXCHANGE_SCHEMA_VERSIONS:
            return (
                False,
                [f"Unsupported exchange schema version '{ver}'. Supported: {sorted(SUPPORTED_EXCHANGE_SCHEMA_VERSIONS)}"],
                None,
            )
        try:
            manifest = CanonicalExchangeManifest(**data)
        except Exception as e:
            return (False, [f"Manifest validation error: {str(e)}"], None)
    else:
        return (False, [f"Invalid manifest data type: {type(data)}"], None)

    if manifest.validation_status == ExchangeValidationStatus.INVALID:
        return (False, manifest.warnings, manifest)

    return (True, manifest.warnings, manifest)
