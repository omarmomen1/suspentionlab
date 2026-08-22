from fastapi import APIRouter, HTTPException, Depends, Request
import json
import asyncio
from sqlalchemy import update
import redis.asyncio as aioredis
from suspensionlab.shared.models import JobResponse, MonteCarloRequest
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry.propagate import inject

router = APIRouter()

@router.post("/simulate/monte-carlo", response_model=JobResponse, status_code=202)
async def simulate_monte_carlo(payload: MonteCarloRequest, request: Request, db: AsyncSession = Depends(get_db_dependency)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
        
    from suspensionlab.backend.services.quota import assert_can_run_job
    tier = getattr(request.state, "plan", "FREE")
    user = {"user_id": user_id, "plan": tier}
    await assert_can_run_job(user, db)

    from suspensionlab.backend.services.simulation_service import SimulationService
    try:
        job_id = await SimulationService.enqueue_simulation(
            user_id=user_id,
            plan=tier,
            job_type="MONTE_CARLO_QUARTER",
            payload=payload.model_dump(),
            db=db, team_id=getattr(user, "team_id", None)
        )
        return JobResponse(job_id=job_id, status="PENDING")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal simulation error.")
