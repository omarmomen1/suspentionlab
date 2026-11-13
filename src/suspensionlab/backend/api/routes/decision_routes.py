"""
backend/api/routes/decision_routes.py
======================================
Vehicle Development Timeline & Engineering Decisions API Routes (Sections 10-15).

Endpoints:
GET  /api/v1/timeline           → Chronological vehicle development timeline (11 event types)
GET  /api/v1/timeline/compare   → 'What Changed?' comparative diffing between two events
POST /api/v1/timeline/events    → Record a manual / tool timeline event
GET  /api/v1/decisions          → List formal engineering decisions
POST /api/v1/decisions          → Create formal Engineering Decision Record
GET  /api/v1/decisions/{id}     → Get decision detail with evidence & hashes
POST /api/v1/decisions/{id}/approve → Cryptographic sign-off (HMAC-SHA256 signature)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.timeline_decision_service import TimelineDecisionService

router = APIRouter(tags=["timeline-decisions"])


# ── Pydantic Request Models ───────────────────────────────────────────────────

class CreateDecisionRequest(BaseModel):
    question: str = Field(..., min_length=5, description="Engineering problem/question")
    context: Dict[str, Any] = Field(..., description="Vehicle, setup, track, session, model_version")
    candidates: List[Dict[str, Any]] = Field(..., description="Candidate setup options tested")
    selected_option: Dict[str, Any] = Field(..., description="Selected winning setup candidate")
    reason: str = Field(..., description="Technical engineering justification")
    tradeoffs: List[Dict[str, Any]] = Field(..., description="Mandatory exposed tradeoffs")
    simulation_evidence: Dict[str, Any] = Field(..., description="Solver KPIs, run IDs, deltas")
    telemetry_evidence: Dict[str, Any] = Field(..., description="Telemetry session correlation & residuals")
    validation_evidence: Dict[str, Any] = Field(..., description="Rig dyno correlation, constraint checks")
    risks: List[str] = Field(default_factory=list, description="Operational boundaries & risks")
    author: Optional[str] = Field(None, description="Authoring engineer name")


class ApproveDecisionRequest(BaseModel):
    approver_name: str = Field(..., min_length=2, description="Approver's full name")
    approver_role: str = Field("Chief Race Engineer", description="Sign-off role: Chief Race Engineer | Technical Director | Performance Lead")


class CreateTimelineEventRequest(BaseModel):
    event_type: str = Field(..., description="vehicle_change | setup_change | telemetry_session | calibration | simulation | optimization | validation | report | approval | track_session | engineering_decision")
    title: str = Field(..., min_length=3)
    description: str = Field(..., min_length=5)
    vehicle_ref: str = Field("CAR-2026-07")
    setup_ref: str = Field("SETUP-PROD")
    model_version: str = Field("QCAR-ODE-RK45-v2.4")
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    parameter_changes: Optional[List[Dict[str, Any]]] = None
    engineering_effects: Optional[List[Dict[str, Any]]] = None
    validation_effects: Optional[Dict[str, Any]] = None
    decision_consequences: Optional[List[str]] = None
    evidence: Optional[Dict[str, Any]] = None
    approval_status: Optional[str] = "UNVALIDATED"
    author: Optional[str] = Field(None, description="Authoring engineer name")


# ── Timeline Routes ───────────────────────────────────────────────────────────

@router.get("/timeline")
async def list_timeline(
    limit: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Chronological Vehicle Development Timeline (Section 10).
    Aggregates events across vehicle changes, calibrations, approvals, and track runs.
    """
    events = await TimelineDecisionService.list_timeline_events(
        db=db,
        user_id=user.user_id,
        team_id=getattr(user, "team_id", None),
        limit=limit,
    )
    return {"total": len(events), "events": events}


