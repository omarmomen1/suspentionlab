import os

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Create monte_carlo.py
mc_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\simulate\monte_carlo.py")
mc_content = """from fastapi import APIRouter, HTTPException, Depends, Request
import json
import asyncio
from sqlalchemy import update
import redis.asyncio as aioredis
from suspensionlab.shared.models import JobResponse, MonteCarloRequest
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry.propagate import inject

router = APIRouter()

@router.post("/simulate/monte-carlo", response_model=JobResponse)
async def simulate_monte_carlo(payload: MonteCarloRequest, request: Request, db: AsyncSession = Depends(get_db_dependency)):
    from suspensionlab.backend.workers.unified_worker import run_job
    from suspensionlab.backend.api.routes.optimize import job_queue, redis_conn, RedisUnavailableError
    from rq import Retry
    import redis
    
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")

    job_id = str(uuid.uuid4())
    
    job_record = JobRecord(
        id=job_id,
        user_id=uuid.UUID(user_id),
        job_type="MONTE_CARLO_QUARTER",
        status="PENDING",
    )
    db.add(job_record)
    await db.commit()

    trace_carrier = {}
    inject(trace_carrier)

    res_data = {"job_id": job_id, "status": "PENDING", "user_id": user_id, "result": None, "error": None}
    await asyncio.to_thread(redis_conn.setex, f"job_status:{job_id}", 86400, json.dumps(res_data))

    try:
        job = await asyncio.to_thread(
            job_queue.enqueue,
            run_job,
            args=(job_id, payload.model_dump(), trace_carrier),
            job_id=job_id,
            result_ttl=86400,
            failure_ttl=86400,
            retry=Retry(max=3, interval=[10, 30, 60])
        )
    except redis.exceptions.ConnectionError:
        await db.execute(
            update(JobRecord)
            .where(JobRecord.id == job_id)
            .values(status="FAILED", error="Redis enqueue failed. Compute plane unavailable.")
        )
        await db.commit()
        try:
            redis_conn.delete(f"job_status:{job_id}")
        except redis.exceptions.ConnectionError:
            pass
        raise HTTPException(status_code=503, detail="Queue unavailable.")
    
    return JobResponse(job_id=job.id, status="PENDING")
"""
with open(mc_path, "w", encoding="utf-8") as f:
    f.write(mc_content)

# 2. Update __init__.py for simulate routes
init_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\simulate\__init__.py")
with open(init_path, "r", encoding="utf-8") as f:
    init_content = f.read()

init_content = init_content.replace("from .sweep import router as sweep_router", "from .sweep import router as sweep_router\nfrom .monte_carlo import router as mc_router")
init_content = init_content.replace("router.include_router(sweep_router)", "router.include_router(sweep_router)\nrouter.include_router(mc_router)")
with open(init_path, "w", encoding="utf-8") as f:
    f.write(init_content)

# 3. Update unified_worker.py
worker_path = os.path.join(project_dir, r"src\suspensionlab\backend\workers\unified_worker.py")
with open(worker_path, "r", encoding="utf-8") as f:
    worker_content = f.read()

mc_worker_logic = """
def perform_monte_carlo_sync(payload_dict: dict) -> dict:
    import numpy as np
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
    
    iters = payload_dict["iterations"]
    tol = payload_dict["tolerance_pct"] / 100.0
    
    p_dict = payload_dict["params"]
    base_ks = p_dict.get("k_s", 25000.0)
    base_c = p_dict.get("c", 2050.0)
    base_kt = p_dict.get("k_t", 200000.0)
    
    # Generate samples
    ks_samples = np.random.normal(base_ks, base_ks * tol, iters)
    c_samples = np.random.normal(base_c, base_c * tol, iters)
    kt_samples = np.random.normal(base_kt, base_kt * tol, iters)
    
    profile = RoadProfile(**payload_dict["profile"])
    
    body_accel_list = []
    tire_load_list = []
    
    for i in range(iters):
        p = QuarterCarParams(**p_dict)
        p.k_s = max(1000, ks_samples[i])
        p.c = max(100, c_samples[i])
        p.k_t = max(10000, kt_samples[i])
        
        sim_res = run_quarter_car_analysis(p, profile)
        body_accel_list.append(sim_res.rms_body_accel_wk)
        tire_load_list.append(sim_res.rms_tire_load)
        
    mean_body = float(np.mean(body_accel_list))
    std_body = float(np.std(body_accel_list))
    p95_body = float(np.percentile(body_accel_list, 95))
    
    mean_tire = float(np.mean(tire_load_list))
    std_tire = float(np.std(tire_load_list))
    
    return {
        "iterations": iters,
        "tolerance_pct": payload_dict["tolerance_pct"],
        "mean_rms_body_accel_wk": mean_body,
        "std_rms_body_accel_wk": std_body,
        "p95_rms_body_accel_wk": p95_body,
        "mean_rms_tire_load": mean_tire,
        "std_rms_tire_load": std_tire
    }
"""

