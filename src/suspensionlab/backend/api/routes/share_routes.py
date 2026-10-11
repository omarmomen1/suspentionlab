"""
Shareable Report Routes — public links for simulation results WITH PROVENANCE (#24).

Enterprise redesign:
    Simulation Run (JobRecord artifact)
        ↓
    immutable result loaded SERVER-SIDE
        ↓
    SHA-256 hashes (params / result / input)
        ↓
    report row stamped with provenance
        ↓
    HMAC-signed share token

Two sharing paths:
  * VERIFIED (preferred): client supplies `simulation_id`; the params/result are
    loaded from the user's own completed JobRecord — the client cannot fabricate
    numbers. Report gets provenance="verified" + HMAC signature.
  * CLIENT-ASSERTED (legacy compatibility): client posts params/result directly.
    These are stored but explicitly labelled provenance="client-asserted" so no
    one can mistake them for engine-produced artifacts.

Every report exposes a provenance block:
    simulation_id, software_version, physics_version, input_hash, result_hash…
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import html
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.config import settings
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.security.audit import canonical_hash
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["shared-reports"])

SOFTWARE_VERSION = "1.0.0"
PHYSICS_VERSIONS = {
    "quarter_car": "quarter-car-v2",
    "half_car": "half-car-v2",
    "full_car": "full-car-v3",
    "handling": "handling-v2",
}


def _sign(token: str, params_hash: str, result_hash: str) -> str:
    """HMAC-SHA256 share-token signature bound to the artifact hashes."""
    from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY
    key = get_jwt_keys()[JWT_ACTIVE_KEY].encode()
    msg = f"{token}:{params_hash}:{result_hash}".encode()
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


class ShareRequest(BaseModel):
    simulation_type: str = "quarter_car"
    simulation_id: str | None = None   # JobRecord id → verified provenance path
    params: dict | None = None         # legacy path only
    result: dict | None = None         # legacy path only
    title: str = ""
    notes: str = ""


class ShareResponse(BaseModel):
    token: str
    url: str
    provenance: str
    message: str


class ProvenanceBlock(BaseModel):
    status: str                 # verified | client-asserted
    simulation_id: str | None = None
    software_version: str | None = None
    physics_version: str | None = None
    params_hash: str | None = None
    result_hash: str | None = None
    input_hash: str | None = None
    artifact_hash: str | None = None
    approval_status: str | None = None
    approved_by_email: str | None = None
    approved_by_role: str | None = None
    approved_at: str | None = None
    approval_signature: str | None = None
    approval_comment: str | None = None
    signature_valid: bool | None = None
    payload_verified: bool = False
    tamper_detected: bool = False


class ReportResponse(BaseModel):
    token: str
    simulation_type: str
    params: dict
    result: dict
    title: str
    notes: str
    created_at: str
    view_count: int
    doc_id: str | None = None
    vehicle_ref: str | None = None
    setup_ref: str | None = None
    tire_ref: str | None = None
    track_ref: str | None = None
    telemetry_ref: str | None = None
    solver_version: str | None = None
    software_build: str | None = None
    validation_status: str | None = None
    correlation_pct: float | None = None
    metrics: dict | None = None
    plot_data: dict | None = None
    provenance: ProvenanceBlock



@router.post("/share", response_model=ShareResponse)
async def create_shared_report(
    req: ShareRequest,
    db: AsyncSession = Depends(get_db_dependency),
    user: UserContext = Depends(require_permission(Permission.REPORT_SHARE)),
):
    """
    Share a simulation result publicly.

    Preferred: pass `simulation_id` of YOUR completed job — the platform loads
    the immutable artifact itself and signs it. Client-supplied params/result
    are accepted for backwards compatibility but are labelled 'client-asserted'.
    """
    token = str(uuid.uuid4())
    params: dict | None = None
    result: dict | None = None
    provenance = "client-asserted"
    sim_id: uuid.UUID | None = None
    software_version = SOFTWARE_VERSION
    physics_version = PHYSICS_VERSIONS.get(req.simulation_type, "unknown")
    params_hash = result_hash = input_hash = None

    doc_id = None
    vehicle_ref = setup_ref = tire_ref = track_ref = telemetry_ref = None
    solver_version = software_build = None
    validation_status = "UNVALIDATED"
    correlation_pct = None
    metrics = None
    plot_data = None
    artifact_hash = None

    if req.simulation_id:
        # ── Verified path: load artifact server-side (SimulationRun or JobRecord) ──
        from suspensionlab.backend.services import report_service
        run = None
        try:
            run = await report_service.get_simulation_run(
                db, req.simulation_id, str(user.user_id), getattr(user, "team_id", None)
            )
        except LookupError:
            run = None

        if run is not None:
            sim_id = run.id
            params = run.params or {}
            result = run.result or {}
            provenance = "verified"
            params_hash = run.params_hash or canonical_hash(params)
            result_hash = run.result_hash or canonical_hash(result)
            input_hash = run.input_hash or canonical_hash(run.profile or {})
            physics_version = run.physics_version
            software_version = run.software_version or SOFTWARE_VERSION
            doc_id = f"DOC-2026-SL-{run.seq:04d}" if hasattr(run, "seq") else None
            vehicle_ref = run.vehicle_ref
            setup_ref = run.setup_ref
            tire_ref = run.tire_ref
            track_ref = run.track_ref
            telemetry_ref = run.telemetry_ref
            solver_version = run.solver_version
            software_build = run.git_build_id
            try:
                hydrated = await report_service.hydrate_engineering_report(
                    db, run.label or str(run.id), str(user.user_id), getattr(user, "team_id", None)
                )
                metrics = hydrated.get("metrics")
                plot_data = hydrated.get("plot_data")
                artifact_hash = hydrated.get("artifact_hash")
                correlation_pct = hydrated.get("correlation_pct")
                validation_status = hydrated.get("validation_status", "UNVALIDATED")
            except Exception:
                pass
        else:
            try:
                job_uuid = uuid.UUID(req.simulation_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="simulation_id must be a valid job UUID or RUN-xxxxxx label.")

            job_res = await db.execute(
                select(JobRecord).where(
                    JobRecord.id == job_uuid,
                    JobRecord.user_id == uuid.UUID(str(user.user_id)),
                    JobRecord.status.in_(["COMPLETED", "COMPLETED_VALID", "COMPLETED_WITH_WARNINGS"]),
                )
            )
            job: JobRecord | None = job_res.scalar_one_or_none()
            if job is None:
                raise HTTPException(
                    status_code=404,
                    detail="No completed simulation found with that ID for your account. "
                           "Reports can only be shared from runs you actually executed.",
                )

            sim_id = job.id
            params = job.params or {}
            result = job.result or {}
            provenance = "verified"
            params_hash = canonical_hash(params)
            result_hash = canonical_hash(result)
            input_hash = canonical_hash(job.profile or {})

        if req.simulation_type not in ("quarter_car",):
            req.simulation_type = req.simulation_type  # keep caller's label
    else:
        # ── Legacy path: client-asserted content ──────────────────────────
        if req.params is None or req.result is None:
            raise HTTPException(
                status_code=400,
                detail="Provide either `simulation_id` (verified provenance) or both "
                       "`params` and `result` (client-asserted).",
            )
        params = req.params
        result = req.result
        params_hash = canonical_hash(params)
        result_hash = canonical_hash(result)

    signature = _sign(token, params_hash, result_hash)

    report = SharedReport(
        token=token,
        simulation_type=req.simulation_type,
        params=params,
        result=result,
        title=html.escape(req.title or f"Suspension Analysis ({req.simulation_type.replace('_', ' ').title()})"),
        notes=html.escape(req.notes),
        owner_id=uuid.UUID(str(user.user_id)),
        team_id=uuid.UUID(str(user.team_id)) if getattr(user, "team_id", None) else None,
        organization_id=uuid.UUID(str(user.organization_id)) if getattr(user, "organization_id", None) else None,
        is_public=True,
        simulation_id=sim_id,
        doc_id=doc_id,
        vehicle_ref=vehicle_ref,
        setup_ref=setup_ref,
        tire_ref=tire_ref,
        track_ref=track_ref,
        telemetry_ref=telemetry_ref,
        solver_version=solver_version,
        software_build=software_build,
        validation_status=validation_status,
        correlation_pct=correlation_pct,
        metrics=metrics,
        plot_data=plot_data,
        artifact_hash=artifact_hash,
        params_hash=params_hash,
        result_hash=result_hash,
        input_hash=input_hash,
        software_version=software_version,
        physics_version=physics_version,
        provenance=provenance,
        signature=signature,
    )
    db.add(report)
    await db.commit()

    try:
        from suspensionlab.backend.security.audit import record_audit_event
        await record_audit_event(
            db=db,
            event_type="REPORT_SHARED",
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            artifact_id=token,
            metadata={
                "token": token,
                "simulation_type": req.simulation_type,
                "provenance": provenance,
                "title": req.title,
                "params_hash": params_hash,
                "result_hash": result_hash,
            }
        )
    except Exception as e:
        logger.warning("Audit logging warning for shared report creation: %s", e)

    return ShareResponse(
        token=token,
        url=f"/report/{token}",
        provenance=provenance,
        message=("Report shared with verified engine provenance."
                 if provenance == "verified"
                 else "Report shared. Note: contents were supplied by the client and are "
                      "labelled 'client-asserted' — they are NOT verified engine output."),
    )


@router.get("/{token}", response_model=ReportResponse)
async def get_shared_report(
    token: str,
    db: AsyncSession = Depends(get_db_dependency),
):
    """Retrieve a shared simulation report by token. Public endpoint."""
    result_q = await db.execute(
        select(SharedReport).where(SharedReport.token == token, SharedReport.deleted_at.is_(None))
    )
    report: SharedReport | None = result_q.scalar_one_or_none()

    if not report or not report.is_public:
        raise HTTPException(status_code=404, detail="Report not found or has expired.")

    try:
        await db.execute(
            update(SharedReport).where(SharedReport.token == token)
            .values(view_count=SharedReport.view_count + 1)
        )
        await db.commit()
        await db.refresh(report)
    except Exception:
        await db.rollback()

    # Verify integrity + signature dynamically on every read (Finding P0-1).
    computed_params_hash = canonical_hash(report.params or {})
    computed_result_hash = canonical_hash(report.result or {})

    # Check if database payload matches stamped hashes
    params_match = (computed_params_hash == report.params_hash) if report.params_hash else True
    result_match = (computed_result_hash == report.result_hash) if report.result_hash else True
    payload_verified = params_match and result_match
    tamper_detected = not payload_verified

    signature_valid: bool | None = None
    if report.signature and report.params_hash and report.result_hash:
        if payload_verified:
            expected = _sign(report.token, report.params_hash, report.result_hash)
            signature_valid = _hmac.compare_digest(expected, report.signature)
        else:
            signature_valid = False

    return ReportResponse(
        token=report.token,
        simulation_type=report.simulation_type,
        params=report.params,
        result=report.result,
        title=report.title,
        notes=report.notes,
        created_at=report.created_at.isoformat(),
        view_count=report.view_count or 0,
        doc_id=report.doc_id,
        vehicle_ref=report.vehicle_ref,
        setup_ref=report.setup_ref,
        tire_ref=report.tire_ref,
        track_ref=report.track_ref,
        telemetry_ref=report.telemetry_ref,
        solver_version=report.solver_version,
        software_build=report.software_build,
        validation_status=report.validation_status or "UNVALIDATED",
        correlation_pct=report.correlation_pct,
        metrics=report.metrics,
        plot_data=report.plot_data,
        provenance=ProvenanceBlock(
            status=report.provenance,
            simulation_id=str(report.simulation_id) if report.simulation_id else None,
            software_version=report.software_version,
            physics_version=report.physics_version,
            params_hash=report.params_hash,
            result_hash=report.result_hash,
            input_hash=report.input_hash,
            artifact_hash=report.artifact_hash,
            approval_status=report.status,
            approved_by_email=report.approved_by_email,
            approved_by_role=report.approved_by_role,
            approved_at=report.approved_at.isoformat() if report.approved_at else None,
            approval_signature=report.approval_signature,
            approval_comment=report.approval_comment,
            signature_valid=signature_valid,
            payload_verified=payload_verified,
            tamper_detected=tamper_detected,
        ),
    )


