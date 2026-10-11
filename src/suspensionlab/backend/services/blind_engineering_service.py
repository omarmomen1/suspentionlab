"""
backend/services/blind_engineering_service.py
=============================================
SuspensionLab PRO — Phase 5.1 Blind Engineering Information Firewall Service.

Provides complete information governance for blind evaluation experiments:
- Explicit finite state machine transitions with immutable configuration locking
- Strict multi-tenant and personal workspace isolation
- Information firewall guaranteeing zero hidden outcome leakage
- Explicit allowlisted visible context derivation via Evidence Graph
- Deterministic cryptographic hashing (session, context, submission)
- Concurrency-safe atomic submission locking boundary
- Immutable audit event logging with no withheld data leakage
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSubmission,
    BlindSessionStatus,
    VisibilityClassification,
    ConfigurationImmutabilityError,
    BlindSubmissionImmutabilityError,
    BlindComparisonResult,
    BlindComparisonImmutabilityError,
)
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.security.audit import record_audit_event
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
)
from suspensionlab.backend.services.blind_prediction_schema import (
    PREDICTION_SCHEMA_V1,
    SUPPORTED_SCHEMA_VERSIONS,
    SUPPORTED_UNITS,
    PredictionType,
    ExpectedDirection,
    PredictionSchemaError,
    UnsupportedSchemaVersionError,
    InvalidPredictionTypeError,
    InvalidPredictionTargetError,
    InvisibleTargetError,
    InvisibleCandidateError,
    MissingUnitError,
    InvalidUnitError,
    InvalidNumericValueError,
    InvalidConfidenceError,
    ContextBindingMismatchError,
    validate_prediction_contract,
    canonicalize_prediction_payload,
)
from suspensionlab.backend.services.blind_comparison_engine import (
    COMPARISON_POLICY_V1,
    ComparisonVerdict,
    evaluate_prediction_comparison,
    compute_canonical_comparison_hash,
    compute_canonical_outcome_identity,
    check_dimensional_compatibility,
    normalize_unit_value,
)

logger = logging.getLogger("blind_engineering_service")
logger.setLevel(logging.INFO)


# ── EXCEPTIONS ────────────────────────────────────────────────────────────────

class BlindEngineeringError(Exception):
    """Base exception for all Blind Engineering operations."""
    pass



class SessionNotFoundError(BlindEngineeringError):
    """Raised when a session does not exist or user is unauthorized."""
    pass


class InvalidStateTransitionError(BlindEngineeringError):
    """Raised when an unpermitted lifecycle state transition is attempted."""
    pass


class DuplicateSubmissionError(BlindEngineeringError):
    """Raised when a replacement submission is attempted on an active/locked session."""
    pass


class InvalidSubmissionError(BlindEngineeringError):
    """Raised when a submission payload is invalid or malformed."""
    pass


class InformationFirewallViolationError(BlindEngineeringError):
    """Raised when an operation attempts unauthorized access to hidden outcomes."""
    pass


class SessionAbortedError(BlindEngineeringError):
    """Raised when mutation is attempted on an aborted session."""
    pass


class UnauthorizedRevealError(BlindEngineeringError):
    """Raised when an actor lacks privileges to reveal a withheld engineering outcome."""
    pass


class OutcomeResolutionError(BlindEngineeringError):
    """Raised when the authoritative withheld outcome cannot be resolved or found."""
    pass


class ComparisonExecutionError(BlindEngineeringError):
    """Raised when comparative evaluation fails during outcome reveal."""
    pass


class DuplicateComparisonError(BlindEngineeringError):
    """Raised when a duplicate comparison result is attempted for the same policy version."""
    pass


# ── STATE MACHINE TRANSITIONS ────────────────────────────────────────────────

VALID_TRANSITIONS: Dict[str, Set[str]] = {
    BlindSessionStatus.DRAFT.value: {
        BlindSessionStatus.ARMED.value,
        BlindSessionStatus.ABORTED.value,
    },
    BlindSessionStatus.ARMED.value: {
        BlindSessionStatus.BLIND_ACTIVE.value,
        BlindSessionStatus.ABORTED.value,
    },
    BlindSessionStatus.BLIND_ACTIVE.value: {
        BlindSessionStatus.SUBMISSION_LOCKED.value,
        BlindSessionStatus.ABORTED.value,
    },
    BlindSessionStatus.SUBMISSION_LOCKED.value: {
        BlindSessionStatus.READY_FOR_REVEAL.value,
        BlindSessionStatus.ABORTED.value,
    },
    BlindSessionStatus.READY_FOR_REVEAL.value: {
        BlindSessionStatus.REVEALED.value,
        BlindSessionStatus.ABORTED.value,
    },
    BlindSessionStatus.REVEALED.value: {
        BlindSessionStatus.COMPLETED.value,
        BlindSessionStatus.ABORTED.value,
    },
    BlindSessionStatus.COMPLETED.value: set(),
    BlindSessionStatus.ABORTED.value: set(),
}


# ── DEFAULT ALLOWLIST FOR VISIBLE CONTEXT ─────────────────────────────────────

DEFAULT_VISIBLE_FIELDS: Dict[str, List[str]] = {
    "EngineeringDecision": [
        "decision_id", "question", "context", "candidates", "tradeoffs", "risks", "created_at"
    ],
    "TelemetrySession": [
        "session_number", "session_code", "track_name", "vehicle_id", "setup_id",
        "channels", "summary_metrics", "sample_count", "duration_s", "created_at"
    ],
    "Investigation": [
        "investigation_number", "investigation_code", "session_code", "detection_type",
        "symptom", "affected_regime", "severity", "status", "evidence_snapshot", "created_at"
    ],
    "EngineeringQuestion": [
        "question_number", "question_code", "title", "question_text", "regime", "status", "created_at"
    ],
    "Experiment": [
        "experiment_number", "experiment_code", "title", "hypothesis", "variables_evaluated", "design_type", "created_at"
    ],
    "SimulationRun": [
        "run_number", "run_code", "model_version", "solver_name", "setup_code", "operating_conditions", "status", "created_at"
    ],
    "SetupCandidate": [
        "candidate_number", "candidate_code", "name", "parameters", "rationale", "status", "created_at"
    ],
    "EngineeringProblem": [
        "problem_number", "problem_code", "title", "description", "regime", "created_at"
    ],
    "CausalHypothesis": [
        "hypothesis_number", "hypothesis_code", "hypothesis_statement", "created_at"
    ],
    "ControlledExperiment": [
        "design_number", "design_code", "title", "created_at"
    ],
    "TrackTestPrediction": [
        "prediction_number", "prediction_code", "created_at"
    ],
    "TimelineEvent": [
        "event_number", "event_type", "summary", "created_at"
    ],
}

FORBIDDEN_OUTCOME_FIELDS: Set[str] = {
    "selected_option",
    "reason",
    "validation_evidence",
    "holdout_metrics",
    "pass_fail",
    "test_verdict",
    "r2_score",
    "residual_metrics",
    "approved_by",
    "approval_status",
}


# ── DETERMINISTIC HASHING CONTRACTS ──────────────────────────────────────────

def compute_canonical_session_hash(
    name: str,
    root_entity_type: str,
    root_entity_id: str,
    hidden_outcome_type: str,
    hidden_outcome_id: str,
    configuration: Dict[str, Any],
    organization_id: Optional[Union[str, uuid.UUID]] = None,
    team_id: Optional[Union[str, uuid.UUID]] = None,
    created_by_user_id: Optional[Union[str, uuid.UUID]] = None,
) -> str:
    """
    Computes deterministic SHA-256 hash over canonical session creation attributes.
    """
    canonical_data = {
        "name": str(name).strip(),
        "root_entity_type": str(root_entity_type).strip(),
        "root_entity_id": str(root_entity_id).strip(),
        "hidden_outcome_type": str(hidden_outcome_type).strip(),
        "hidden_outcome_id": str(hidden_outcome_id).strip(),
        "configuration": configuration,
        "organization_id": str(organization_id) if organization_id else None,
        "team_id": str(team_id) if team_id else None,
        "created_by_user_id": str(created_by_user_id) if created_by_user_id else None,
    }
    canonical_str = json.dumps(canonical_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_canonical_context_hash(context_dict: Dict[str, Any]) -> str:
    """
    Computes deterministic SHA-256 hash over the canonical visible context dictionary.
    Excludes non-deterministic access timestamps and session status to preserve
    strict invariant identity of visible engineering context.
    """
    cleaned = copy.deepcopy(context_dict)
    cleaned.pop("accessed_at", None)
    cleaned.pop("status", None)
    cleaned.pop("visible_context_hash", None)
    canonical_str = json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()



def compute_canonical_submission_hash(
    session_id: Union[str, uuid.UUID],
    submitter_user_id: Union[str, uuid.UUID],
    submission_payload: Dict[str, Any],
    visible_context_hash: str,
    schema_version: str = "1.0",
) -> str:
    """
    Computes deterministic SHA-256 hash over canonical submission components:
    - canonical session identity
    - submission payload (RFC 8785 canonical JSON)
    - submitter identity
    - visible-context snapshot identity (visible_context_hash)
    - submission schema version
    Volatile timestamps are excluded to ensure mathematical reproducibility.
    """
    canonical_data = {
        "session_id": str(session_id),
        "submitter_user_id": str(submitter_user_id),
        "submission_payload": submission_payload,
        "visible_context_hash": str(visible_context_hash),
        "schema_version": str(schema_version),
    }
    canonical_str = json.dumps(canonical_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


# ── SERVICE IMPLEMENTATION ───────────────────────────────────────────────────

class BlindEngineeringService:
    """
    Canonical Information Firewall and Blind Session Governance Service.
    """
    _session_locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    def _get_lock(cls, session_id: str) -> asyncio.Lock:
        if session_id not in cls._session_locks:
            cls._session_locks[session_id] = asyncio.Lock()
        return cls._session_locks[session_id]

    @classmethod
    def enforce_session_tenant_access(
        cls,
        session: BlindEngineeringSession,
        user_context: UserContext,
    ) -> None:
        """
        Enforces strict workspace/tenant boundaries.
        Unauthorized or cross-tenant access is indistinguishable from not-found.
        """
        user_uuid_str = str(user_context.user_id)

        # Team-scoped session
        if session.team_id is not None:
            if user_context.team_id is None or str(session.team_id) != str(user_context.team_id):
                raise SessionNotFoundError(f"Blind session '{session.id}' not found.")
        else:
            # Personal workspace session: strictly creator only
            if str(session.created_by_user_id) != user_uuid_str:
                raise SessionNotFoundError(f"Blind session '{session.id}' not found.")

        # Organization scope if set
        if session.organization_id is not None and user_context.organization_id is not None:
            if str(session.organization_id) != str(user_context.organization_id):
                raise SessionNotFoundError(f"Blind session '{session.id}' not found.")

    @classmethod
    async def create_session(
        cls,
        db: AsyncSession,
        user_context: UserContext,
        name: str,
        root_entity_type: str,
        root_entity_id: str,
        hidden_outcome_type: str,
        hidden_outcome_id: str,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> BlindEngineeringSession:
        """
        Creates a new BlindEngineeringSession in DRAFT state.
        Validates referential existence of endpoints within the requester's tenant.
        """
        user_uuid = uuid.UUID(str(user_context.user_id))
        team_uuid = uuid.UUID(str(user_context.team_id)) if user_context.team_id else None
        org_uuid = uuid.UUID(str(user_context.organization_id)) if user_context.organization_id else None

        # 1. Validate root entity exists in tenant
        await EvidenceGraphService.validate_endpoint(
            db=db,
            entity_type=root_entity_type,
            entity_id=root_entity_id,
            expected_team_id=team_uuid,
            expected_org_id=org_uuid,
            expected_user_id=user_uuid if team_uuid is None else None,
        )

        # 2. Validate hidden outcome entity exists in tenant
        await EvidenceGraphService.validate_endpoint(
            db=db,
            entity_type=hidden_outcome_type,
            entity_id=hidden_outcome_id,
            expected_team_id=team_uuid,
            expected_org_id=org_uuid,
            expected_user_id=user_uuid if team_uuid is None else None,
        )

        # 3. Canonicalize configuration structure
        cfg = configuration or {}
        normalized_cfg = {
            "visible_entities": cfg.get("visible_entities", []),
            "visible_graph_relationships": cfg.get("visible_graph_relationships", [
                r.value for r in EvidenceGraphRelationship
            ]),
            "hidden_entity": {
                "entity_type": hidden_outcome_type,
                "entity_id": hidden_outcome_id,
                "hidden_fields": list(FORBIDDEN_OUTCOME_FIELDS),
            },
            "submission_schema": cfg.get("submission_schema", {"type": "object", "required": ["prediction"]}),
            "reveal_policy": cfg.get("reveal_policy", {"policy": "LOCKED_APPROVAL_REQUIRED"}),
        }

        # 4. Deterministic session hash
        session_hash = compute_canonical_session_hash(
            name=name,
            root_entity_type=root_entity_type,
            root_entity_id=root_entity_id,
            hidden_outcome_type=hidden_outcome_type,
            hidden_outcome_id=hidden_outcome_id,
            configuration=normalized_cfg,
            organization_id=org_uuid,
            team_id=team_uuid,
            created_by_user_id=user_uuid,
        )

        session = BlindEngineeringSession(
            name=name.strip(),
            organization_id=org_uuid,
            team_id=team_uuid,
            created_by_user_id=user_uuid,
            status=BlindSessionStatus.DRAFT.value,
            root_entity_type=root_entity_type,
            root_entity_id=root_entity_id,
            hidden_outcome_type=hidden_outcome_type,
            hidden_outcome_id=hidden_outcome_id,
            configuration=normalized_cfg,
            session_hash=session_hash,
        )

        db.add(session)
        await db.commit()
        await db.refresh(session)

        # Audit event (NO withheld data logged)
        await record_audit_event(
            db=db,
            event_type="SESSION_CREATED",
            user_id=str(user_uuid),
            team_id=str(team_uuid) if team_uuid else None,
            organization_id=str(org_uuid) if org_uuid else None,
            artifact_id=f"blind_session:{session.id}",
            metadata={
                "session_id": str(session.id),
                "name": session.name,
                "status": session.status,
                "root_entity_type": session.root_entity_type,
                "root_entity_id": session.root_entity_id,
                "session_hash": session.session_hash,
            },
        )

        logger.info(
            "Created BlindEngineeringSession id=%s root=%s:%s status=%s",
            session.id, session.root_entity_type, session.root_entity_id, session.status
        )
        return session

    @classmethod
    async def get_session_record(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> BlindEngineeringSession:
        """
        Retrieves internal session record enforcing strict tenant boundary.
        """
        try:
            sess_uuid = uuid.UUID(str(session_id))
        except Exception:
            raise SessionNotFoundError(f"Blind session '{session_id}' not found.")

        stmt = select(BlindEngineeringSession).where(BlindEngineeringSession.id == sess_uuid)
        result = await db.execute(stmt)
        session = result.scalars().first()
        if not session:
            raise SessionNotFoundError(f"Blind session '{session_id}' not found.")

        cls.enforce_session_tenant_access(session, user_context)
        return session

    @classmethod
    async def get_session(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> Dict[str, Any]:
        """
        Retrieves evaluator-safe public DTO for the session.
        Withheld outcome IDs and values are strictly suppressed.
        """
        session = await cls.get_session_record(db, session_id, user_context)

        # Check if submission exists
        sub_stmt = select(BlindSubmission).where(BlindSubmission.session_id == session.id)
        sub_res = await db.execute(sub_stmt)
        submission = sub_res.scalars().first()

        # Check if comparison exists
        comp_stmt = select(BlindComparisonResult).where(BlindComparisonResult.session_id == session.id)
        comp_res = await db.execute(comp_stmt)
        comparison = comp_res.scalars().first()

        is_revealed = session.status in (BlindSessionStatus.REVEALED.value, BlindSessionStatus.COMPLETED.value)

        return {
            "id": str(session.id),
            "status": session.status,
            "name": session.name,
            "root_entity_type": session.root_entity_type,
            "root_entity_id": session.root_entity_id,
            "visibility_summary": {
                "hidden_outcome_withheld": not is_revealed,
                "visible_relationships_count": len(session.configuration.get("visible_graph_relationships", [])),
                "visible_entities_count": len(session.configuration.get("visible_entities", [])),
            },
            "has_submission": submission is not None,
            "submission_id": str(submission.id) if submission else None,
            "submission_hash": submission.submission_hash if submission else None,
            "has_comparison": comparison is not None,
            "comparison_id": str(comparison.id) if comparison else None,
            "comparison_hash": comparison.comparison_hash if comparison else None,
            "session_hash": session.session_hash,
            "visible_context_hash": session.visible_context_hash,
            "created_at": session.created_at.isoformat(),
            "locked_at": session.locked_at.isoformat() if session.locked_at else None,
            "revealed_at": session.revealed_at.isoformat() if session.revealed_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }

    @classmethod
    async def arm_session(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> BlindEngineeringSession:
        """
        Transitions session DRAFT -> ARMED.
        Freezes configuration immutably.
        """
        lock = cls._get_lock(str(session_id))
        async with lock:
            session = await cls.get_session_record(db, session_id, user_context)
            if session.status != BlindSessionStatus.DRAFT.value:
                raise InvalidStateTransitionError(
                    f"Cannot arm session from status '{session.status}'. Must be in DRAFT."
                )

            session.status = BlindSessionStatus.ARMED.value
            await db.commit()
            await db.refresh(session)

            await record_audit_event(
                db=db,
                event_type="SESSION_ARMED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "status": session.status,
                    "session_hash": session.session_hash,
                },
            )

            logger.info("Armed BlindEngineeringSession id=%s", session.id)
            return session

    @classmethod
    async def activate_session(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> BlindEngineeringSession:
        """
        Transitions session ARMED -> BLIND_ACTIVE.
        Computes the initial canonical visible context hash.
        """
        lock = cls._get_lock(str(session_id))
        async with lock:
            session = await cls.get_session_record(db, session_id, user_context)
            if session.status != BlindSessionStatus.ARMED.value:
                raise InvalidStateTransitionError(
                    f"Cannot activate session from status '{session.status}'. Must be in ARMED."
                )

            # Compute initial visible context hash
            context_data = await cls._build_visible_context(db, session, user_context)
            context_hash = compute_canonical_context_hash(context_data)

            session.status = BlindSessionStatus.BLIND_ACTIVE.value
            session.visible_context_hash = context_hash

            await db.commit()
            await db.refresh(session)

            await record_audit_event(
                db=db,
                event_type="SESSION_ACTIVATED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "status": session.status,
                    "visible_context_hash": session.visible_context_hash,
                },
            )

            logger.info("Activated BlindEngineeringSession id=%s ctx_hash=%s", session.id, context_hash)
            return session

    @classmethod
    async def _build_visible_context(
        cls,
        db: AsyncSession,
        session: BlindEngineeringSession,
        user_context: UserContext,
    ) -> Dict[str, Any]:
        """
        Constructs the allowlisted visible context using the Evidence Graph.
        Strictly applies information firewall:
        - Completely omits the hidden outcome entity and all edges attached to it
        - Strictly filters out forbidden fields
        - Uses explicit allowlist
        """
        team_uuid = uuid.UUID(str(user_context.team_id)) if user_context.team_id else None
        user_uuid = uuid.UUID(str(user_context.user_id))
        org_uuid = uuid.UUID(str(user_context.organization_id)) if user_context.organization_id else None

        # 1. Resolve and extract allowlisted root entity fields
        root_res = await EvidenceGraphService.validate_endpoint(
            db=db,
            entity_type=session.root_entity_type,
            entity_id=session.root_entity_id,
            expected_team_id=team_uuid,
            expected_org_id=org_uuid,
            expected_user_id=user_uuid if team_uuid is None else None,
        )

        allowed_root_fields = DEFAULT_VISIBLE_FIELDS.get(session.root_entity_type, ["created_at"])
        root_data: Dict[str, Any] = {
            "entity_type": session.root_entity_type,
            "entity_id": session.root_entity_id,
        }
        for field in allowed_root_fields:
            if field in FORBIDDEN_OUTCOME_FIELDS:
                continue
            val = getattr(root_res.record, field, None)
            if val is not None:
                root_data[field] = val.isoformat() if hasattr(val, "isoformat") else val

        # 2. Traverse evidence graph upstream/downstream within allowed relationships
        allowed_rels = set(session.configuration.get("visible_graph_relationships", []))
        
        # Traverse backward to gather upstream evidence
        bw_traversal = await EvidenceGraphService.traverse_backward(
            db=db,
            root_type=session.root_entity_type,
            root_id=session.root_entity_id,
            team_id=team_uuid,
            user_id=user_uuid if team_uuid is None else None,
            organization_id=org_uuid,
            max_depth=5,
        )

        # Traverse forward to gather downstream evidence
        fw_traversal = await EvidenceGraphService.traverse_forward(
            db=db,
            root_type=session.root_entity_type,
            root_id=session.root_entity_id,
            team_id=team_uuid,
            user_id=user_uuid if team_uuid is None else None,
            organization_id=org_uuid,
            max_depth=5,
        )

        combined_nodes = {
            (n["entity_type"], n["entity_id"])
            for n in bw_traversal.get("nodes", []) + fw_traversal.get("nodes", [])
        }
        combined_edges = bw_traversal.get("edges", []) + fw_traversal.get("edges", [])

        # 3. FIREWALL FILTER: Strictly drop the hidden outcome and attached edges
        hidden_key = (session.hidden_outcome_type, session.hidden_outcome_id)

        safe_nodes = []
        for n_type, n_id in sorted(combined_nodes):
            if (n_type, n_id) == hidden_key:
                # WITHHELD
                continue
            if n_type == session.root_entity_type and n_id == session.root_entity_id:
                continue

            # Load entity and extract allowlisted fields
            try:
                node_res = await EvidenceGraphService.validate_endpoint(
                    db=db,
                    entity_type=n_type,
                    entity_id=n_id,
                    expected_team_id=team_uuid,
                    expected_org_id=org_uuid,
                    expected_user_id=user_uuid if team_uuid is None else None,
                )
                fields = DEFAULT_VISIBLE_FIELDS.get(n_type, ["created_at"])
                n_dict: Dict[str, Any] = {"entity_type": n_type, "entity_id": n_id}
                for f in fields:
                    if f in FORBIDDEN_OUTCOME_FIELDS:
                        continue
                    v = getattr(node_res.record, f, None)
                    if v is not None:
                        n_dict[f] = v.isoformat() if hasattr(v, "isoformat") else v
                safe_nodes.append(n_dict)
            except Exception:
                safe_nodes.append({"entity_type": n_type, "entity_id": n_id})

        safe_edges = []
        seen_edge_ids = set()
        for edge in combined_edges:
            e_id = edge.get("id")
            if e_id in seen_edge_ids:
                continue
            seen_edge_ids.add(e_id)

            s_pair = (edge.get("source_type"), edge.get("source_id"))
            t_pair = (edge.get("target_type"), edge.get("target_id"))
            rel = edge.get("relationship")

            # If connected to hidden outcome -> EXCLUDE
            if s_pair == hidden_key or t_pair == hidden_key:
                continue

            # If relationship not in allowed visible relationships -> EXCLUDE
            if allowed_rels and rel not in allowed_rels:
                continue

            safe_edges.append({
                "source_type": edge.get("source_type"),
                "source_id": edge.get("source_id"),
                "relationship": rel,
                "target_type": edge.get("target_type"),
                "target_id": edge.get("target_id"),
                "edge_hash": edge.get("edge_hash"),
            })

        safe_edges.sort(key=lambda e: (e["source_type"], e["source_id"], e["relationship"], e["target_type"], e["target_id"]))

        context_dict = {
            "session_id": str(session.id),
            "status": session.status,
            "root_entity": root_data,
            "visible_entities": safe_nodes,
            "visible_edges": safe_edges,
        }
        return context_dict

    @classmethod
    async def get_visible_context(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> Dict[str, Any]:
        """
        Retrieves the allowlisted visible context for an active/locked session.
        Records CONTEXT_ACCESSED audit event.
        """
        session = await cls.get_session_record(db, session_id, user_context)

        # Allow inspection if session is in an inspection state
        allowed_states = {
            BlindSessionStatus.DRAFT.value,
            BlindSessionStatus.ARMED.value,
            BlindSessionStatus.BLIND_ACTIVE.value,
            BlindSessionStatus.SUBMISSION_LOCKED.value,
            BlindSessionStatus.READY_FOR_REVEAL.value,
            BlindSessionStatus.REVEALED.value,
            BlindSessionStatus.COMPLETED.value,
        }
        if session.status not in allowed_states:
            raise InformationFirewallViolationError(
                f"Cannot access visible context when session is in status '{session.status}'."
            )

        context_data = await cls._build_visible_context(db, session, user_context)
        context_hash = compute_canonical_context_hash(context_data)
        context_data["visible_context_hash"] = context_hash
        context_data["accessed_at"] = datetime.now(timezone.utc).isoformat()

        # Audit context access
        await record_audit_event(
            db=db,
            event_type="CONTEXT_ACCESSED",
            user_id=str(user_context.user_id),
            team_id=str(user_context.team_id) if user_context.team_id else None,
            organization_id=str(user_context.organization_id) if user_context.organization_id else None,
            artifact_id=f"blind_session:{session.id}",
            metadata={
                "session_id": str(session.id),
                "status": session.status,
                "visible_context_hash": context_hash,
            },
        )

        return context_data

    @classmethod
    def validate_submission(
        cls,
        session: BlindEngineeringSession,
        payload: Dict[str, Any],
        visible_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Validates the submission payload against the authoritative versioned prediction contract.
        Ensures target visibility, numerical integrity, unit validity, and bounded confidence.
        """
        if not isinstance(payload, dict) or not payload:
            raise InvalidSubmissionError("Submission payload must be a non-empty JSON object.")

        ctx = visible_context or {}
        return validate_prediction_contract(
            payload=payload,
            visible_context=ctx,
            hidden_outcome_type=session.hidden_outcome_type,
            hidden_outcome_id=session.hidden_outcome_id,
        )

    @classmethod
    async def lock_submission(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        submission_payload: Dict[str, Any],
        user_context: UserContext,
        schema_version: str = PREDICTION_SCHEMA_V1,
    ) -> BlindSubmission:
        """
        Locks the engineer's prediction/decision into an immutable BlindSubmission record.
        Transitions session BLIND_ACTIVE -> SUBMISSION_LOCKED.
        Freezes context and submission hash deterministically.
        Rejects duplicates and concurrent replacement attempts.
        """
        lock = cls._get_lock(str(session_id))
        async with lock:
            session = await cls.get_session_record(db, session_id, user_context)

            if session.status == BlindSessionStatus.ABORTED.value:
                raise SessionAbortedError("Cannot submit to an aborted session.")

            if session.status != BlindSessionStatus.BLIND_ACTIVE.value:
                raise InvalidStateTransitionError(
                    f"Submissions can only be locked when session is in BLIND_ACTIVE state (current: {session.status})."
                )

            # Check for existing submission
            existing_stmt = select(BlindSubmission).where(BlindSubmission.session_id == session.id)
            existing_res = await db.execute(existing_stmt)
            if existing_res.scalars().first() is not None:
                raise DuplicateSubmissionError(
                    f"Session '{session.id}' already has an immutable submission. Replacement prohibited."
                )

            # Compute frozen visible context hash
            context_data = await cls._build_visible_context(db, session, user_context)
            context_hash = compute_canonical_context_hash(context_data)
            context_data["visible_context_hash"] = context_hash

            # Validate and canonicalize payload against visible context
            clean_payload = cls.validate_submission(session, submission_payload, context_data)

            # Record PREDICTION_VALIDATED audit event
            user_uuid = uuid.UUID(str(user_context.user_id))
            team_uuid = uuid.UUID(str(user_context.team_id)) if user_context.team_id else None
            org_uuid = uuid.UUID(str(user_context.organization_id)) if user_context.organization_id else None

            await record_audit_event(
                db=db,
                event_type="PREDICTION_VALIDATED",
                user_id=str(user_uuid),
                team_id=str(team_uuid) if team_uuid else None,
                organization_id=str(org_uuid) if org_uuid else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "schema_version": clean_payload.get("schema_version"),
                    "prediction_type": clean_payload.get("prediction_type"),
                    "confidence": clean_payload.get("confidence"),
                },
            )

            # Compute deterministic submission hash using canonical clean payload
            effective_schema_ver = str(clean_payload.get("schema_version", schema_version))
            submission_hash = compute_canonical_submission_hash(
                session_id=session.id,
                submitter_user_id=user_uuid,
                submission_payload=clean_payload,
                visible_context_hash=context_hash,
                schema_version=effective_schema_ver,
            )

            # Create immutable submission
            submission = BlindSubmission(
                session_id=session.id,
                organization_id=org_uuid,
                team_id=team_uuid,
                submitted_by_user_id=user_uuid,
                submission_payload=clean_payload,
                submission_hash=submission_hash,
                status="LOCKED",
            )
            db.add(submission)

            # Mutate session state
            session.status = BlindSessionStatus.SUBMISSION_LOCKED.value
            session.locked_at = datetime.now(timezone.utc)
            session.visible_context_hash = context_hash

            await db.commit()
            await db.refresh(submission)
            await db.refresh(session)

            # Audit events: PREDICTION_SUBMITTED and SUBMISSION_LOCKED
            await record_audit_event(
                db=db,
                event_type="PREDICTION_SUBMITTED",
                user_id=str(user_uuid),
                team_id=str(team_uuid) if team_uuid else None,
                organization_id=str(org_uuid) if org_uuid else None,
                artifact_id=f"blind_submission:{submission.id}",
                metadata={
                    "session_id": str(session.id),
                    "submission_id": str(submission.id),
                    "submission_hash": submission.submission_hash,
                    "prediction_type": clean_payload.get("prediction_type"),
                },
            )

            await record_audit_event(
                db=db,
                event_type="SUBMISSION_LOCKED",
                user_id=str(user_uuid),
                team_id=str(team_uuid) if team_uuid else None,
                organization_id=str(org_uuid) if org_uuid else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "submission_id": str(submission.id),
                    "status": session.status,
                    "submission_hash": submission.submission_hash,
                    "visible_context_hash": session.visible_context_hash,
                },
            )
            logger.info(
                "Locked submission id=%s for session id=%s hash=%s",
                submission.id, session.id, submission.submission_hash
            )
            return submission

    @classmethod
    async def prepare_reveal(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> BlindEngineeringSession:
        """
        Transitions session SUBMISSION_LOCKED -> READY_FOR_REVEAL.
        Prepares the reveal boundary without exposing the hidden outcome.
        """
        lock = cls._get_lock(str(session_id))
        async with lock:
            session = await cls.get_session_record(db, session_id, user_context)

            if session.status != BlindSessionStatus.SUBMISSION_LOCKED.value:
                raise InvalidStateTransitionError(
                    f"Cannot prepare reveal from status '{session.status}'. Must be SUBMISSION_LOCKED."
                )

            session.status = BlindSessionStatus.READY_FOR_REVEAL.value
            await db.commit()
            await db.refresh(session)

            await record_audit_event(
                db=db,
                event_type="REVEAL_REQUESTED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "status": session.status,
                },
            )

            logger.info("Session id=%s transitioned to READY_FOR_REVEAL", session.id)
            return session

    @classmethod
    async def abort_session(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
        reason: str = "User requested abort",
    ) -> BlindEngineeringSession:
        """
        Transitions session from any non-terminal state to ABORTED.
        """
        lock = cls._get_lock(str(session_id))
        async with lock:
            session = await cls.get_session_record(db, session_id, user_context)

            if session.status in (BlindSessionStatus.COMPLETED.value, BlindSessionStatus.ABORTED.value):
                raise InvalidStateTransitionError(
                    f"Cannot abort session in terminal status '{session.status}'."
                )

            session.status = BlindSessionStatus.ABORTED.value
            session.aborted_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(session)

            await record_audit_event(
                db=db,
                event_type="SESSION_ABORTED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "status": session.status,
                    "reason": reason,
                },
            )

            logger.info("Aborted session id=%s reason=%s", session.id, reason)
            return session

    @classmethod
    def check_reveal_authorization(
        cls,
        session: BlindEngineeringSession,
        user_context: UserContext,
    ) -> bool:
        """
        Determines whether user_context has explicit authorization to reveal the withheld outcome.
        - System Admin: Authorized
        - Org Admin / Owner / Admin: Authorized
        - Personal Workspace: Creator is Authorized
        - Team Workspace: Team Lead / Admin / Owner or user with 'setup:approve' or 'team:admin' permission
        Evaluators/Engineers without lead permissions are strictly UNAUTHORIZED.
        """
        if getattr(user_context, "is_admin", False):
            return True

        org_role = str(getattr(user_context, "org_role", "") or "").upper()
        if org_role in ("ORG_ADMIN", "OWNER", "ADMIN", "SUPER_ADMIN"):
            return True

        if session.team_id is None:
            # Personal workspace: session creator only
            return str(session.created_by_user_id) == str(user_context.user_id)

        # Team-scoped session: must belong to the same team
        if not user_context.team_id or str(user_context.team_id) != str(session.team_id):
            return False

        team_role = str(getattr(user_context, "team_role", "") or "").upper()
        if team_role in ("OWNER", "ADMIN", "TEAM_ADMIN", "LEAD", "LEAD_ENGINEER", "CHIEF_ENGINEER"):
            return True

        # Check explicit granular permissions if present
        user_perms = set(getattr(user_context, "permissions", []) or [])
        if "setup:approve" in user_perms or "team:admin" in user_perms:
            return True

        return False

    @classmethod
    async def execute_reveal(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> BlindComparisonResult:
        """
        Executes controlled outcome reveal and prediction-vs-outcome comparative evaluation.
        Privileged transition: READY_FOR_REVEAL -> REVEALED -> COMPLETED.
        Guarantees fail-closed rollback if outcome resolution or comparison fails.
        """
        lock = cls._get_lock(str(session_id))
        async with lock:
            session = await cls.get_session_record(db, session_id, user_context)

            # 1. State machine check: Only READY_FOR_REVEAL is permitted to transition to REVEALED
            if session.status != BlindSessionStatus.READY_FOR_REVEAL.value:
                raise InvalidStateTransitionError(
                    f"Cannot execute reveal from status '{session.status}'. Must be in READY_FOR_REVEAL."
                )

            # 2. Authorization check
            if not cls.check_reveal_authorization(session, user_context):
                raise UnauthorizedRevealError(
                    "User is not authorized to reveal the withheld outcome for this session."
                )

            # 3. Verify locked submission exists
            sub_stmt = select(BlindSubmission).where(BlindSubmission.session_id == session.id)
            sub_res = await db.execute(sub_stmt)
            submission = sub_res.scalars().first()
            if not submission or submission.status != "LOCKED":
                raise InvalidSubmissionError("Cannot reveal session without an immutable locked submission.")

            # 4. Audit: OUTCOME_REVEAL_REQUESTED
            await record_audit_event(
                db=db,
                event_type="OUTCOME_REVEAL_REQUESTED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "status": session.status,
                },
            )

            # 5. Resolve authoritative outcome entity (Fail-closed)
            try:
                resolution = await EvidenceGraphService.validate_endpoint(
                    db=db,
                    entity_type=session.hidden_outcome_type,
                    entity_id=session.hidden_outcome_id,
                    expected_team_id=session.team_id,
                    expected_org_id=session.organization_id,
                    expected_user_id=session.created_by_user_id if session.team_id is None else None,
                )
            except Exception as e:
                await db.rollback()
                raise OutcomeResolutionError(f"Failed to resolve authoritative hidden outcome: {str(e)}") from e

            # 6. Create immutable outcome identity & hash snapshot
            outcome_identity, outcome_hash = compute_canonical_outcome_identity(
                entity_type=session.hidden_outcome_type,
                entity_id=session.hidden_outcome_id,
                record=resolution.record,
                artifact_hash=resolution.artifact_hash,
                reveal_policy_version="1",
                comparison_policy_version=COMPARISON_POLICY_V1,
            )

            # 7. Evaluate comparison under COMPARISON_POLICY_V1 (Fail-closed)
            try:
                comp_eval = evaluate_prediction_comparison(
                    submission_payload=submission.submission_payload,
                    outcome_record=resolution.record,
                    outcome_entity_type=session.hidden_outcome_type,
                    outcome_entity_id=session.hidden_outcome_id,
                    session_config=session.configuration,
                    policy_version=COMPARISON_POLICY_V1,
                )
            except Exception as e:
                await db.rollback()
                raise ComparisonExecutionError(f"Comparative evaluation failed: {str(e)}") from e

            # 8. Compute deterministic comparison hash
            comp_hash = compute_canonical_comparison_hash(
                session_id=session.id,
                submission_id=submission.id,
                submission_hash=submission.submission_hash,
                outcome_identity=outcome_identity,
                comparison_policy_version=COMPARISON_POLICY_V1,
                prediction_schema_version=str(submission.submission_payload.get("schema_version", "1")),
                comparison_type=comp_eval["comparison_type"],
                verdict=comp_eval["verdict"],
                comparison_metrics=comp_eval["comparison_metrics"],
                tolerance_applied=comp_eval.get("tolerance_applied"),
            )

            # 9. Verify duplicate comparison does not exist
            dup_stmt = select(BlindComparisonResult).where(
                and_(
                    BlindComparisonResult.session_id == session.id,
                    BlindComparisonResult.comparison_policy_version == COMPARISON_POLICY_V1,
                )
            )
            dup_res = await db.execute(dup_stmt)
            if dup_res.scalars().first() is not None:
                raise DuplicateComparisonError(
                    f"Comparison result for session '{session.id}' and policy '{COMPARISON_POLICY_V1}' already exists."
                )

            # 10. Persist immutable BlindComparisonResult
            comparison_result = BlindComparisonResult(
                session_id=session.id,
                submission_id=submission.id,
                organization_id=session.organization_id,
                team_id=session.team_id,
                outcome_identity=outcome_identity,
                prediction_schema_version=str(submission.submission_payload.get("schema_version", "1")),
                comparison_policy_version=COMPARISON_POLICY_V1,
                comparison_type=comp_eval["comparison_type"],
                verdict=comp_eval["verdict"],
                comparison_metrics=comp_eval["comparison_metrics"],
                tolerance_applied=comp_eval.get("tolerance_applied"),
                interpretation=comp_eval["interpretation"],
                comparison_hash=comp_hash,
            )
            db.add(comparison_result)

            # 11. State transitions: READY_FOR_REVEAL -> REVEALED -> COMPLETED
            now = datetime.now(timezone.utc)
            session.status = BlindSessionStatus.REVEALED.value
            session.revealed_at = now
            session.status = BlindSessionStatus.COMPLETED.value
            session.completed_at = now

            try:
                await db.commit()
            except Exception as e:
                await db.rollback()
                raise ComparisonExecutionError(f"Failed to persist comparison result: {str(e)}") from e

            await db.refresh(comparison_result)
            await db.refresh(session)

            # 12. Audit Events: OUTCOME_REVEALED, COMPARISON_CREATED, SESSION_COMPLETED
            await record_audit_event(
                db=db,
                event_type="OUTCOME_REVEALED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "actor_id": str(user_context.user_id),
                    "outcome_entity_type": session.hidden_outcome_type,
                    "outcome_entity_id": session.hidden_outcome_id,
                    "outcome_hash": outcome_hash,
                    "reveal_policy_version": "1",
                },
            )

            await record_audit_event(
                db=db,
                event_type="COMPARISON_CREATED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_comparison:{comparison_result.id}",
                metadata={
                    "session_id": str(session.id),
                    "comparison_id": str(comparison_result.id),
                    "comparison_hash": comparison_result.comparison_hash,
                    "comparison_policy_version": comparison_result.comparison_policy_version,
                    "comparison_type": comparison_result.comparison_type,
                    "verdict": comparison_result.verdict,
                },
            )

            await record_audit_event(
                db=db,
                event_type="SESSION_COMPLETED",
                user_id=str(user_context.user_id),
                team_id=str(user_context.team_id) if user_context.team_id else None,
                organization_id=str(user_context.organization_id) if user_context.organization_id else None,
                artifact_id=f"blind_session:{session.id}",
                metadata={
                    "session_id": str(session.id),
                    "status": session.status,
                    "comparison_hash": comparison_result.comparison_hash,
                },
            )

            logger.info(
                "Revealed and completed session id=%s comparison_id=%s verdict=%s hash=%s",
                session.id, comparison_result.id, comparison_result.verdict, comparison_result.comparison_hash
            )
            return comparison_result

    @classmethod
    async def get_comparison_result(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
        policy_version: str = COMPARISON_POLICY_V1,
    ) -> Dict[str, Any]:
        """
        Retrieves the immutable prediction-vs-outcome comparison result.
        Withheld with InformationFirewallViolationError if session has not been revealed.
        """
        session = await cls.get_session_record(db, session_id, user_context)

        # Pre-reveal firewall check
        if session.status not in (BlindSessionStatus.REVEALED.value, BlindSessionStatus.COMPLETED.value):
            raise InformationFirewallViolationError(
                "Comparison result is withheld until session outcome is legitimately revealed."
            )

        comp_stmt = select(BlindComparisonResult).where(
            and_(
                BlindComparisonResult.session_id == session.id,
                BlindComparisonResult.comparison_policy_version == policy_version,
            )
        )
        comp_res = await db.execute(comp_stmt)
        comp = comp_res.scalars().first()
        if not comp:
            raise BlindEngineeringError(
                f"No comparison result found for session '{session.id}' with policy '{policy_version}'."
            )

        sub_stmt = select(BlindSubmission).where(BlindSubmission.session_id == session.id)
        sub_res = await db.execute(sub_stmt)
        submission = sub_res.scalars().first()

        return {
            "id": str(comp.id),
            "session_id": str(comp.session_id),
            "submission_id": str(comp.submission_id),
            "outcome_identity": comp.outcome_identity,
            "prediction_schema_version": comp.prediction_schema_version,
            "comparison_policy_version": comp.comparison_policy_version,
            "comparison_type": comp.comparison_type,
            "verdict": comp.verdict,
            "comparison_metrics": comp.comparison_metrics,
            "tolerance_applied": comp.tolerance_applied,
            "interpretation": comp.interpretation,
            "comparison_hash": comp.comparison_hash,
            "computed_at": comp.computed_at.isoformat(),
            "prediction_payload": submission.submission_payload if submission else None,
        }

    @classmethod
    async def get_revealed_outcome(
        cls,
        db: AsyncSession,
        session_id: Union[str, uuid.UUID],
        user_context: UserContext,
    ) -> Dict[str, Any]:
        """
        Retrieves the authoritative revealed outcome identity snapshot.
        Withheld with InformationFirewallViolationError if session has not been revealed.
        """
        session = await cls.get_session_record(db, session_id, user_context)

        # Pre-reveal firewall check
        if session.status not in (BlindSessionStatus.REVEALED.value, BlindSessionStatus.COMPLETED.value):
            raise InformationFirewallViolationError(
                "Revealed outcome is withheld until session is legitimately revealed."
            )

        resolution = await EvidenceGraphService.validate_endpoint(
            db=db,
            entity_type=session.hidden_outcome_type,
            entity_id=session.hidden_outcome_id,
            expected_team_id=session.team_id,
            expected_org_id=session.organization_id,
            expected_user_id=session.created_by_user_id if session.team_id is None else None,
        )

        outcome_identity, outcome_hash = compute_canonical_outcome_identity(
            entity_type=session.hidden_outcome_type,
            entity_id=session.hidden_outcome_id,
            record=resolution.record,
            artifact_hash=resolution.artifact_hash,
        )

        return {
            "session_id": str(session.id),
            "status": session.status,
            "outcome_entity_type": session.hidden_outcome_type,
            "outcome_entity_id": session.hidden_outcome_id,
            "outcome_identity": outcome_identity,
            "outcome_hash": outcome_hash,
            "revealed_at": session.revealed_at.isoformat() if session.revealed_at else None,
        }
