"""
backend/api/routes/run_routes.py
=================================
Immutable Run Artifacts API (Issues 32–35).

POST /api/v1/runs                      → snapshot a completed job into RUN-xxxxxx
GET  /api/v1/runs                      → list my runs (newest first)
GET  /api/v1/runs/{label}              → full artifact
GET  /api/v1/runs/{a}/diff/{b}         → Setup Diff table + predicted consequences
GET  /api/v1/runs/{a}/what-changed/{b} → the Issue-35 headline summary

Runs are immutable: there is deliberately no PUT/PATCH/DELETE.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.services import run_artifacts
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/runs", tags=["run-artifacts"])


class CreateRunRequest(BaseModel):
    job_id: str = Field(..., description="Completed job ID to snapshot")
    title: str = ""
    setup_ref: Optional[str] = Field(None, description="Named setup, e.g. 'Spain-R3'")
    tire_ref: Optional[str] = None
    track_ref: Optional[str] = None
    telemetry_ref: Optional[str] = None


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("", status_code=201)
async def create_run(
    req: CreateRunRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Snapshot one of your completed simulations into an immutable RUN artifact."""
    try:
        run = await run_artifacts.create_run_from_job(
            db, req.job_id, user.user_id, getattr(user, "team_id", None),
            title=req.title,
            setup_ref=req.setup_ref,
            tire_ref=req.tire_ref,
            track_ref=req.track_ref,
            telemetry_ref=req.telemetry_ref,
        )
    except LookupError as exc:
        raise _not_found(exc)
    return run  # plain dict: {label, id, seq, created_at, params_hash, result_hash}


@router.get("")
async def list_runs(
    limit: int = 50,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    runs = await run_artifacts.list_runs(db, user.user_id, getattr(user, "team_id", None), limit)
    return {
        "total": len(runs),
        "runs": [
            {
                "label": r.label,
                "title": r.title,
                "simulation_type": r.simulation_type,
                "setup_ref": r.setup_ref,
                "track_ref": r.track_ref,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "result_hash": r.result_hash[:12],
            }
            for r in runs
        ],
    }


@router.get("/{label}")
async def get_run(
    label: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    try:
        run = await run_artifacts.get_run(db, label, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)
    return run_artifacts.run_to_dict(run, include_payload=True)


@router.get("/{a}/diff/{b}")
async def diff_runs(
    a: str,
    b: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Setup Diff (#33): parameter table (A/B/Δ%) plus predicted consequences
    computed from the two runs' own result metrics.
    """
    team_id = getattr(user, "team_id", None)
    try:
        run_a = await run_artifacts.get_run(db, a, user.user_id, team_id)
        run_b = await run_artifacts.get_run(db, b, user.user_id, team_id)
    except LookupError as exc:
        raise _not_found(exc)

    return {
        "a": run_a.label,
        "b": run_b.label,
        "parameters": run_artifacts.diff_params(run_a.params or {}, run_b.params or {}),
        "predicted_consequences": run_artifacts.diff_metrics(run_a.result or {}, run_b.result or {}),
    }


@router.get("/{a}/what-changed/{b}")
async def what_changed(
    a: str,
    b: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """The Issue-35 headline view: answers 'what changed?' in one payload."""
    team_id = getattr(user, "team_id", None)
    try:
        run_a = await run_artifacts.get_run(db, a, user.user_id, team_id)
        run_b = await run_artifacts.get_run(db, b, user.user_id, team_id)
    except LookupError as exc:
        raise _not_found(exc)
    return run_artifacts.what_changed(run_a, run_b)
