from fastapi import APIRouter, HTTPException
import numpy as np
import asyncio
import logging
from suspensionlab.physics.exceptions import MathConvergenceError, PhysicsValidationError

logger = logging.getLogger(__name__)
from suspensionlab.shared.models import FullCarSimulateRequest, FullCarResultSchema
from suspensionlab.physics.full_car import FullCarParams, run_full_car_analysis, FourCornerRoadProfile

router = APIRouter()

@router.post("/simulate/full-car", response_model=FullCarResultSchema)
async def simulate_full_car(payload: FullCarSimulateRequest):
    try:
        pdump = payload.params.model_dump()
        asymmetry = pdump.pop("road_asymmetry", 0.3)
        pdump.pop("damper_curve_v_f", None)
        pdump.pop("damper_curve_f_f", None)
        pdump.pop("damper_curve_v_r", None)
        pdump.pop("damper_curve_f_r", None)
        
        params = FullCarParams(**pdump)
        
        from suspensionlab.physics.quarter_car import RoadProfile, _road_profile_fn
        base_profile = RoadProfile(**payload.profile.model_dump())
        
        # Generate the discrete arrays from the analytical profile
        zr_fn, _ = _road_profile_fn(base_profile)
        dt = 0.002
        time_array = np.arange(0.0, base_profile.duration, dt)
        
        # Front wheels hit bump at t
        z_road_f = np.array([float(zr_fn(np.array([t]))[0]) for t in time_array])
        
        # Rear wheels hit bump delayed by wheelbase / speed
        t_delay = params.L / params.speed_mps if params.speed_mps > 0 else 0.0
        z_road_r = np.array([float(zr_fn(np.array([t - t_delay]))[0]) if t - t_delay >= 0 else 0.0 for t in time_array])
        
        z_road_fr = z_road_f * asymmetry
        z_road_rr = z_road_r * asymmetry
        
        profile = FourCornerRoadProfile(
            time=time_array, 
            z_rfl=z_road_f, 
            z_rfr=z_road_fr, 
            z_rrl=z_road_r, 
            z_rrr=z_road_rr
        )
        
        result = await asyncio.to_thread(run_full_car_analysis, params, profile)
        
        result_dict = result.__dict__.copy()
        for key, value in result_dict.items():
            if isinstance(value, np.ndarray):
                result_dict[key] = value.tolist()
                
        return FullCarResultSchema(**result_dict)
    except (ValueError, PhysicsValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MathConvergenceError as e:
        raise HTTPException(
            status_code=422,
            detail="Solver did not converge. Try reducing amplitude or adjusting damping."
        )
    except Exception as e:
        logger.exception("Unhandled error in /simulate/full-car: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error. Request ID is in X-Request-ID header.")