@router.api_route("/timeline/compare", methods=["GET", "POST"])
async def compare_timeline_events_endpoint(
    request: Request,
    event_a_id: Optional[str] = Query(None, description="First event UUID"),
    event_b_id: Optional[str] = Query(None, description="Second event UUID"),
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    'What Changed?' comparison engine between two timeline events (Section 12).
    Accepts GET query params or POST JSON body with {event_a_id, event_b_id} or {event_id_a, event_id_b}.
    """
    eid_a = event_a_id
    eid_b = event_b_id
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                eid_a = eid_a or body.get("event_a_id") or body.get("event_id_a")
                eid_b = eid_b or body.get("event_b_id") or body.get("event_id_b")
        except Exception:
            pass
    if not eid_a or not eid_b:
        raise HTTPException(status_code=422, detail="Both event_a_id and event_b_id are required.")
    try:
        report = await TimelineDecisionService.compare_timeline_events(
            db=db,
            event_a_id=eid_a,
            event_b_id=eid_b,
            user_id=user.user_id,
            team_id=getattr(user, "team_id", None),
        )
        return report
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Event comparison failed: {exc}")


@router.post("/timeline/events", status_code=status.HTTP_201_CREATED)
async def create_timeline_event_endpoint(
    req: CreateTimelineEventRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Explicitly record a Vehicle Development Timeline event."""
    ev = await TimelineDecisionService.create_timeline_event(
        db=db,
        user_id=user.user_id,
        team_id=getattr(user, "team_id", None),
        event_type=req.event_type,
        title=req.title,
        description=req.description,
        author=user.name or user.email or req.author or "Dynamics Engineer",
        vehicle_ref=req.vehicle_ref,
        setup_ref=req.setup_ref,
        model_version=req.model_version,
        before_state=req.before_state,
        after_state=req.after_state,
        parameter_changes=req.parameter_changes,
        engineering_effects=req.engineering_effects,
        validation_effects=req.validation_effects,
        decision_consequences=req.decision_consequences,
        evidence=req.evidence,
        approval_status=req.approval_status or "UNVALIDATED",
    )
    return ev


# ── Decision Routes ───────────────────────────────────────────────────────────

@router.get("/decisions")
async def list_decisions_endpoint(
    limit: int = Query(50, ge=1, le=100),
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Lists formal Engineering Decision Records (Section 13)."""
    decisions = await TimelineDecisionService.list_decisions(
        db=db,
        user_id=user.user_id,
        team_id=getattr(user, "team_id", None),
        limit=limit,
    )
    return {"total": len(decisions), "decisions": decisions}


@router.post("/decisions", status_code=status.HTTP_201_CREATED)
async def create_decision_endpoint(
    req: CreateDecisionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Creates a formal Engineering Decision Record with three-pillar evidence (Section 13).
    Strictly distinguishes RECOMMENDED vs VALIDATED vs APPROVED.
    """
    # ── Trial Governance: Expired trials cannot create decisions ──
    from suspensionlab.backend.services.trial_service import TrialService
    await TrialService.assert_trial_access(db, user, action="decision")

    dec = await TimelineDecisionService.create_decision(
        db=db,
        user_id=user.user_id,
        team_id=getattr(user, "team_id", None),
        question=req.question,
        context=req.context,
        candidates=req.candidates,
        selected_option=req.selected_option,
        reason=req.reason,
        tradeoffs=req.tradeoffs,
        simulation_evidence=req.simulation_evidence,
        telemetry_evidence=req.telemetry_evidence,
        validation_evidence=req.validation_evidence,
        risks=req.risks,
        author=user.name or user.email or req.author or "Lead Dynamics Engineer",
    )
    return dec


@router.get("/decisions/{id}")
async def get_decision_endpoint(
    id: str,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Retrieves an Engineering Decision Record with full cryptographic provenance."""
    try:
        dec = await TimelineDecisionService.get_decision(
            db=db,
            decision_id=id,
            user_id=user.user_id,
            team_id=getattr(user, "team_id", None),
        )
        return dec
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/decisions/{id}/approve")
async def approve_decision_endpoint(
    id: str,
    req: ApproveDecisionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_APPROVE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Formal sign-off of an Engineering Decision with HMAC-SHA256 non-repudiable signature (Section 15).
    """
    try:
        dec = await TimelineDecisionService.approve_decision(
            db=db,
            decision_id=id,
            approver_name=req.approver_name,
            approver_role=req.approver_role,
            user_id=user.user_id,
            team_id=getattr(user, "team_id", None),
        )
        return dec
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Approval failed: {exc}")


@router.get("/decisions/reconstruct/{identifier}")
async def reconstruct_decision_memory_endpoint(
    identifier: str,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Answers 'Why did we choose Setup X?' (Requirement 5).
    Reconstructs the full 7-element engineering provenance chain:
    QUESTION → EVIDENCE → EXPERIMENTS → SIMULATION → COMPARISON → VALIDATION → APPROVAL
    """
    try:
        return await TimelineDecisionService.reconstruct_institutional_memory(
            db=db,
            identifier=identifier,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to reconstruct institutional memory: {exc}")

