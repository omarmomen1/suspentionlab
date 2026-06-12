from fastapi import APIRouter, HTTPException
import numpy as np
import asyncio
import hashlib
import json
import logging
from suspensionlab.physics.exceptions import MathConvergenceError, PhysicsValidationError

logger = logging.getLogger(__name__)
from suspensionlab.shared.models import SimulateRequest, QuarterCarResultSchema
from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis
)

router = APIRouter()

# Maximum allowed simulation wall-clock time (seconds)
_SIMULATION_TIMEOUT_S = 120.0


@router.post("/simulate", response_model=QuarterCarResultSchema)
async def simulate(payload: SimulateRequest):
    try:
        # Convert request models to physics dataclasses
        params = QuarterCarParams(**payload.params.model_dump())
        profile = RoadProfile(**payload.profile.model_dump())

        # Compute params integrity hash (ARCH-02) — bind result to input
        params_raw = json.dumps(payload.params.model_dump(), sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_raw.encode()).hexdigest()[:16]

        # Run simulation off the main event loop to prevent blocking under load.
        # Hard timeout prevents degenerate parameter sets from running forever.
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(run_quarter_car_analysis, params, profile),
                timeout=_SIMULATION_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Simulation timed out after %.0fs for params_hash=%s",
                _SIMULATION_TIMEOUT_S, params_hash
            )
            raise HTTPException(
                status_code=504,
                detail=f"Simulation timed out after {int(_SIMULATION_TIMEOUT_S)}s. "
                       "Reduce duration or simplify road profile.",
            )

        # Convert dataclass to dict and handle numpy arrays
        result_dict = result.__dict__.copy()

        for key, value in result_dict.items():
            if isinstance(value, np.ndarray):
                result_dict[key] = value.tolist()

        # Attach integrity hash
        result_dict["params_hash"] = params_hash

        return QuarterCarResultSchema(**result_dict)

    except (ValueError, PhysicsValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MathConvergenceError as e:
        raise HTTPException(
            status_code=422,
            detail="Solver did not converge. Try reducing amplitude or adjusting damping."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in /simulate/quarter-car: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error. Request ID is in X-Request-ID header.")
