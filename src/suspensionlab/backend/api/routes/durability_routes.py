"""
Road Durability Analyzer — ISO 8608 Road Profile Generator + Fatigue Life Calculator
Uses pure numpy/scipy math (already installed). Zero extra cost.
Implements: ISO 2631-1 VDV, Palmgren-Miner fatigue rule, component life predictions.
"""
from __future__ import annotations
import numpy as np
import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.services.simulation_service import SimulationService
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulate", tags=["durability"])

# ISO 8608 road roughness coefficient Gd (m^3/cycle) per road class
# Based on Table 1 of ISO 8608:2016
ISO_8608_Gd = {
    "A": 16e-6,    # Perfect highway
    "B": 64e-6,    # Good highway
    "C": 256e-6,   # Average road
    "D": 1024e-6,  # Poor road
    "E": 4096e-6,  # Very poor road
    "F": 16384e-6, # Off-road track
    "G": 65536e-6, # Rough off-road
    "H": 262144e-6,# Extreme terrain
}

ISO_8608_LABELS = {
    "A": "Perfect Highway",
    "B": "Good Highway",
    "C": "Average Road",
    "D": "Poor Road",
    "E": "Very Poor Road",
    "F": "Off-Road Track",
    "G": "Rough Off-Road",
    "H": "Extreme Terrain",
}

# Wave 18: the ranking index saturates here and is labeled ">= max".
MAX_LIFE_INDEX = 1_000_000.0

LIFE_INDEX_DISCLAIMER = (
    "Ranking only: generic S-N exponents (shock 3.5, spring 8, bushings 2.5, bearing 3.0) with body "
    "acceleration as the load proxy. Not a predicted service life. Valid for comparing setups on the "
    "same road class and speed."
)

# Component fatigue SN-curve slope (Wöhler exponent m)
# and reference stress/load for each component
COMPONENT_DATA = {
    "shock_absorber": {"m": 3.5, "ref_cycles": 5_000_000, "ref_rms": 0.5},
    "coil_spring":    {"m": 8.0, "ref_cycles": 10_000_000, "ref_rms": 0.3},
    "bushings":       {"m": 2.5, "ref_cycles": 2_000_000,  "ref_rms": 0.4},
    "wheel_bearing":  {"m": 3.0, "ref_cycles": 8_000_000,  "ref_rms": 0.6},
}


class DurabilityRequest(BaseModel):
    road_class: Literal["A", "B", "C", "D", "E", "F", "G", "H"] = "C"
    speed_kph: float = Field(default=80.0, ge=10.0, le=200.0)
    # Quarter-car params
    m_s: float = Field(default=300.0, gt=10.0, le=5000.0)
    m_u: float = Field(default=35.0, gt=1.0, le=500.0)
    k_s: float = Field(default=25000.0, gt=100.0, le=500000.0)
    c: float = Field(default=2050.0, ge=0.0, le=50000.0)
    k_t: float = Field(default=200000.0, gt=10000.0, le=1000000.0)
    MR: float = Field(default=0.85, gt=0.1, le=1.5)


class ComponentLifeResult(BaseModel):
    name: str
    display_name: str
    # Wave 18: this is a relative ranking index, not a predicted service life.
    life_index: float
    life_index_label: str
    # Deprecated alias kept for one release; same number, no longer a km claim.
    life_km: float
    life_label: str
    condition: str  # "Excellent" | "Good" | "Fair" | "Poor" | "Critical"
    condition_color: str


class DurabilityResult(BaseModel):
    road_class: str
    road_label: str
    speed_kph: float
    # Metrics
    rms_body_accel: float
    rms_body_accel_wk: float
    vdv: float  # Vibration Dose Value [m/s^1.75]
    peak_susp_travel_mm: float
    rms_susp_travel_mm: float
    rms_tire_load_n: float
    # Scores
    durability_score: int   # 0-100
    comfort_rating: str
    iso_2631_class: str
    # Component life
    components: list[ComponentLifeResult]
    # Summary
    summary: str
    worst_component: str
    # Wave 18: the limiting figure is a ranking index, not a distance.
    best_range_index: float
    # Deprecated alias kept for one release.
    best_range_km: float
    life_index_disclaimer: str
    life_index_unit: str


