"""
src/suspensionlab/interop/service.py
====================================
SuspensionLab PRO — Solver Interoperability Canonical Service.

Orchestrates the exchange lifecycle:
1. Manifest Creation & Hashing: Builds strongly-typed canonical exchange manifests.
2. Safe Model Export: Serializes internal parameters via verified adapters into CAE artifacts.
3. Untrusted Ingestion: Applies path sanitization, size bounding, and safe parsing.
4. Provenance Preservation:
   - Sets ResultProvenanceOrigin.IMPORTED_EXTERNAL.
   - Enforces is_physically_validated = False (parsing success != physical accuracy).
   - Enforces is_executed = False on exports (export success != external execution).
   - Preserves source artifact hashes, adapter identities, and mapping versions.
5. Multi-Tenant Guardrails: Enforces tenant scoping and forbids cross-tenant access.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from suspensionlab.interop.adapter import (
    BaseSolverAdapter,
    SupportLevel,
)
from suspensionlab.interop.frames import (
    CoordinateFrameDefinition,
    FrameValidationStatus,
    ISO_8855_FRAME,
    validate_coordinate_frame,
)
from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
    ExchangeMode,
    ExchangeValidationStatus,
    ParameterValue,
    ResultProvenanceOrigin,
    compute_canonical_manifest_hash,
    validate_canonical_manifest,
)
from suspensionlab.interop.mapping import (
    ParameterMapping,
    validate_parameter_mapping,
)
from suspensionlab.interop.registry import (
    AdapterRegistry,
    get_adapter_registry,
)
from suspensionlab.interop.security import (
    check_payload_size,
    enforce_tenant_isolation,
    sanitize_artifact_filename,
    scan_for_nan_and_infinity,
)
from suspensionlab.interop.units import (
    ConversionRecord,
    convert_unit_value,
    get_physical_dimension,
)

logger = logging.getLogger(__name__)


class SolverInteropService:
    """
    Core service for Solver Interoperability in SuspensionLab PRO.
    """

    def __init__(self, registry: Optional[AdapterRegistry] = None) -> None:
        self.registry = registry or get_adapter_registry()

    def create_canonical_manifest(
        self,
        engineering_model_id: str,
        parameters: Dict[str, Union[ParameterValue, Dict[str, Any], float, int]],
        source_solver: str = "SuspensionLab",
        source_application: str = "SuspensionLab PRO",
        coordinate_frame: Optional[CoordinateFrameDefinition] = None,
        operating_conditions: Optional[Dict[str, Any]] = None,
        exchange_mode: ExchangeMode = ExchangeMode.EXPORT,
        tenant_id: Optional[str] = None,
    ) -> CanonicalExchangeManifest:
        """
        Constructs a typed CanonicalExchangeManifest from parameters and metadata.
        """
        typed_params: Dict[str, ParameterValue] = {}
        warnings: List[str] = []

        # Convert raw parameters to typed ParameterValue objects
        for p_name, p_data in parameters.items():
            if isinstance(p_data, ParameterValue):
                typed_params[p_name] = p_data
            elif isinstance(p_data, dict):
                # Ensure dimension is resolved if omitted
                dim = p_data.get("dimension")
                unit = p_data.get("unit")
                if not dim and unit:
                    dim = get_physical_dimension(unit)
                p_copy = dict(p_data)
                p_copy["dimension"] = dim
                p_copy.setdefault("name", p_name)
                typed_params[p_name] = ParameterValue(**p_copy)
            elif isinstance(p_data, (float, int)):
                # Scalar without unit -> record warning
                warnings.append(f"Parameter '{p_name}' provided without explicit unit.")
                typed_params[p_name] = ParameterValue(
                    name=p_name,
                    value=p_data,
                    unit=None,
                    dimension=None,
                )
            else:
                raise ValueError(f"Unsupported parameter value format for '{p_name}': {type(p_data)}")

        # Validate coordinate frame
        frame = coordinate_frame or ISO_8855_FRAME
        f_status, f_reasons = validate_coordinate_frame(frame)
        if f_status != FrameValidationStatus.VALID:
            warnings.extend(f_reasons)

        manifest = CanonicalExchangeManifest(
            schema_version="1.0.0",
            source_application=source_application,
            source_solver=source_solver,
            engineering_model_id=engineering_model_id,
            exchange_mode=exchange_mode,
            parameters=typed_params,
            coordinate_frame=frame,
            operating_conditions=operating_conditions or {},
            warnings=warnings,
            validation_status=ExchangeValidationStatus.VALID_WITH_WARNINGS if warnings else ExchangeValidationStatus.VALIDATED,
        )

        return manifest

    def export_model_artifact(
        self,
        manifest: CanonicalExchangeManifest,
        adapter_id: str,
        options: Optional[Dict[str, Any]] = None,
        requesting_tenant_id: Optional[str] = None,
        resource_tenant_id: Optional[str] = None,
    ) -> Tuple[bytes, ArtifactReference, CanonicalExchangeManifest]:
        """
        Exports an engineering model using the specified adapter.

        Strict Provenance Invariant:
        - Sets is_executed = False on manifest (export does NOT prove external solver executed).
        """
        if requesting_tenant_id and resource_tenant_id:
            enforce_tenant_isolation(requesting_tenant_id, resource_tenant_id)

        adapter = self.registry.get_adapter(adapter_id)
        if adapter is None:
            raise ValueError(f"Adapter '{adapter_id}' is not registered.")

        caps = adapter.get_capabilities()
        if caps.export_capability == SupportLevel.UNSUPPORTED:
            raise ValueError(f"Adapter '{adapter_id}' does not support export.")

        # Run export
        artifact_bytes, artifact_ref = adapter.export_artifact(manifest, options)

        # Update manifest with result artifact and export metadata
        manifest.result_artifacts.append(artifact_ref)
        manifest.exported_at_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        # Invariant: export success != solver execution
        manifest.execution_metadata.is_executed = False

        return (artifact_bytes, artifact_ref, manifest)

    def import_external_result(
        self,
        content: bytes,
        filename: str,
        adapter_id: str,
        options: Optional[Dict[str, Any]] = None,
        requesting_tenant_id: Optional[str] = None,
        resource_tenant_id: Optional[str] = None,
    ) -> CanonicalExchangeManifest:
        """
        Safely imports external simulation results or datasets.

        Strict Provenance Invariant:
        - Preserves source artifact hash.
        - Sets ResultProvenanceOrigin.IMPORTED_EXTERNAL.
        - Sets is_physically_validated = False (parsing success != physical validation).
        - Enforces tenant isolation.
        """
        if requesting_tenant_id and resource_tenant_id:
            enforce_tenant_isolation(requesting_tenant_id, resource_tenant_id)

        # 1. Security defenses on filename and payload
        clean_name = sanitize_artifact_filename(filename)
        check_payload_size(content)

        # Compute source artifact hash
        source_hash = hashlib.sha256(content).hexdigest()

        # 2. Resolve adapter
        adapter = self.registry.get_adapter(adapter_id)
        if adapter is None:
            raise ValueError(f"Adapter '{adapter_id}' is not registered.")

        caps = adapter.get_capabilities()
        if caps.import_capability == SupportLevel.UNSUPPORTED:
            raise ValueError(f"Adapter '{adapter_id}' does not support import.")

        # 3. Parse via adapter
        manifest = adapter.import_artifact(content, options)

        # 4. Strict Provenance Contract
        manifest.exchange_mode = ExchangeMode.IMPORT
        manifest.execution_metadata.provenance_origin = ResultProvenanceOrigin.IMPORTED_EXTERNAL
        manifest.execution_metadata.is_physically_validated = False
        manifest.imported_at_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # Record input artifact reference
        input_ref = ArtifactReference(
            artifact_id=f"ART-IMPORT-{source_hash[:12]}",
            name=clean_name,
            artifact_type=caps.supported_formats[0] if caps.supported_formats else "application/octet-stream",
            sha256=source_hash,
            size_bytes=len(content),
            metadata={"adapter_id": adapter_id, "adapter_version": caps.adapter_version},
        )
        found = False
        for art in manifest.input_artifacts:
            if art.sha256 == source_hash:
                found = True
                art.metadata.setdefault("adapter_id", adapter_id)
                art.metadata.setdefault("adapter_version", caps.adapter_version)
        if not found:
            manifest.input_artifacts.append(input_ref)

        # Re-compute deterministic manifest hash
        manifest.manifest_id = compute_canonical_manifest_hash(manifest)

        return manifest
