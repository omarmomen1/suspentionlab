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
from sqlalchemy import select
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
from suspensionlab.backend.database.models.solver_execution import (
    ExecutionJobState,
    ImmutableExecutionError,
    InvalidExecutionStateTransitionError,
    SolverExecutionJob,
)
from suspensionlab.backend.security.auth import UserContext, verify_api_key
from suspensionlab.backend.services.solver_exchange_service import SolverExchangeService
from suspensionlab.backend.services.solver_execution_service import (
    ExecutionJobNotFoundError,
    RuntimeUnavailableError,
    SolverExecutionService,
)
from suspensionlab.interop.adapter import AdapterCapability, SupportLevel
from suspensionlab.interop.execution.runtimes import SolverRuntimeRegistry
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
_exec_service = SolverExecutionService()


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


class ExecuteJobRequest(BaseModel):
    solver_name: str = Field(..., description="Target solver runtime (e.g. 'FMI_COSIMULATION', 'EXTERNAL_CAE_SOLVER').")
    input_artifact_id: str = Field(..., description="UUID string of existing input artifact.")
    execution_config: Optional[Dict[str, Any]] = Field(default=None, description="Solver execution configuration.")
    resource_limits: Optional[Dict[str, Any]] = Field(default=None, description="Resource limits (e.g. timeout_seconds).")
    idempotency_key: Optional[str] = Field(default=None, description="Optional idempotency key.")
    wait_for_completion: bool = Field(default=True, description="Whether to execute immediately and return completed job.")


class JobResponseDTO(BaseModel):
    id: str
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    user_id: str
    solver_name: str
    solver_version: str
    adapter_id: str
    state: str
    input_artifact_id: Optional[str] = None
    input_artifact_hash: str
    output_artifact_ids: List[str] = Field(default_factory=list)
    execution_config: Dict[str, Any] = Field(default_factory=dict)
    resource_limits: Dict[str, Any] = Field(default_factory=dict)
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    stdout_excerpt: Optional[str] = None
    stderr_excerpt: Optional[str] = None
    failure_reason: Optional[str] = None
    error_category: Optional[str] = None
    lease_expires_at: Optional[str] = None
    heartbeat_at: Optional[str] = None
    execution_mode: Optional[str] = "TRUSTED_ALLOWLIST"
    benchmark_reference_type: Optional[str] = None
    is_executed: bool = False
    is_physically_validated: bool = False
    execution_provenance: Dict[str, Any] = Field(default_factory=dict)
    reconciliation_summary: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobPreflightRequest(BaseModel):
    solver_name: str
    input_artifact_id: str


class JobPreflightResponse(BaseModel):
    is_supported: bool
    is_available: bool
    solver_name: str
    licensing_model: str
    executable_path: Optional[str] = None
    notes: str
    warnings: List[str] = Field(default_factory=list)


class ReconcileJobRequest(BaseModel):
    custom_tolerances: Optional[Dict[str, float]] = None
    custom_absolute_tolerances: Optional[Dict[str, float]] = None
    benchmark_method: Optional[str] = None
    required_signals: Optional[List[str]] = None


def _job_to_dto(job: SolverExecutionJob) -> JobResponseDTO:
    return JobResponseDTO(
        id=str(job.id),
        organization_id=str(job.organization_id) if job.organization_id else None,
        team_id=str(job.team_id) if job.team_id else None,
        user_id=str(job.user_id),
        solver_name=job.solver_name,
        solver_version=job.solver_version,
        adapter_id=job.adapter_id,
        state=job.state,
        input_artifact_id=str(job.input_artifact_id) if job.input_artifact_id else None,
        input_artifact_hash=job.input_artifact_hash,
        output_artifact_ids=job.output_artifact_ids or [],
        execution_config=job.execution_config or {},
        resource_limits=job.resource_limits or {},
        pid=job.pid,
        exit_code=job.exit_code,
        stdout_excerpt=job.stdout_excerpt,
        stderr_excerpt=job.stderr_excerpt,
        failure_reason=job.failure_reason,
        error_category=job.error_category,
        lease_expires_at=job.lease_expires_at.isoformat() if getattr(job, "lease_expires_at", None) else None,
        heartbeat_at=job.heartbeat_at.isoformat() if getattr(job, "heartbeat_at", None) else None,
        execution_mode=getattr(job, "execution_mode", "TRUSTED_ALLOWLIST"),
        benchmark_reference_type=getattr(job, "benchmark_reference_type", None),
        is_executed=job.is_executed,
        is_physically_validated=job.is_physically_validated,
        execution_provenance=job.execution_provenance or {},
        reconciliation_summary=job.reconciliation_summary or {},
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )


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


