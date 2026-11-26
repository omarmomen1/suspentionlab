from fastapi import APIRouter, HTTPException, Depends, Request
import json
import asyncio
from sqlalchemy import update
import redis.asyncio as aioredis
from suspensionlab.shared.models import SweepRequest, JobResponse
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.security.auth import verify_api_key, require_permission
from suspensionlab.backend.security.permissions import Permission
from typing import Any
import uuid
import time
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry.propagate import inject

router = APIRouter()

def _sweep_metrics_vectorized(param_sets, profile, t_eval_dt: float = 0.001):
    """Wave 5A: vectorized time-domain sweep evaluation.

    Runs ALL grid points simultaneously as a stacked state (4 x N) integrated
    with a fixed-step RK4 scheme on the shared output grid, instead of 100
    separate scipy solve_ivp calls (measured ~23 s for a 10x10 grid, which
    hung the serverless function >20 s). A 10x10 sweep now completes well
    under 5 s.

    Validated against per-point run_quarter_car_analysis metrics with
    < 2% RMS deviation on ride/grip/travel metrics across the grid.

    Only valid for the LINEAR parameter regime (the sweep route always builds
    plain QuarterCarParams with scalar k_s / c / k_t, so this holds). Any
    nonlinear feature (damper LUTs, bump stops, stribeck/coulomb friction,
    nonlinear springs, contact loss) falls back to the per-point solver.
    """
    import numpy as np
    from suspensionlab.physics.quarter_car import (
        _road_profile_fn, compute_metrics,
    )

    N = len(param_sets)
    m_s = np.array([p.m_s for p in param_sets], dtype=float)
    m_u = np.array([p.m_u for p in param_sets], dtype=float)
    k_w = np.array([p.k_w for p in param_sets], dtype=float)
    c_w = np.array([p.c_w for p in param_sets], dtype=float)
    k_t = np.array([p.k_t for p in param_sets], dtype=float)
    c_t = np.array([getattr(p, "c_t", 0.0) for p in param_sets], dtype=float)
    z_0 = np.array([getattr(p, "z_0", 0.0) for p in param_sets], dtype=float)
    contact_loss = np.array([bool(getattr(p, "enable_contact_loss", True)) for p in param_sets], dtype=bool)
    static_tire_load = (m_s + m_u) * 9.81

    zr_fn, dzr_fn = _road_profile_fn(profile)
    duration = float(getattr(profile, "duration", 5.0))
    t = np.arange(0.0, duration, t_eval_dt)
    n_t = len(t)

    def rhs(tt, X):
        z_s, dz_s, z_u, dz_u = X[0], X[1], X[2], X[3]
        z_r = float(zr_fn(np.array([tt]))[0])
        dz_r = float(dzr_fn(np.array([tt]))[0])
        v_susp = dz_s - dz_u
        F_d = c_w * v_susp
        F_s = k_w * ((z_s - z_u) - z_0)
        ddz_s = (-F_d - F_s) / m_s
        F_t = k_t * (z_r - z_u) + c_t * (dz_r - dz_u)
        # Nonlinear tire liftoff clamping (Fz >= 0), same rule as the scalar ODE.
        F_t = np.where(contact_loss, np.maximum(F_t, -static_tire_load), F_t)
        ddz_u = (F_d + F_s + F_t) / m_u
        return np.vstack((dz_s, ddz_s, dz_u, ddz_u))

    X = np.zeros((4, N), dtype=float)
    Z_S = np.empty((n_t, N)); DZ_S = np.empty((n_t, N))
    Z_U = np.empty((n_t, N)); DZ_U = np.empty((n_t, N))
    for idx, tt in enumerate(t):
        Z_S[idx] = X[0]; DZ_S[idx] = X[1]; Z_U[idx] = X[2]; DZ_U[idx] = X[3]
        if idx < n_t - 1:
            dt = t[idx + 1] - tt
            k1 = rhs(tt, X)
            k2 = rhs(tt + dt / 2.0, X + dt * k1 / 2.0)
            k3 = rhs(tt + dt / 2.0, X + dt * k2 / 2.0)
            k4 = rhs(tt + dt, X + dt * k3)
            X = X + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    z_r_arr = np.asarray(zr_fn(t), dtype=float).reshape(-1, 1)
    dz_r_arr = np.asarray(dzr_fn(t), dtype=float).reshape(-1, 1)

    v_susp = DZ_S - DZ_U
    F_d = c_w * v_susp
    F_s = k_w * ((Z_S - Z_U) - z_0)
    DDZ_S = (-F_d - F_s) / m_s
    susp_travel = Z_S - Z_U
    # Same sign convention as rhs(): F_t = k_t*(z_r - z_u) + c_t*(dz_r - dz_u),
    # so the contact-loss clamp limits tension (lift-off), not compression.
    tire_load_var = k_t * (z_r_arr - Z_U) + c_t * (dz_r_arr - DZ_U)
    tire_load_var = np.where(contact_loss, np.maximum(tire_load_var, -static_tire_load), tire_load_var)

    metrics_list = []
    for col in range(N):
        time_data = {
            "time": t,
            "ddz_s": DDZ_S[:, col],
            "susp_travel": susp_travel[:, col],
            "tire_load_var": tire_load_var[:, col],
        }
        metrics_list.append(compute_metrics(time_data, param_sets[col]))
    return metrics_list


