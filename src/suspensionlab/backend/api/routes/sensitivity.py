"""
backend/api/routes/sensitivity.py
==================================
Revolutionary Feature: Parametric Sensitivity Analysis
=======================================================

Computes partial-derivative sensitivity of key KPIs (ride comfort, suspension travel,
transmissibility peak) to each input parameter by perturbing them ±δ% and computing
finite-difference gradients. Returns a ranked tornado chart dataset.

This is a production-grade feature that engineering teams use to:
  1. Identify which parameters dominate ride quality
  2. Prioritize tuning effort (high-sensitivity params first)
  3. Understand coupling between spring rate, damping, and tire stiffness

Solver: same BDF ODE as main simulator, run N_params×2 times in threadpool.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException

from suspensionlab.physics.exceptions import MathConvergenceError, PhysicsValidationError
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
from suspensionlab.shared.models import SimulateRequest

logger = logging.getLogger(__name__)
router = APIRouter()

_TIMEOUT_S = 180.0  # Sensitivity runs N_params×2 sims — allow longer


def _extract_kpis(result) -> dict[str, float]:
    """Extract the 4 KPIs used for sensitivity analysis."""
    return {
        "rms_body_accel_wk": float(result.rms_body_accel_wk or result.rms_body_accel),
        "rms_susp_travel":   float(result.rms_susp_travel * 1000),  # convert to mm
        "peak_transmissibility": float(result.peak_transmissibility),
        "rms_tire_load":     float(result.rms_tire_load),
    }


def _perturb_params(base: dict, key: str, delta: float) -> dict:
    """Return a copy of params dict with param `key` perturbed by `delta` fraction."""
    p = base.copy()
    p[key] = base[key] * (1.0 + delta)
    return p


async def _run_one(params_dict: dict, profile_dict: dict) -> dict[str, float]:
    """Run one simulation and return KPIs. Raises on failure."""
    params = QuarterCarParams(**params_dict)
    profile = RoadProfile(**profile_dict)
    result = await asyncio.wait_for(
        asyncio.to_thread(run_quarter_car_analysis, params, profile),
        timeout=60.0,
    )
    return _extract_kpis(result)


PARAMETER_LABELS = {
    "m_s":  "Sprung Mass (m_s)",
    "m_u":  "Unsprung Mass (m_u)",
    "k_s":  "Spring Rate (k_s)",
    "c":    "Damping (c)",
    "k_t":  "Tire Stiffness (k_t)",
    "MR":   "Motion Ratio (MR)",
}

DELTA = 0.10  # ±10% perturbation for finite difference


@router.post("/sensitivity")
async def sensitivity_analysis(payload: SimulateRequest) -> dict[str, Any]:
    """
    Parametric Sensitivity Analysis — Tornado Chart Data

    For each of the 6 physical parameters, runs two simulations at ±10% perturbation
    and computes the normalized sensitivity of each KPI:

        S_i = (KPI_+ - KPI_-) / (2 * DELTA * KPI_base)

    Returns ranked sensitivity bars for each KPI, ready for a tornado chart.
    """
    base_params_dict = payload.params.model_dump()
    profile_dict = payload.profile.model_dump()

    # Filter to numeric, tunable parameters only (exclude LUT arrays)
    tunable_keys = [k for k in PARAMETER_LABELS if k in base_params_dict and isinstance(base_params_dict[k], (int, float))]

    try:
        # Run baseline simulation
        base_kpis = await _run_one(base_params_dict, profile_dict)
    except (ValueError, PhysicsValidationError, MathConvergenceError) as e:
        raise HTTPException(status_code=422, detail=f"Baseline simulation failed: {e}")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Baseline simulation timed out.")

    # Run all perturbations concurrently (2 × N_params sims in parallel)
    perturb_tasks: list[tuple[str, float, asyncio.Task]] = []
    async with asyncio.TaskGroup() as tg:
        for key in tunable_keys:
            for sign, delta in [("+", +DELTA), ("-", -DELTA)]:
                p_dict = _perturb_params(base_params_dict, key, delta)
                # Validate mass constraint: m_u must be < m_s
                if "m_u" in p_dict and "m_s" in p_dict:
                    if p_dict["m_u"] >= p_dict["m_s"]:
                        continue  # Skip invalid perturbation
                task = tg.create_task(_run_one(p_dict, profile_dict))
                perturb_tasks.append((key, delta, task))

    # Collect results: map (key, sign) → KPIs
    results_map: dict[str, dict[float, dict[str, float]]] = {k: {} for k in tunable_keys}
    for key, delta, task in perturb_tasks:
        try:
            results_map[key][delta] = task.result()
        except Exception as e:
            logger.warning("Perturbation failed for %s delta=%.2f: %s", key, delta, e)
            results_map[key][delta] = base_kpis  # fallback: zero sensitivity

    # Compute normalized sensitivity for each param × KPI
    kpi_names = list(base_kpis.keys())
    sensitivities: list[dict] = []

    for key in tunable_keys:
        kpi_high = results_map[key].get(+DELTA, base_kpis)
        kpi_low  = results_map[key].get(-DELTA, base_kpis)
        param_sensitivities: dict[str, float] = {}
        for kpi in kpi_names:
            base_val = base_kpis[kpi]
            if abs(base_val) < 1e-10:
                param_sensitivities[kpi] = 0.0
            else:
                # Central finite difference normalized sensitivity
                param_sensitivities[kpi] = (kpi_high[kpi] - kpi_low[kpi]) / (2.0 * DELTA * base_val)

        sensitivities.append({
            "param_key":   key,
            "param_label": PARAMETER_LABELS[key],
            "sensitivity": param_sensitivities,
            # Composite magnitude for ranking (RMS of all KPI sensitivities)
            "magnitude":   float(np.sqrt(np.mean([v**2 for v in param_sensitivities.values()]))),
        })

    # Sort by magnitude descending (most impactful parameter first)
    sensitivities.sort(key=lambda x: x["magnitude"], reverse=True)

    return {
        "base_kpis":       base_kpis,
        "kpi_labels": {
            "rms_body_accel_wk":    "Wk RMS Accel (m/s²)",
            "rms_susp_travel":      "RMS Susp Travel (mm)",
            "peak_transmissibility": "Peak TX (–)",
            "rms_tire_load":        "RMS Tire Load (N)",
        },
        "sensitivities":   sensitivities,
        "perturbation_pct": DELTA * 100,
        "n_simulations":   len(perturb_tasks) + 1,
    }