def _compute_durability(req: DurabilityRequest) -> DurabilityResult:
    """Run physics simulation and compute all durability metrics."""
    speed_mps = req.speed_kph / 3.6

    params = QuarterCarParams(
        m_s=req.m_s, m_u=req.m_u, k_s=req.k_s,
        c=req.c, k_t=req.k_t, MR=req.MR, c_t=0.0
    )
    # Use ISO 8608 profile with the selected class
    profile = RoadProfile(
        profile_type="iso8608",
        iso_class=req.road_class,
        amplitude=0.05,
        frequency=2.0,
        duration=20.0,
        speed_mps=speed_mps,
    )

    result = run_quarter_car_analysis(params, profile)

    rms_accel = result.rms_body_accel
    rms_accel_wk = result.rms_body_accel_wk
    rms_susp = result.rms_susp_travel
    rms_tire = result.rms_tire_load
    peak_susp = result.peak_susp_travel

    # VDV: Vibration Dose Value = (integral of a(t)^4 dt)^0.25
    # Approximate from RMS: VDV ≈ rms_accel_wk * (duration^0.25) * 1.4
    duration = 20.0
    vdv = rms_accel_wk * (duration ** 0.25) * 1.4

    # ISO 2631-1 comfort classification based on Wk-weighted RMS
    if rms_accel_wk < 0.315:
        iso_class = "Not uncomfortable"
        comfort = "Excellent"
    elif rms_accel_wk < 0.5:
        iso_class = "A little uncomfortable"
        comfort = "Good"
    elif rms_accel_wk < 0.8:
        iso_class = "Fairly uncomfortable"
        comfort = "Fair"
    elif rms_accel_wk < 1.25:
        iso_class = "Uncomfortable"
        comfort = "Poor"
    elif rms_accel_wk < 2.0:
        iso_class = "Very uncomfortable"
        comfort = "Bad"
    else:
        iso_class = "Extremely uncomfortable"
        comfort = "Critical"

    # Durability score 0-100 (100 = perfectly tuned for the road)
    # Penalise for: high body accel, excessive susp travel, high tire load variation
    accel_score = max(0, 100 - rms_accel * 40)
    susp_score  = max(0, 100 - rms_susp * 3000)
    tire_score  = max(0, 100 - rms_tire / 100)
    durability_score = int(round((accel_score * 0.4 + susp_score * 0.3 + tire_score * 0.3)))
    durability_score = max(0, min(100, durability_score))

    # Component life predictions using Palmgren-Miner rule
    # Life = ref_cycles * (ref_rms / current_rms)^m  cycles → convert to km
    # Assume 1 cycle ≈ 1 m of road at given speed for normalization
    components: list[ComponentLifeResult] = []
    worst_km = float("inf")
    worst_name = ""

    for comp_key, data in COMPONENT_DATA.items():
        m = data["m"]
        ref_cycles = data["ref_cycles"]
        ref_rms = data["ref_rms"]

        # Use rms_body_accel as the loading proxy (normalized)
        current_rms = max(rms_accel, 0.001)
        life_cycles = ref_cycles * ((ref_rms / current_rms) ** m)

        # Convert to km: 1 cycle ≈ speed_mps / (dominant_freq ≈ 2 Hz) meters
        meters_per_cycle = speed_mps / max(result.f_n_s, 0.1)
        life_km = (life_cycles * meters_per_cycle) / 1000.0
        # Wave 18 item 3: cap at a labeled maximum instead of printing a suspicious 999,999.
        life_index = min(life_km, MAX_LIFE_INDEX)
        capped = life_km >= MAX_LIFE_INDEX
        life_km = life_index

        if life_km < worst_km:
            worst_km = life_km
            worst_name = comp_key

        # Condition classification
        if life_km > 100_000:
            condition, color = "Excellent", "#22c55e"
        elif life_km > 50_000:
            condition, color = "Good", "#84cc16"
        elif life_km > 25_000:
            condition, color = "Fair", "#eab308"
        elif life_km > 10_000:
            condition, color = "Poor", "#f97316"
        else:
            condition, color = "Critical", "#ef4444"

        if capped:
            life_label = ">= max"
        elif life_index >= 1000:
            life_label = f"index {life_index/1000:.0f}k"
        else:
            life_label = f"index {life_index:.0f}"

        display_names = {
            "shock_absorber": "Shock Absorber",
            "coil_spring": "Coil Spring",
            "bushings": "Rubber Bushings",
            "wheel_bearing": "Wheel Bearing",
        }

        components.append(ComponentLifeResult(
            name=comp_key,
            display_name=display_names[comp_key],
            life_index=round(life_index, 1),
            life_index_label=life_label,
            life_km=round(life_km, 1),
            life_label=life_label,
            condition=condition,
            condition_color=color,
        ))

    # Sort by life ascending (most critical first)
    components.sort(key=lambda x: x.life_km)

    road_label = ISO_8608_LABELS[req.road_class]
    best_range_km = min(c.life_km for c in components)

    summary = (
        f"On {road_label} at {req.speed_kph:.0f} km/h, this suspension scores {durability_score}/100. "
        f"ISO 2631-1 comfort: '{iso_class}'. "
        f"Most critical component: {components[0].display_name} (~{components[0].life_label}). "
    )
    if durability_score >= 70:
        summary += "The setup is well-matched to this road type."
    elif durability_score >= 40:
        summary += "Consider increasing damping or reducing spring stiffness for this road type."
    else:
        summary += "This suspension is significantly mismatched for this road. Major retuning recommended."

    return DurabilityResult(
        road_class=req.road_class,
        road_label=road_label,
        speed_kph=req.speed_kph,
        rms_body_accel=round(rms_accel, 4),
        rms_body_accel_wk=round(rms_accel_wk, 4),
        vdv=round(vdv, 4),
        peak_susp_travel_mm=round(peak_susp * 1000, 2),
        rms_susp_travel_mm=round(rms_susp * 1000, 2),
        rms_tire_load_n=round(rms_tire, 1),
        durability_score=durability_score,
        comfort_rating=comfort,
        iso_2631_class=iso_class,
        components=components,
        summary=summary,
        worst_component=components[0].display_name,
        best_range_index=round(best_range_km, 1),
        # Deprecated alias kept for one release.
        best_range_km=round(best_range_km, 1),
        life_index_disclaimer=LIFE_INDEX_DISCLAIMER,
        life_index_unit="relative index (higher = longer life)",
    )


