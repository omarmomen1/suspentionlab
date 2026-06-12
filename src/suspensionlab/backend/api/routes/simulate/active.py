from fastapi import APIRouter, HTTPException
import asyncio
import logging
from suspensionlab.physics.exceptions import MathConvergenceError, PhysicsValidationError

logger = logging.getLogger(__name__)
from suspensionlab.shared.models import ActiveRequest, ActiveResultSchema
from suspensionlab.physics.active_quarter_car import ActiveQuarterCarParams, simulate_active_time_response
from suspensionlab.physics.quarter_car import QuarterCarParams, simulate_time_response, compute_metrics, RoadProfile

router = APIRouter()

@router.post("/simulate/active", response_model=ActiveResultSchema)
async def simulate_active(payload: ActiveRequest):
    try:
        p_active = ActiveQuarterCarParams(**payload.params.model_dump())
        profile = RoadProfile(profile_type="step", amplitude=payload.bump_height, duration=3.0)
        
        active_res = await asyncio.to_thread(simulate_active_time_response, p_active, profile)
        
        p_passive = QuarterCarParams(
            m_s=p_active.m_s, m_u=p_active.m_u, k_s=p_active.k_s, c=1500.0, k_t=p_active.k_t, MR=p_active.MR
        )
        passive_res = await asyncio.to_thread(simulate_time_response, p_passive, profile)
        passive_metrics = compute_metrics(passive_res, p_passive)
        
        return ActiveResultSchema(
            time=active_res.time.tolist(),
            active_ddz_s=active_res.ddz_s.tolist(),
            active_susp_travel=active_res.susp_travel.tolist(),
            active_rms_accel=active_res.rms_body_accel,
            passive_ddz_s=passive_res["ddz_s"].tolist(),
            passive_susp_travel=passive_res["susp_travel"].tolist(),
            passive_rms_accel=passive_metrics["rms_body_accel"]
        )
    except (ValueError, PhysicsValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MathConvergenceError as e:
        raise HTTPException(
            status_code=422,
            detail="Solver did not converge. Try reducing amplitude or adjusting damping."
        )
    except Exception as e:
        logger.exception("Unhandled error in /simulate/active: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error. Request ID is in X-Request-ID header.")
