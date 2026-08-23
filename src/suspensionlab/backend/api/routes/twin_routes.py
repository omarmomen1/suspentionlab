"""
backend/api/routes/twin_routes.py
==================================
Digital Setup Twin API (Issues 40 & 41).

POST /api/v1/twins                        → create a twin (car + setup + base params)
GET  /api/v1/twins/{id}                   → twin state (base vs calibrated params)
POST /api/v1/twins/{id}/calibrate         → identify from telemetry CSV, learn
GET  /api/v1/twins/{id}/learnings         → vehicle-specific intelligence (#41)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.services import digital_twin
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/twins", tags=["digital-twin"])


class CreateTwinRequest(BaseModel):
    car_ref: str = Field(..., max_length=120, description="e.g. CAR-2026-07")
    setup_ref: str = Field(..., max_length=120, description="e.g. SETUP-SPA-R4")
    track_ref: Optional[str] = None
    base_params: dict = Field(..., description="Handbook parameters (m_s, k_s, c, MR, …)")


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201)
async def create_twin(
    req: CreateTwinRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if "m_s" not in req.base_params:
        raise HTTPException(status_code=400, detail="base_params must include m_s (sprung mass).")
    twin = await digital_twin.create_twin(
        db, user.user_id, getattr(user, "team_id", None),
        req.car_ref, req.setup_ref, req.track_ref, req.base_params,
    )
    return {
        "id": str(twin.id),
        "car_ref": twin.car_ref,
        "setup_ref": twin.setup_ref,
        "calibrated": False,
        "message": "Twin created. POST telemetry to /twins/{id}/calibrate to identify parameters.",
    }


@router.get("/{twin_id}")
async def get_twin(
    twin_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)
    return {
        "id": str(twin.id),
        "car_ref": twin.car_ref,
        "setup_ref": twin.setup_ref,
        "track_ref": twin.track_ref,
        "base_params": twin.base_params,
        "calibrated_params": twin.calibrated_params,
        "calibration_count": twin.calibration_count,
        "last_identification": twin.last_identification,
        "created_at": twin.created_at.isoformat() if twin.created_at else None,
    }


@router.post("/{twin_id}/calibrate")
async def calibrate_twin(
    twin_id: str,
    file: UploadFile = File(..., description="Telemetry CSV with time + vertical acceleration"),
    speed_band: Optional[str] = Form(None, description="Operating condition, e.g. '105-140 km/h'"),
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Parameter identification (#40): ingest a telemetry session, identify the
    sprung ride frequency & damping, update the twin's calibrated parameters,
    and record a learning observation (#41).
    """
    content = (await file.read(20 * 1024 * 1024)).decode("utf-8", errors="replace")
    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)

    conditions = {"speed_band": speed_band} if speed_band else {}
    try:
        result = await digital_twin.calibrate_twin(db, twin, content, conditions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("Twin calibration failed")
        raise HTTPException(status_code=500, detail=f"Calibration failed: {exc}")
    return result


@router.get("/{twin_id}/learnings")
async def twin_learnings(
    twin_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Vehicle-specific engineering intelligence aggregated from all calibrations (#41)."""
    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)
    return await digital_twin.get_learnings(db, twin)


# ── Setup Proposals (Issue 50) ────────────────────────────────────────────────

class ProposalRequest(BaseModel):
    problem: str = Field(..., min_length=5, max_length=4000,
                         description="Engineer's problem statement, e.g. "
                                     "'Why is the car unstable in T9?'")


@router.post("/{twin_id}/propose", status_code=201)
async def create_proposal(
    twin_id: str,
    req: ProposalRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    The Issue-50 workflow endpoint: given the twin's CALIBRATED parameters and
    the engineer's problem, search the feasible setup space (simulate every
    candidate), validate constraints, and persist an immutable Setup Proposal.
    Every number is simulation-derived — no generated values.
    """
    from suspensionlab.backend.services import setup_proposal as sp
    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)

    proposal = await sp.generate_proposal(
        db, twin, req.problem, user.user_id, getattr(user, "team_id", None)
    )
    return sp.proposal_to_dict(proposal)


@router.get("/{twin_id}/proposals")
async def list_proposals(
    twin_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """All proposals for this twin, newest first."""
    from sqlalchemy import select, desc
    import uuid as _uuid
    from suspensionlab.backend.database.models.setup_proposal import SetupProposal
    from suspensionlab.backend.services import setup_proposal as sp

    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)

    result = await db.execute(
        select(SetupProposal)
        .where(SetupProposal.twin_id == twin.id)
        .order_by(desc(SetupProposal.created_at))
        .limit(50)
    )
    return {"proposals": [sp.proposal_to_dict(p) for p in result.scalars().all()]}


@router.post("/proposals/{proposal_id}/status")
async def set_proposal_status(
    proposal_id: str,
    status: str = Query(..., pattern="^(APPROVED|REJECTED|EXPORTED)$"),
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Engineer decision on a proposal. Only `status` is mutable — the technical
    content of a proposal is immutable once created.
    """
    import uuid as _uuid
    from sqlalchemy import select
    from suspensionlab.backend.database.models.setup_proposal import SetupProposal

    conditions = [SetupProposal.id == _uuid.UUID(proposal_id),
                  SetupProposal.user_id == _uuid.UUID(user.user_id)]
    if getattr(user, "team_id", None):
        pass  # team members may act on shared proposals

    result = await db.execute(select(SetupProposal).where(*conditions))
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    proposal.status = status
    await db.commit()
    return {"id": str(proposal.id), "status": proposal.status}
