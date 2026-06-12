from fastapi import APIRouter, HTTPException
import numpy as np
import asyncio
import logging
from suspensionlab.physics.exceptions import MathConvergenceError, PhysicsValidationError

logger = logging.getLogger(__name__)
from suspensionlab.shared.models import HalfCarSimulateRequest, HalfCarResultSchema
from suspensionlab.physics.half_car import HalfCarParams, run_half_car_analysis
from suspensionlab.physics.quarter_car import RoadProfile

router = APIRouter()

@router.post("/simulate/half-car", response_model=HalfCarResultSchema)
async def simulate_half_car(payload: HalfCarSimulateRequest):
    try:
        params = HalfCarParams(**payload.params.model_dump())
        profile = RoadProfile(**payload.profile.model_dump())
        
        # 8-DOF is heavier, so we definitely run this off the main event loop
        result = await asyncio.to_thread(run_half_car_analysis, params, profile)
        
        result_dict = result.__dict__.copy()
        for key, value in result_dict.items():
            if isinstance(value, np.ndarray):
                result_dict[key] = value.tolist()
                
        return HalfCarResultSchema(**result_dict)
    except (ValueError, PhysicsValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MathConvergenceError as e:
        raise HTTPException(
            status_code=422,
            detail="Solver did not converge. Try reducing amplitude or adjusting damping."
        )
    except Exception as e:
        logger.exception("Unhandled error in /simulate/half-car: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error. Request ID is in X-Request-ID header.")
