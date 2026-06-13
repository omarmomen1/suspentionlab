"""
Shareable Report Routes— generate public links for simulation results.
Free: uses existing PostgreSQL/SQLite database. Zero extra cost.
"""
from __future__ import annotations
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.shared_report import SharedReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["shared-reports"])


class ShareRequest(BaseModel):
    simulation_type: str = "quarter_car"
    params: dict
    result: dict
    title: str = ""
    notes: str = ""


class ShareResponse(BaseModel):
    token: str
    url: str
    message: str


class ReportResponse(BaseModel):
    token: str
    simulation_type: str
    params: dict
    result: dict
    title: str
    notes: str
    created_at: str
    view_count: str


@router.post("/share", response_model=ShareResponse)
async def create_shared_report(
    req: ShareRequest,
    db: AsyncSession = Depends(get_db_dependency),
):
    """Save a simulation result and return a public share link."""
    token = str(uuid.uuid4())

    report = SharedReport(
        token=token,
        simulation_type=req.simulation_type,
        params=req.params,
        result=req.result,
        title=req.title or f"Suspension Analysis ({req.simulation_type.replace('_', ' ').title()})",
        notes=req.notes,
    )
    db.add(report)
    await db.commit()

    return ShareResponse(
        token=token,
        url=f"/report/{token}",
        message="Report shared successfully!",
    )


@router.get("/{token}", response_model=ReportResponse)
async def get_shared_report(
    token: str,
    db: AsyncSession = Depends(get_db_dependency),
):
    """Retrieve a shared simulation report by token. Public endpoint."""
    result = await db.execute(
        select(SharedReport).where(SharedReport.token == token)
    )
    report: SharedReport | None = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found or has expired.")

    if not report.is_public:
        raise HTTPException(status_code=403, detail="This report is private.")

    # Increment view count
    try:
        report.view_count = str(int(report.view_count or "0") + 1)
        await db.commit()
    except Exception:
        await db.rollback()

    return ReportResponse(
        token=report.token,
        simulation_type=report.simulation_type,
        params=report.params,
        result=report.result,
        title=report.title,
        notes=report.notes,
        created_at=report.created_at.isoformat(),
        view_count=report.view_count,
    )
