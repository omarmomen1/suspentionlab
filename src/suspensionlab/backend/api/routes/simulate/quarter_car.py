from fastapi import APIRouter, HTTPException, Depends, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.simulation_service import SimulationService
from suspensionlab.shared.models import SimulateRequest
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

class JobResponse(BaseModel):
    job_id: str
    status: str
    result: dict | None = None
    error: str | None = None

@router.post("/simulate", response_model=JobResponse, status_code=status.HTTP_200_OK)
async def simulate(
    payload: SimulateRequest,
    response: Response,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency)
):
    try:
        # Pass B: record usage (Redis primary, DB fallback) so the meter reflects actual runs.
        from suspensionlab.backend.core.compute_governance import meter_simulation
        await meter_simulation(db, str(user.user_id), str(getattr(user, "plan", "FREE")))
        job_res = await SimulationService.execute_or_enqueue(
            user_id=user.user_id,
            plan=user.plan,
            job_type="SIMULATE_QUARTER",
            payload=payload.model_dump(),
            db=db,
            team_id=getattr(user, "team_id", None),
        )
        if job_res.get("status") == "PENDING":
            response.status_code = status.HTTP_202_ACCEPTED
        return JobResponse(
            job_id=job_res["job_id"],
            status=job_res.get("status", "COMPLETED"),
            result=job_res.get("result"),
            error=job_res.get("error"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in /simulate: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error.")
