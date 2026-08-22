from fastapi import APIRouter, HTTPException, Depends, Request
import json
import asyncio
from sqlalchemy import update
import redis.asyncio as aioredis
from suspensionlab.shared.models import SweepRequest, JobResponse
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
import uuid
import time
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry.propagate import inject

router = APIRouter()

def perform_sweep_sync(payload_dict: dict) -> dict:
    import numpy as np
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
    
    res = payload_dict["grid_res"]
    ranges = {
        "Spring Rate (ks)": np.linspace(15000, 45000, res),
        "Damping (c)": np.linspace(1000, 4000, res),
        "Tire Stiffness (kt)": np.linspace(150000, 350000, res)
    }
    x_vals = ranges[payload_dict["var_x"]]
    y_vals = ranges[payload_dict["var_y"]]
    X, Y = np.meshgrid(x_vals, y_vals)
    Z = np.zeros_like(X)
    
    profile = RoadProfile(profile_type="step", amplitude=0.05)
    
    for i in range(res):
        for j in range(res):
            p = QuarterCarParams()
            if "Spring" in payload_dict["var_x"]: p.k_s = X[i, j]
            elif "Damping" in payload_dict["var_x"]: p.c = X[i, j]
            elif "Tire" in payload_dict["var_x"]: p.k_t = X[i, j]
            
            if "Spring" in payload_dict["var_y"]: p.k_s = Y[i, j]
            elif "Damping" in payload_dict["var_y"]: p.c = Y[i, j]
            elif "Tire" in payload_dict["var_y"]: p.k_t = Y[i, j]
            
            sim_res = run_quarter_car_analysis(p, profile)
            if payload_dict["objective"] == "Ride Comfort (ISO RMS)":
                Z[i, j] = sim_res.rms_body_accel_wk
            elif payload_dict["objective"] == "Grip (Tire RMS)":
                Z[i, j] = sim_res.rms_tire_load
            else:
                comfort_norm = sim_res.rms_body_accel_wk / 1.5
                grip_norm = sim_res.rms_tire_load / 1500.0
                travel_norm = sim_res.rms_susp_travel / 0.05
                Z[i, j] = (0.5 * comfort_norm) + (0.3 * grip_norm) + (0.2 * travel_norm)
    
    min_idx = np.unravel_index(np.argmin(Z), Z.shape)
    return {
        "X": X.tolist(), "Y": Y.tolist(), "Z": Z.tolist(),
        "min_x": float(X[min_idx]), "min_y": float(Y[min_idx]), "min_z": float(Z[min_idx])
    }

@router.post("/simulate/sweep", response_model=JobResponse, status_code=202)
async def simulate_sweep(payload: SweepRequest, request: Request, db: AsyncSession = Depends(get_db_dependency)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
        
    from suspensionlab.backend.services.quota import assert_can_run_job
    tier = getattr(request.state, "plan", "FREE")
    user_dict = {"user_id": user_id, "plan": tier}
    await assert_can_run_job(user_dict, db)

    from suspensionlab.backend.services.simulation_service import SimulationService
    try:
        job_id = await SimulationService.enqueue_simulation(
            user_id=user_id,
            plan=tier,
            job_type="SWEEP_QUARTER",
            payload=payload.model_dump(),
            db=db, team_id=getattr(user, "team_id", None)
        )
        return JobResponse(job_id=job_id, status="PENDING")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal simulation error.")
