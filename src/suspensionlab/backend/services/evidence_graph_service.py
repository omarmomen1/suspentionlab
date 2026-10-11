"""
backend/services/evidence_graph_service.py
==========================================
SuspensionLab PRO — Phase 4 Engineering Evidence Graph Canonical Service.

Provides production-grade relationship management over existing engineering entities:
- Service-level polymorphic referential integrity
- Endpoint resolution and historical artifact hash capture
- Strict semantic relationship vocabulary and entity-type gating
- Tenant-isolated query and mutation boundaries
- Append-only immutability enforcement
- Deterministic SHA-256 edge hashing and metadata canonicalization
- Strict directed cycle prevention (DAG guarantee)
"""
from __future__ import annotations

import asyncio
import collections
import hashlib
import json
import logging
import math
import re
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy import and_, bindparam, or_, select, text, Uuid
from sqlalchemy.ext.asyncio import AsyncSession

# Models
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
    EdgeImmutabilityError,
)
from suspensionlab.backend.database.models.decision_loop import (
    ApprovalRecord,
    BlindValidationRecord,
    InvestigationRecord,
    OptimizationRecord,
    SetupComparisonRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.database.models.experiment import ExperimentRecord
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.setup_engineering import (
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    EngineeringProblemRecord,
    PostTrackReconciliationRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
)
from suspensionlab.backend.database.models.setup_proposal import SetupProposal
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.timeline_event import TimelineEventRecord
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin

logger = logging.getLogger(__name__)


# ── EXCEPTIONS ────────────────────────────────────────────────────────────────

class EvidenceGraphError(Exception):
    """Base exception for all Evidence Graph operations."""
    pass


class UnsupportedEntityTypeError(EvidenceGraphError):
    """Raised when an unrecognized entity type is supplied."""
    pass


class UnsupportedRelationshipError(EvidenceGraphError):
    """Raised when an unconstrained or unsupported relationship is requested."""
    pass


class MalformedIdentifierError(EvidenceGraphError):
    """Raised when an entity identifier string is empty, invalid, or malformed."""
    pass


class EntityNotFoundError(EvidenceGraphError):
    """Raised when an endpoint entity does not exist in the database."""
    pass


class TenantIsolationError(EvidenceGraphError):
    """Raised when an operation attempts cross-tenant edge creation or traversal."""
    pass


class CycleDetectedError(EvidenceGraphError):
    """Raised when adding an edge would violate the DAG invariant by creating a cycle."""
    pass


class DuplicateEdgeError(EvidenceGraphError):
    """Raised when a duplicate edge is detected in non-idempotent mode."""
    pass


class MetadataValidationError(EvidenceGraphError):
    """Raised when edge metadata fails serialization, size, or security rules."""
    pass


class EdgeIntegrityError(EvidenceGraphError):
    """Raised when edge hash verification fails."""
    pass


class TraversalLimitError(EvidenceGraphError):
    """Raised when traversal resource bounds or parameters are invalid."""
    pass


# ── TRAVERSAL LIMIT CONSTANTS ─────────────────────────────────────────────────

DEFAULT_MAX_DEPTH = 5
MAX_ALLOWED_DEPTH = 20
DEFAULT_MAX_NODES = 100
MAX_ALLOWED_NODES = 1000
DEFAULT_MAX_EDGES = 200
MAX_ALLOWED_EDGES = 2000


# ── DATA CONTAINERS ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EndpointResolution:
    """Resolved engineering entity endpoint information."""
    entity_type: str
    canonical_id: str
    artifact_hash: str
    team_id: Optional[uuid.UUID]
    organization_id: Optional[uuid.UUID]
    record: Any
    user_id: Optional[uuid.UUID] = None


# ── METADATA & HASHING UTILITIES ──────────────────────────────────────────────

MAX_METADATA_BYTES = 32768  # 32 KB maximum payload per edge metadata

FORBIDDEN_KEY_PATTERNS = {
    "api_key", "token", "secret", "password", "auth", "authorization",
    "private_key", "credential", "jwt", "access_token", "refresh_token"
}

SENSITIVE_VALUE_REGEX = re.compile(
    r"(-----BEGIN [A-Z ]+ PRIVATE KEY-----|bearer\s+[a-zA-Z0-9_\-\.]+|sl_live_[a-zA-Z0-9]+|eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,})",
    re.IGNORECASE
)

EXECUTABLE_PATTERNS = re.compile(
    r"(<script|javascript:|eval\(|__import__|os\.system|subprocess\.)",
    re.IGNORECASE
)


def validate_and_canonicalize_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates that metadata is JSON-serializable, bounded in size, and free of secrets or scripts.
    Returns a canonicalized dictionary.
    """
    if metadata is None:
        return {}

    if not isinstance(metadata, dict):
        raise MetadataValidationError(f"Edge metadata must be a dictionary, got {type(metadata).__name__}.")

    def _inspect_item(k: Any, v: Any) -> None:
        if not isinstance(k, str):
            raise MetadataValidationError(f"Metadata keys must be strings, got {type(k).__name__}.")
        k_lower = k.lower()
        for forbidden in FORBIDDEN_KEY_PATTERNS:
            if forbidden in k_lower:
                raise MetadataValidationError(f"Metadata contains forbidden security key: '{k}'.")

        if isinstance(v, str):
            if SENSITIVE_VALUE_REGEX.search(v):
                raise MetadataValidationError(f"Metadata field '{k}' contains prohibited secret or credential tokens.")
            if EXECUTABLE_PATTERNS.search(v):
                raise MetadataValidationError(f"Metadata field '{k}' contains prohibited executable or script patterns.")
        elif isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                raise MetadataValidationError(f"Metadata field '{k}' has non-finite float value.")
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                _inspect_item(sub_k, sub_v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, (dict, list)):
                    _inspect_item(k, item)
                elif isinstance(item, str) and SENSITIVE_VALUE_REGEX.search(item):
                    raise MetadataValidationError(f"Metadata list '{k}' contains prohibited credential token.")

    for k, v in metadata.items():
        _inspect_item(k, v)

    try:
        serialized = json.dumps(metadata, sort_keys=True, default=str)
    except (TypeError, ValueError) as err:
        raise MetadataValidationError(f"Metadata is not JSON-serializable: {err}")

    if len(serialized.encode("utf-8")) > MAX_METADATA_BYTES:
        raise MetadataValidationError(
            f"Metadata size ({len(serialized.encode('utf-8'))} bytes) exceeds maximum allowable limit of {MAX_METADATA_BYTES} bytes."
        )

    # Return clean parsed dictionary
    return json.loads(serialized)


def compute_edge_hash(
    organization_id: Optional[Union[str, uuid.UUID]],
    team_id: Optional[Union[str, uuid.UUID]],
    source_type: str,
    source_id: str,
    source_artifact_hash: Optional[str],
    relationship: str,
    target_type: str,
    target_id: str,
    target_artifact_hash: Optional[str],
    metadata: Dict[str, Any],
    created_by_user_id: Union[str, uuid.UUID],
) -> str:
    """
    Computes deterministic SHA-256 edge hash over canonical payload:
    Field ordering (alphabetical keys in sorted JSON dump):
      1. created_by_user_id (str)
      2. metadata (alphabetically sorted, compact JSON separators)
      3. organization_id (str or null)
      4. relationship (str)
      5. source_artifact_hash (str, empty if null)
      6. source_id (str)
      7. source_type (str)
      8. target_artifact_hash (str, empty if null)
      9. target_id (str)
      10. target_type (str)
      11. team_id (str or null)
    Encoding: UTF-8
    """
    payload = {
        "created_by_user_id": str(created_by_user_id),
        "metadata": metadata,
        "organization_id": str(organization_id) if organization_id else None,
        "relationship": str(relationship),
        "source_artifact_hash": str(source_artifact_hash or ""),
        "source_id": str(source_id),
        "source_type": str(source_type),
        "target_artifact_hash": str(target_artifact_hash or ""),
        "target_id": str(target_id),
        "target_type": str(target_type),
        "team_id": str(team_id) if team_id else None,
    }
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


# ── ENTITY MODEL REGISTRY ─────────────────────────────────────────────────────

ENTITY_MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
    SupportedEntityType.TELEMETRY_SESSION.value: {
        "model": TelemetrySessionRecord,
        "uuid_col": "id",
        "key_cols": ["session_code", "session_number"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.INVESTIGATION.value: {
        "model": InvestigationRecord,
        "uuid_col": "id",
        "key_cols": ["investigation_code", "investigation_number"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.ENGINEERING_QUESTION.value: {
        "model": EngineeringQuestion,
        "uuid_col": "id",
        "key_cols": ["question_id"],
        "hash_col": None,
        "tenant_team": "team_id",
        "tenant_org": "organization_id",
    },
    SupportedEntityType.ENGINEERING_PROBLEM.value: {
        "model": EngineeringProblemRecord,
        "uuid_col": "id",
        "key_cols": ["problem_id"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.CAUSAL_HYPOTHESIS.value: {
        "model": CausalHypothesisRecord,
        "uuid_col": "id",
        "key_cols": ["hypothesis_id"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.EXPERIMENT.value: {
        "model": ExperimentRecord,
        "uuid_col": "id",
        "key_cols": [],
        "hash_col": "result_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.CONTROLLED_EXPERIMENT.value: {
        "model": ControlledExperimentDesignRecord,
        "uuid_col": "id",
        "key_cols": ["experiment_id"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.SIMULATION_RUN.value: {
        "model": SimulationRun,
        "uuid_col": "id",
        "key_cols": ["label", "seq"],
        "hash_col": "result_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.SETUP_CANDIDATE.value: {
        "model": SetupCandidateRecord,
        "uuid_col": "id",
        "key_cols": ["setup_id"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.VEHICLE_PROFILE.value: {
        "model": VehicleProfile,
        "uuid_col": "id",
        "key_cols": ["name"],
        "hash_col": None,
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.VEHICLE_TWIN.value: {
        "model": VehicleTwin,
        "uuid_col": "id",
        "key_cols": ["car_ref"],
        "hash_col": None,
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.SETUP_PROPOSAL.value: {
        "model": SetupProposal,
        "uuid_col": "id",
        "key_cols": [],
        "hash_col": "proposal_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.SETUP_COMPARISON.value: {
        "model": SetupComparisonRecord,
        "uuid_col": "id",
        "key_cols": ["comparison_code", "comparison_number"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.OPTIMIZATION.value: {
        "model": OptimizationRecord,
        "uuid_col": "id",
        "key_cols": ["optimization_code", "optimization_number"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.BLIND_VALIDATION.value: {
        "model": BlindValidationRecord,
        "uuid_col": "id",
        "key_cols": ["validation_code", "validation_number"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.ENGINEERING_DECISION.value: {
        "model": EngineeringDecision,
        "uuid_col": "id",
        "key_cols": ["decision_id"],
        "hash_col": "artifact_hashes",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.APPROVAL.value: {
        "model": ApprovalRecord,
        "uuid_col": "id",
        "key_cols": ["approval_code", "approval_number"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.TRACK_TEST_PREDICTION.value: {
        "model": TrackTestPredictionRecord,
        "uuid_col": "id",
        "key_cols": ["prediction_id"],
        "hash_col": "prediction_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.POST_TRACK_RECONCILIATION.value: {
        "model": PostTrackReconciliationRecord,
        "uuid_col": "id",
        "key_cols": ["reconciliation_id"],
        "hash_col": "artifact_hash",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
    SupportedEntityType.TIMELINE_EVENT.value: {
        "model": TimelineEventRecord,
        "uuid_col": "id",
        "key_cols": [],
        "hash_col": "artifact_hashes",
        "tenant_team": "team_id",
        "tenant_org": None,
    },
}


# ── CORE EVIDENCE GRAPH SERVICE ───────────────────────────────────────────────

class EvidenceGraphService:
    """
    Production-grade Evidence Graph Service implementing the canonical relationship layer.
    """
    DEFAULT_MAX_DEPTH = DEFAULT_MAX_DEPTH
    MAX_ALLOWED_DEPTH = MAX_ALLOWED_DEPTH
    DEFAULT_MAX_NODES = DEFAULT_MAX_NODES
    MAX_ALLOWED_NODES = MAX_ALLOWED_NODES
    DEFAULT_MAX_EDGES = DEFAULT_MAX_EDGES
    MAX_ALLOWED_EDGES = MAX_ALLOWED_EDGES

    _tenant_locks: Dict[str, asyncio.Lock] = collections.defaultdict(asyncio.Lock)

    @classmethod
    def _get_tenant_lock(cls, lock_key: str) -> asyncio.Lock:
        return cls._tenant_locks[lock_key]

    @classmethod
    async def validate_endpoint(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        expected_team_id: Optional[Union[str, uuid.UUID]] = None,
        expected_org_id: Optional[Union[str, uuid.UUID]] = None,
        expected_user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> EndpointResolution:
        """
        Resolves a polymorphic (entity_type, entity_id) locator against the database.
        Verifies existence, extracts historical artifact hash, and enforces tenant boundaries.
        """
        # 1. Type validation
        supported_types = {e.value for e in SupportedEntityType}
        if entity_type not in supported_types:
            raise UnsupportedEntityTypeError(
                f"Unsupported entity type: '{entity_type}'. Must be one of {sorted(supported_types)}."
            )

        # 2. Identifier validation
        if not entity_id or not isinstance(entity_id, str) or not entity_id.strip():
            raise MalformedIdentifierError("Entity identifier must be a non-empty string.")
        clean_id = entity_id.strip()
        if len(clean_id) > 128:
            raise MalformedIdentifierError(f"Entity identifier '{clean_id[:20]}...' exceeds maximum length of 128 characters.")

        config = ENTITY_MODEL_CONFIGS[entity_type]
        model = config["model"]
        uuid_col_name = config["uuid_col"]
        key_cols = config["key_cols"]

        # 3. Construct lookup criteria
        clauses = []
        is_valid_uuid = False
        parsed_uuid = None
        try:
            parsed_uuid = uuid.UUID(clean_id)
            is_valid_uuid = True
            clauses.append(getattr(model, uuid_col_name) == parsed_uuid)
        except (ValueError, AttributeError):
            pass

        for kc in key_cols:
            col_attr = getattr(model, kc, None)
            if col_attr is not None:
                clauses.append(col_attr == clean_id)
                if clean_id.isdigit():
                    try:
                        clauses.append(col_attr == int(clean_id))
                    except Exception:
                        pass

        if not clauses:
            raise MalformedIdentifierError(f"Entity '{entity_type}' cannot be resolved with identifier '{clean_id}'.")

        stmt = select(model).where(or_(*clauses))
        result = await db.execute(stmt)
        record = result.scalars().first()

        if record is None:
            raise EntityNotFoundError(f"Endpoint entity '{entity_type}:{clean_id}' does not exist.")

        # 4. Resolve tenant scope & user ownership
        team_id = getattr(record, config["tenant_team"], None) if config["tenant_team"] else None
        org_col = config["tenant_org"]
        org_id = getattr(record, org_col, None) if org_col else None
        entity_user_id = getattr(record, "user_id", None) or getattr(record, "created_by_user_id", None) or getattr(record, "owner_id", None)
        user_uuid = None
        if entity_user_id:
            try:
                user_uuid = uuid.UUID(str(entity_user_id))
            except Exception:
                pass

        # 5. Enforce tenant boundaries if expected scope is passed
        if expected_team_id is not None:
            if team_id is None or str(team_id) != str(expected_team_id):
                raise TenantIsolationError(
                    f"Cross-tenant isolation violation: {entity_type}:{clean_id} is not accessible in the requested tenant scope."
                )

        if expected_org_id is not None and org_col is not None:
            if org_id is None or str(org_id) != str(expected_org_id):
                raise TenantIsolationError(
                    f"Cross-tenant isolation violation: {entity_type}:{clean_id} is not accessible in the requested tenant scope."
                )

        if expected_user_id is not None and expected_team_id is None:
            if user_uuid is None or str(user_uuid) != str(expected_user_id):
                raise TenantIsolationError(
                    f"Cross-user isolation violation: {entity_type}:{clean_id} is not accessible in the requested personal workspace scope."
                )

        # 6. Extract or compute artifact hash
        artifact_hash = ""
        hash_col = config["hash_col"]
        if hash_col:
            raw_hash = getattr(record, hash_col, None)
            if isinstance(raw_hash, dict):
                artifact_hash = raw_hash.get("decision_hash") or raw_hash.get("result_hash") or ""
                if not artifact_hash:
                    artifact_hash = hashlib.sha256(json.dumps(raw_hash, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            elif isinstance(raw_hash, str) and raw_hash:
                artifact_hash = raw_hash

        if not artifact_hash:
            # Fallback deterministic canonical hash of entity's primary identity
            fallback_payload = {
                "entity_type": entity_type,
                "id": str(getattr(record, uuid_col_name)),
                "created_at": getattr(record, "created_at", None),
            }
            artifact_hash = hashlib.sha256(json.dumps(fallback_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        canonical_id = clean_id

        return EndpointResolution(
            entity_type=entity_type,
            canonical_id=canonical_id,
            artifact_hash=artifact_hash,
            team_id=team_id,
            organization_id=org_id,
            record=record,
            user_id=user_uuid,
        )

    @classmethod
    async def check_cycle(
        cls,
        db: AsyncSession,
        team_id: Optional[Union[str, uuid.UUID]],
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> bool:
        """
        Detects if inserting directed edge (source -> target) would create a cycle.
        Returns False if no cycle is created.
        Raises CycleDetectedError if target can already reach source.
        """
        # Immediate self-loop check
        if source_type == target_type and source_id == target_id:
            raise CycleDetectedError(f"Self-loop cycle prohibited: {source_type}:{source_id} -> {target_type}:{target_id}.")

        # BFS search: Does target have a directed path to source?
        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        user_uuid = uuid.UUID(str(user_id)) if user_id else None
        visited: Set[Tuple[str, str]] = set()
        queue: collections.deque[Tuple[str, str]] = collections.deque([(target_type, target_id)])

        while queue:
            curr_type, curr_id = queue.popleft()
            if (curr_type, curr_id) == (source_type, source_id):
                raise CycleDetectedError(
                    f"Cycle detected: adding edge from {source_type}:{source_id} to "
                    f"{target_type}:{target_id} closes a cycle back to {source_type}:{source_id}."
                )

            if (curr_type, curr_id) in visited:
                continue
            visited.add((curr_type, curr_id))

            # Query outgoing edges from (curr_type, curr_id)
            query = select(
                EvidenceGraphEdgeRecord.target_type,
                EvidenceGraphEdgeRecord.target_id
            ).where(
                EvidenceGraphEdgeRecord.source_type == curr_type,
                EvidenceGraphEdgeRecord.source_id == curr_id,
            )
            if team_uuid is not None:
                query = query.where(EvidenceGraphEdgeRecord.team_id == team_uuid)
            else:
                query = query.where(EvidenceGraphEdgeRecord.team_id.is_(None))
                if user_uuid is not None:
                    query = query.where(EvidenceGraphEdgeRecord.created_by_user_id == user_uuid)

            res = await db.execute(query)
            for n_type, n_id in res.all():
                if (n_type, n_id) not in visited:
                    queue.append((n_type, n_id))

        return False

    @classmethod
    async def edge_exists(
        cls,
        db: AsyncSession,
        team_id: Optional[Union[str, uuid.UUID]],
        source_type: str,
        source_id: str,
        relationship: str,
        target_type: str,
        target_id: str,
    ) -> bool:
        """Checks if a matching edge already exists."""
        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        stmt = select(EvidenceGraphEdgeRecord.id).where(
            EvidenceGraphEdgeRecord.source_type == source_type,
            EvidenceGraphEdgeRecord.source_id == source_id,
            EvidenceGraphEdgeRecord.relationship == relationship,
            EvidenceGraphEdgeRecord.target_type == target_type,
            EvidenceGraphEdgeRecord.target_id == target_id,
        )
        if team_uuid:
            stmt = stmt.where(EvidenceGraphEdgeRecord.team_id == team_uuid)
        else:
            stmt = stmt.where(EvidenceGraphEdgeRecord.team_id.is_(None))

        res = await db.execute(stmt)
        return res.scalar_one_or_none() is not None

    @classmethod
    async def record_edge(
        cls,
        db: AsyncSession,
        user_id: Union[str, uuid.UUID],
        team_id: Optional[Union[str, uuid.UUID]],
        source_type: str,
        source_id: str,
        relationship: str,
        target_type: str,
        target_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        idempotent: bool = True,
    ) -> EvidenceGraphEdgeRecord:
        """
        Creates an immutable, cryptographically hashed directed graph edge.
        Resolves both endpoints, verifies tenant boundaries, checks cycle safety,
        and computes deterministic SHA-256 edge_hash.
        """
        # 1. Validate relationship vocabulary
        supported_rels = {r.value for r in EvidenceGraphRelationship}
        if relationship not in supported_rels:
            raise UnsupportedRelationshipError(
                f"Unsupported relationship '{relationship}'. Must be one of {sorted(supported_rels)}."
            )

        # 2. Validate user identity
        user_uuid = uuid.UUID(str(user_id))
        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        org_uuid = uuid.UUID(str(organization_id)) if organization_id else None

        # 3. Validate endpoints & capture historical hashes
        source_res = await cls.validate_endpoint(
            db=db,
            entity_type=source_type,
            entity_id=source_id,
            expected_team_id=team_uuid,
            expected_org_id=org_uuid,
            expected_user_id=user_uuid if team_uuid is None else None,
        )
        target_res = await cls.validate_endpoint(
            db=db,
            entity_type=target_type,
            entity_id=target_id,
            expected_team_id=team_uuid,
            expected_org_id=org_uuid,
            expected_user_id=user_uuid if team_uuid is None else None,
        )

        # 4. Cross-tenant endpoint consistency check
        if source_res.team_id is not None and target_res.team_id is not None and source_res.team_id != target_res.team_id:
            raise TenantIsolationError("Cross-tenant edge prohibited: source and target belong to different teams.")
        if source_res.organization_id is not None and target_res.organization_id is not None and source_res.organization_id != target_res.organization_id:
            raise TenantIsolationError("Cross-tenant edge prohibited: source and target belong to different organizations.")
        if team_uuid is None and source_res.user_id != target_res.user_id:
            raise TenantIsolationError("Cross-user edge prohibited: source and target belong to different personal workspaces.")

        # Resolve edge-level tenant scope
        effective_team_id = team_uuid or source_res.team_id or target_res.team_id
        effective_org_id = org_uuid or source_res.organization_id or target_res.organization_id

        # 5. Validate & canonicalize metadata
        clean_metadata = validate_and_canonicalize_metadata(metadata)

        # 6. Concurrency synchronization & Cycle prevention
        lock_key = str(effective_team_id) if effective_team_id else f"user_{user_uuid}"
        async with cls._get_tenant_lock(lock_key):
            if hasattr(db, "bind") and db.bind and getattr(db.bind.dialect, "name", None) == "postgresql":
                try:
                    tenant_int = zlib.crc32(lock_key.encode("utf-8"))
                    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": tenant_int})
                except Exception:
                    pass

            await cls.check_cycle(
                db=db,
                team_id=effective_team_id,
                source_type=source_type,
                source_id=source_res.canonical_id,
                target_type=target_type,
                target_id=target_res.canonical_id,
                user_id=user_uuid if effective_team_id is None else None,
            )

            # 7. Duplicate protection check
            stmt = select(EvidenceGraphEdgeRecord).where(
                EvidenceGraphEdgeRecord.source_type == source_type,
                EvidenceGraphEdgeRecord.source_id == source_res.canonical_id,
                EvidenceGraphEdgeRecord.relationship == relationship,
                EvidenceGraphEdgeRecord.target_type == target_type,
                EvidenceGraphEdgeRecord.target_id == target_res.canonical_id,
            )
            if effective_team_id is not None:
                stmt = stmt.where(EvidenceGraphEdgeRecord.team_id == effective_team_id)
            else:
                stmt = stmt.where(
                    EvidenceGraphEdgeRecord.team_id.is_(None),
                    EvidenceGraphEdgeRecord.created_by_user_id == user_uuid,
                )

            res = await db.execute(stmt)
            existing = res.scalars().first()
            if existing is not None:
                if idempotent:
                    return existing
                raise DuplicateEdgeError(
                    f"Duplicate edge prohibited: ({source_type}:{source_res.canonical_id}) "
                    f"--[{relationship}]--> ({target_type}:{target_res.canonical_id})."
                )

            # 8. Deterministic SHA-256 edge hash
            edge_hash = compute_edge_hash(
                organization_id=effective_org_id,
                team_id=effective_team_id,
                source_type=source_type,
                source_id=source_res.canonical_id,
                source_artifact_hash=source_res.artifact_hash,
                relationship=relationship,
                target_type=target_type,
                target_id=target_res.canonical_id,
                target_artifact_hash=target_res.artifact_hash,
                metadata=clean_metadata,
                created_by_user_id=user_uuid,
            )

            # 9. Persist immutable record
            edge = EvidenceGraphEdgeRecord(
                id=uuid.uuid4(),
                organization_id=effective_org_id,
                team_id=effective_team_id,
                created_by_user_id=user_uuid,
                source_type=source_type,
                source_id=source_res.canonical_id,
                relationship=relationship,
                target_type=target_type,
                target_id=target_res.canonical_id,
                source_artifact_hash=source_res.artifact_hash,
                target_artifact_hash=target_res.artifact_hash,
                metadata_=clean_metadata,
                edge_hash=edge_hash,
            )
            db.add(edge)
            await db.commit()
            await db.refresh(edge)
            return edge

    @classmethod
    async def get_edge(
        cls,
        db: AsyncSession,
        edge_id: Union[str, uuid.UUID],
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        verify_integrity: bool = False,
    ) -> Optional[EvidenceGraphEdgeRecord]:
        """
        Retrieves a single edge by primary ID, enforcing tenant isolation boundary.
        """
        try:
            edge_uuid = uuid.UUID(str(edge_id))
        except (ValueError, AttributeError):
            return None

        stmt = select(EvidenceGraphEdgeRecord).where(EvidenceGraphEdgeRecord.id == edge_uuid)
        if team_id is not None:
            team_uuid = uuid.UUID(str(team_id))
            stmt = stmt.where(EvidenceGraphEdgeRecord.team_id == team_uuid)
        elif user_id is not None:
            user_uuid = uuid.UUID(str(user_id))
            stmt = stmt.where(
                EvidenceGraphEdgeRecord.team_id.is_(None),
                EvidenceGraphEdgeRecord.created_by_user_id == user_uuid,
            )

        if organization_id is not None:
            org_uuid = uuid.UUID(str(organization_id))
            stmt = stmt.where(
                or_(
                    EvidenceGraphEdgeRecord.organization_id == org_uuid,
                    EvidenceGraphEdgeRecord.organization_id.is_(None),
                )
            )

        res = await db.execute(stmt)
        edge = res.scalars().first()
        if edge is not None and verify_integrity:
            recomputed = compute_edge_hash(
                organization_id=edge.organization_id,
                team_id=edge.team_id,
                source_type=edge.source_type,
                source_id=edge.source_id,
                source_artifact_hash=edge.source_artifact_hash,
                relationship=edge.relationship,
                target_type=edge.target_type,
                target_id=edge.target_id,
                target_artifact_hash=edge.target_artifact_hash,
                metadata=edge.metadata_ or {},
                created_by_user_id=edge.created_by_user_id,
            )
            if edge.edge_hash != recomputed:
                raise EdgeIntegrityError(f"Edge {edge.id} hash mismatch detected.")

        return edge

    @classmethod
    async def verify_edge_integrity(
        cls,
        db: AsyncSession,
        edge_id: Union[str, uuid.UUID],
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """
        Verifies that an edge's cryptographic hash matches its exact persisted state.
        Detects any out-of-band tampering or mutation.
        """
        edge = await cls.get_edge(db=db, edge_id=edge_id, team_id=team_id, user_id=user_id, organization_id=organization_id)
        if edge is None:
            raise EntityNotFoundError(f"Edge {edge_id} not found.")

        recomputed = compute_edge_hash(
            organization_id=edge.organization_id,
            team_id=edge.team_id,
            source_type=edge.source_type,
            source_id=edge.source_id,
            source_artifact_hash=edge.source_artifact_hash,
            relationship=edge.relationship,
            target_type=edge.target_type,
            target_id=edge.target_id,
            target_artifact_hash=edge.target_artifact_hash,
            metadata=edge.metadata_ or {},
            created_by_user_id=edge.created_by_user_id,
        )

        is_valid = (edge.edge_hash == recomputed)
        return {
            "edge_id": str(edge.id),
            "valid": is_valid,
            "stored_hash": edge.edge_hash,
            "recomputed_hash": recomputed,
            "source": f"{edge.source_type}:{edge.source_id}",
            "relationship": edge.relationship,
            "target": f"{edge.target_type}:{edge.target_id}",
            "created_at": edge.created_at.isoformat(),
        }

    @classmethod
    async def list_edges(
        cls,
        db: AsyncSession,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        created_by_user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[EvidenceGraphEdgeRecord]:
        """
        Lists tenant-scoped edges matching search filters with deterministic ordering.
        """
        if limit < 1:
            raise ValueError("Limit must be positive.")
        limit = min(limit, 200)
        if offset < 0:
            raise ValueError("Offset must be non-negative.")

        if relationship:
            supported_rels = {r.value for r in EvidenceGraphRelationship}
            if relationship not in supported_rels:
                raise UnsupportedRelationshipError(f"Unsupported relationship '{relationship}'.")

        if source_type:
            supported_types = {e.value for e in SupportedEntityType}
            if source_type not in supported_types:
                raise UnsupportedEntityTypeError(f"Unsupported entity type '{source_type}'.")

        if target_type:
            supported_types = {e.value for e in SupportedEntityType}
            if target_type not in supported_types:
                raise UnsupportedEntityTypeError(f"Unsupported entity type '{target_type}'.")

        stmt = select(EvidenceGraphEdgeRecord)
        if team_id is not None:
            team_uuid = uuid.UUID(str(team_id))
            stmt = stmt.where(EvidenceGraphEdgeRecord.team_id == team_uuid)
        elif user_id is not None:
            user_uuid = uuid.UUID(str(user_id))
            stmt = stmt.where(
                EvidenceGraphEdgeRecord.team_id.is_(None),
                EvidenceGraphEdgeRecord.created_by_user_id == user_uuid,
            )

        if organization_id is not None:
            org_uuid = uuid.UUID(str(organization_id))
            stmt = stmt.where(
                or_(
                    EvidenceGraphEdgeRecord.organization_id == org_uuid,
                    EvidenceGraphEdgeRecord.organization_id.is_(None),
                )
            )

        if created_by_user_id is not None:
            c_uuid = uuid.UUID(str(created_by_user_id))
            stmt = stmt.where(EvidenceGraphEdgeRecord.created_by_user_id == c_uuid)

        if source_type:
            stmt = stmt.where(EvidenceGraphEdgeRecord.source_type == source_type)
        if source_id:
            stmt = stmt.where(EvidenceGraphEdgeRecord.source_id == source_id)
        if target_type:
            stmt = stmt.where(EvidenceGraphEdgeRecord.target_type == target_type)
        if target_id:
            stmt = stmt.where(EvidenceGraphEdgeRecord.target_id == target_id)
        if relationship:
            stmt = stmt.where(EvidenceGraphEdgeRecord.relationship == relationship)

        # Deterministic ordering
        stmt = stmt.order_by(
            EvidenceGraphEdgeRecord.created_at.desc(),
            EvidenceGraphEdgeRecord.id.asc(),
        ).limit(limit).offset(offset)

        res = await db.execute(stmt)
        return list(res.scalars().all())

    @classmethod
    async def _execute_recursive_traversal(
        cls,
        db: AsyncSession,
        root_type: str,
        root_id: str,
        direction: str = "FORWARD",
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        relationship: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes bounded, deterministic, cycle-safe recursive graph traversal using SQL CTE.
        """
        dir_upper = direction.upper()
        if dir_upper not in ("FORWARD", "BACKWARD"):
            raise ValueError(f"Invalid direction '{direction}'. Must be 'FORWARD' or 'BACKWARD'.")

        if max_depth < 1:
            raise ValueError("max_depth must be at least 1.")
        effective_max_depth = min(max_depth, cls.MAX_ALLOWED_DEPTH)

        if max_nodes < 1:
            raise ValueError("max_nodes must be at least 1.")
        effective_max_nodes = min(max_nodes, cls.MAX_ALLOWED_NODES)

        if max_edges < 1:
            raise ValueError("max_edges must be at least 1.")
        effective_max_edges = min(max_edges, cls.MAX_ALLOWED_EDGES)

        supported_types = {e.value for e in SupportedEntityType}
        if root_type not in supported_types:
            raise UnsupportedEntityTypeError(f"Unsupported root entity type '{root_type}'.")

        if entity_type is not None and entity_type not in supported_types:
            raise UnsupportedEntityTypeError(f"Unsupported entity type filter '{entity_type}'.")

        if relationship is not None:
            supported_rels = {r.value for r in EvidenceGraphRelationship}
            if relationship not in supported_rels:
                raise UnsupportedRelationshipError(f"Unsupported relationship filter '{relationship}'.")

        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        user_uuid = uuid.UUID(str(user_id)) if user_id else None
        org_uuid = uuid.UUID(str(organization_id)) if organization_id else None

        # Verify root entity existence and tenant scope
        try:
            root_res = await cls.validate_endpoint(
                db=db,
                entity_type=root_type,
                entity_id=root_id,
                expected_team_id=team_uuid,
                expected_org_id=org_uuid,
                expected_user_id=user_uuid if team_uuid is None else None,
            )
            canonical_root_id = root_res.canonical_id
        except (EntityNotFoundError, TenantIsolationError, MalformedIdentifierError):
            raise EntityNotFoundError(f"Root entity {root_type}:{root_id} not found in current workspace context.")

        # Build SQL CTE
        params: Dict[str, Any] = {
            "root_type": root_type,
            "root_id": canonical_root_id,
            "query_max_depth": effective_max_depth + 1,
        }
        binds = [
            bindparam("root_type"),
            bindparam("root_id"),
            bindparam("query_max_depth"),
        ]

        if team_uuid is not None:
            anchor_tenant = "e.team_id = :team_id"
            rec_tenant = "e.team_id = :team_id"
            params["team_id"] = team_uuid
            binds.append(bindparam("team_id", type_=Uuid(as_uuid=True)))
        else:
            anchor_tenant = "e.team_id IS NULL AND e.created_by_user_id = :user_id"
            rec_tenant = "e.team_id IS NULL AND e.created_by_user_id = :user_id"
            params["user_id"] = user_uuid
            binds.append(bindparam("user_id", type_=Uuid(as_uuid=True)))

        if org_uuid is not None:
            anchor_org = "AND (e.organization_id = :org_id OR e.organization_id IS NULL)"
            rec_org = "AND (e.organization_id = :org_id OR e.organization_id IS NULL)"
            params["org_id"] = org_uuid
            binds.append(bindparam("org_id", type_=Uuid(as_uuid=True)))
        else:
            anchor_org = ""
            rec_org = ""

        rel_filter_anchor = ""
        rel_filter_rec = ""
        if relationship is not None:
            rel_filter_anchor = "AND e.relationship = :rel_filter"
            rel_filter_rec = "AND e.relationship = :rel_filter"
            params["rel_filter"] = relationship
            binds.append(bindparam("rel_filter"))

        entity_filter_anchor = ""
        entity_filter_rec = ""
        if entity_type is not None:
            if dir_upper == "FORWARD":
                entity_filter_anchor = "AND e.target_type = :ent_filter"
                entity_filter_rec = "AND e.target_type = :ent_filter"
            else:
                entity_filter_anchor = "AND e.source_type = :ent_filter"
                entity_filter_rec = "AND e.source_type = :ent_filter"
            params["ent_filter"] = entity_type
            binds.append(bindparam("ent_filter"))

        if dir_upper == "FORWARD":
            cte_sql = f"""
            WITH RECURSIVE traversal AS (
                SELECT 
                    e.id, e.organization_id, e.team_id, e.created_by_user_id,
                    e.source_type, e.source_id, e.relationship, e.target_type, e.target_id,
                    e.source_artifact_hash, e.target_artifact_hash, e.metadata, e.edge_hash, e.created_at,
                    1 AS depth,
                    '/' || e.source_type || ':' || e.source_id || '/' || e.target_type || ':' || e.target_id || '/' AS path
                FROM evidence_graph_edges e
                WHERE {anchor_tenant} {anchor_org} {rel_filter_anchor} {entity_filter_anchor}
                  AND e.source_type = :root_type AND e.source_id = :root_id
                UNION ALL
                SELECT 
                    e.id, e.organization_id, e.team_id, e.created_by_user_id,
                    e.source_type, e.source_id, e.relationship, e.target_type, e.target_id,
                    e.source_artifact_hash, e.target_artifact_hash, e.metadata, e.edge_hash, e.created_at,
                    t.depth + 1 AS depth,
                    t.path || e.target_type || ':' || e.target_id || '/' AS path
                FROM evidence_graph_edges e
                JOIN traversal t ON e.source_type = t.target_type AND e.source_id = t.target_id
                WHERE {rec_tenant} {rec_org} {rel_filter_rec} {entity_filter_rec}
                  AND t.depth < :query_max_depth
                  AND t.path NOT LIKE '%/' || e.target_type || ':' || e.target_id || '/%'
            )
            SELECT * FROM traversal
            ORDER BY depth, source_type, source_id, relationship, target_type, target_id;
            """
        else:
            cte_sql = f"""
            WITH RECURSIVE traversal AS (
                SELECT 
                    e.id, e.organization_id, e.team_id, e.created_by_user_id,
                    e.source_type, e.source_id, e.relationship, e.target_type, e.target_id,
                    e.source_artifact_hash, e.target_artifact_hash, e.metadata, e.edge_hash, e.created_at,
                    1 AS depth,
                    '/' || e.target_type || ':' || e.target_id || '/' || e.source_type || ':' || e.source_id || '/' AS path
                FROM evidence_graph_edges e
                WHERE {anchor_tenant} {anchor_org} {rel_filter_anchor} {entity_filter_anchor}
                  AND e.target_type = :root_type AND e.target_id = :root_id
                UNION ALL
                SELECT 
                    e.id, e.organization_id, e.team_id, e.created_by_user_id,
                    e.source_type, e.source_id, e.relationship, e.target_type, e.target_id,
                    e.source_artifact_hash, e.target_artifact_hash, e.metadata, e.edge_hash, e.created_at,
                    t.depth + 1 AS depth,
                    t.path || e.source_type || ':' || e.source_id || '/' AS path
                FROM evidence_graph_edges e
                JOIN traversal t ON e.target_type = t.source_type AND e.target_id = t.source_id
                WHERE {rec_tenant} {rec_org} {rel_filter_rec} {entity_filter_rec}
                  AND t.depth < :query_max_depth
                  AND t.path NOT LIKE '%/' || e.source_type || ':' || e.source_id || '/%'
            )
            SELECT * FROM traversal
            ORDER BY depth, source_type, source_id, relationship, target_type, target_id;
            """

        stmt = text(cte_sql).bindparams(*binds)
        res = await db.execute(stmt, params)
        raw_rows = res.mappings().all()

        depth_overflow = any(r["depth"] > effective_max_depth for r in raw_rows)
        valid_rows = [r for r in raw_rows if r["depth"] <= effective_max_depth]

        # Deduplicate edges by edge UUID
        seen_edge_ids: Set[str] = set()
        deduped_edges: List[Dict[str, Any]] = []
        for r in valid_rows:
            raw_id = r["id"]
            try:
                e_id = str(uuid.UUID(str(raw_id)))
            except Exception:
                e_id = str(raw_id)
            if e_id not in seen_edge_ids:
                seen_edge_ids.add(e_id)
                raw_meta = r["metadata"]
                if isinstance(raw_meta, str):
                    try:
                        clean_meta = json.loads(raw_meta)
                    except Exception:
                        clean_meta = {}
                else:
                    clean_meta = raw_meta or {}

                created_at_val = r["created_at"]
                created_at_str = created_at_val.isoformat() if hasattr(created_at_val, "isoformat") else str(created_at_val)

                deduped_edges.append({
                    "id": e_id,
                    "source_type": r["source_type"],
                    "source_id": r["source_id"],
                    "relationship": r["relationship"],
                    "target_type": r["target_type"],
                    "target_id": r["target_id"],
                    "source_artifact_hash": r["source_artifact_hash"],
                    "target_artifact_hash": r["target_artifact_hash"],
                    "metadata": clean_meta,
                    "edge_hash": r["edge_hash"],
                    "created_at": created_at_str,
                    "depth": r["depth"],
                })

        # Track distinct nodes
        nodes_dict: Dict[Tuple[str, str], int] = {(root_type, canonical_root_id): 0}
        for e in deduped_edges:
            s_key = (e["source_type"], e["source_id"])
            t_key = (e["target_type"], e["target_id"])
            if dir_upper == "FORWARD":
                if s_key not in nodes_dict:
                    nodes_dict[s_key] = e["depth"] - 1
                if t_key not in nodes_dict:
                    nodes_dict[t_key] = e["depth"]
            else:
                if t_key not in nodes_dict:
                    nodes_dict[t_key] = e["depth"] - 1
                if s_key not in nodes_dict:
                    nodes_dict[s_key] = e["depth"]

        limit_reached = False
        limit_type = None

        if depth_overflow:
            limit_reached = True
            limit_type = "max_depth"
        elif len(nodes_dict) > effective_max_nodes:
            limit_reached = True
            limit_type = "max_nodes"
            sorted_node_keys = sorted(nodes_dict.items(), key=lambda item: (item[1], item[0][0], item[0][1]))[:effective_max_nodes]
            nodes_dict = dict(sorted_node_keys)
            deduped_edges = [
                e for e in deduped_edges
                if (e["source_type"], e["source_id"]) in nodes_dict and (e["target_type"], e["target_id"]) in nodes_dict
            ]
        elif len(deduped_edges) > effective_max_edges:
            limit_reached = True
            limit_type = "max_edges"
            deduped_edges = deduped_edges[:effective_max_edges]
            retained_node_keys = {(root_type, canonical_root_id)}
            for e in deduped_edges:
                retained_node_keys.add((e["source_type"], e["source_id"]))
                retained_node_keys.add((e["target_type"], e["target_id"]))
            nodes_dict = {k: v for k, v in nodes_dict.items() if k in retained_node_keys}

        final_nodes = [
            {"entity_type": k[0], "entity_id": k[1], "depth": depth_val}
            for k, depth_val in nodes_dict.items()
        ]
        final_nodes.sort(key=lambda n: (n["depth"], n["entity_type"], n["entity_id"]))

        deduped_edges.sort(
            key=lambda e: (e["depth"], e["source_type"], e["source_id"], e["relationship"], e["target_type"], e["target_id"])
        )

        return {
            "root": {"entity_type": root_type, "entity_id": canonical_root_id},
            "nodes": final_nodes,
            "edges": deduped_edges,
            "traversal": {
                "direction": dir_upper,
                "max_depth": max_depth,
                "nodes_returned": len(final_nodes),
                "edges_returned": len(deduped_edges),
                "limit_reached": limit_reached,
                "limit_type": limit_type,
            },
        }

    @classmethod
    async def traverse_forward(
        cls,
        db: AsyncSession,
        root_type: str,
        root_id: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        relationship: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Follows outgoing edges downstream from root entity.
        """
        return await cls._execute_recursive_traversal(
            db=db,
            root_type=root_type,
            root_id=root_id,
            direction="FORWARD",
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            relationship=relationship,
            entity_type=entity_type,
        )

    @classmethod
    async def traverse_backward(
        cls,
        db: AsyncSession,
        root_type: str,
        root_id: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        relationship: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Follows incoming edges upstream to supporting/explaining entities.
        """
        return await cls._execute_recursive_traversal(
            db=db,
            root_type=root_type,
            root_id=root_id,
            direction="BACKWARD",
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            relationship=relationship,
            entity_type=entity_type,
        )

    @classmethod
    async def get_subgraph(
        cls,
        db: AsyncSession,
        root_type: str,
        root_id: str,
        direction: str = "FORWARD",
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
        relationship: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queries bounded subgraph rooted at specified entity.
        """
        return await cls._execute_recursive_traversal(
            db=db,
            root_type=root_type,
            root_id=root_id,
            direction=direction,
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            relationship=relationship,
            entity_type=entity_type,
        )

    @classmethod
    async def count_reachable(
        cls,
        db: AsyncSession,
        root_type: str,
        root_id: str,
        direction: str = "FORWARD",
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> Dict[str, Any]:
        """
        Counts reachable distinct nodes and edges within bounded depth.
        """
        res = await cls._execute_recursive_traversal(
            db=db,
            root_type=root_type,
            root_id=root_id,
            direction=direction,
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
            max_depth=max_depth,
            max_nodes=cls.MAX_ALLOWED_NODES,
            max_edges=cls.MAX_ALLOWED_EDGES,
        )
        return {
            "root": res["root"],
            "direction": res["traversal"]["direction"],
            "max_depth": res["traversal"]["max_depth"],
            "reachable_nodes_count": len(res["nodes"]),
            "reachable_edges_count": len(res["edges"]),
        }

    @classmethod
    async def explain_path(
        cls,
        db: AsyncSession,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        max_depth: int = 10,
    ) -> Dict[str, Any]:
        """
        Computes the shortest deterministic directed graph path from source to target.
        Returns provenance-preserving chain of exact stored edges and nodes.
        """
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1.")
        effective_max_depth = min(max_depth, cls.MAX_ALLOWED_DEPTH)

        supported_types = {e.value for e in SupportedEntityType}
        if source_type not in supported_types:
            raise UnsupportedEntityTypeError(f"Unsupported source entity type '{source_type}'.")
        if target_type not in supported_types:
            raise UnsupportedEntityTypeError(f"Unsupported target entity type '{target_type}'.")

        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        user_uuid = uuid.UUID(str(user_id)) if user_id else None
        org_uuid = uuid.UUID(str(organization_id)) if organization_id else None

        try:
            src_res = await cls.validate_endpoint(
                db=db, entity_type=source_type, entity_id=source_id,
                expected_team_id=team_uuid, expected_org_id=org_uuid,
                expected_user_id=user_uuid if team_uuid is None else None,
            )
            clean_src_id = src_res.canonical_id
        except (EntityNotFoundError, TenantIsolationError, MalformedIdentifierError):
            raise EntityNotFoundError(f"Source entity {source_type}:{source_id} not found in workspace.")

        try:
            tgt_res = await cls.validate_endpoint(
                db=db, entity_type=target_type, entity_id=target_id,
                expected_team_id=team_uuid, expected_org_id=org_uuid,
                expected_user_id=user_uuid if team_uuid is None else None,
            )
            clean_tgt_id = tgt_res.canonical_id
        except (EntityNotFoundError, TenantIsolationError, MalformedIdentifierError):
            raise EntityNotFoundError(f"Target entity {target_type}:{target_id} not found in workspace.")

        if source_type == target_type and clean_src_id == clean_tgt_id:
            return {
                "path_found": True,
                "length": 0,
                "source": {"entity_type": source_type, "entity_id": clean_src_id},
                "target": {"entity_type": target_type, "entity_id": clean_tgt_id},
                "nodes": [{"entity_type": source_type, "entity_id": clean_src_id, "depth": 0}],
                "edges": [],
            }

        params: Dict[str, Any] = {
            "src_type": source_type,
            "src_id": clean_src_id,
            "tgt_type": target_type,
            "tgt_id": clean_tgt_id,
            "max_depth": effective_max_depth,
        }
        binds = [
            bindparam("src_type"),
            bindparam("src_id"),
            bindparam("tgt_type"),
            bindparam("tgt_id"),
            bindparam("max_depth"),
        ]

        if team_uuid is not None:
            anchor_tenant = "e.team_id = :team_id"
            rec_tenant = "e.team_id = :team_id"
            params["team_id"] = team_uuid
            binds.append(bindparam("team_id", type_=Uuid(as_uuid=True)))
        else:
            anchor_tenant = "e.team_id IS NULL AND e.created_by_user_id = :user_id"
            rec_tenant = "e.team_id IS NULL AND e.created_by_user_id = :user_id"
            params["user_id"] = user_uuid
            binds.append(bindparam("user_id", type_=Uuid(as_uuid=True)))

        if org_uuid is not None:
            anchor_org = "AND (e.organization_id = :org_id OR e.organization_id IS NULL)"
            rec_org = "AND (e.organization_id = :org_id OR e.organization_id IS NULL)"
            params["org_id"] = org_uuid
            binds.append(bindparam("org_id", type_=Uuid(as_uuid=True)))
        else:
            anchor_org = ""
            rec_org = ""

        path_cte = f"""
        WITH RECURSIVE path_finder AS (
            SELECT 
                e.id, e.organization_id, e.team_id, e.created_by_user_id,
                e.source_type, e.source_id, e.relationship, e.target_type, e.target_id,
                e.source_artifact_hash, e.target_artifact_hash, e.metadata, e.edge_hash, e.created_at,
                1 AS depth,
                '/' || e.source_type || ':' || e.source_id || '/' || e.target_type || ':' || e.target_id || '/' AS path,
                '/' || e.id || '/' AS edge_path
            FROM evidence_graph_edges e
            WHERE {anchor_tenant} {anchor_org}
              AND e.source_type = :src_type AND e.source_id = :src_id
            UNION ALL
            SELECT 
                e.id, e.organization_id, e.team_id, e.created_by_user_id,
                e.source_type, e.source_id, e.relationship, e.target_type, e.target_id,
                e.source_artifact_hash, e.target_artifact_hash, e.metadata, e.edge_hash, e.created_at,
                p.depth + 1 AS depth,
                p.path || e.target_type || ':' || e.target_id || '/' AS path,
                p.edge_path || e.id || '/' AS edge_path
            FROM evidence_graph_edges e
            JOIN path_finder p ON e.source_type = p.target_type AND e.source_id = p.target_id
            WHERE {rec_tenant} {rec_org}
              AND p.depth < :max_depth
              AND p.path NOT LIKE '%/' || e.target_type || ':' || e.target_id || '/%'
        )
        SELECT edge_path, depth FROM path_finder
        WHERE target_type = :tgt_type AND target_id = :tgt_id
        ORDER BY depth ASC, path ASC, edge_path ASC
        LIMIT 1;
        """

        stmt = text(path_cte).bindparams(*binds)
        res = await db.execute(stmt, params)
        found_row = res.mappings().first()

        if not found_row:
            return {
                "path_found": False,
                "length": 0,
                "source": {"entity_type": source_type, "entity_id": clean_src_id},
                "target": {"entity_type": target_type, "entity_id": clean_tgt_id},
                "nodes": [],
                "edges": [],
            }

        edge_id_strs = [s for s in found_row["edge_path"].split("/") if s]
        edge_uuids = [uuid.UUID(s) for s in edge_id_strs]

        edges_query = select(EvidenceGraphEdgeRecord).where(EvidenceGraphEdgeRecord.id.in_(edge_uuids))
        edges_res = await db.execute(edges_query)
        edges_by_id = {str(e.id).replace("-", ""): e for e in edges_res.scalars().all()}
        for k, v in list(edges_by_id.items()):
            edges_by_id[str(v.id)] = v

        ordered_edges: List[Dict[str, Any]] = []
        path_nodes: List[Dict[str, Any]] = [{"entity_type": source_type, "entity_id": clean_src_id, "depth": 0}]

        for idx, e_id_str in enumerate(edge_id_strs):
            clean_lookup = e_id_str.replace("-", "")
            rec = edges_by_id.get(clean_lookup) or edges_by_id.get(e_id_str)
            if rec:
                raw_meta = rec.metadata_ or {}
                ordered_edges.append({
                    "id": str(rec.id),
                    "source_type": rec.source_type,
                    "source_id": rec.source_id,
                    "relationship": rec.relationship,
                    "target_type": rec.target_type,
                    "target_id": rec.target_id,
                    "source_artifact_hash": rec.source_artifact_hash,
                    "target_artifact_hash": rec.target_artifact_hash,
                    "metadata": raw_meta,
                    "edge_hash": rec.edge_hash,
                    "created_at": rec.created_at.isoformat() if hasattr(rec.created_at, "isoformat") else str(rec.created_at),
                    "depth": idx + 1,
                })
                path_nodes.append({
                    "entity_type": rec.target_type,
                    "entity_id": rec.target_id,
                    "depth": idx + 1,
                })

        return {
            "path_found": True,
            "length": len(ordered_edges),
            "source": {"entity_type": source_type, "entity_id": clean_src_id},
            "target": {"entity_type": target_type, "entity_id": clean_tgt_id},
            "nodes": path_nodes,
            "edges": ordered_edges,
        }

