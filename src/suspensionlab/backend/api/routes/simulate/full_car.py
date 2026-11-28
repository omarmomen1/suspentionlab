from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import numpy as np

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, require_permission
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.core.compute_governance import bounded_run, assert_user_concurrency, meter_simulation
from suspensionlab.shared.models import FullCarSimulateRequest
from suspensionlab.physics.full_car import FullCarParams, run_full_car_analysis, FourCornerRoadProfile, FullCarDivergedError
from suspensionlab.physics.quarter_car import RoadProfile, _road_profile_fn
from typing import Any

router = APIRouter()
logger = logging.getLogger(__name__)

from suspensionlab.backend.workers.unified_worker import _serialize_for_json

def _serialize_numpy(obj):
    return _serialize_for_json(obj)

@router.post("/simulate/full-car")
async def simulate_full_car(
    payload: FullCarSimulateRequest,
    user: Any = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency)
):
    try:
        await assert_user_concurrency(db, str(user.user_id), getattr(user, "plan", "FREE"))
        # Pass B: record usage (Redis primary, DB fallback) so the meter reflects actual runs.
        await meter_simulation(db, str(user.user_id), str(getattr(user, "plan", "FREE")))
        pdump = payload.params.model_dump()
        # Wave 11 item 1: no silent 30% asymmetry. A default run is symmetric.
        asymmetry = pdump.pop("road_asymmetry", 1.0)
        if "lateral_accel_mps2" in pdump and "lateral_accel_g" not in pdump:
            pdump["lateral_accel_g"] = float(pdump.pop("lateral_accel_mps2")) / 9.81
        else:
            pdump.pop("lateral_accel_mps2", None)
        p = FullCarParams(**pdump)

        base_profile = RoadProfile(**payload.profile.model_dump())
        zr_fn, _ = _road_profile_fn(base_profile)
        dt = 0.002
        time_array = np.arange(0.0, base_profile.duration, dt)

        z_road_f = np.array([float(zr_fn(np.array([t]))[0]) for t in time_array])
        t_delay = p.L / p.speed_mps if p.speed_mps > 0 else 0.0
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
        raw_res = await bounded_run(run_full_car_analysis, p, profile, timeout=45.0, model="full_car")
        res_dict = _serialize_numpy(raw_res)
        # Wave 11 item 1: echo the excitation actually used so the page can show it.
        # Wave 11 item 2: state where roll and load transfer come from.
        meta = res_dict.get("metadata") if isinstance(res_dict.get("metadata"), dict) else {}
        meta.update({
            "road_asymmetry": float(asymmetry),
            "road_asymmetry_note": "Road asymmetry: {:.2f} (right = {:.0f}% of left)".format(
                float(asymmetry), float(asymmetry) * 100.0
            ),
            "lateral_g_source": "input",
            "lateral_g_model_note": (
                "Ride-and-attitude model: roll and load transfer are computed from the "
                "lateral g you enter here, not solved."
            ),
        })
        res_dict["metadata"] = meta
        res_dict["road_asymmetry"] = float(asymmetry)
        return res_dict
    except HTTPException:
        raise
    except FullCarDivergedError as e:
        # Numerical blow-up is a property of the submitted parameter set, not a
        # server fault: report a structured 422 instead of an unhandled 500.
        logger.warning("Full-car simulation diverged: %s", e)
        raise HTTPException(
            status_code=422,
            detail={"code": FullCarDivergedError.status, "message": str(e)},
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Full-car simulation timed out.")
    except Exception as e:
        logger.exception("Unhandled error in /simulate/full-car: %s", e)
        raise HTTPException(status_code=400, detail="Full-car simulation failed. Check the submitted parameters and try again.")
