"""
src/suspensionlab/interop/adapter.py
====================================
SuspensionLab PRO — Solver Adapter Protocol & Capability Contracts.

Defines the typed adapter interface and capability models for integrating
external engineering solvers, CAE tools, and data exchange formats.

Key Invariants:
1. Truthful Reporting: An adapter reports what it ACTUALLY supports.
   A capability is NOT reported as SUPPORTED until verified parsing, validation,
   or export paths exist and pass targeted tests.
2. Honest Dependencies: Commercial or proprietary dependencies (e.g. MSC Adams Solver,
   MATLAB runtime, IPG CarMaker) report UNAVAILABLE_DEPENDENCY or is_available=False
   when not installed.
3. Distinction of Levels:
   - SUPPORTED: Fully operational and verified.
   - PARTIALLY_SUPPORTED: Certain formats or subsets supported (e.g. metadata only).
   - UNSUPPORTED: Not supported or deliberately disabled.
   - UNAVAILABLE_DEPENDENCY: Solver/engine license or runtime executable not present.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
)
from suspensionlab.interop.mapping import (
    ParameterMapping,
    validate_parameter_mapping,
)


class SupportLevel(str, Enum):
    """Granular operational support classification."""
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNAVAILABLE_DEPENDENCY = "UNAVAILABLE_DEPENDENCY"


class DataCategory(str, Enum):
    """Domain data categories handled during exchange."""
    PARAMETERS = "PARAMETERS"
    GEOMETRY = "GEOMETRY"
    KINEMATICS = "KINEMATICS"
    TIME_SERIES = "TIME_SERIES"
    MODAL_STATES = "MODAL_STATES"
    TIRE_PROPERTY = "TIRE_PROPERTY"
    FREQUENCY_RESPONSE = "FREQUENCY_RESPONSE"


class VerificationStatus(str, Enum):
    """Verification and validation status of the adapter implementation."""
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    EXPERIMENTAL = "EXPERIMENTAL"


class DependencyRequirement(BaseModel):
    """Specification of an external tool, runtime, or license dependency."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    name: str = Field(..., description="Name of external software or library.")
    version_spec: Optional[str] = Field(default=None, description="Minimum or compatible version.")
    is_available: bool = Field(default=False, description="True if installed and verified on host.")
    description: str = Field(default="", description="Role of the dependency.")


class AdapterCapability(BaseModel):
    """
    Deterministic capability profile of an external solver adapter.
    """
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    adapter_id: str = Field(..., description="Unique immutable adapter identity (e.g. 'adapter-msc-adams-v1').")
    adapter_version: str = Field(..., description="Adapter implementation version (e.g. '1.0.0').")
    solver_name: str = Field(..., description="Target solver (e.g. 'MSC_ADAMS', 'MATLAB_SIMULINK', 'PAC2002').")
    supported_formats: List[str] = Field(..., description="File extensions or MIME types (e.g. ['.adm', '.cmd']).")
    supported_import_formats: List[str] = Field(default_factory=list, description="Explicit formats supported for import.")
    supported_export_formats: List[str] = Field(default_factory=list, description="Explicit formats supported for export.")
    supported_versions: List[str] = Field(default_factory=list, description="Supported solver/model versions.")
    supported_categories: List[DataCategory] = Field(..., description="Supported data categories.")
    unit_restrictions: List[str] = Field(default_factory=list, description="Mandatory unit requirements.")
    frame_restrictions: List[str] = Field(default_factory=list, description="Mandatory coordinate frames (e.g. ISO_8855).")
    import_capability: SupportLevel = Field(default=SupportLevel.UNSUPPORTED, description="Import support level.")
    export_capability: SupportLevel = Field(default=SupportLevel.UNSUPPORTED, description="Export support level.")
    required_dependencies: List[DependencyRequirement] = Field(default_factory=list, description="Host dependencies.")
    known_limitations: List[str] = Field(default_factory=list, description="Explicit technical limitations.")
    verification_status: VerificationStatus = Field(default=VerificationStatus.VERIFIED, description="Verification state.")


class BaseSolverAdapter(ABC):
    """
    Abstract base interface for solver interoperability adapters.
    """

    @abstractmethod
    def get_capabilities(self) -> AdapterCapability:
        """Returns the truthful, deterministic capability profile of the adapter."""
        pass

    @abstractmethod
    def get_supported_versions(self) -> List[str]:
        """Returns list of supported external solver or schema versions."""
        pass

    @abstractmethod
    def validate_input(self, content: Union[str, bytes, Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str]]:
        """
        Validates raw external artifact or configuration before ingestion.

        Returns:
            (is_valid, validation_messages)
        """
        pass

    @abstractmethod
    def export_artifact(
        self,
        manifest: CanonicalExchangeManifest,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, ArtifactReference]:
        """
        Exports a canonical exchange manifest into external solver format.

        Returns:
            (artifact_bytes, artifact_reference)
        """
        pass

    @abstractmethod
    def import_artifact(
        self,
        content: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> CanonicalExchangeManifest:
        """
        Parses external solver dataset into a CanonicalExchangeManifest.

        Strict Provenance Invariant:
        - ResultProvenanceOrigin must be IMPORTED_EXTERNAL.
        - is_physically_validated must be False.
        """
        pass

    def validate_mapping(self, mapping: ParameterMapping) -> Tuple[bool, List[str]]:
        """Validates parameter mapping compatibility with this adapter's solver."""
        return validate_parameter_mapping(mapping)

    def normalize_results(self, raw_result: Any) -> Dict[str, Any]:
        """Normalizes external raw simulation output into standard SuspensionLab metrics dict."""
        return {}
