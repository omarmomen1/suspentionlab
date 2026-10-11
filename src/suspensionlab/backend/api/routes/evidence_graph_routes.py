"""
backend/api/routes/evidence_graph_routes.py
===========================================
SuspensionLab PRO — Phase 4.2 Engineering Evidence Graph Read API.

Exposes authenticated, tenant-isolated, deterministic graph query and traversal endpoints:
- GET /edges/{edge_id}: Direct edge lookup with cryptographic integrity check
- GET /edges: Filtered, paginated edge enumeration
- GET /traverse: Forward/backward recursive traversal from root entity
- GET /subgraph: Subgraph extraction rooted at entity
- GET /path: Deterministic shortest-path explanation between two entities

Strictly READ-ONLY. No mutation or traversal-based entity fabrication.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    UnsupportedRelationshipError,
    TraversalLimitError,
    DEFAULT_MAX_DEPTH,
    MAX_ALLOWED_DEPTH,
    DEFAULT_MAX_NODES,
    MAX_ALLOWED_NODES,
    DEFAULT_MAX_EDGES,
    MAX_ALLOWED_EDGES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evidence-graph", tags=["evidence-graph"])


# ── RESPONSE MODELS ────────────────────────────────────────────────────────────

class CanonicalEdgeDTO(BaseModel):
    id: str
    source_type: str
    source_id: str
    relationship: str
    target_type: str
    target_id: str
    source_artifact_hash: Optional[str] = None
    target_artifact_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    edge_hash: str
    created_at: str


class NodeDTO(BaseModel):
    entity_type: str
    entity_id: str
    depth: int


class TraversalMetadataDTO(BaseModel):
    direction: str
    max_depth: int
    nodes_returned: int
    edges_returned: int
    limit_reached: bool
    limit_type: Optional[str] = None


class TraversalResponse(BaseModel):
    root: Dict[str, str]
    nodes: List[NodeDTO]
    edges: List[CanonicalEdgeDTO]
    traversal: TraversalMetadataDTO


class PathExplanationResponse(BaseModel):
    path_found: bool
    length: int
    source: Dict[str, str]
    target: Dict[str, str]
    nodes: List[NodeDTO]
    edges: List[CanonicalEdgeDTO]


class EdgeListResponse(BaseModel):
    edges: List[CanonicalEdgeDTO]
    total: int
    limit: int
    offset: int


def _to_edge_dto(rec) -> CanonicalEdgeDTO:
    raw_meta = getattr(rec, "metadata_", None) or getattr(rec, "metadata", {}) or {}
    created_at_val = rec.created_at
    created_at_str = created_at_val.isoformat() if hasattr(created_at_val, "isoformat") else str(created_at_val)
    return CanonicalEdgeDTO(
        id=str(rec.id),
        source_type=rec.source_type,
        source_id=rec.source_id,
        relationship=rec.relationship,
        target_type=rec.target_type,
        target_id=rec.target_id,
        source_artifact_hash=rec.source_artifact_hash,
        target_artifact_hash=rec.target_artifact_hash,
        metadata=raw_meta if isinstance(raw_meta, dict) else {},
        edge_hash=rec.edge_hash,
        created_at=created_at_str,
    )


# ── ENDPOINTS ──────────────────────────────────────────────────────────────────

@router.get("/edges/{edge_id}", response_model=CanonicalEdgeDTO)
async def get_edge_endpoint(
    edge_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Direct lookup for a single Evidence Graph edge.
    Enforces tenant and personal workspace boundaries without information leakage.
    """
    team_id = user.team_id if getattr(user, "team_id", None) else None
    user_id = user.user_id
    org_id = user.organization_id if getattr(user, "organization_id", None) else None

    edge = await EvidenceGraphService.get_edge(
        db=db,
        edge_id=edge_id,
        team_id=team_id,
        user_id=user_id,
        organization_id=org_id,
    )
    if edge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge '{edge_id}' not found.",
        )
    return _to_edge_dto(edge)


