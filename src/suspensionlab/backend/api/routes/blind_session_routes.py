"""
backend/api/routes/blind_session_routes.py
==========================================
SuspensionLab PRO — Phase 5.1 Blind Engineering Session API.

Exposes authenticated, tenant-isolated blind engineering session endpoints:
- POST /api/v1/blind-sessions: Create new session (DRAFT)
- GET /api/v1/blind-sessions/{session_id}: Query session state & metadata (censored DTO)
- GET /api/v1/blind-sessions/{session_id}/context: Evaluator visible context
- POST /api/v1/blind-sessions/{session_id}/arm: Freeze configuration (ARMED)
- POST /api/v1/blind-sessions/{session_id}/activate: Begin evaluation (BLIND_ACTIVE)
- POST /api/v1/blind-sessions/{session_id}/submit: Lock prediction (SUBMISSION_LOCKED)
- POST /api/v1/blind-sessions/{session_id}/lock: Lock submission alias
- POST /api/v1/blind-sessions/{session_id}/abort: Abort session
- POST /api/v1/blind-sessions/{session_id}/prepare-reveal: Transition to READY_FOR_REVEAL

Strictly NO reveal endpoints or hidden outcome queries.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.blind_engineering_service import (
    BlindEngineeringService,
    BlindEngineeringError,
    SessionNotFoundError,
    InvalidStateTransitionError,
    DuplicateSubmissionError,
    InvalidSubmissionError,
    InformationFirewallViolationError,
    SessionAbortedError,
    UnauthorizedRevealError,
    OutcomeResolutionError,
    ComparisonExecutionError,
    DuplicateComparisonError,
)
from suspensionlab.backend.services.blind_prediction_schema import (
    PredictionSchemaError,
    InvisibleTargetError,
    InvisibleCandidateError,
    ContextBindingMismatchError,
)
from suspensionlab.backend.services.evidence_graph_service import (
    EntityNotFoundError,
    TenantIsolationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/blind-sessions", tags=["blind-sessions"])


# ── REQUEST & RESPONSE SCHEMAS ────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    root_entity_type: str = Field(...)
    root_entity_id: str = Field(...)
    hidden_outcome_type: str = Field(...)
    hidden_outcome_id: str = Field(...)
    configuration: Optional[Dict[str, Any]] = None


class SubmitPredictionRequest(BaseModel):
    submission_payload: Dict[str, Any] = Field(...)
    schema_version: str = Field("1.0")


class AbortSessionRequest(BaseModel):
    reason: str = Field("User requested abort", max_length=255)


class BlindSessionResponse(BaseModel):
    id: str
    status: str
    name: str
    root_entity_type: str
    root_entity_id: str
    visibility_summary: Dict[str, Any]
    has_submission: bool
    submission_id: Optional[str] = None
    submission_hash: Optional[str] = None
    has_comparison: bool = False
    comparison_id: Optional[str] = None
    comparison_hash: Optional[str] = None
    session_hash: str
    visible_context_hash: Optional[str] = None
    created_at: str
    locked_at: Optional[str] = None
    revealed_at: Optional[str] = None
    completed_at: Optional[str] = None


class BlindComparisonResponse(BaseModel):
    id: str
    session_id: str
    submission_id: str
    outcome_identity: Dict[str, Any]
    prediction_schema_version: str
    comparison_policy_version: str
    comparison_type: str
    verdict: str
    comparison_metrics: Dict[str, Any]
    tolerance_applied: Optional[Dict[str, Any]] = None
    interpretation: str
    comparison_hash: str
    computed_at: str
    prediction_payload: Optional[Dict[str, Any]] = None


class RevealedOutcomeResponse(BaseModel):
    session_id: str
    status: str
    outcome_entity_type: str
    outcome_entity_id: str
    outcome_identity: Dict[str, Any]
    outcome_hash: str
    revealed_at: Optional[str] = None


class VisibleContextResponse(BaseModel):
    session_id: str
    status: str
    root_entity: Dict[str, Any]
    visible_entities: List[Dict[str, Any]]
    visible_edges: List[Dict[str, Any]]
    visible_context_hash: str
    accessed_at: str


class BlindSubmissionResponse(BaseModel):
    id: str
    session_id: str
    submitted_by_user_id: str
    submission_hash: str
    submitted_at: str
    status: str


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("", response_model=BlindSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Creates a new blind engineering session in DRAFT state."""
    try:
        session = await BlindEngineeringService.create_session(
            db=db,
            user_context=user_context,
            name=payload.name,
            root_entity_type=payload.root_entity_type,
            root_entity_id=payload.root_entity_id,
            hidden_outcome_type=payload.hidden_outcome_type,
            hidden_outcome_id=payload.hidden_outcome_id,
            configuration=payload.configuration,
        )
        return await BlindEngineeringService.get_session(db, session.id, user_context)
    except (EntityNotFoundError, TenantIsolationError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Failed to create blind session: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{session_id}", response_model=BlindSessionResponse)
async def get_session(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Retrieves session metadata, strictly withholding outcome IDs and data."""
    try:
        return await BlindEngineeringService.get_session(db, session_id, user_context)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")


@router.get("/{session_id}/context", response_model=VisibleContextResponse)
async def get_visible_context(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Retrieves allowlisted visible engineering context for evaluator."""
    try:
        return await BlindEngineeringService.get_visible_context(db, session_id, user_context)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except InformationFirewallViolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{session_id}/arm", response_model=BlindSessionResponse)
async def arm_session(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Arms the session, freezing its configuration."""
    try:
        session = await BlindEngineeringService.arm_session(db, session_id, user_context)
        return await BlindEngineeringService.get_session(db, session.id, user_context)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{session_id}/activate", response_model=BlindSessionResponse)
async def activate_session(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Activates the session, making it BLIND_ACTIVE for evaluator."""
    try:
        session = await BlindEngineeringService.activate_session(db, session_id, user_context)
        return await BlindEngineeringService.get_session(db, session.id, user_context)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{session_id}/submit", response_model=BlindSubmissionResponse)
async def submit_prediction(
    session_id: str,
    payload: SubmitPredictionRequest,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Locks evaluator's prediction into an immutable BlindSubmission record."""
    try:
        sub = await BlindEngineeringService.lock_submission(
            db=db,
            session_id=session_id,
            submission_payload=payload.submission_payload,
            user_context=user_context,
            schema_version=payload.schema_version,
        )
        return {
            "id": str(sub.id),
            "session_id": str(sub.session_id),
            "submitted_by_user_id": str(sub.submitted_by_user_id),
            "submission_hash": sub.submission_hash,
            "submitted_at": sub.submitted_at.isoformat(),
            "status": sub.status,
        }
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except (InvisibleTargetError, InvisibleCandidateError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Target is not available in the active session context.")
    except ContextBindingMismatchError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (PredictionSchemaError, InvalidSubmissionError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (InvalidStateTransitionError, DuplicateSubmissionError, SessionAbortedError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{session_id}/lock", response_model=BlindSubmissionResponse)
async def lock_submission_alias(
    session_id: str,
    payload: SubmitPredictionRequest,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Alias for /submit to satisfy submission locking boundary endpoint."""
    return await submit_prediction(session_id, payload, user_context, db)


@router.post("/{session_id}/prepare-reveal", response_model=BlindSessionResponse)
async def prepare_reveal(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Transitions SUBMISSION_LOCKED -> READY_FOR_REVEAL."""
    try:
        session = await BlindEngineeringService.prepare_reveal(db, session_id, user_context)
        return await BlindEngineeringService.get_session(db, session.id, user_context)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{session_id}/abort", response_model=BlindSessionResponse)
async def abort_session(
    session_id: str,
    payload: AbortSessionRequest,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Aborts a non-terminal blind engineering session."""
    try:
        session = await BlindEngineeringService.abort_session(db, session_id, user_context, payload.reason)
        return await BlindEngineeringService.get_session(db, session.id, user_context)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{session_id}/reveal", response_model=BlindComparisonResponse)
async def reveal_session(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes controlled reveal of the withheld outcome and performs comparative evaluation.
    Privileged transition: READY_FOR_REVEAL -> REVEALED -> COMPLETED.
    """
    try:
        await BlindEngineeringService.execute_reveal(
            db=db,
            session_id=session_id,
            user_context=user_context,
        )
        return await BlindEngineeringService.get_comparison_result(
            db=db,
            session_id=session_id,
            user_context=user_context,
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except UnauthorizedRevealError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (InvalidSubmissionError, DuplicateSubmissionError, DuplicateComparisonError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (OutcomeResolutionError, ComparisonExecutionError) as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{session_id}/comparison", response_model=BlindComparisonResponse)
async def get_comparison(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves the immutable prediction-vs-outcome comparison result.
    Withheld if session outcome has not been legitimately revealed.
    """
    try:
        return await BlindEngineeringService.get_comparison_result(
            db=db,
            session_id=session_id,
            user_context=user_context,
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except InformationFirewallViolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except BlindEngineeringError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{session_id}/reveal", response_model=RevealedOutcomeResponse)
async def get_reveal(
    session_id: str,
    user_context: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves the authoritative revealed outcome identity snapshot.
    Withheld if session outcome has not been legitimately revealed.
    """
    try:
        return await BlindEngineeringService.get_revealed_outcome(
            db=db,
            session_id=session_id,
            user_context=user_context,
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blind session '{session_id}' not found.")
    except InformationFirewallViolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