# ── PHASE 7.3 CONTROLLED EXECUTION & RECONCILIATION ENDPOINTS ─────────────────

@router.get("/runtimes")
def list_runtimes() -> List[Dict[str, Any]]:
    """
    Returns detected CAE solver execution runtimes and their verified availability status.
    Truthfully reports unavailable proprietary solvers (MSC Adams, MATLAB).
    """
    runtimes = SolverRuntimeRegistry.inspect_all()
    return [r.to_dict() for r in runtimes.values()]


@router.post("/execute/preflight", response_model=JobPreflightResponse)
async def preflight_execution(
    req: JobPreflightRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> JobPreflightResponse:
    """
    Preflight check verifying solver runtime availability and input artifact presence.
    """
    runtime = SolverRuntimeRegistry.get_runtime(req.solver_name)
    if not runtime:
        return JobPreflightResponse(
            is_supported=False,
            is_available=False,
            solver_name=req.solver_name,
            licensing_model="Unknown",
            notes=f"Solver runtime '{req.solver_name}' is not recognized.",
            warnings=["Solver is unsupported."],
        )

    warnings: List[str] = []
    if not runtime.is_available:
        warnings.append(f"Solver '{runtime.solver_name}' is not installed on this host environment.")

    # Check input artifact
    try:
        art_id = uuid.UUID(req.input_artifact_id)
        stmt = select(SolverExchangeArtifact).where(SolverExchangeArtifact.id == art_id)
        res = await db.execute(stmt)
        art = res.scalar_one_or_none()
        if not art:
            warnings.append(f"Input artifact '{req.input_artifact_id}' does not exist.")
        elif art.file_format not in runtime.supported_input_formats and f".{art.file_format.lstrip('.')}" not in runtime.supported_input_formats:
            warnings.append(f"Artifact format '{art.file_format}' is not in supported inputs {runtime.supported_input_formats}.")
    except Exception as e:
        warnings.append(f"Invalid artifact ID: {e}")

    return JobPreflightResponse(
        is_supported=True,
        is_available=runtime.is_available,
        solver_name=runtime.solver_name,
        licensing_model=runtime.licensing_model,
        executable_path=runtime.executable_path,
        notes=runtime.notes,
        warnings=warnings,
    )


@router.post("/execute", response_model=JobResponseDTO)
async def submit_execution_job(
    req: ExecuteJobRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> JobResponseDTO:
    """
    Creates and executes a controlled solver execution job within an isolated sandbox.
    Enforces tenant boundaries, wall-clock timeouts, and immutable provenance recording.
    """
    try:
        art_id = uuid.UUID(req.input_artifact_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid artifact UUID '{req.input_artifact_id}'.")

    try:
        job = await _exec_service.create_execution_job(
            db=db,
            user=user,
            solver_name=req.solver_name,
            input_artifact_id=art_id,
            execution_config=req.execution_config,
            resource_limits=req.resource_limits,
            idempotency_key=req.idempotency_key,
        )

        if req.wait_for_completion and job.state == ExecutionJobState.QUEUED.value:
            job = await _exec_service.execute_job(db=db, job_id=job.id, user=user)

        return _job_to_dto(job)

    except RuntimeUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error submitting execution job: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Execution error: {e}")


@router.get("/jobs", response_model=List[JobResponseDTO])
async def list_execution_jobs(
    limit: int = Query(50, ge=1, le=100),
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> List[JobResponseDTO]:
    """
    Lists execution jobs accessible to the calling tenant user.
    """
    jobs = await _exec_service.list_jobs(db=db, user=user, limit=limit)
    return [_job_to_dto(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponseDTO)
async def get_execution_job(
    job_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> JobResponseDTO:
    """
    Retrieves execution job state, resource logs, and provenance metadata.
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job UUID '{job_id}'.")

    try:
        j = await _exec_service.get_job(db=db, job_id=jid, user=user)
        return _job_to_dto(j)
    except ExecutionJobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/jobs/{job_id}/cancel", response_model=JobResponseDTO)
async def cancel_execution_job(
    job_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> JobResponseDTO:
    """
    Cancels an active or queued execution job and terminates its sandbox process.
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job UUID '{job_id}'.")

    try:
        j = await _exec_service.cancel_job(db=db, job_id=jid, user=user)
        return _job_to_dto(j)
    except ExecutionJobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ImmutableExecutionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/jobs/recover-crashed", response_model=List[JobResponseDTO])
async def recover_crashed_jobs_endpoint(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> List[JobResponseDTO]:
    """
    Identifies and recovers orphaned solver execution jobs whose lease expired or worker crashed.
    """
    recovered = await _exec_service.recover_crashed_jobs(db=db)
    return [_job_to_dto(j) for j in recovered]


@router.get("/benchmarks/capabilities")
async def get_benchmark_capabilities() -> Dict[str, Any]:
    """
    Returns available independent benchmark methods, scenarios, taxonomy definitions,
    channel tolerance provenance, and truthful capability flags.
    """
    from suspensionlab.interop.benchmarks.independent_solver import (
        BenchmarkMethod,
        BenchmarkScenario,
        EXPERIMENTAL_PHYSICAL_VALIDATION_VERIFIED,
        TAXONOMY_DEFINITIONS,
        THIRD_PARTY_SOLVER_INDEPENDENCE_VERIFIED,
        UNTRUSTED_FMU_ISOLATION_VERIFIED,
    )
    from suspensionlab.interop.reconciliation.engine import ResultReconciliationEngine

    return {
        "taxonomy": TAXONOMY_DEFINITIONS,
        "available_methods": [m.value for m in BenchmarkMethod],
        "available_scenarios": [s.value for s in BenchmarkScenario],
        "channel_provenance": {
            k: v.to_dict() for k, v in ResultReconciliationEngine.CHANNEL_PROVENANCE.items()
        },
        "epistemic_invariants": {
            "third_party_solver_independence_verified": THIRD_PARTY_SOLVER_INDEPENDENCE_VERIFIED,
            "experimental_physical_validation_verified": EXPERIMENTAL_PHYSICAL_VALIDATION_VERIFIED,
            "untrusted_fmu_isolation_verified": UNTRUSTED_FMU_ISOLATION_VERIFIED,
            "executed_implies_verified_correct": False,
            "numerical_agreement_implies_physical_validation": False,
        },
    }


@router.post("/jobs/{job_id}/reconcile")
async def reconcile_job_results(
    job_id: str,
    req: Optional[ReconcileJobRequest] = None,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> Dict[str, Any]:
    """
    Reconciles external solver output against independent reference dynamics.
    Returns unit-normalized peak, RMS, NRMSE, phase, and energy consistency metrics.
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job UUID '{job_id}'.")

    try:
        tolerances = req.custom_tolerances if req else None
        abs_tolerances = req.custom_absolute_tolerances if req else None
        bench_method = req.benchmark_method if req else None
        req_signals = req.required_signals if req else None
        report = await _exec_service.reconcile_job_results(
            db=db,
            job_id=jid,
            user=user,
            custom_tolerances=tolerances,
            custom_absolute_tolerances=abs_tolerances,
            benchmark_method=bench_method,
            required_signals=req_signals,
        )
        return report.to_dict()
    except ExecutionJobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
