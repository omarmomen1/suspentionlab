from fastapi import APIRouter, HTTPException
import numpy as np
import asyncio
import logging
from suspensionlab.physics.exceptions import MathConvergenceError, PhysicsValidationError

logger = logging.getLogger(__name__)
from suspensionlab.shared.models import HandlingRequest, HandlingResultSchema
from suspensionlab.physics.handling_model import HandlingParams, simulate_maneuver

router = APIRouter()

@router.post("/simulate/handling", response_model=HandlingResultSchema)
async def simulate_handling(payload: HandlingRequest):
    try:
        pdump = payload.params.model_dump()
        if pdump.get("tire_coeffs"):
            from suspensionlab.physics.magic_formula import TireCoeffs
            pdump["tire_coeffs"] = TireCoeffs(**pdump["tire_coeffs"])
        else:
            pdump.pop("tire_coeffs", None)
        params = HandlingParams(**pdump)
        v_init = payload.v_init_kph / 3.6
        
        if payload.maneuver_type == "Step Steer (J-Turn)":
            def steer(t): return 0.05 if t > 1.0 else 0.0
            def throttle(t): return 0.0
            def brake(t): return 0.0
            duration = 5.0
        elif payload.maneuver_type == "Sine Sweep (Slalom)":
            def steer(t): return 0.04 * np.sin(2 * np.pi * 0.5 * t) if t > 1.0 else 0.0
            def throttle(t): return 0.2
            def brake(t): return 0.0
            duration = 8.0
        elif payload.maneuver_type == "Constant Radius Cornering":
            def steer(t): return 0.03 * (t/2.0 if t < 2.0 else 1.0)
            def throttle(t): return 0.4
            def brake(t): return 0.0
            duration = 10.0
        else: # Brake in Turn
            def steer(t): return 0.03 if t > 1.0 else 0.0
            def throttle(t): return 0.0
            def brake(t): return 0.8 if t > 3.0 else 0.0
            duration = 6.0
            
        res = await asyncio.to_thread(simulate_maneuver, params, v_init, steer, throttle, brake, duration)
        
        for k, v in res.items():
            if isinstance(v, np.ndarray):
                res[k] = v.tolist()
                
        return HandlingResultSchema(**res)
    except (ValueError, PhysicsValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MathConvergenceError as e:
        raise HTTPException(
            status_code=422,
            detail="Solver did not converge. Try reducing amplitude or adjusting damping."
        )
    except Exception as e:
        logger.exception("Unhandled error in /simulate/handling: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error. Request ID is in X-Request-ID header.")
