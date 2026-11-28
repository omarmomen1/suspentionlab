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

import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services import digital_twin
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["digital-twin"])


class CreateTwinRequest(BaseModel):
    car_ref: str = Field(..., max_length=120, description="e.g. CAR-2026-07")
    setup_ref: str = Field(..., max_length=120, description="e.g. SETUP-SPA-R4")
    track_ref: Optional[str] = None
    base_params: dict = Field(..., description="Handbook parameters (m_s, k_s, c, MR, …)")


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail="The requested resource was not found.")


@router.post("", status_code=201)
async def create_twin(
    req: CreateTwinRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    if "m_s" not in req.base_params:
        raise HTTPException(status_code=400, detail="base_params must include m_s (sprung mass).")

    # ── Trial Governance: Enforce 1 vehicle limit & expiration ──
    from suspensionlab.backend.services.trial_service import TrialService
    trial = await TrialService.assert_trial_access(db, user, action="vehicle", delta=1)

    twin = await digital_twin.create_twin(
        db, user.user_id, getattr(user, "team_id", None),
        req.car_ref, req.setup_ref, req.track_ref, req.base_params,
    )
    if trial:
        await TrialService.record_trial_usage(db, user, action="vehicle", delta=1)
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
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
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
    user: UserContext = Depends(require_permission(Permission.CALIBRATION_RUN)),
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
        raise HTTPException(status_code=500, detail="Calibration failed.")
    return result


@router.get("/{twin_id}/report")
async def twin_dyno_report(
    twin_id: str,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Dyno Day in a Box (Tier A2): everything a chief engineer needs on one page —
    identified ride frequency & damping, calibration confidence, model-validity
    assessment, and a SHA-256 provenance hash over the canonical payload so the
    printed report is verifiable against this exact API response.
    """
    import hashlib
    import json as _json

    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)

    from suspensionlab.physics.model_validity import assess_quarter_car

    identification = twin.last_identification or {}
    calibrated = twin.calibrated_params or {}
    validity = assess_quarter_car(calibrated if calibrated else twin.base_params)

    report = {
        "twin": {
            "id": str(twin.id),
            "car_ref": twin.car_ref,
            "setup_ref": twin.setup_ref,
            "track_ref": twin.track_ref,
            "calibration_count": twin.calibration_count,
            "last_calibration_at": (
                twin.last_calibration_at.isoformat() if twin.last_calibration_at else None
            ),
        },
        "identification": {
            "sprung_freq_hz": identification.get("f_n_s_hz") or identification.get("sprung_freq_hz"),
            "damping_ratio": identification.get("zeta_s") or identification.get("damping_ratio"),
            "confidence": identification.get("confidence"),
        },
        "parameters": {
            "base": twin.base_params,
            "calibrated": calibrated,
        },
        "validity": validity.to_dict(),
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }

    # Provenance: SHA-256 over the canonical JSON of everything above.
    canonical = _json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    report["provenance"] = {
        "algorithm": "sha256",
        "hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "note": "Hash of the canonical JSON of this payload excluding this field.",
    }
    return report


@router.get("/{twin_id}/learnings")
async def twin_learnings(
    twin_id: str,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
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
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
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
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
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
@router.put("/proposals/{proposal_id}/status")
async def set_proposal_status(
    proposal_id: str,
    status: str = Query(..., pattern="^(APPROVED|REJECTED|EXPORTED)$"),
    user: UserContext = Depends(require_permission(Permission.SETUP_APPROVE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Engineer decision on a proposal. Only `status` is mutable — the technical
    content of a proposal is immutable once created.
    """
    import uuid as _uuid
    from sqlalchemy import select
    from suspensionlab.backend.database.models.setup_proposal import SetupProposal

    # 1. Fetch proposal by ID
    query = select(SetupProposal).where(SetupProposal.id == _uuid.UUID(str(proposal_id)))
    result = await db.execute(query)
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    # 2. Multi-tenant boundary enforcement
    is_owner = (str(proposal.user_id) == str(user.user_id))
    is_same_team = bool(proposal.team_id and user.team_id and str(proposal.team_id) == str(user.team_id))
    
    # Org admin can only approve within their own organization
    is_same_org_admin = False
    if getattr(user, "organization_id", None) and (user.is_admin or user.org_role in ("ORG_ADMIN", "ADMIN")):
        if proposal.team_id:
            from suspensionlab.backend.database.models.team import Team
            team_res = await db.execute(select(Team).where(Team.id == proposal.team_id))
            p_team = team_res.scalar_one_or_none()
            if p_team and str(p_team.organization_id) == str(user.organization_id):
                is_same_org_admin = True
    elif bool(user.is_admin and not getattr(user, "organization_id", None)):
        is_same_org_admin = True

    if not (is_owner or is_same_team or is_same_org_admin):
        raise HTTPException(
            status_code=403,
            detail="Cross-tenant access forbidden: Cannot approve proposals from another organization or team."
        )

    # 3. Idempotency check: If already in requested status, return existing record
    if proposal.status == status:
        return {
            "id": str(proposal.id),
            "status": proposal.status,
            "approved_by": str(proposal.approved_by_user_id) if proposal.approved_by_user_id else str(user.user_id),
            "approved_role": proposal.approved_by_role or (user.team_role or user.org_role or "Admin").upper(),
            "approved_at": proposal.approved_at.isoformat() if proposal.approved_at else None,
            "proposal_hash": proposal.proposal_hash,
            "approval_signature": proposal.approval_signature,
            "idempotent": True,
        }

    import hmac as _hmac
    import hashlib
    from datetime import datetime, timezone
    from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY
    from suspensionlab.backend.security.audit import record_audit_event, canonical_hash

    now_utc = datetime.now(timezone.utc)
    actor_id = str(user.user_id)
    actor_role = (user.team_role or user.org_role or "Admin").upper()

    # Ensure proposal_hash is populated
    if not proposal.proposal_hash:
        prop_payload = {
            "recommended_params": proposal.recommended_params,
            "param_changes": proposal.param_changes,
            "predicted_effects": proposal.predicted_effects,
        }
        proposal.proposal_hash = canonical_hash(prop_payload)

    jwt_keys = get_jwt_keys()
    active_key = jwt_keys.get(JWT_ACTIVE_KEY)
    if not active_key:
        raise HTTPException(
            status_code=500,
            detail="Active cryptographic key missing for digital twin sign-off.",
        )
    secret_key = active_key.encode("utf-8")
    sig_msg = f"{proposal.id}:{actor_id}:{actor_role}:{status}:{proposal.proposal_hash}:{now_utc.isoformat()}".encode()
    approval_sig = _hmac.new(secret_key, sig_msg, hashlib.sha256).hexdigest()

    proposal.status = status
    proposal.approved_by_user_id = _uuid.UUID(actor_id)
    proposal.approved_by_role = actor_role
    proposal.approved_at = now_utc
    proposal.approval_signature = approval_sig

    # Emit tamper-evident Merkle audit log event
    await record_audit_event(
        db=db,
        event_type=f"PROPOSAL_{status}",
        user_id=actor_id,
        team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
        metadata={
            "proposal_id": str(proposal.id),
            "twin_id": str(proposal.twin_id),
            "status": status,
            "role": actor_role,
            "proposal_hash": proposal.proposal_hash,
            "approval_signature": approval_sig,
            "timestamp": now_utc.isoformat(),
        }
    )

    await db.commit()
    await db.refresh(proposal)

    return {
        "id": str(proposal.id),
        "status": status,
        "approved_by": actor_id,
        "approved_role": actor_role,
        "approved_at": now_utc.isoformat(),
        "proposal_hash": proposal.proposal_hash,
        "approval_signature": approval_sig,
    }


@router.get("/{twin_id}/operational-state")
async def get_twin_operational_state_endpoint(
    twin_id: str,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Answers: 'What does the virtual vehicle currently believe is happening to the real vehicle?' (Section 6 & 7).
    Renders MEASURED, ESTIMATED, SIMULATED, RESIDUAL states, model health, and model divergence.
    """
    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)

    return await digital_twin.get_twin_operational_state(db, twin)


class TrackLoopRequest(BaseModel):
    session_id: str = Field(..., description="Track telemetry session ID, e.g. SESS-FP3-009")
    telemetry_csv: str = Field(..., description="Raw CSV string from track telemetry")
    proposal_id: Optional[str] = Field(None, description="Setup proposal ID being validated")


@router.post("/{twin_id}/track-loop")
async def execute_track_loop_endpoint(
    twin_id: str,
    req: TrackLoopRequest,
    user: UserContext = Depends(require_permission(Permission.CALIBRATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes Closed Track Loop (Section 16):
    new telemetry → compare prediction → residual → model divergence → recalibrate if justified → update twin → record timeline event.
    """
    try:
        twin = await digital_twin.get_twin(db, twin_id, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)

    try:
        report = await digital_twin.execute_track_loop_closure(
            db=db,
            twin=twin,
            session_id=req.session_id,
            telemetry_csv=req.telemetry_csv,
            proposal_id=req.proposal_id,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
        )
        return report
    except Exception as exc:
        logger.exception("Track loop closure failed: %s", exc)
        raise HTTPException(status_code=500, detail="Track loop closure failed.")


