"""
src/suspensionlab/interop/adapters/canonical_json.py
====================================================
Canonical JSON Adapter for SuspensionLab PRO Solver Interoperability.

Bidirectional, reference adapter providing lossless serialization and ingestion
of CanonicalExchangeManifest in standard JSON.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple, Union

from suspensionlab.interop.adapter import (
    AdapterCapability,
    BaseSolverAdapter,
    DataCategory,
    DependencyRequirement,
    SupportLevel,
    VerificationStatus,
)
from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
    ExchangeMode,
    ExchangeValidationStatus,
    ResultProvenanceOrigin,
    validate_canonical_manifest,
)
from suspensionlab.interop.security import safe_parse_json, check_payload_size


class CanonicalJsonAdapter(BaseSolverAdapter):
    """
    Standard lossless JSON adapter for CanonicalExchangeManifest exchange.
    """

    ADAPTER_ID = "adapter-canonical-json-v1"
    ADAPTER_VERSION = "1.0.0"

    def get_capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            adapter_id=self.ADAPTER_ID,
            adapter_version=self.ADAPTER_VERSION,
            solver_name="CANONICAL_JSON",
            supported_formats=[".json", "application/json"],
            supported_import_formats=[".json", "application/json"],
            supported_export_formats=[".json", "application/json"],
            supported_versions=["1.0.0"],
            supported_categories=[
                DataCategory.PARAMETERS,
                DataCategory.GEOMETRY,
                DataCategory.KINEMATICS,
                DataCategory.TIME_SERIES,
                DataCategory.MODAL_STATES,
                DataCategory.TIRE_PROPERTY,
                DataCategory.FREQUENCY_RESPONSE,
            ],
            unit_restrictions=[],
            frame_restrictions=[],
            import_capability=SupportLevel.SUPPORTED,
            export_capability=SupportLevel.SUPPORTED,
            required_dependencies=[
                DependencyRequirement(
                    name="python-json",
                    version_spec=">=3.10",
                    is_available=True,
                    description="Standard Python JSON parsing library.",
                )
            ],
            known_limitations=[],
            verification_status=VerificationStatus.VERIFIED,
        )

    def get_supported_versions(self) -> List[str]:
        return ["1.0.0"]

    def validate_input(
        self,
        content: Union[str, bytes, Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        try:
            if isinstance(content, (str, bytes)):
                parsed = safe_parse_json(content)
            elif isinstance(content, dict):
                parsed = content
            else:
                return (False, [f"Invalid input type: {type(content)}"])

            is_valid, warnings, _ = validate_canonical_manifest(parsed)
            return (is_valid, warnings)
        except Exception as e:
            return (False, [f"JSON validation failed: {str(e)}"])

    def export_artifact(
        self,
        manifest: CanonicalExchangeManifest,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, ArtifactReference]:
        raw_dict = manifest.model_dump(mode="json")
        json_bytes = json.dumps(raw_dict, indent=2, sort_keys=True).encode("utf-8")
        sha = hashlib.sha256(json_bytes).hexdigest()

        artifact_ref = ArtifactReference(
            artifact_id=f"ART-JSON-{sha[:12]}",
            name="canonical_exchange_manifest.json",
            artifact_type="application/json",
            sha256=sha,
            size_bytes=len(json_bytes),
            metadata={"schema_version": manifest.schema_version, "adapter": self.ADAPTER_ID},
        )
        return (json_bytes, artifact_ref)

    def import_artifact(
        self,
        content: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> CanonicalExchangeManifest:
        check_payload_size(content)
        parsed = safe_parse_json(content)

        if not isinstance(parsed, dict):
            raise ValueError("Parsed JSON payload is not an object.")

        # Construct manifest with IMPORT mode and verify strict provenance
        parsed["exchange_mode"] = ExchangeMode.IMPORT.value
        manifest = CanonicalExchangeManifest(**parsed)

        # Enforce provenance boundaries
        manifest.execution_metadata.provenance_origin = ResultProvenanceOrigin.IMPORTED_EXTERNAL
        manifest.execution_metadata.is_physically_validated = False
        if manifest.validation_status == ExchangeValidationStatus.VALIDATED:
            manifest.validation_status = ExchangeValidationStatus.VALID_WITH_WARNINGS
            manifest.warnings.append("Imported artifact parsed successfully but is NOT physically validated.")

        return manifest
