"""
src/suspensionlab/backend/api/routes/solver_interop_routes.py
=============================================================
SuspensionLab PRO — Solver Interoperability Operational API Router (Phase 7.2).

Exposes authenticated, tenant-isolated endpoints for:
1. Adapter capability discovery and inspection:
   - GET /api/v1/interop/adapters
   - GET /api/v1/interop/adapters/{adapter_id}
2. Secure solver artifact exchange operations:
   - POST /api/v1/interop/import (start persistent import)
   - POST /api/v1/interop/export (start persistent export)
   - GET /api/v1/interop/operations/{operation_id} (inspect operation)
   - GET /api/v1/interop/operations/{operation_id}/diagnostics (read diagnostics)
   - GET /api/v1/interop/operations/{operation_id}/artifact (download generated/ingested artifact)
3. Preflight validation & checks:
   - POST /api/v1/interop/manifests/validate
   - POST /api/v1/interop/mappings/validate
   - POST /api/v1/interop/units/check
   - POST /api/v1/interop/frames/check

Strict Epistemic Invariants:
- EXPORTED != EXECUTED (is_executed strictly False)
- IMPORTED != PHYSICALLY VALIDATED (is_physically_validated strictly False)
- SCHEMA VALID != ENGINEERING CORRECT
- METADATA PARSED != CO-SIMULATION PERFORMED
"""
from __future__ import annotations

import base64
import logging
import uuid
from typing import Any, Dict, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.solver_exchange import (
    ExchangeOperationState,
    ExchangeOperationType,
    ImmutableOperationError,
    InvalidStateTransitionError,
    SolverExchangeArtifact,
    SolverExchangeOperation,
)
from suspensionlab.backend.security.auth import UserContext, verify_api_key
from suspensionlab.backend.services.solver_exchange_service import SolverExchangeService
from suspensionlab.interop.adapter import AdapterCapability, SupportLevel
from suspensionlab.interop.frames import (
    CoordinateFrameDefinition,
    FrameValidationStatus,
    validate_coordinate_frame,
)
from suspensionlab.interop.manifest import (
    CanonicalExchangeManifest,
    validate_canonical_manifest,
)
from suspensionlab.interop.mapping import (
    ParameterMapping,
    validate_parameter_mapping,
)
from suspensionlab.interop.registry import get_adapter_registry
from suspensionlab.interop.security import (
    ContentMismatchSecurityError,
    ExecutableContentSecurityError,
    HashMismatchSecurityError,
    InteropSecurityError,
    PathTraversalSecurityError,
    ResourceExhaustionSecurityError,
    TenantIsolationError,
)
from suspensionlab.interop.units import (
    UnitCompatibilityStatus,
    check_unit_compatibility,
    convert_unit_value,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interop", tags=["Solver Interoperability"])
_service = SolverExchangeService()


# ── DTO SCHEMAS ───────────────────────────────────────────────────────────────

class UnitCheckRequest(BaseModel):
    unit_a: str = Field(..., description="First unit string.")
    unit_b: str = Field(..., description="Second unit string.")


class UnitCheckResponse(BaseModel):
    status: UnitCompatibilityStatus
    dimension: Optional[str] = None
    detail: Optional[str] = None


class ManifestValidationResponse(BaseModel):
    is_valid: bool
    warnings: List[str]
    manifest: Optional[Dict[str, Any]] = None


class MappingValidationResponse(BaseModel):
    is_valid: bool
    status: str
    is_dimensionally_compatible: bool
    warnings: List[str]


class ImportOperationRequest(BaseModel):
    adapter_id: str = Field(..., description="Target adapter identity (e.g. 'adapter-msc-adams-v1').")
    filename: str = Field(..., description="Artifact filename with extension (e.g. 'model.adm').")
    content: str = Field(..., description="File content as UTF-8 text or Base64 string.")
    is_base64: bool = Field(default=False, description="Set True if content is base64 encoded.")
    idempotency_key: Optional[str] = Field(default=None, description="Optional client idempotency key.")
    expected_sha256: Optional[str] = Field(default=None, description="Optional client-computed SHA-256 for tamper protection.")
    options: Optional[Dict[str, Any]] = Field(default=None, description="Adapter-specific options.")


class ExportOperationRequest(BaseModel):
    adapter_id: str = Field(..., description="Target adapter identity (e.g. 'adapter-canonical-json-v1').")
    target_format: str = Field(..., description="Target file extension (e.g. '.adm', '.json', '.m').")
    manifest: Dict[str, Any] = Field(..., description="Canonical exchange manifest dictionary.")
    idempotency_key: Optional[str] = Field(default=None, description="Optional client idempotency key.")
    options: Optional[Dict[str, Any]] = Field(default=None, description="Adapter-specific options.")


class OperationResponseDTO(BaseModel):
    id: str
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    user_id: str
    operation_type: str
    adapter_id: str
    adapter_version: str
    solver_name: str
    state: str
    input_artifact_id: Optional[str] = None
    output_artifact_id: Optional[str] = None
    canonical_manifest_version: str
    manifest_hash: Optional[str] = None
    coordinate_frame: Dict[str, Any]
    units_summary: Dict[str, Any]
    mapping_diagnostics: Dict[str, Any]
    validation_diagnostics: Dict[str, Any]
    failure_reason: Optional[str] = None
    idempotency_key: Optional[str] = None
    is_executed: bool = False
    is_physically_validated: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None


class DiagnosticsResponseDTO(BaseModel):
    operation_id: str
    operation_type: str
    state: str
    is_executed: bool
    is_physically_validated: bool
    coordinate_frame: Dict[str, Any]
    units_summary: Dict[str, Any]
    mapping_diagnostics: Dict[str, Any]
    validation_diagnostics: Dict[str, Any]
    failure_reason: Optional[str] = None


# ── ADAPTER CAPABILITY DISCOVERY ─────────────────────────────────────────────

@router.get("/adapters", response_model=List[AdapterCapability])
def list_solver_adapters(
    direction: Optional[str] = Query(None, description="Filter by 'import' or 'export' capability"),
) -> List[AdapterCapability]:
    """
    Returns list of registered solver interoperability adapters in deterministic order.
    Optionally filters by direction ('import' or 'export').
    """
    reg = get_adapter_registry()
    adapters = reg.list_adapters()
    if not direction:
        return adapters

    dir_lower = direction.lower().strip()
    if dir_lower == "import":
        return [a for a in adapters if a.import_capability != SupportLevel.UNSUPPORTED]
    elif dir_lower == "export":
        return [a for a in adapters if a.export_capability != SupportLevel.UNSUPPORTED]
    return adapters


@router.get("/adapters/{adapter_id}", response_model=AdapterCapability)
def get_solver_adapter(adapter_id: str) -> AdapterCapability:
    """
    Retrieves capability specifications for a specific registered adapter.
    """
    reg = get_adapter_registry()
    adapter = reg.get_adapter(adapter_id)
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Adapter '{adapter_id}' is not registered.",
        )
    return adapter.get_capabilities()


