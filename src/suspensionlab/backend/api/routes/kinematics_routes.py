"""
backend/api/routes/kinematics_routes.py
========================================
SuspensionLab PRO — Kinematics API Routes

POST /kinematics/solve   — Full wheel-travel sweep, returns all curves
GET  /kinematics/default — Default hardpoints (for UI initialisation)
GET  /kinematics/info    — Backend info (C++ vs Python fallback)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from suspensionlab.physics.kinematics import (
    solve_kinematics,
    backend_info,
    DEFAULT_HARDPOINTS,
    KinematicsCurves,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kinematics", tags=["kinematics"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class HardpointInput(BaseModel):
    """3D coordinates [x, y, z] in mm."""
    model_config = {"arbitrary_types_allowed": True}

    x: float
    y: float
    z: float

    @property
    def as_list(self) -> list[float]:
        return [self.x, self.y, self.z]


def _hp3(x: float, y: float, z: float) -> HardpointInput:
    return HardpointInput(x=x, y=y, z=z)


class HardpointSetInput(BaseModel):
    """All hardpoints defining one suspension corner."""
    # Upper wishbone
    UWI_fwd: list[float] = Field(default=[-50.0,  80.0, 300.0],
        description="Upper wishbone inboard pivot — forward [x, y, z] mm")
    UWI_aft: list[float] = Field(default=[ 50.0,  80.0, 300.0],
        description="Upper wishbone inboard pivot — aft    [x, y, z] mm")
    UWO:     list[float] = Field(default=[  0.0, 650.0, 295.0],
        description="Upper wishbone outboard (upper ball joint) [x, y, z] mm")

    # Lower wishbone
    LWI_fwd: list[float] = Field(default=[-80.0,  80.0, 155.0],
        description="Lower wishbone inboard pivot — forward [x, y, z] mm")
    LWI_aft: list[float] = Field(default=[ 80.0,  80.0, 155.0],
        description="Lower wishbone inboard pivot — aft    [x, y, z] mm")
    LWO:     list[float] = Field(default=[  0.0, 720.0, 145.0],
        description="Lower wishbone outboard (lower ball joint) [x, y, z] mm")

    # Tierod
    TRI: list[float] = Field(default=[  0.0, 150.0, 220.0],
        description="Tierod inboard (rack end) [x, y, z] mm")
    TRO: list[float] = Field(default=[-15.0, 710.0, 205.0],
        description="Tierod outboard (steering arm) [x, y, z] mm")

    # Wheel
    WC:  list[float] = Field(default=[  0.0, 760.0, 220.0],
        description="Wheel centre (neutral) [x, y, z] mm")
    CP:  list[float] = Field(default=[  0.0, 760.0,   0.0],
        description="Contact patch (ground plane) [x, y, z] mm")

    # Pushrod / rocker
    PRI: list[float] = Field(default=[-20.0, 300.0, 390.0],
        description="Pushrod inboard / rocker pivot [x, y, z] mm")
    PRO: list[float] = Field(default=[-15.0, 690.0, 250.0],
        description="Pushrod outboard on upright [x, y, z] mm")

    @field_validator("UWI_fwd", "UWI_aft", "UWO",
                     "LWI_fwd", "LWI_aft", "LWO",
                     "TRI", "TRO", "WC", "CP", "PRI", "PRO",
                     mode="before")
    @classmethod
    def must_be_3(cls, v):
        if len(v) != 3:
            raise ValueError("Each hardpoint must be a list of 3 floats [x, y, z].")
        return [float(c) for c in v]

    def to_dict(self) -> dict:
        return {
            "UWI_fwd": self.UWI_fwd, "UWI_aft": self.UWI_aft, "UWO": self.UWO,
            "LWI_fwd": self.LWI_fwd, "LWI_aft": self.LWI_aft, "LWO": self.LWO,
            "TRI": self.TRI, "TRO": self.TRO,
            "WC": self.WC, "CP": self.CP,
            "PRI": self.PRI, "PRO": self.PRO,
        }


class KinematicsSolveRequest(BaseModel):
    hardpoints: HardpointSetInput = Field(
        default_factory=HardpointSetInput,
        description="Corner hardpoint coordinates in mm.")
    z_min_mm: float = Field(default=-80.0, ge=-200.0, le=0.0,
        description="Minimum wheel travel (droop, negative) [mm]")
    z_max_mm: float = Field(default= 80.0, ge=0.0, le=200.0,
        description="Maximum wheel travel (bump, positive) [mm]")
    n_steps:  int   = Field(default=33, ge=5, le=201,
        description="Number of evaluation steps (5–201)")


class KinematicsResponse(BaseModel):
    wheel_travel_mm:       list[float]
    camber_deg:            list[float]
    toe_deg:               list[float]
    caster_deg:            list[float]
    kpi_deg:               list[float]
    track_change_mm:       list[float]
    wheelbase_change_mm:   list[float]
    roll_center_height_mm: list[float]
    motion_ratio:          list[float]
    scrub_radius_mm:       list[float]
    converged:             list[bool]
    n_points:              int
    backend:               str
    all_converged:         bool


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/solve", response_model=KinematicsResponse,
             summary="Solve double-wishbone corner kinematics")
async def solve(
    req: KinematicsSolveRequest,
) -> KinematicsResponse:
    """
    Solve kinematics for a double-wishbone corner over a wheel-travel sweep.

    Returns camber, toe, caster, KPI, track change, wheelbase change,
    roll-centre height, motion ratio, and scrub radius — all as arrays
    indexed by wheel travel.
    """
    try:
        curves: KinematicsCurves = solve_kinematics(
            hardpoints=req.hardpoints.to_dict(),
            z_min_mm=req.z_min_mm,
            z_max_mm=req.z_max_mm,
            n_steps=req.n_steps,
        )
    except Exception as exc:
        logger.exception("Kinematics solver error")
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    d = curves.to_dict()
    all_conv = all(d["converged"])
    if not all_conv:
        n_fail = sum(1 for c in d["converged"] if not c)
        logger.warning("Kinematics: %d/%d steps did not fully converge", n_fail, req.n_steps)

    info = backend_info()
    return KinematicsResponse(
        wheel_travel_mm       = d["wheel_travel_mm"],
        camber_deg            = d["camber_deg"],
        toe_deg               = d["toe_deg"],
        caster_deg            = d["caster_deg"],
        kpi_deg               = d["kpi_deg"],
        track_change_mm       = d["track_change_mm"],
        wheelbase_change_mm   = d["wheelbase_change_mm"],
        roll_center_height_mm = d["roll_center_height_mm"],
        motion_ratio          = d["motion_ratio"],
        scrub_radius_mm       = d["scrub_radius_mm"],
        converged             = d["converged"],
        n_points              = len(d["wheel_travel_mm"]),
        backend               = info["backend"],
        all_converged         = all_conv,
    )


@router.get("/default",
            summary="Return default hardpoints for UI initialisation")
async def get_defaults() -> dict:
    """Return the default Formula-style hardpoint set."""
    return {
        "hardpoints": DEFAULT_HARDPOINTS,
        "description": "Right-front corner, open-wheel Formula car, all values in mm",
        "coordinate_system": {
            "X": "forward (positive = toward front of car)",
            "Y": "outboard (positive = away from vehicle centreline)",
            "Z": "up (positive = upward)",
        },
    }


@router.get("/info",
            summary="Kinematics backend information")
async def get_info() -> dict:
    """Return backend info: whether the C++ extension is active."""
    return backend_info()
