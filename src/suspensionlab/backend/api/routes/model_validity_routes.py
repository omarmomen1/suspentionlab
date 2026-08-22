"""
backend/api/routes/model_validity_routes.py
============================================
Exposes the Model Validity & Confidence engine (Issue 16).

POST /api/v1/models/validity   → assess a ride or lap-sim model configuration
GET  /api/v1/models/validity/meta → check catalogue for UI tooltips
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from suspensionlab.physics.model_validity import (
    assess_lap_sim,
    assess_quarter_car,
)

router = APIRouter(prefix="/models", tags=["model-validity"])


class ValidityRequest(BaseModel):
    model: str = Field(..., description="'quarter_car' | 'lap_sim'")
    params: dict[str, Any] = Field(default_factory=dict)
    telemetry_correlation: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Optional model-to-telemetry correlation from a prior /telemetry/analyse run.",
    )


@router.post("/validity")
async def model_validity(req: ValidityRequest):
    """
    Compute the MODEL VALIDITY score and checklist for a given model config.

    Returns {score, band, summary, checks[]} — render this next to every result.
    """
    if req.model == "quarter_car":
        report = assess_quarter_car(req.params, req.telemetry_correlation)
    elif req.model == "lap_sim":
        report = assess_lap_sim(req.params, req.telemetry_correlation)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown model '{req.model}'. Supported: quarter_car, lap_sim.")

    # (#28) publish the score to Prometheus physics observability
    from suspensionlab.backend.observability import record_model_validity
    record_model_validity(report.model, report.score)

    return report.to_dict()


@router.get("/validity/meta")
async def validity_meta():
    """Static metadata describing status semantics for UI rendering."""
    return {
        "bands": {
            "High":   {"min_score": 80, "color": "#22c55e", "meaning": "Safe to base setup decisions on."},
            "Medium": {"min_score": 55, "color": "#f59e0b", "meaning": "Directionally useful; validate changes on the car."},
            "Low":    {"min_score": 0,  "color": "#ef4444", "meaning": "Conceptual only — do not use for race decisions."},
        },
        "statuses": {
            "pass": "Validated",
            "warn": "Approximation in effect",
            "fail": "Not supported by this model",
        },
    }
