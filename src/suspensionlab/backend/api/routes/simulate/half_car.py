from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import numpy as np

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, require_permission
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.core.compute_governance import bounded_run, assert_user_concurrency, meter_simulation
from suspensionlab.shared.models import HalfCarSimulateRequest
from suspensionlab.physics.half_car import HalfCarParams, RoadProfile, run_half_car_analysis
from typing import Any

router = APIRouter()
logger = logging.getLogger(__name__)

from suspensionlab.backend.workers.unified_worker import _serialize_for_json

def _serialize_numpy(obj):
    return _serialize_for_json(obj)

@router.post("/simulate/half-car")
async def simulate_half_car(
    payload: HalfCarSimulateRequest,
    user: Any = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency)
):
    try:
        await assert_user_concurrency(db, str(user.user_id), getattr(user, "plan", "FREE"))
        # Pass B: record usage (Redis primary, DB fallback) so the meter reflects actual runs.
        await meter_simulation(db, str(user.user_id), str(getattr(user, "plan", "FREE")))
        p = HalfCarParams(**payload.params.model_dump())
        r = RoadProfile(**payload.profile.model_dump())
        raw_res = await bounded_run(run_half_car_analysis, p, r, timeout=30.0, model="half_car")
        res_dict = _serialize_numpy(raw_res)
        return res_dict
    except HTTPException:
        raise
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Half-car simulation timed out.")
    except Exception as e:
        logger.exception("Unhandled error in /simulate/half-car: %s", e)
        raise HTTPException(status_code=400, detail="Half-car simulation failed. Check the submitted parameters and try again.")
