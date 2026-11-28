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
import hashlib
import logging
import pathlib
import uuid
from typing import Any, Dict, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
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
    VETTED_FMU_SHA256,
)
from suspensionlab.backend.services.cosimulation_service import CoSimulationService
from suspensionlab.backend.database.models.cosim_contract import (
    CoSimulationCouplingContract as CoSimContractModel,
)
from suspensionlab.interop.cosim.contract import CouplingContractError
from suspensionlab.interop.fmi.capability_audit import FMICapabilityAuditor
from suspensionlab.interop.cosim.fencing import (
    WorkerFencingManager,
    StaleWorkerFencingError,
    WorkerAuthenticationError,
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
_cosim_service = CoSimulationService()


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


class SolverExecutionConfigSchema(BaseModel):
    """Strict allowlisted solver execution configuration schema."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    duration: Optional[float] = Field(default=None, gt=0.0, le=3600.0)
    stop_time: Optional[float] = Field(default=None, gt=0.0, le=3600.0)
    t_end: Optional[float] = Field(default=None, gt=0.0, le=3600.0)
    step: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    step_size: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    communication_step_size: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    bump_height: Optional[float] = Field(default=None, ge=-10.0, le=10.0)
    bump_time: Optional[float] = Field(default=None, ge=0.0, le=3600.0)
    road_input_type: Optional[str] = Field(default=None)
    m_s: Optional[float] = Field(default=None, gt=0.0)
    m_u: Optional[float] = Field(default=None, gt=0.0)
    k_s: Optional[float] = Field(default=None, gt=0.0)
    c: Optional[float] = Field(default=None, ge=0.0)
    k_t: Optional[float] = Field(default=None, gt=0.0)
    MR: Optional[float] = Field(default=None, gt=0.0)
    benchmark_method: Optional[str] = Field(default=None)
    contract_id: Optional[str] = Field(default=None)


class ResourceLimitsSchema(BaseModel):
    """Strict allowlisted solver resource limits schema."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    timeout_seconds: Optional[float] = Field(default=None, gt=0.0, le=300.0)
    max_memory_mb: Optional[int] = Field(default=None, gt=0, le=16384)


class ExecuteJobRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    solver_name: str = Field(..., description="Target solver runtime (e.g. 'FMI_COSIMULATION', 'EXTERNAL_CAE_SOLVER').")
    input_artifact_id: str = Field(..., description="UUID string of existing input artifact.")
    execution_config: Optional[SolverExecutionConfigSchema] = Field(default=None, description="Solver execution configuration.")
    resource_limits: Optional[ResourceLimitsSchema] = Field(default=None, description="Resource limits (e.g. timeout_seconds).")
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
    worker_id: Optional[str] = None
    lease_generation: int = 1
    coupling_contract_id: Optional[str] = None
    co_simulation_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    is_executed: bool = False
    is_physically_validated: bool = False
    execution_provenance: Dict[str, Any] = Field(default_factory=dict)
    reconciliation_summary: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobPreflightRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

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
        execution_config=SolverExecutionService.sanitize_execution_config(job.execution_config),
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
        worker_id=getattr(job, "worker_id", None),
        lease_generation=getattr(job, "lease_generation", 1) or 1,
        coupling_contract_id=str(job.coupling_contract_id) if getattr(job, "coupling_contract_id", None) else None,
        co_simulation_diagnostics=getattr(job, "co_simulation_diagnostics", {}) or {},
        is_executed=job.is_executed,
        is_physically_validated=job.is_physically_validated,
        execution_provenance=job.execution_provenance or {},
        reconciliation_summary=job.reconciliation_summary or {},
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )


class CreateCoSimContractRequest(BaseModel):
    contract_id: Optional[str] = Field(default=None, description="Unique human-readable contract ID (e.g. 'COSIM-ROAD-QC-01').")
    name: Optional[str] = Field(default=None, description="Descriptive contract name.")
    contract_name: Optional[str] = Field(default=None, description="Alternative name field.")
    contract_version: Optional[str] = Field(default=None, description="Contract version.")
    participating_models: Optional[List[Dict[str, Any]]] = Field(default=None, description="List of participating model specifications.")
    participating_components: Optional[Dict[str, Any]] = Field(default=None, description="Component dictionary.")
    connections: Optional[List[Dict[str, Any]]] = Field(default=None, description="List of signal connection wiring specifications.")
    signal_connections: Optional[List[Dict[str, Any]]] = Field(default=None, description="List of signal connection wiring specifications.")
    time_sync_config: Optional[Dict[str, Any]] = Field(default=None, description="Time synchronization configuration.")
    operating_bounds: Optional[Dict[str, Any]] = Field(default=None, description="Operating bounds and failure policies.")
    failure_propagation_policy: Optional[str] = Field(default=None, description="Failure propagation policy.")
    description: Optional[str] = Field(default=None, description="Optional contract notes.")
    seal_now: Optional[bool] = Field(default=False, description="Whether to seal contract upon creation.")


class ExecuteCoSimJobRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    duration: float = Field(default=1.0, gt=0.0, le=3600.0, description="Simulation duration in seconds.")
    t_end: Optional[float] = Field(default=None, gt=0.0, le=3600.0, description="Simulation duration in seconds.")
    worker_id: Optional[str] = Field(default=None, description="Worker identifier requesting execution.")
    wait_for_completion: Optional[bool] = Field(default=True, description="Synchronous execution flag.")
    idempotency_key: Optional[str] = Field(default=None, description="Idempotency key.")
    resource_limits: Optional[ResourceLimitsSchema] = Field(default=None, description="Resource limits.")


class WorkerHeartbeatRequest(BaseModel):
    worker_id: str = Field(..., description="Worker identifier holding the lease.")
    lease_generation: int = Field(..., description="Monotonically increasing lease fencing token.")
    lease_duration_seconds: float = Field(default=30.0, description="Requested lease extension duration.")
    worker_token: Optional[str] = Field(default=None, description="Worker principal authentication token.")


class CoSimContractResponseDTO(BaseModel):
    id: str
    contract_id: str
    name: str
    version: str
    description: Optional[str] = None
    status: str
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    created_by_user_id: str
    participating_models: List[Dict[str, Any]] = Field(default_factory=list)
    connections: List[Dict[str, Any]] = Field(default_factory=list)
    time_sync_config: Dict[str, Any] = Field(default_factory=dict)
    operating_bounds: Dict[str, Any] = Field(default_factory=dict)
    validation_report: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _contract_to_dto(c: CoSimContractModel) -> CoSimContractResponseDTO:
    return CoSimContractResponseDTO(
        id=str(c.id),
        contract_id=c.contract_id,
        name=c.name,
        version=c.version,
        description=c.description,
        status=c.status,
        organization_id=str(c.organization_id) if c.organization_id else None,
        team_id=str(c.team_id) if c.team_id else None,
        created_by_user_id=str(c.created_by_user_id),
        participating_models=c.participating_models or [],
        connections=c.connections or [],
        time_sync_config=c.time_sync_config or {},
        operating_bounds=c.operating_bounds or {},
        validation_report=c.validation_report or {},
        created_at=c.created_at.isoformat() if c.created_at else None,
        updated_at=c.updated_at.isoformat() if c.updated_at else None,
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
                logger.warning("Invalid base64 payload: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid base64 payload.",
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Import operation failed.")


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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="File import failed.")


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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Export operation failed.")


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
            execution_config=(
                req.execution_config.model_dump(exclude_none=True)
                if req.execution_config is not None
                else None
            ),
            resource_limits=(
                req.resource_limits.model_dump(exclude_none=True)
                if req.resource_limits is not None
                else None
            ),
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Execution error.")


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
    Enforces tenant scoping so ordinary users only recover their own tenant's jobs.
    """
    recovered = await _exec_service.recover_crashed_jobs(db=db, user=user)
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


# ── CO-SIMULATION COUPLING & TIME SYNCHRONIZATION (PHASE 7.5) ──────────────────

@router.get("/cosim/capabilities")
async def get_cosimulation_capabilities() -> Dict[str, Any]:
    """
    Returns available FMI models, internal components, communication step capabilities,
    and honest audit disclosures for multi-domain co-simulation.
    """
    raw = _cosim_service.get_fmi_capabilities()
    vetted_fmus = []
    candidates = [
        ("ActiveQuarterCarModel.fmu", "ActiveQuarterCarModel"),
        ("ActiveSuspensionController.fmu", "ActiveSuspensionController"),
        ("QuarterCarRideModel.fmu", "QuarterCarRideModel"),
    ]
    for fn, m_name in candidates:
        p = pathlib.Path(fn)
        if not p.exists():
            p = pathlib.Path(f"artifacts/{fn}")
        if p.exists():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h in VETTED_FMU_SHA256:
                vetted_fmus.append({
                    "filename": p.name,
                    "hash_sha256": h,
                    "model_name": m_name,
                    "path": str(p),
                })
    return {
        "vetted_fmus": vetted_fmus,
        "available_fmus": raw.get("available_fmus", []),
        "internal_components": [
            {
                "name": "RoadProfileGenerator",
                "description": "Analytical road profile generator (ISO 8608, discrete bump, chirp)",
                "signals": {"outputs": ["z_r"]},
            }
        ],
        "supported_policies": ["GAUSS_SEIDEL", "JACOBI"],
        "supported_interpolation": ["ZERO_ORDER_HOLD", "FIRST_ORDER_HOLD"],
        "truthful_status": {
            "two_fmu_cosimulation_verified": True,
            "feedback_cosimulation_verified": True,
            "plant_controller_feedback_verified": True,
            "untrusted_fmu_isolation_verified": False,
            "fmu_state_rollback_supported": False,
        },
    }


@router.get("/cosim/fmu-capabilities")
async def get_cosim_fmu_capabilities(
    fmu_path: Optional[str] = Query(None, description="Path to FMU"),
    user: UserContext = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Audits and inspects FMI capabilities of QuarterCarRideModel.fmu.
    """
    target = pathlib.Path(fmu_path) if fmu_path else pathlib.Path("artifacts/QuarterCarRideModel.fmu")
    if not target.exists():
        target = pathlib.Path("QuarterCarRideModel.fmu")
    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FMU not found")
    report = FMICapabilityAuditor.audit_fmu(target)
    return report.to_dict()


@router.post("/cosim/contracts", response_model=CoSimContractResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_cosim_contract(
    req: CreateCoSimContractRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> CoSimContractResponseDTO:
    """
    Creates a new versioned co-simulation interface coupling contract.
    """
    try:
        record = await _cosim_service.create_contract(
            db=db,
            user=user,
            contract_id=req.contract_id,
            name=req.name or req.contract_name,
            contract_name=req.contract_name,
            participating_models=req.participating_models,
            participating_components=req.participating_components,
            connections=req.connections,
            signal_connections=req.signal_connections,
            time_sync_config=req.time_sync_config,
            operating_bounds=req.operating_bounds,
            description=req.description,
            seal_now=req.seal_now or False,
        )
        return _contract_to_dto(record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/cosim/contracts", response_model=List[CoSimContractResponseDTO])
async def list_cosim_contracts(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> List[CoSimContractResponseDTO]:
    """
    Lists tenant-scoped co-simulation coupling contracts.
    """
    contracts = await _cosim_service.list_contracts(db=db, user=user)
    return [_contract_to_dto(c) for c in contracts]


@router.get("/cosim/contracts/{contract_id}", response_model=CoSimContractResponseDTO)
async def get_cosim_contract(
    contract_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> CoSimContractResponseDTO:
    """
    Retrieves a specific co-simulation coupling contract.
    """
    try:
        c = await _cosim_service.get_contract(db=db, contract_identifier=contract_id, user=user)
        return _contract_to_dto(c)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/cosim/contracts/{contract_id}/preflight")
async def preflight_cosim_contract(
    contract_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> Dict[str, Any]:
    """
    Executes preflight verification on a coupling contract:
    - Signal causality (source=output, target=input)
    - Unit dimensional compatibility and scale conversion
    - Algebraic loop detection without step delay
    - Communication step size bounds
    """
    try:
        return await _cosim_service.preflight_validate_contract(db=db, contract_identifier=contract_id, user=user)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/cosim/contracts/{contract_id}/execute", response_model=JobResponseDTO)
async def execute_cosim_job(
    contract_id: str,
    req: Optional[ExecuteCoSimJobRequest] = None,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> JobResponseDTO:
    """
    Dispatches and executes an authorized coupled co-simulation across participating models.
    Enforces preflight validation, worker lease fencing, and epistemic recording.
    """
    duration = 1.0
    if req:
        if req.t_end is not None:
            duration = req.t_end
        elif req.duration is not None:
            duration = req.duration
    worker_id = req.worker_id if req else None

    try:
        job = await _cosim_service.execute_coupled_simulation(
            db=db,
            contract_identifier=contract_id,
            user=user,
            duration=duration,
            worker_id=worker_id,
        )
        return _job_to_dto(job)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CouplingContractError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Co-simulation execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error. The details have been logged server-side.")


@router.get("/cosim/jobs/{job_id}/diagnostics")
async def get_cosim_job_diagnostics(
    job_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
) -> Dict[str, Any]:
    """
    Returns time synchronization diagnostics, energy balance, phase error,
    and step stability metrics for a co-simulation job.
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job UUID '{job_id}'.")

    try:
        job = await _exec_service.get_job(db=db, job_id=jid, user=user)
        return {
            "job_id": str(job.id),
            "state": job.state,
            "is_executed": job.is_executed,
            "worker_id": getattr(job, "worker_id", None),
            "lease_generation": getattr(job, "lease_generation", 1),
            "co_simulation_diagnostics": getattr(job, "co_simulation_diagnostics", {}) or {},
            "feedback_metrics": getattr(job, "feedback_metrics", {}) or {},
            "cosim_synchronization_mode": getattr(job, "cosim_synchronization_mode", "GAUSS_SEIDEL"),
            "reconciliation_summary": job.reconciliation_summary or {},
        }
    except ExecutionJobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/cosim/jobs/{job_id}/heartbeat")
async def cosim_worker_heartbeat(
    job_id: str,
    req: WorkerHeartbeatRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
    worker_token: Optional[str] = Header(None, alias="X-Worker-Token"),
) -> Dict[str, Any]:
    """
    Heartbeat endpoint for workers holding active execution leases.
    Validates the worker principal token and monotonically increasing lease_generation fencing token.
    Rejects stale or recovered workers with 409 Conflict.
    Rejects unauthorized worker impersonators with 403 Forbidden.
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job UUID '{job_id}'.")

    effective_worker_token = worker_token or req.worker_token
    try:
        await WorkerFencingManager.renew_lease(
            db=db,
            job_id=jid,
            worker_id=req.worker_id,
            lease_generation=req.lease_generation,
            worker_token=effective_worker_token,
            lease_duration_seconds=req.lease_duration_seconds,
        )
        return {
            "status": "LEASE_RENEWED",
            "job_id": str(jid),
            "worker_id": req.worker_id,
            "lease_generation": req.lease_generation,
        }
    except WorkerAuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except StaleWorkerFencingError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
