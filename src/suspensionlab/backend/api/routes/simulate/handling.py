from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.services.simulation_service import SimulationService
from suspensionlab.shared.models import HandlingRequest
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

class JobResponse(BaseModel):
    job_id: str
    status: str

@router.post("/simulate/handling", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def simulate_handling(
    payload: HandlingRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    try:
        job_id = await SimulationService.enqueue_simulation(
            user_id=user.user_id,
            plan=user.plan,
            job_type="SIMULATE_HANDLING",
            payload=payload.model_dump(),
            db=db
        )
        return {"job_id": job_id, "status": "PENDING"}
    except Exception as e:
        logger.exception("Unhandled error in /simulate/handling: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error.")
