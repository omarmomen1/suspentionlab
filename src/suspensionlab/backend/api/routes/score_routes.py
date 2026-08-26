"""
backend/api/routes/score_routes.py
===================================
Setup Score fleet benchmark API (Tier A1).

POST /api/v1/scores/submit     → score a setup, opt in to the anonymous fleet
GET /api/v1/scores/percentile  → fleet percentile for a given score

Privacy: submitted rows contain NO user/team identifiers — only vehicle class,
score components, and a timestamp. A submission cannot be traced back to its
author; that guarantee is what makes engineers willing to opt in.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.core.compute_governance import inline_compute_guard
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.setup_score import SetupScore
from suspensionlab.physics.setup_score import compute_setup_score
from suspensionlab.backend.security.rate_limit import RateLimiter

router = APIRouter(prefix="/scores", tags=["setup-score"])

VEHICLE_CLASSES = ("road", "track", "gt", "rally", "offroad", "formula")


class SubmitScoreRequest(BaseModel):
    vehicle_class: str = Field(..., description="road|track|gt|rally|offroad|formula")
    rms_body_accel_ms2: float = Field(..., ge=0)
    rms_tire_load_var_n: float = Field(..., ge=0)
    peak_susp_travel_mm: float = Field(..., ge=0)
    static_load_per_corner_n: float = Field(3500.0, gt=0)
    travel_window_mm: float = Field(60.0, gt=0)


async def _percentile(db: AsyncSession, vehicle_class: str, score: float) -> tuple[float, int]:
    """Fraction of the class fleet scoring strictly below `score`."""
    total_q = await db.execute(
        select(func.count())
        .select_from(SetupScore)
        .where(SetupScore.vehicle_class == vehicle_class)
    )
    total = int(total_q.scalar_one() or 0)
    if total == 0:
        return 50.0, 0
    below_q = await db.execute(
        select(func.count())
        .select_from(SetupScore)
        .where(SetupScore.vehicle_class == vehicle_class, SetupScore.score < score)
    )
    below = int(below_q.scalar_one() or 0)
    return round((below / total) * 100.0, 1), total


@router.post("/submit")
async def submit_score(
    req: SubmitScoreRequest,
    user=Depends(inline_compute_guard),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Score a setup and (implicitly) add it to the anonymous fleet benchmark."""
    if req.vehicle_class not in VEHICLE_CLASSES:
        raise HTTPException(status_code=400, detail=f"vehicle_class must be one of {VEHICLE_CLASSES}.")

    result = compute_setup_score(
        rms_body_accel_ms2=req.rms_body_accel_ms2,
        rms_tire_load_var_n=req.rms_tire_load_var_n,
        peak_susp_travel_mm=req.peak_susp_travel_mm,
        static_load_per_corner_n=req.static_load_per_corner_n,
        travel_window_mm=req.travel_window_mm,
    )

    db.add(SetupScore(
        vehicle_class=req.vehicle_class,
        score=result.score,
        comfort=result.components.comfort,
        grip=result.components.grip,
        control=result.components.control,
    ))
    await db.commit()

    percentile, fleet_size = await _percentile(db, req.vehicle_class, result.score)
    payload = result.to_dict()
    payload.update({
        "vehicle_class": req.vehicle_class,
        "percentile": percentile,
        "fleet_size": fleet_size,
        "message": (
            f"Your setup beats {percentile:.0f}% of the {req.vehicle_class} fleet."
            if fleet_size > 1 else "First submission in this class — you set the baseline."
        ),
    })
    return payload


@router.get("/percentile")
async def get_percentile(
    vehicle_class: str = Query(...),
    score: float = Query(..., ge=0.0, le=100.0),
    user=Depends(inline_compute_guard),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Fleet percentile for a hypothetical score without submitting."""
    if vehicle_class not in VEHICLE_CLASSES:
        raise HTTPException(status_code=400, detail=f"vehicle_class must be one of {VEHICLE_CLASSES}.")
    percentile, fleet_size = await _percentile(db, vehicle_class, score)
    return {"vehicle_class": vehicle_class, "score": score, "percentile": percentile, "fleet_size": fleet_size}