# ── OPERATIONAL EXCHANGE LIFECYCLE ───────────────────────────────────────────

@router.post("/import", response_model=OperationResponseDTO)
async def start_import_operation_endpoint(
    req: ImportOperationRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> OperationResponseDTO:
    """
    Starts a persistent, tenant-scoped solver import operation.
    Enforces path traversal, executable rejection, and content-extension verification.
    """
    try:
        if req.is_base64:
            try:
                content_bytes = base64.b64decode(req.content)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid base64 payload: {e}",
                )
        else:
            content_bytes = req.content.encode("utf-8")

        op = await _service.start_import_operation(
            db=db,
            user=user,
            filename=req.filename,
            content=content_bytes,
            adapter_id=req.adapter_id,
            idempotency_key=req.idempotency_key,
            expected_sha256=req.expected_sha256,
            options=req.options,
        )
        return OperationResponseDTO(**op.to_dict())

    except (ExecutableContentSecurityError, ContentMismatchSecurityError, HashMismatchSecurityError, PathTraversalSecurityError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ResourceExhaustionSecurityError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in solver import: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Import operation failed: {e}")


@router.post("/import/file", response_model=OperationResponseDTO)
async def upload_import_file_endpoint(
    adapter_id: str = Form(...),
    file: UploadFile = File(...),
    idempotency_key: Optional[str] = Form(None),
    expected_sha256: Optional[str] = Form(None),
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> OperationResponseDTO:
    """
    Starts a solver import operation using multipart/form-data file upload.
    """
    try:
        content_bytes = await file.read()
        op = await _service.start_import_operation(
            db=db,
            user=user,
            filename=file.filename or "upload.dat",
            content=content_bytes,
            adapter_id=adapter_id,
            idempotency_key=idempotency_key,
            expected_sha256=expected_sha256,
        )
        return OperationResponseDTO(**op.to_dict())
    except (ExecutableContentSecurityError, ContentMismatchSecurityError, HashMismatchSecurityError, PathTraversalSecurityError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ResourceExhaustionSecurityError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in file upload import: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"File import failed: {e}")


@router.post("/export", response_model=OperationResponseDTO)
async def start_export_operation_endpoint(
    req: ExportOperationRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> OperationResponseDTO:
    """
    Starts a persistent, tenant-scoped solver export operation from a canonical manifest.
    Strict Invariant: export success != solver execution (is_executed strictly False).
    """
    try:
        op = await _service.start_export_operation(
            db=db,
            user=user,
            manifest_payload=req.manifest,
            adapter_id=req.adapter_id,
            target_format=req.target_format,
            idempotency_key=req.idempotency_key,
            options=req.options,
        )
        return OperationResponseDTO(**op.to_dict())

    except (ExecutableContentSecurityError, PathTraversalSecurityError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ResourceExhaustionSecurityError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in solver export: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Export operation failed: {e}")


@router.get("/operations/{operation_id}", response_model=OperationResponseDTO)
async def get_operation_endpoint(
    operation_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> OperationResponseDTO:
    """
    Inspects an exchange operation record with full epistemic and provenance metadata.
    Enforces tenant isolation.
    """
    try:
        op_uuid = uuid.UUID(operation_id)
        op = await _service.get_operation(db=db, operation_id=op_uuid, user=user)
        return OperationResponseDTO(**op.to_dict())
    except (ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Operation '{operation_id}' not found.")
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/operations/{operation_id}/diagnostics", response_model=DiagnosticsResponseDTO)
async def get_operation_diagnostics_endpoint(
    operation_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> DiagnosticsResponseDTO:
    """
    Retrieves detailed mapping and validation diagnostics for an exchange operation.
    """
    try:
        op_uuid = uuid.UUID(operation_id)
        op = await _service.get_operation(db=db, operation_id=op_uuid, user=user)
        return DiagnosticsResponseDTO(
            operation_id=str(op.id),
            operation_type=op.operation_type,
            state=op.state,
            is_executed=bool(op.is_executed),
            is_physically_validated=bool(op.is_physically_validated),
            coordinate_frame=op.coordinate_frame or {},
            units_summary=op.units_summary or {},
            mapping_diagnostics=op.mapping_diagnostics or {},
            validation_diagnostics=op.validation_diagnostics or {},
            failure_reason=op.failure_reason,
        )
    except (ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Operation '{operation_id}' not found.")
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/operations/{operation_id}/artifact")
async def download_operation_artifact_endpoint(
    operation_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> Response:
    """
    Downloads the authorized generated export or ingested source artifact.
    Re-verifies on-disk SHA-256 hash against persisted metadata.
    """
    try:
        op_uuid = uuid.UUID(operation_id)
        artifact, content_bytes = await _service.get_operation_artifact(db=db, operation_id=op_uuid, user=user)

        headers = {
            "Content-Disposition": f'attachment; filename="{artifact.artifact_name}"',
            "X-Artifact-Hash-SHA256": artifact.sha256_hash,
            "X-Artifact-Size-Bytes": str(artifact.size_bytes),
            "X-Artifact-Direction": artifact.direction,
        }
        return Response(
            content=content_bytes,
            media_type=artifact.mime_type or "application/octet-stream",
            headers=headers,
        )
    except (ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Artifact for operation '{operation_id}' not found.")
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except HashMismatchSecurityError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ── PREFLIGHT VALIDATION UTILITIES ───────────────────────────────────────────

@router.post("/manifests/validate", response_model=ManifestValidationResponse)
def validate_manifest(payload: Dict[str, Any]) -> ManifestValidationResponse:
    """
    Validates a canonical exchange manifest against schema version,
    units, coordinate frames, and numerical safety constraints.
    """
    is_valid, warnings, manifest_obj = validate_canonical_manifest(payload)
    return ManifestValidationResponse(
        is_valid=is_valid,
        warnings=warnings,
        manifest=manifest_obj.model_dump(mode="json") if manifest_obj else None,
    )


@router.post("/mappings/validate", response_model=MappingValidationResponse)
def validate_mapping(mapping: ParameterMapping) -> MappingValidationResponse:
    """
    Validates parameter mapping against authoritative models and dimensions.
    """
    is_valid, warnings = validate_parameter_mapping(mapping)
    return MappingValidationResponse(
        is_valid=is_valid,
        status=mapping.status.value,
        is_dimensionally_compatible=mapping.is_dimensionally_compatible,
        warnings=warnings,
    )


@router.post("/units/check", response_model=UnitCheckResponse)
def check_units(req: UnitCheckRequest) -> UnitCheckResponse:
    """
    Checks dimensional compatibility between two unit declarations.
    """
    comp_status, detail = check_unit_compatibility(req.unit_a, req.unit_b)
    dim = detail if comp_status in (UnitCompatibilityStatus.IDENTICAL, UnitCompatibilityStatus.CONVERTIBLE) else None
    return UnitCheckResponse(
        status=comp_status,
        dimension=dim,
        detail=detail,
    )


@router.post("/frames/check")
def check_frame(frame: CoordinateFrameDefinition) -> Dict[str, Any]:
    """
    Checks coordinate frame orthogonality and handedness consistency.
    """
    f_status, reasons = validate_coordinate_frame(frame)
    return {
        "status": f_status.value,
        "is_valid": f_status == FrameValidationStatus.VALID,
        "reasons": reasons,
    }
