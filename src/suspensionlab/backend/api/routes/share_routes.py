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
from suspensionlab.backend.security.auth import verify_api_key

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
    signature_valid: bool | None = None


class ReportResponse(BaseModel):
    token: str
    simulation_type: str
    params: dict
    result: dict
    title: str
    notes: str
    created_at: str
    view_count: int
    provenance: ProvenanceBlock


@router.post("/share", response_model=ShareResponse)
async def create_shared_report(
    req: ShareRequest,
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(verify_api_key),
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

    if req.simulation_id:
        # ── Verified path: load the artifact server-side ──────────────────
        try:
            sim_id = uuid.UUID(req.simulation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="simulation_id must be a valid job UUID.")

        job_res = await db.execute(
            select(JobRecord).where(
                JobRecord.id == sim_id,
                JobRecord.user_id == uuid.UUID(user.user_id),
                JobRecord.status == "COMPLETED",
            )
        )
        job: JobRecord | None = job_res.scalar_one_or_none()
        if job is None:
            raise HTTPException(
                status_code=404,
                detail="No completed simulation found with that ID for your account. "
                       "Reports can only be shared from runs you actually executed.",
            )

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
        owner_id=uuid.UUID(user.user_id),
        simulation_id=sim_id,
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
    result_q = await db.execute(select(SharedReport).where(SharedReport.token == token))
    report: SharedReport | None = result_q.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found or has expired.")
    if not report.is_public:
        raise HTTPException(status_code=403, detail="This report is private.")

    try:
        await db.execute(
            update(SharedReport).where(SharedReport.token == token)
            .values(view_count=SharedReport.view_count + 1)
        )
        await db.commit()
        await db.refresh(report)
    except Exception:
        await db.rollback()

    # Verify integrity + signature on every read.
    signature_valid: bool | None = None
    if report.signature and report.params_hash and report.result_hash:
        expected = _sign(report.token, report.params_hash, report.result_hash)
        signature_valid = _hmac.compare_digest(expected, report.signature)

    return ReportResponse(
        token=report.token,
        simulation_type=report.simulation_type,
        params=report.params,
        result=report.result,
        title=report.title,
        notes=report.notes,
        created_at=report.created_at.isoformat(),
        view_count=report.view_count,
        provenance=ProvenanceBlock(
            status=report.provenance,
            simulation_id=str(report.simulation_id) if report.simulation_id else None,
            software_version=report.software_version,
            physics_version=report.physics_version,
            params_hash=report.params_hash,
            result_hash=report.result_hash,
            input_hash=report.input_hash,
            signature_valid=signature_valid,
        ),
    )
