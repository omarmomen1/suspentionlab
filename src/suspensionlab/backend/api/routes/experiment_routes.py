"""
backend/api/routes/experiment_routes.py
=======================================
API endpoints for Hypothesis-Driven Engineering Experiments & Optimization.

POST /api/v1/experiments/run            → Run 1-click experiment & persist object
GET  /api/v1/experiments                → List recent experiments
GET  /api/v1/experiments/{id}           → Get reproducible experiment by ID
POST /api/v1/experiments/{id}/retry     → Re-execute stored experiment definition & verify hash
POST /api/v1/experiments/compare        → Deep comparison: "Why is B better than A?"
POST /api/v1/experiments/batch-optimize → Batch optimization & multi-objective Pareto frontier
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.services.experiment_service import ExperimentService

router = APIRouter(prefix="/experiments", tags=["engineering-experiments"])


class RunExperimentRequest(BaseModel):
    question: str = Field(..., description="Engineering question, e.g. 'What happens if I increase front roll stiffness by 10%?'")
    hypothesis: Optional[str] = Field(None, description="Physical hypothesis being evaluated")
    parent_setup: Optional[Dict[str, float]] = Field(None, description="Baseline setup parameters")
    parameter_changes: Optional[Any] = Field(None, description="List or dictionary of parameter changes")
    road_profile: Optional[Dict[str, Any]] = Field(None, description="Excitation profile definition")
    author: Optional[str] = Field(None, description="Signee dynamics engineer name")
    clone_from: Optional[str] = Field(None, description="Cloned optimization candidate identifier")
    optimization_id: Optional[str] = Field(None, description="Parent optimization ID")


class CompareSetupsRequest(BaseModel):
    setup_a: Dict[str, float] = Field(..., description="Setup A (Baseline) parameters")
    setup_b: Dict[str, float] = Field(..., description="Setup B (Candidate) parameters")
    road_profile: Optional[Dict[str, Any]] = Field(None, description="Excitation profile definition")


class BatchOptimizeRequest(BaseModel):
    base_params: Optional[Dict[str, float]] = Field(None, description="Base setup parameters")
    param_ranges: Optional[Dict[str, List[float]]] = Field(None, description="Parameter ranges for grid sweep e.g. {'k_s': [20000, 50000, 5]}")
    road_profile: Optional[Dict[str, Any]] = Field(None, description="Road excitation profile")


@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_experiment(
    req: RunExperimentRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes a 1-click experiment:
    clone setup → validate parameter → run simulation → calculate KPIs → check constraints → persist provenance → return result.
    """
    try:
        user_id = getattr(user, "user_id", str(user))
        team_id = getattr(user, "team_id", None)
        org_id = getattr(user, "organization_id", None)

        # ── Trial Governance: Check 7-day expiration & simulation quota ──
        from suspensionlab.backend.services.trial_service import TrialService
        trial = await TrialService.assert_trial_access(db, user, action="simulate", delta=1)

        res = await ExperimentService.run_experiment(
            db=db,
            user_id=str(user_id),
            team_id=str(team_id) if team_id else None,
            organization_id=str(org_id) if org_id else None,
            question=req.question,
            hypothesis=req.hypothesis,
            parent_setup=req.parent_setup,
            parameter_changes=req.parameter_changes,
            road_profile=req.road_profile,
            author=req.author,
            clone_from=req.clone_from,
            optimization_id=req.optimization_id,
        )
        if trial:
            await TrialService.record_trial_usage(db, user, action="simulate", delta=1)
        return res
    except HTTPException:
        raise
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Experiment simulation failed: {exc}")


@router.get("")
async def list_experiments(
    limit: int = 50,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Lists recent experiments for the authenticated user/team."""
    user_id = getattr(user, "user_id", str(user))
    team_id = getattr(user, "team_id", None)
    experiments = await ExperimentService.list_experiments(
        db=db,
        user_id=str(user_id),
        team_id=str(team_id) if team_id else None,
        limit=limit,
    )
    return {
        "total": len(experiments),
        "experiments": experiments,
    }


@router.get("/{id}")
async def get_experiment(
    id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Retrieves reproducible experiment record by ID."""
    user_id = getattr(user, "user_id", str(user))
    team_id = getattr(user, "team_id", None)
    try:
        return await ExperimentService.get_experiment(
            db=db,
            exp_id=id,
            user_id=str(user_id),
            team_id=str(team_id) if team_id else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{id}/retry")
async def retry_experiment(
    id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Re-executes an experiment from its stored definition and verifies mathematical reproducibility."""
    user_id = getattr(user, "user_id", str(user))
    team_id = getattr(user, "team_id", None)
    try:
        return await ExperimentService.retry_experiment(
            db=db,
            exp_id=id,
            user_id=str(user_id),
            team_id=str(team_id) if team_id else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/compare")
async def compare_setups(
    req: CompareSetupsRequest,
    user: dict = Depends(verify_api_key),
):
    """
    Performs deep comparative analysis: 'WHY IS B BETTER THAN A?'.
    Returns What Changed, What Improved, What Got Worse, Causality Chain, Evidence, and Confidence.
    """
    try:
        return ExperimentService.compare_setups(
            setup_a=req.setup_a,
            setup_b=req.setup_b,
            road_profile=req.road_profile,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Comparison evaluation failed: {exc}")


@router.post("/batch-optimize")
async def batch_optimize(
    req: BatchOptimizeRequest,
    user: dict = Depends(verify_api_key),
):
    """
    Executes multi-objective optimization across candidate setups and returns the Pareto frontier.
    """
    try:
        return ExperimentService.batch_optimize_pareto(
            base_params=req.base_params or {},
            param_ranges=req.param_ranges,
            road_profile=req.road_profile,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Batch optimization failed: {exc}")