if "def perform_monte_carlo_sync" not in worker_content:
    worker_content += mc_worker_logic

old_worker_route = """                elif job_type == "SWEEP_QUARTER":
                    from suspensionlab.backend.api.routes.simulate.sweep import perform_sweep_sync
                    res = await asyncio.to_thread(perform_sweep_sync, payload)"""

new_worker_route = """                elif job_type == "SWEEP_QUARTER":
                    from suspensionlab.backend.api.routes.simulate.sweep import perform_sweep_sync
                    res = await asyncio.to_thread(perform_sweep_sync, payload)
                    
                elif job_type == "MONTE_CARLO_QUARTER":
                    res = await asyncio.to_thread(perform_monte_carlo_sync, payload)"""

worker_content = worker_content.replace(old_worker_route, new_worker_route)

with open(worker_path, "w", encoding="utf-8") as f:
    f.write(worker_content)

# 4. Rewrite cae_exporter.py
cae_path = os.path.join(project_dir, r"src\suspensionlab\backend\services\cae_exporter.py")
with open(cae_path, "r", encoding="utf-8") as f:
    cae_content = f.read()

import re
old_adams = re.search(r"def export_quarter_car_to_adams\(.*?\).*?return adm_content", cae_content, flags=re.DOTALL).group(0)

new_adams = """def export_quarter_car_to_adams(params: QuarterCarParams, filename: str = "quarter_car_export.adm") -> str:
    \"\"\"
    Generates a realistic, valid MSC ADAMS (.adm) file for the Quarter Car model.
    \"\"\"
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    adm_content = f\"\"\"! MSC.ADAMS/Solver Dataset
! Generated by SuspensionLab PRO MAX (Enterprise)
! Timestamp: {now}

ADAMS/View model name: Quarter_Car_Rig
!
UNITS/ FORCE=NEWTON, MASS=KILOGRAM, LENGTH=METER, TIME=SECOND
!
!----------------------------------- PARTS -------------------------------------
!
PART/1, GROUND
!
PART/2, MASS={params.m_s}, CM=201, IP=201, 1, 1
! Sprung Mass
!
PART/3, MASS={params.m_u}, CM=301, IP=301, 1, 1
! Unsprung Mass (Wheel Assembly)
!
!---------------------------------- MARKERS ------------------------------------
!
MARKER/201, PART = 2, QP = 0, 0.5, 0
MARKER/301, PART = 3, QP = 0, 0.25, 0
MARKER/101, PART = 1, QP = 0, 0, 0
!
!----------------------------------- JOINTS ------------------------------------
!
JOINT/1, TRANSLATIONAL, I = 201, J = 101
JOINT/2, TRANSLATIONAL, I = 301, J = 101
!
!----------------------------------- FORCES ------------------------------------
!
! Suspension Spring & Damper
SFORCE/1, TRANSLATIONAL, I = 201, J = 301, ACTIONONLY
, FUNCTION = {-params.k_w} * (DZ(201,301)) - {params.c} * (VZ(201,301))
!
! Tire Spring
SFORCE/2, TRANSLATIONAL, I = 301, J = 101, ACTIONONLY
, FUNCTION = {-params.k_t} * (DZ(301,101))
!
!----------------------------------- RESULTS -----------------------------------
!
REQUEST/1, DISPLACEMENT, I=201, J=101, RM=101
REQUEST/2, ACCELERATION, I=201, J=101, RM=101
!
END
\"\"\"
    return adm_content"""

cae_content = cae_content.replace(old_adams, new_adams)

with open(cae_path, "w", encoding="utf-8") as f:
    f.write(cae_content)

print("Monte carlo and CAE refactored.")