@router.post("/durability", response_model=DurabilityResult)
async def road_durability_analysis(req: DurabilityRequest):
    """
    ISO 8608 Road Profile Durability Analyzer.
    Generates realistic stochastic road profiles and calculates:
    - Component fatigue ranking index (relative, not a predicted service life)
    - ISO 2631-1 vibration comfort classification
    - Vibration Dose Value (VDV)
    - Overall suspension durability score (0-100)
    """
    try:
        result = await asyncio.to_thread(_compute_durability, req)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Durability analysis error: %s", e)
        raise HTTPException(status_code=500, detail="Durability analysis failed.")


class JobResponse(BaseModel):
    job_id: str
    status: str


@router.post("/durability/async", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def road_durability_analysis_async(
    req: DurabilityRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Asynchronous ISO 8608 Road Profile Durability Analyzer.
    Enqueues durability computation to background RQ worker.
    """
    try:
        user_id = getattr(user, "user_id", str(user.get("user_id") if isinstance(user, dict) else user))
        plan = getattr(user, "plan", user.get("plan", "PRO") if isinstance(user, dict) else "PRO")
        team_id = getattr(user, "team_id", user.get("team_id", None) if isinstance(user, dict) else None)
        job_id = await SimulationService.enqueue_simulation(
            user_id=user_id,
            plan=plan,
            job_type="SIMULATE_DURABILITY",
            payload=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            db=db,
            team_id=team_id,
        )
        return {"job_id": job_id, "status": "PENDING"}
    except Exception as e:
        logger.exception("Failed to enqueue durability job: %s", e)
        raise HTTPException(status_code=500, detail="Failed to enqueue durability analysis.")

