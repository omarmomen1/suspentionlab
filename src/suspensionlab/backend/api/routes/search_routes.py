"""
backend/api/routes/search_routes.py
====================================
SuspensionLab PRO — Universal Engineering Search API (Requirement 4).

Endpoint:
GET /api/v1/search?q={query}&category={category}&limit={limit}
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.universal_search_service import UniversalSearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=None)
async def universal_search_endpoint(
    q: str = Query(..., min_length=1, description="Engineering search term"),
    category: Optional[str] = Query(None, description="Optional category filter (e.g. 'experiments', 'decisions', 'parameters')"),
    limit: int = Query(30, ge=1, le=100, description="Maximum results to return"),
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes universal cross-entity engineering search across:
    vehicles, setups, telemetry, simulations, experiments, optimizations, decisions, reports, parameters.
    """
    cats = [category] if category else None
    return await UniversalSearchService.search(
        db=db,
        query=q,
        user_id=str(user.user_id),
        team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
        categories=cats,
        limit=limit,
    )
