"""
backend/services/solver_exchange_service.py
===========================================
SuspensionLab PRO — Phase 7.2 Solver Interoperability Persistent Exchange Service.

Orchestrates tenant-scoped solver artifact exchange operations:
- Ingestion of supported solver files (JSON, MSC Adams .adm, PAC2002 .tir, FMI .xml).
- Export to supported solver files (JSON, MSC Adams .adm/.cmd/.py, MATLAB .m, PAC2002 .tir, FMI .xml).
- Immutable Finite State Machine transitions (PENDING -> VALIDATING -> TRANSFORMING -> COMPLETED / REJECTED / FAILED).
- Sandboxed artifact storage with path traversal, extension mismatch, and hash verification defenses.
- Strict tenant isolation and cross-tenant access denial.
- Truthful epistemic bounds:
    EXPORTED != EXECUTED (is_executed strictly False)
    IMPORTED != PHYSICALLY VALIDATED (is_physically_validated strictly False)
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import os
import pathlib
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.solver_exchange import (
    ArtifactDirection,
    ExchangeOperationState,
    ExchangeOperationType,
    ImmutableOperationError,
    InvalidStateTransitionError,
    SolverExchangeArtifact,
    SolverExchangeOperation,
    TERMINAL_OPERATION_STATES,
)
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.interop.adapter import BaseSolverAdapter, SupportLevel
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
from suspensionlab.interop.mapping import ParameterMapping, validate_parameter_mapping
from suspensionlab.interop.registry import AdapterRegistry, get_adapter_registry
from suspensionlab.interop.security import (
    ContentMismatchSecurityError,
    ExecutableContentSecurityError,
    HashMismatchSecurityError,
    InteropSecurityError,
    PathTraversalSecurityError,
    ResourceExhaustionSecurityError,
    TenantIsolationError,
    check_payload_size,
    enforce_tenant_isolation,
    sanitize_artifact_filename,
    verify_content_extension_match,
    verify_safe_path,
)

logger = logging.getLogger(__name__)

ARTIFACT_STORAGE_ROOT = (pathlib.Path("data") / "interop_artifacts").resolve()


def _ensure_storage_dir() -> pathlib.Path:
    ARTIFACT_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_STORAGE_ROOT


class SolverExchangeService:
    """
    Service managing persistent solver interoperability exchange operations.
    """

    def __init__(self, registry: Optional[AdapterRegistry] = None) -> None:
        self.registry = registry or get_adapter_registry()
        self.storage_root = _ensure_storage_dir()

    def _check_tenant_access(
        self,
        user: UserContext,
        resource_user_id: uuid.UUID,
        resource_team_id: Optional[uuid.UUID],
        resource_org_id: Optional[uuid.UUID],
    ) -> None:
        """
        Enforces tenant isolation between requesting user and persisted resource.
        """
        if user.is_admin:
            return

        user_uid_str = str(user.user_id)
        if user_uid_str == str(resource_user_id):
            return

        if user.team_id and resource_team_id and str(user.team_id) == str(resource_team_id):
            return

        if (
            user.organization_id
            and resource_org_id
            and str(user.organization_id) == str(resource_org_id)
            and getattr(user, "org_role", None) in ("ORG_ADMIN", "ADMIN")
        ):
            return

        raise TenantIsolationError(
            f"Access denied: user '{user.user_id}' cannot access solver exchange resource owned by '{resource_user_id}'."
        )

    def _get_tenant_storage_path(
        self,
        user: UserContext,
        artifact_id: uuid.UUID,
        filename: str,
    ) -> pathlib.Path:
        """
        Calculates safe sandboxed filesystem path for artifact storage.
        """
        tenant_folder = str(user.team_id) if user.team_id else str(user.user_id)
        target_dir = self.storage_root / tenant_folder / str(artifact_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / filename
        return verify_safe_path(target_file, self.storage_root)

    async def start_import_operation(
        self,
        db: AsyncSession,
        user: UserContext,
        filename: str,
        content: bytes,
        adapter_id: str,
        idempotency_key: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> SolverExchangeOperation:
        """
        Executes a persistent, auditable solver import operation.
        """
        user_uuid = uuid.UUID(str(user.user_id))
        team_uuid = uuid.UUID(str(user.team_id)) if user.team_id else None
        org_uuid = uuid.UUID(str(user.organization_id)) if user.organization_id else None

        # 1. Idempotency Check
        if idempotency_key:
            stmt = select(SolverExchangeOperation).where(
                SolverExchangeOperation.user_id == user_uuid,
                SolverExchangeOperation.idempotency_key == idempotency_key,
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        # 2. Filename and Payload Size Sanitization
        clean_name = sanitize_artifact_filename(filename)
        check_payload_size(content)

        actual_hash = hashlib.sha256(content).hexdigest()

        # 3. Hash verification (tamper protection)
        if expected_sha256 and expected_sha256.lower().strip() != actual_hash.lower().strip():
            raise HashMismatchSecurityError(
                f"Content hash mismatch: expected '{expected_sha256}', but computed '{actual_hash}'."
            )

        # 4. Content / Extension match verification
        verify_content_extension_match(content, clean_name)

        # 5. Resolve Adapter & Capabilities
        adapter = self.registry.get_adapter(adapter_id)
        if adapter is None:
            raise ValueError(f"Adapter '{adapter_id}' is not registered.")

        caps = adapter.get_capabilities()
        if caps.import_capability == SupportLevel.UNSUPPORTED:
            raise ValueError(
                f"Adapter '{adapter_id}' does not support import (SupportLevel.UNSUPPORTED)."
            )

        # Verify extension is explicitly supported for import
        ext = pathlib.Path(clean_name).suffix.lower()
        if ext not in caps.supported_import_formats and clean_name not in caps.supported_import_formats:
            raise ValueError(
                f"Format '{ext}' is not supported for import by adapter '{adapter_id}'. "
                f"Supported import formats: {caps.supported_import_formats}"
            )

        # 6. Initialize Persistent Operation in PENDING state
        operation = SolverExchangeOperation(
            id=uuid.uuid4(),
            organization_id=org_uuid,
            team_id=team_uuid,
            user_id=user_uuid,
            operation_type=ExchangeOperationType.IMPORT.value,
            adapter_id=caps.adapter_id,
            adapter_version=caps.adapter_version,
            solver_name=caps.solver_name,
            state=ExchangeOperationState.PENDING.value,
            canonical_manifest_version="1.0.0",
            idempotency_key=idempotency_key,
            is_executed=False,
            is_physically_validated=False,
        )
        db.add(operation)
        await db.flush()

        # 7. State Transition: PENDING -> VALIDATING
        operation.transition_to(ExchangeOperationState.VALIDATING)

        import_opts = dict(options or {})
        import_opts["filename"] = clean_name
        import_opts["format"] = ext

        is_valid, validation_msgs = adapter.validate_input(content, import_opts)
        if not is_valid:
            operation.transition_to(
                ExchangeOperationState.REJECTED,
                failure_reason="; ".join(validation_msgs),
            )
            operation.validation_diagnostics = {
                "is_valid": False,
                "errors": validation_msgs,
                "warnings": [],
            }
            await db.commit()
            return operation

        # 8. State Transition: VALIDATING -> TRANSFORMING
        operation.transition_to(ExchangeOperationState.TRANSFORMING)

        # 9. Persist Input Artifact to Sandboxed Storage
        artifact_id = uuid.uuid4()
        storage_path = self._get_tenant_storage_path(user, artifact_id, clean_name)
        with open(storage_path, "wb") as f_out:
            f_out.write(content)

        input_artifact = SolverExchangeArtifact(
            id=artifact_id,
            organization_id=org_uuid,
            team_id=team_uuid,
            user_id=user_uuid,
            artifact_name=clean_name,
            file_format=ext,
            mime_type=caps.supported_formats[0] if caps.supported_formats else "application/octet-stream",
            size_bytes=len(content),
            sha256_hash=actual_hash,
            storage_path=str(storage_path),
            direction=ArtifactDirection.INPUT.value,
        )
        db.add(input_artifact)
        await db.flush()

        operation.input_artifact_id = input_artifact.id

        # 10. Perform Ingestion / Manifest Generation
        try:
            manifest = adapter.import_artifact(content, import_opts)

            # Strict Provenance Invariant Enforcement
            manifest.exchange_mode = ExchangeMode.IMPORT
            manifest.execution_metadata.provenance_origin = ResultProvenanceOrigin.IMPORTED_EXTERNAL
            manifest.execution_metadata.is_physically_validated = False
            manifest.execution_metadata.is_executed = False
            manifest.imported_at_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            manifest_hash = compute_canonical_manifest_hash(manifest)

            operation.manifest_hash = manifest_hash
            operation.coordinate_frame = manifest.coordinate_frame.model_dump(mode="json") if manifest.coordinate_frame else {}
            operation.units_summary = {
                p.name: {"unit": p.unit, "dimension": p.dimension}
                for p in manifest.parameters.values()
            }
            operation.mapping_diagnostics = {
                "imported_parameters_count": len(manifest.parameters),
                "parameter_names": sorted(list(manifest.parameters.keys())),
                "unmapped": [],
                "lossy": [],
                "provenance_origin": ResultProvenanceOrigin.IMPORTED_EXTERNAL.value,
                "source_type": "EXTERNALLY_IMPORTED_SOURCE",
                "is_executed": False,
                "is_physically_validated": False,
            }

            operation.validation_diagnostics = {
                "is_valid": True,
                "warnings": manifest.warnings,
                "errors": [],
            }

            # 11. State Transition: TRANSFORMING -> COMPLETED
            operation.transition_to(ExchangeOperationState.COMPLETED)
            operation.is_executed = False
            operation.is_physically_validated = False

            await db.commit()
            return operation

        except Exception as exc:
            logger.exception("Solver import transformation failed: %s", exc)
            operation.transition_to(
                ExchangeOperationState.FAILED,
                failure_reason=f"Transformation error: {exc}",
            )
            await db.commit()
            return operation

    async def start_export_operation(
        self,
        db: AsyncSession,
        user: UserContext,
        manifest_payload: Dict[str, Any],
        adapter_id: str,
        target_format: str,
        idempotency_key: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> SolverExchangeOperation:
        """
        Executes a persistent, auditable solver export operation from a canonical manifest.
        """
        user_uuid = uuid.UUID(str(user.user_id))
        team_uuid = uuid.UUID(str(user.team_id)) if user.team_id else None
        org_uuid = uuid.UUID(str(user.organization_id)) if user.organization_id else None

        # 1. Idempotency Check
        if idempotency_key:
            stmt = select(SolverExchangeOperation).where(
                SolverExchangeOperation.user_id == user_uuid,
                SolverExchangeOperation.idempotency_key == idempotency_key,
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        # 2. Resolve Adapter & Capabilities
        adapter = self.registry.get_adapter(adapter_id)
        if adapter is None:
            raise ValueError(f"Adapter '{adapter_id}' is not registered.")

        caps = adapter.get_capabilities()
        if caps.export_capability == SupportLevel.UNSUPPORTED:
            raise ValueError(
                f"Adapter '{adapter_id}' does not support export (SupportLevel.UNSUPPORTED)."
            )

        norm_target_format = target_format.lower().strip()
        if norm_target_format and not norm_target_format.startswith("."):
            norm_target_format = f".{norm_target_format}"

        if norm_target_format not in caps.supported_export_formats and target_format not in caps.supported_export_formats:
            raise ValueError(
                f"Format '{target_format}' is not supported for export by adapter '{adapter_id}'. "
                f"Supported export formats: {caps.supported_export_formats}"
            )

        # 3. Initialize Persistent Operation in PENDING state
        operation = SolverExchangeOperation(
            id=uuid.uuid4(),
            organization_id=org_uuid,
            team_id=team_uuid,
            user_id=user_uuid,
            operation_type=ExchangeOperationType.EXPORT.value,
            adapter_id=caps.adapter_id,
            adapter_version=caps.adapter_version,
            solver_name=caps.solver_name,
            state=ExchangeOperationState.PENDING.value,
            canonical_manifest_version="1.0.0",
            idempotency_key=idempotency_key,
            is_executed=False,
            is_physically_validated=False,
        )
        db.add(operation)
        await db.flush()

        # 4. State Transition: PENDING -> VALIDATING
        operation.transition_to(ExchangeOperationState.VALIDATING)

        is_valid_manifest, manifest_warnings, manifest_obj = validate_canonical_manifest(manifest_payload)
        if not is_valid_manifest or manifest_obj is None:
            operation.transition_to(
                ExchangeOperationState.REJECTED,
                failure_reason="Canonical manifest validation failed.",
            )
            operation.validation_diagnostics = {
                "is_valid": False,
                "errors": ["Invalid canonical manifest schema or numerical values."],
                "warnings": manifest_warnings,
            }
            await db.commit()
            return operation

        # 5. State Transition: VALIDATING -> TRANSFORMING
        operation.transition_to(ExchangeOperationState.TRANSFORMING)

        try:
            export_opts = dict(options or {})
            export_opts["format"] = norm_target_format

            artifact_bytes, artifact_ref = adapter.export_artifact(manifest_obj, export_opts)

            # Strict Provenance Invariant: export success != solver execution
            manifest_obj.execution_metadata.is_executed = False
            manifest_obj.exported_at_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            clean_filename = sanitize_artifact_filename(
                artifact_ref.name or f"export_{manifest_obj.engineering_model_id}{norm_target_format}"
            )

            # Persist output artifact to sandboxed storage
            artifact_id = uuid.uuid4()
            storage_path = self._get_tenant_storage_path(user, artifact_id, clean_filename)
            with open(storage_path, "wb") as f_out:
                f_out.write(artifact_bytes)

            output_artifact = SolverExchangeArtifact(
                id=artifact_id,
                organization_id=org_uuid,
                team_id=team_uuid,
                user_id=user_uuid,
                artifact_name=clean_filename,
                file_format=norm_target_format,
                mime_type=artifact_ref.artifact_type,
                size_bytes=len(artifact_bytes),
                sha256_hash=artifact_ref.sha256,
                storage_path=str(storage_path),
                direction=ArtifactDirection.OUTPUT.value,
            )
            db.add(output_artifact)
            await db.flush()

            manifest_hash = compute_canonical_manifest_hash(manifest_obj)

            operation.output_artifact_id = output_artifact.id
            operation.manifest_hash = manifest_hash
            operation.coordinate_frame = manifest_obj.coordinate_frame.model_dump(mode="json") if manifest_obj.coordinate_frame else {}
            operation.units_summary = {
                p.name: {"unit": p.unit, "dimension": p.dimension}
                for p in manifest_obj.parameters.values()
            }
            prov_origin = manifest_obj.execution_metadata.provenance_origin.value
            operation.mapping_diagnostics = {
                "exported_parameters_count": len(manifest_obj.parameters),
                "parameter_names": sorted(list(manifest_obj.parameters.keys())),
                "target_format": norm_target_format,
                "known_limitations": caps.known_limitations,
                "provenance_origin": prov_origin,
                "source_type": (
                    "INTERNAL_SOURCE_MODEL"
                    if manifest_obj.execution_metadata.provenance_origin == ResultProvenanceOrigin.NATIVE_SOLVER
                    else "TRANSFORMED_DERIVATIVE"
                ),
                "is_executed": False,
                "is_physically_validated": False,
            }

            operation.validation_diagnostics = {
                "is_valid": True,
                "warnings": manifest_warnings + manifest_obj.warnings,
                "errors": [],
            }

            # 6. State Transition: TRANSFORMING -> COMPLETED
            operation.transition_to(ExchangeOperationState.COMPLETED)
            operation.is_executed = False
            operation.is_physically_validated = False

            await db.commit()
            return operation

        except Exception as exc:
            logger.exception("Solver export transformation failed: %s", exc)
            operation.transition_to(
                ExchangeOperationState.FAILED,
                failure_reason=f"Export transformation error: {exc}",
            )
            await db.commit()
            return operation

    async def get_operation(
        self,
        db: AsyncSession,
        operation_id: uuid.UUID,
        user: UserContext,
    ) -> SolverExchangeOperation:
        """
        Retrieves a solver exchange operation by ID with strict tenant isolation.
        """
        stmt = select(SolverExchangeOperation).where(SolverExchangeOperation.id == operation_id)
        result = await db.execute(stmt)
        operation = result.scalar_one_or_none()
        if operation is None:
            raise KeyError(f"Operation '{operation_id}' not found.")

        self._check_tenant_access(
            user=user,
            resource_user_id=operation.user_id,
            resource_team_id=operation.team_id,
            resource_org_id=operation.organization_id,
        )
        return operation

    async def get_operation_artifact(
        self,
        db: AsyncSession,
        operation_id: uuid.UUID,
        user: UserContext,
    ) -> Tuple[SolverExchangeArtifact, bytes]:
        """
        Retrieves generated or ingested artifact bytes with tenant verification
        and on-disk SHA-256 hash integrity validation.
        """
        op = await self.get_operation(db, operation_id, user)

        artifact_id = op.output_artifact_id or op.input_artifact_id
        if artifact_id is None:
            raise KeyError(f"No artifact associated with operation '{operation_id}'.")

        stmt = select(SolverExchangeArtifact).where(SolverExchangeArtifact.id == artifact_id)
        result = await db.execute(stmt)
        artifact = result.scalar_one_or_none()
        if artifact is None:
            raise KeyError(f"Artifact '{artifact_id}' record not found.")

        self._check_tenant_access(
            user=user,
            resource_user_id=artifact.user_id,
            resource_team_id=artifact.team_id,
            resource_org_id=artifact.organization_id,
        )

        storage_path = pathlib.Path(artifact.storage_path)
        if not storage_path.exists():
            raise FileNotFoundError(f"Artifact file '{storage_path}' is missing from storage.")

        with open(storage_path, "rb") as f_in:
            data = f_in.read()

        # On-disk hash integrity check (tamper detection)
        computed_hash = hashlib.sha256(data).hexdigest()
        if computed_hash != artifact.sha256_hash:
            raise HashMismatchSecurityError(
                f"Artifact file on disk was modified or corrupted: expected '{artifact.sha256_hash}', got '{computed_hash}'."
            )

        return artifact, data