@router.get("/edges", response_model=EdgeListResponse)
async def list_edges_endpoint(
    source_type: Optional[str] = Query(None, description="Filter by source entity type"),
    source_id: Optional[str] = Query(None, description="Filter by source entity identifier"),
    target_type: Optional[str] = Query(None, description="Filter by target entity type"),
    target_id: Optional[str] = Query(None, description="Filter by target entity identifier"),
    relationship: Optional[str] = Query(None, description="Filter by relationship vocabulary"),
    limit: int = Query(50, ge=1, le=200, description="Page limit (max 200)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Lists tenant-scoped edges with bounded pagination and deterministic ordering.
    """
    team_id = user.team_id if getattr(user, "team_id", None) else None
    user_id = user.user_id
    org_id = user.organization_id if getattr(user, "organization_id", None) else None

    try:
        edges = await EvidenceGraphService.list_edges(
            db=db,
            team_id=team_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relationship=relationship,
            limit=limit,
            offset=offset,
            user_id=user_id,
            organization_id=org_id,
        )
    except (UnsupportedEntityTypeError, UnsupportedRelationshipError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    edge_dtos = [_to_edge_dto(e) for e in edges]
    return EdgeListResponse(
        edges=edge_dtos,
        total=len(edge_dtos),
        limit=limit,
        offset=offset,
    )


@router.get("/traverse", response_model=TraversalResponse)
async def traverse_endpoint(
    root_type: str = Query(..., description="Canonical root entity type"),
    root_id: str = Query(..., description="Root entity identifier"),
    direction: str = Query("FORWARD", description="Traversal direction: FORWARD or BACKWARD"),
    max_depth: int = Query(DEFAULT_MAX_DEPTH, ge=1, le=MAX_ALLOWED_DEPTH, description="Maximum traversal depth"),
    max_nodes: int = Query(DEFAULT_MAX_NODES, ge=1, le=MAX_ALLOWED_NODES, description="Maximum nodes returned"),
    max_edges: int = Query(DEFAULT_MAX_EDGES, ge=1, le=MAX_ALLOWED_EDGES, description="Maximum edges returned"),
    relationship: Optional[str] = Query(None, description="Filter by relationship"),
    entity_type: Optional[str] = Query(None, description="Filter by node entity type"),
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes bounded, deterministic, cycle-safe recursive traversal from root entity.
    """
    start_time = time.monotonic()
    team_id = user.team_id if getattr(user, "team_id", None) else None
    user_id = user.user_id
    org_id = user.organization_id if getattr(user, "organization_id", None) else None

    try:
        res = await EvidenceGraphService.get_subgraph(
            db=db,
            root_type=root_type,
            root_id=root_id,
            direction=direction,
            team_id=team_id,
            user_id=user_id,
            organization_id=org_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            relationship=relationship,
            entity_type=entity_type,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (UnsupportedEntityTypeError, UnsupportedRelationshipError, ValueError, TraversalLimitError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    elapsed_ms = (time.monotonic() - start_time) * 1000.0
    logger.info(
        "EvidenceGraph traversal completed: direction=%s root=%s:%s nodes=%d edges=%d duration_ms=%.2f",
        direction, root_type, root_id, len(res["nodes"]), len(res["edges"]), elapsed_ms
    )

    return TraversalResponse(
        root=res["root"],
        nodes=[NodeDTO(**n) for n in res["nodes"]],
        edges=[CanonicalEdgeDTO(**e) for e in res["edges"]],
        traversal=TraversalMetadataDTO(**res["traversal"]),
    )


@router.get("/subgraph", response_model=TraversalResponse)
async def subgraph_endpoint(
    root_type: str = Query(..., description="Canonical root entity type"),
    root_id: str = Query(..., description="Root entity identifier"),
    direction: str = Query("FORWARD", description="Traversal direction: FORWARD or BACKWARD"),
    max_depth: int = Query(DEFAULT_MAX_DEPTH, ge=1, le=MAX_ALLOWED_DEPTH, description="Maximum traversal depth"),
    max_nodes: int = Query(DEFAULT_MAX_NODES, ge=1, le=MAX_ALLOWED_NODES, description="Maximum nodes returned"),
    max_edges: int = Query(DEFAULT_MAX_EDGES, ge=1, le=MAX_ALLOWED_EDGES, description="Maximum edges returned"),
    relationship: Optional[str] = Query(None, description="Filter by relationship"),
    entity_type: Optional[str] = Query(None, description="Filter by node entity type"),
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Subgraph query endpoint. Alias for bounded traversal returning full deduplicated subgraph.
    """
    return await traverse_endpoint(
        root_type=root_type,
        root_id=root_id,
        direction=direction,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_edges=max_edges,
        relationship=relationship,
        entity_type=entity_type,
        user=user,
        db=db,
    )


@router.get("/path", response_model=PathExplanationResponse)
async def path_endpoint(
    source_type: str = Query(..., description="Source entity type"),
    source_id: str = Query(..., description="Source entity identifier"),
    target_type: str = Query(..., description="Target entity type"),
    target_id: str = Query(..., description="Target entity identifier"),
    max_depth: int = Query(10, ge=1, le=MAX_ALLOWED_DEPTH, description="Maximum search hops"),
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Reconstructs the shortest deterministic directed provenance path from source to target.
    """
    start_time = time.monotonic()
    team_id = user.team_id if getattr(user, "team_id", None) else None
    user_id = user.user_id
    org_id = user.organization_id if getattr(user, "organization_id", None) else None

    try:
        res = await EvidenceGraphService.explain_path(
            db=db,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            team_id=team_id,
            user_id=user_id,
            organization_id=org_id,
            max_depth=max_depth,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (UnsupportedEntityTypeError, UnsupportedRelationshipError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    elapsed_ms = (time.monotonic() - start_time) * 1000.0
    logger.info(
        "EvidenceGraph path explanation completed: %s:%s -> %s:%s found=%s duration_ms=%.2f",
        source_type, source_id, target_type, target_id, res["path_found"], elapsed_ms
    )

    return PathExplanationResponse(
        path_found=res["path_found"],
        length=res["length"],
        source=res["source"],
        target=res["target"],
        nodes=[NodeDTO(**n) for n in res["nodes"]],
        edges=[CanonicalEdgeDTO(**e) for e in res["edges"]],
    )