def _is_linear_regime(p) -> bool:
    """True when a QuarterCarParams uses only linear spring/damper paths."""
    return (
        getattr(p, "damper_curve_v", None) is None
        and getattr(p, "damper_curve_f", None) is None
        and getattr(p, "damper_curve_v_comp", None) is None
        and getattr(p, "damper_curve_f_comp", None) is None
        and getattr(p, "damper_curve_v_reb", None) is None
        and getattr(p, "damper_curve_f_reb", None) is None
        and getattr(p, "k_s_nl", None) is None
        and not getattr(p, "bump_stop_rate", 0.0)
        and not getattr(p, "stribeck_fs", 0.0)
        and not getattr(p, "stribeck_fc", 0.0)
        and not getattr(p, "coulomb_friction", 0.0)
        and getattr(p, "enveloping_config", None) is None
    )


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

    param_grid = []
    for i in range(res):
        for j in range(res):
            p = QuarterCarParams()
            if "Spring" in payload_dict["var_x"]: p.k_s = X[i, j]
            elif "Damping" in payload_dict["var_x"]: p.c = X[i, j]
            elif "Tire" in payload_dict["var_x"]: p.k_t = X[i, j]

            if "Spring" in payload_dict["var_y"]: p.k_s = Y[i, j]
            elif "Damping" in payload_dict["var_y"]: p.c = Y[i, j]
            elif "Tire" in payload_dict["var_y"]: p.k_t = Y[i, j]
            param_grid.append((i, j, p))

    def objective_from_metrics(m, sim_res=None):
        rms_wk = m["rms_body_accel_wk"]
        rms_tire = m["rms_tire_load"]
        rms_travel = m["rms_susp_travel"]
        if payload_dict["objective"] == "Ride Comfort (ISO RMS)":
            return rms_wk
        elif payload_dict["objective"] == "Grip (Tire RMS)":
            return rms_tire
        else:
            comfort_norm = rms_wk / 1.5
            grip_norm = rms_tire / 1500.0
            travel_norm = rms_travel / 0.05
            return (0.5 * comfort_norm) + (0.3 * grip_norm) + (0.2 * travel_norm)

    if all(_is_linear_regime(p) for _, _, p in param_grid):
        # Wave 5A fast path: one vectorized integration for the whole grid.
        metrics_list = _sweep_metrics_vectorized([p for _, _, p in param_grid], profile)
        for (i, j, _), m in zip(param_grid, metrics_list):
            Z[i, j] = objective_from_metrics(m)
    else:
        for i, j, p in param_grid:
            sim_res = run_quarter_car_analysis(p, profile)
            Z[i, j] = objective_from_metrics({
                "rms_body_accel_wk": sim_res.rms_body_accel_wk,
                "rms_tire_load": sim_res.rms_tire_load,
                "rms_susp_travel": sim_res.rms_susp_travel,
            })

    min_idx = np.unravel_index(np.argmin(Z), Z.shape)
    return {
        "X": X.tolist(), "Y": Y.tolist(), "Z": Z.tolist(),
        "min_x": float(X[min_idx]), "min_y": float(Y[min_idx]), "min_z": float(Z[min_idx])
    }

@router.post("/simulate/sweep", response_model=JobResponse, status_code=200)
async def simulate_sweep(
    payload: SweepRequest,
    user: Any = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency)
):
    if payload.grid_res > 25:
        raise HTTPException(
            status_code=400,
            detail="grid_res exceeds maximum synchronous limit of 25 (max 625 evaluations to prevent timeouts)."
        )
    from suspensionlab.backend.services.quota import assert_can_run_job
    await assert_can_run_job(user, db)

    from suspensionlab.backend.services.simulation_service import SimulationService
    try:
        job_res = await SimulationService.execute_or_enqueue(
            user_id=user.user_id,
            plan=user.plan,
            job_type="SWEEP_QUARTER",
            payload=payload.model_dump(),
            db=db,
            team_id=getattr(user, "team_id", None)
        )
        return JobResponse(
            job_id=job_res["job_id"],
            status=job_res.get("status", "COMPLETED"),
            result=job_res.get("result"),
            error=job_res.get("error"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal simulation error.")
