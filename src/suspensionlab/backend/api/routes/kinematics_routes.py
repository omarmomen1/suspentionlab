"""
backend/api/routes/kinematics_routes.py
========================================
SuspensionLab PRO — Kinematics API Routes

POST /kinematics/solve   — Full wheel-travel sweep, returns all curves
POST /kinematics/steer-grid — 2-D (bump, rack) grid: MR field, steer-induced camber/caster/toe, Ackermann
GET  /kinematics/default — Default hardpoints (for UI initialisation)
GET  /kinematics/info    — Backend info (C++ vs Python fallback)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.physics.kinematics import (
    backend_info,
    DEFAULT_HARDPOINTS,
    KinematicsCurves,
    compute_kinematic_derivatives,
    compute_geometry_hash,
)
from suspensionlab.physics.kinematics_facade import solve_kinematics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kinematics", tags=["kinematics"])


def _stamped_solver_version(base: str | None) -> str:
    """Wave 6: attach the real git-commit build stamp to the solver version."""
    try:
        from suspensionlab.physics.provenance import build_solver_version
        return build_solver_version(base)
    except Exception:
        return base or "unknown"


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
    """All hardpoints defining one suspension corner.

    Defaults are a physically realistic GT3 front double-wishbone corner
    (tuned against the module's own benchmarks, Wave 5A-2):
    caster 5.7 deg, KPI 9.6 deg, motion ratio 0.78, static RC height
    +70 mm, scrub radius 26 mm, camber gain -0.045 deg/mm, bump steer
    0.028 deg/10mm, static camber -1.2 deg, static toe 0.0 deg.
    WC.z=330 with CP.z=0 derives a 0.330 m tire radius.
    """
    # Upper wishbone
    UWI_fwd: list[float] = Field(default=[-50.0, 300.0, 340.0],
        description="Upper wishbone inboard pivot — forward [x, y, z] mm")
    UWI_aft: list[float] = Field(default=[ 50.0, 300.0, 340.0],
        description="Upper wishbone inboard pivot — aft    [x, y, z] mm")
    UWO:     list[float] = Field(default=[-19.0, 660.0, 425.0],
        description="Upper wishbone outboard (upper ball joint) [x, y, z] mm")

    # Lower wishbone
    LWI_fwd: list[float] = Field(default=[-80.0, 300.0, 202.0],
        description="Lower wishbone inboard pivot — forward [x, y, z] mm")
    LWI_aft: list[float] = Field(default=[ 80.0, 300.0, 202.0],
        description="Lower wishbone inboard pivot — aft    [x, y, z] mm")
    LWO:     list[float] = Field(default=[  0.0, 692.0, 235.0],
        description="Lower wishbone outboard (lower ball joint) [x, y, z] mm")

    # Tierod
    TRI: list[float] = Field(default=[  0.0, 200.0, 190.0],
        description="Tierod inboard (rack end) [x, y, z] mm")
    TRO: list[float] = Field(default=[-15.0, 710.0, 230.0],
        description="Tierod outboard (steering arm) [x, y, z] mm")

    # Wheel
    WC:  list[float] = Field(default=[ -7.05, 758.0, 330.0],
        description="Wheel centre (neutral) [x, y, z] mm")
    CP:  list[float] = Field(default=[ -7.05, 758.0,   0.0],
        description="Contact patch (ground plane) [x, y, z] mm")

    # Pushrod / rocker
    PRI: list[float] = Field(default=[-20.0, 350.0, 620.0],
        description="Pushrod inboard / rocker pivot [x, y, z] mm")
    PRO: list[float] = Field(default=[-15.0, 610.0, 268.0],
        description="Pushrod outboard on upright [x, y, z] mm")

    # Static alignment (upright's built-in spindle angles; not recoverable
    # from hardpoint coordinates alone, so they are explicit inputs).
    static_camber_deg: float = Field(default=0.0,
        description="Static camber built into the upright spindle [deg]. Default 0.0; GT3 presets set -1.2 explicitly.")
    static_toe_deg: float = Field(default=0.0,
        description="Static toe (shim/alignment setting) [deg, + = toe-out]")

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
            "static_camber_deg": self.static_camber_deg,
            "static_toe_deg": self.static_toe_deg,
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
    backend:  str   = Field(default="auto",
        description="Requested backend solver: auto, cpp, or python")
    strict_mode: bool = Field(default=False,
        description="Strict mode: require requested backend, forbid silent fallbacks")
    tire_radius_m: Optional[float] = Field(default=None, gt=0.1, le=1.0,
        description="Dynamic rolling tire radius [m]. Omit (null) to derive it from the hardpoints as (WC.z - CP.z)/1000; an explicit value that disagrees with the hardpoints by >15 mm is rejected with a warning (error in strict mode).")


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
    requested_backend:     str
    available_backend:     bool
    selected_backend:      str
    active_backend:        str
    fallback_reason:       Optional[str] = None
    solver_version:        str
    native_library_version: Optional[str] = None
    build_identifier:      str
    all_converged:         bool
    ic_y_mm:               list[float] = Field(default_factory=list)
    ic_z_mm:               list[float] = Field(default_factory=list)
    ic_sv_x_mm:            list[float] = Field(default_factory=list)
    ic_sv_z_mm:            list[float] = Field(default_factory=list)
    rc_y_mm:               list[float] = Field(default_factory=list)
    roll_center_lateral_mm: list[float] = Field(default_factory=list)
    geometry_steps:        list[dict] = Field(default_factory=list)
    validation_report:     Optional[dict] = None
    derivatives:           dict = Field(default_factory=dict)
    point_diagnostics:     list[dict] = Field(default_factory=list)
    reproducibility:       Optional[dict] = None
    model_validity:        Optional[dict] = None
    model_assumptions:     dict = Field(default_factory=dict)
    benchmarks:            list[dict] = Field(default_factory=list)
    numerical_status:      str = Field(default="PASS")
    physical_status:       str = Field(default="PASS")
    overall_model_status:  str = Field(default="PASS")
    convergence_summary:   str = Field(default="")
    physical_issues:       list[str] = Field(default_factory=list)
    run_id:                str = Field(default="")
    input_sha256:          str = Field(default="")
    geometry_hash:         str = Field(default="")
    timestamp:             str = Field(default="")
    metadata:              dict = Field(default_factory=dict)


class KinematicsCompareRequest(BaseModel):
    setup_a: dict = Field(..., description="Setup A (Baseline) dictionary")
    setup_b: dict = Field(..., description="Setup B (Candidate) dictionary")
    z_min_mm: float = Field(default=-50.0, ge=-200.0, le=0.0)
    z_max_mm: float = Field(default= 50.0, ge=0.0, le=200.0)
    n_steps:  int   = Field(default=33, ge=5, le=201)
    backend:  str   = Field(default="auto")
    vehicle_id: str = Field(default="corner_multibody")


class KinematicsSensitivityRequest(BaseModel):
    hardpoints: dict[str, list[float]] = Field(..., description="Suspension corner hardpoints in mm")
    target_hardpoints: Optional[list[str]] = Field(default=None, description="Subset of hardpoints to perturb")
    axes: Optional[list[str]] = Field(default=None, description="Axes to perturb (X, Y, Z)")
    step_size_mm: float = Field(default=1.0, ge=0.1, le=5.0, description="Finite difference step size in mm")
    z_min_mm: float = Field(default=-35.0, ge=-100.0, le=0.0)
    z_max_mm: float = Field(default=35.0, ge=0.0, le=100.0)
    n_steps: int = Field(default=15, ge=5, le=51)


class KinematicsRecommendRequest(BaseModel):
    hardpoints: dict[str, list[float]] = Field(..., description="Baseline suspension corner hardpoints")
    question_preset_id: Optional[str] = Field(default=None, description="Preset question ID")
    custom_objective: Optional[dict[str, Any]] = None
    custom_constraints: Optional[dict[str, Any]] = None
    custom_candidates: Optional[list[str]] = None
    perturbation_steps_mm: Optional[list[float]] = None
    z_min_mm: float = Field(default=-35.0)
    z_max_mm: float = Field(default=35.0)
    n_steps: int = Field(default=15)


class KinematicsOptimizeRequest(BaseModel):
    hardpoints: dict[str, list[float]] = Field(..., description="Baseline suspension corner hardpoints")
    target_hardpoints: list[str] = Field(..., description="Hardpoints allowed to vary")
    allowed_axes: list[str] = Field(default=["Y", "Z"], description="Axes allowed to vary (X, Y, Z)")
    hardpoint_bounds_mm: float = Field(default=10.0, ge=1.0, le=30.0, description="Max deviation +/- bound in mm")
    objectives: Optional[list[dict[str, Any]]] = None
    constraints: Optional[list[dict[str, Any]]] = None
    n_samples: int = Field(default=40, ge=10, le=100)
    z_min_mm: float = Field(default=-35.0)
    z_max_mm: float = Field(default=35.0)
    n_steps: int = Field(default=15)


class KinematicsApplyToExperimentRequest(BaseModel):
    baseline_hardpoints: dict[str, list[float]]
    candidate_hardpoints: dict[str, list[float]]
    question: str = Field(default="Kinematics Hardpoint Optimization")
    hypothesis: Optional[str] = None
    candidate_id: Optional[str] = None
    optimization_id: Optional[str] = None


class KinematicsExportRequest(BaseModel):
    sweep_data: Optional[dict] = Field(default=None, description="Sweep result dictionary containing curves and metadata")
    hardpoints: Optional[dict] = Field(default=None, description="Hardpoints dictionary in mm for on-the-fly sweep export")
    setup_name: Optional[str] = Field(default="Baseline", description="Optional setup identifier/name")
    z_min_mm: float = Field(default=-50.0, description="Rebound wheel travel bound [mm]")
    z_max_mm: float = Field(default=50.0, description="Bump wheel travel bound [mm]")
    n_steps: int = Field(default=21, ge=5, le=201, description="Number of sweep points")
    tire_radius_m: float = Field(default=0.33, gt=0.1, le=1.0, description="Dynamic rolling tire radius [m]")
    format: str = Field(default="csv", description="Export format: 'csv' or 'json'")


class KinematicsSaveSetupRequest(BaseModel):
    setup_id: str = Field(..., description="Unique setup identifier")
    name: str = Field(..., description="Human-readable setup title")
    hardpoints: dict = Field(..., description="Hardpoint coordinates in mm")
    category: str = Field(default="Custom")
    description: str = Field(default="")
    wheel_travel_range: list[float] = Field(default=[-50.0, 50.0])
    tire_radius_m: float = Field(default=0.33)


class KinematicsSinglePointRequest(BaseModel):
    hardpoints: HardpointSetInput = Field(default_factory=HardpointSetInput)
    dz_mm: float = Field(default=0.0)
    roll_deg: float = Field(default=0.0)
    steer_deg: float = Field(default=0.0)
    pitch_deg: float = Field(default=0.0)
    tire_radius_m: float = Field(default=0.33)
    backend: str = Field(default="auto")
    strict_mode: bool = Field(default=False)


class KinematicPointResponse(BaseModel):
    wheel_travel_mm:       float
    camber_deg:            float
    toe_deg:               float
    caster_deg:            float
    kpi_deg:               float
    track_change_mm:       float
    wheelbase_change_mm:   float
    roll_center_height_mm: float
    motion_ratio:          float
    scrub_radius_mm:       float
    converged:             bool
    anti_dive_pct:         float = 0.0
    anti_squat_pct:        float = 0.0
    anti_lift_pct:         float = 0.0
    jacking_force_coeff:   float = 0.0
    ic_y_mm:               float = 0.0
    ic_z_mm:               float = 0.0
    ic_sv_x_mm:            float = 0.0
    ic_sv_z_mm:            float = 0.0
    geometry:              dict[str, Any] = Field(default_factory=dict)
    metadata:              dict = Field(default_factory=dict)


class HardpointValidationRequest(BaseModel):
    topology: str = Field(default="double_wishbone")
    hardpoints: HardpointSetInput = Field(default_factory=HardpointSetInput)
    tire_radius_m: float = Field(default=0.33)


BENCHMARK_PRESETS = {
    "formula_sae": {
        "id": "formula_sae",
        "name": "Formula SAE / Student Prototype",
        "description": "Agile open-wheel formula car with aggressive camber recovery, low roll center, and direct pushrod actuation.",
        "category": "Open Wheel Formula",
        "wheel_travel_range": [-30.0, 30.0],
        "tire_radius_m": 0.254,
        "half_track_mm": 600.0,
        "hardpoints": {
            "UWI_fwd": [-50.0, 100.0, 295.0],
            "UWI_aft": [ 50.0, 100.0, 295.0],
            "UWO":     [ -7.5, 495.0, 340.0],
            "LWI_fwd": [-80.0, 100.0, 172.0],
            "LWI_aft": [ 80.0, 100.0, 172.0],
            "LWO":     [  7.5, 535.0, 185.0],
            "TRI":     [-15.0, 100.0, 215.1],
            "TRO":     [-20.0, 511.0, 239.2],
            "WC":      [  0.0, 600.0, 254.0],
            "CP":      [  0.0, 600.0,   0.0],
            "PRI":     [-20.0, 280.0, 445.0],
            "PRO":     [-15.0, 515.0, 200.0],
        },
    },
    "formula_sae_low_rc": {
        "id": "formula_sae_low_rc",
        "name": "Formula SAE (Low Roll Center / Raised Inboard UWI)",
        "description": "FSAE corner with raised upper wishbone inboard pivots (UWI Z+5mm), shifting roll center downward to soften front roll couple.",
        "category": "Open Wheel Formula Variant",
        "wheel_travel_range": [-30.0, 30.0],
        "tire_radius_m": 0.254,
        "half_track_mm": 600.0,
        "hardpoints": {
            "UWI_fwd": [-50.0, 100.0, 300.0],
            "UWI_aft": [ 50.0, 100.0, 300.0],
            "UWO":     [ -7.5, 495.0, 340.0],
            "LWI_fwd": [-80.0, 100.0, 172.0],
            "LWI_aft": [ 80.0, 100.0, 172.0],
            "LWO":     [  7.5, 535.0, 185.0],
            "TRI":     [-15.0, 100.0, 216.8],
            "TRO":     [-20.0, 511.0, 239.2],
            "WC":      [  0.0, 600.0, 254.0],
            "CP":      [  0.0, 600.0,   0.0],
            "PRI":     [-20.0, 280.0, 445.0],
            "PRO":     [-15.0, 515.0, 200.0],
        },
    },
    "gt3_touring": {
        "id": "gt3_touring",
        "name": "GT3 Touring / Sports Car",
        "description": "Production-derived GT3 racecar double wishbone geometry with long control arms for high-speed stability and linear tire wear.",
        "category": "GT / Sports Car",
        "wheel_travel_range": [-50.0, 50.0],
        "tire_radius_m": 0.330,
        "half_track_mm": 760.0,
        "hardpoints": {
            "UWI_fwd": [-50.0, 300.0, 340.0],
            "UWI_aft": [ 50.0, 300.0, 340.0],
            "UWO":     [-19.0, 660.0, 425.0],
            "LWI_fwd": [-80.0, 300.0, 202.0],
            "LWI_aft": [ 80.0, 300.0, 202.0],
            "LWO":     [  0.0, 692.0, 235.0],
            "TRI":     [  0.0, 200.0, 190.0],
            "TRO":     [-15.0, 710.0, 230.0],
            "WC":      [ -7.05, 758.0, 330.0],
            "CP":      [ -7.05, 758.0,   0.0],
            "PRI":     [-20.0, 350.0, 620.0],
            "PRO":     [-15.0, 610.0, 268.0],
            "static_camber_deg": -1.2,
            "static_toe_deg": 0.0,
        },
    },
    "gt3_camber_shim_5mm": {
        "id": "gt3_camber_shim_5mm",
        "name": "GT3 Touring (+5mm Camber Shim / Lower Pivot Outboard)",
        "description": "GT3 corner modified with 5mm outboard shim at lower ball joint (LWO Y+5mm) for enhanced static camber & lateral grip.",
        "category": "GT / Sports Car Variant",
        "wheel_travel_range": [-50.0, 50.0],
        "tire_radius_m": 0.330,
        "half_track_mm": 760.0,
        "hardpoints": {
            "UWI_fwd": [-50.0, 300.0, 340.0],
            "UWI_aft": [ 50.0, 300.0, 340.0],
            "UWO":     [-19.0, 660.0, 425.0],
            "LWI_fwd": [-80.0, 300.0, 202.0],
            "LWI_aft": [ 80.0, 300.0, 202.0],
            "LWO":     [  0.0, 697.0, 235.0],
            "TRI":     [  0.0, 200.0, 190.0],
            "TRO":     [-15.0, 710.0, 230.0],
            "WC":      [ -7.05, 758.0, 330.0],
            "CP":      [ -7.05, 758.0,   0.0],
            "PRI":     [-20.0, 350.0, 620.0],
            "PRO":     [-15.0, 610.0, 268.0],
            "static_camber_deg": -1.2,
            "static_toe_deg": 0.0,
        },
    },
    "lmp_prototype": {
        "id": "lmp_prototype",
        "name": "LMP / Hypercar Prototype",
        "description": "High-downforce endurance sports prototype with stiff kinematics, low scrub radius to minimize steering torque, and tight kinematic packaging.",
        "category": "Endurance Prototype",
        "wheel_travel_range": [-35.0, 35.0],
        "tire_radius_m": 0.340,
        "half_track_mm": 820.0,
        "hardpoints": {
            "UWI_fwd": [-60.0,  90.0, 370.0],
            "UWI_aft": [ 60.0,  90.0, 370.0],
            "UWO":     [ -9.0, 685.0, 435.0],
            "LWI_fwd": [-90.0,  90.0, 215.0],
            "LWI_aft": [ 90.0,  90.0, 215.0],
            "LWO":     [  9.0, 735.0, 240.0],
            "TRI":     [-15.0,  90.0, 269.2],
            "TRO":     [-20.0, 707.5, 308.2],
            "WC":      [  0.0, 820.0, 340.0],
            "CP":      [  0.0, 820.0,   0.0],
            "PRI":     [-25.0, 410.0, 550.0],
            "PRO":     [-15.0, 710.0, 265.0],
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/solve", response_model=KinematicsResponse,
             summary="Solve double-wishbone corner kinematics")
async def solve(
    req: KinematicsSolveRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
) -> KinematicsResponse:
    """
    Solve kinematics for a double-wishbone corner over a wheel-travel sweep.

    Returns camber, toe, caster, KPI, track change, wheelbase change,
    roll-centre height, motion ratio, and scrub radius — all as arrays
    indexed by wheel travel with authoritative solver execution provenance,
    3D geometric hardpoints, and comprehensive validation status.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    hp_dict = req.hardpoints.to_dict()
    try:
        curves = solve_kinematics(
            hardpoints=hp_dict,
            z_min_mm=req.z_min_mm,
            z_max_mm=req.z_max_mm,
            n_steps=req.n_steps,
            tire_radius=req.tire_radius_m,
            mode=req.backend,
            strict_mode=req.strict_mode,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Kinematics solver error")
        # Do not leak raw exception strings (internal paths, solver state) to clients.
        raise HTTPException(status_code=422, detail="Kinematics solve failed for the supplied hardpoints; check geometry plausibility (see server logs for detail).") from exc

    d = curves.to_dict()
    all_conv = all(d["converged"])
    if not all_conv:
        n_fail = sum(1 for c in d["converged"] if not c)
        logger.warning("Kinematics: %d/%d steps did not fully converge", n_fail, req.n_steps)

    from suspensionlab.physics.kinematics import (
        validate_hardpoints_py,
        compute_kinematic_derivatives,
        compute_geometry_hash,
    )
    val_report = validate_hardpoints_py("double_wishbone", hp_dict)
    derivatives = compute_kinematic_derivatives(d)
    geom_hash = compute_geometry_hash(hp_dict)
    run_id = f"swp-{uuid.uuid4().hex[:12]}"
    # Wave 6: provenance input hash over the exact solver inputs. Static camber
    # and toe live on the hardpoint set and are already inside hp_dict. A failure
    # here must be loud: an empty hash would silently void the provenance claim.
    from suspensionlab.physics.provenance import compute_input_sha256
    input_sha256 = compute_input_sha256({
        "hardpoints": hp_dict,
        "z_min_mm": req.z_min_mm,
        "z_max_mm": req.z_max_mm,
        "n_steps": req.n_steps,
        "tire_radius_m": req.tire_radius_m,
        "backend": req.backend,
    })
    now_iso = datetime.now(timezone.utc).isoformat()

    n_conv = sum(1 for c in d["converged"] if c)
    n_total = len(d["converged"])
    conv_summary = f"{n_conv} / {n_total} converged" if n_conv == n_total else f"{n_conv} / {n_total} converged, {n_total - n_conv} failed"

    # Single verdict source: validate_hardpoints_py and model_validity are
    # reconciled into one status ladder {NOT_EVALUATED, PASS, WARN, FAIL}.
    # A missing model_validity NEVER defaults to PASS.
    val_eval = d.get("model_validity") or {}
    _status_rank = {"NOT_EVALUATED": 0, "PASS": 1, "VALID": 1, "WARN": 2, "OUT_OF_BOUNDS": 3, "FAIL": 3, "ERROR": 3}
    _status_norm = {"VALID": "PASS", "OUT_OF_BOUNDS": "FAIL", "ERROR": "FAIL"}

    def _norm(s: object) -> str:
        s2 = str(s or "NOT_EVALUATED").upper()
        return _status_norm.get(s2, s2 if s2 in _status_rank else "NOT_EVALUATED")

    def _worst(*statuses: str) -> str:
        return max(statuses, key=lambda s: _status_rank.get(s, 0))

    geom_status = _norm((val_report or {}).get("status"))
    conv_status = "PASS" if all_conv else "FAIL"
    if val_eval:
        num_status = _worst(_norm(val_eval.get("numerical_status")), conv_status)
        phys_status = _norm(val_eval.get("physical_status"))
        overall_status = _worst(_norm(val_eval.get("overall_status")), geom_status, num_status, phys_status)
    else:
        # model_validity absent: NEVER report PASS — the physical validity of
        # the solve was not evaluated.
        num_status = conv_status
        phys_status = "NOT_EVALUATED"
        overall_status = "FAIL" if (geom_status == "FAIL" or not all_conv) else (
            "WARN" if geom_status == "WARN" else "NOT_EVALUATED")
    phys_issues = val_eval.get("issues", [])

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
        backend               = curves.active_backend,
        requested_backend     = curves.requested_backend,
        available_backend     = curves.available_backend,
        selected_backend      = curves.selected_backend,
        active_backend        = curves.active_backend,
        fallback_reason       = curves.fallback_reason,
        solver_version        = _stamped_solver_version(curves.solver_version),
        native_library_version = curves.native_library_version,
        build_identifier      = curves.build_identifier,
        all_converged         = all_conv,
        ic_y_mm               = d.get("ic_y_mm", []),
        ic_z_mm               = d.get("ic_z_mm", []),
        ic_sv_x_mm            = d.get("ic_sv_x_mm", []),
        ic_sv_z_mm            = d.get("ic_sv_z_mm", []),
        rc_y_mm               = d.get("rc_y_mm", [0.0] * len(d["wheel_travel_mm"])),
        roll_center_lateral_mm = d.get("roll_center_lateral_mm", [0.0] * len(d["wheel_travel_mm"])),
        geometry_steps        = d.get("geometry_steps", []),
        validation_report     = val_report,
        derivatives           = derivatives,
        point_diagnostics     = d.get("point_diagnostics", []),
        reproducibility       = d.get("reproducibility"),
        model_validity        = val_eval,
        model_assumptions     = val_eval.get("model_assumptions", {
            "rigid_body_links": True,
            "bushing_compliance": "NOT_MODELED_RIGID_SPHERICAL_JOINTS",
            "structural_compliance": "NOT_MODELED_INFINITELY_STIFF_LINKS_AND_UPRIGHT",
            "disclaimer": "Kinematic solver assumes rigid links and ideal spherical joints without elastokinematic deflection.",
        }),
        benchmarks            = d.get("benchmarks", []),
        numerical_status      = num_status,
        physical_status       = phys_status,
        overall_model_status  = overall_status,
        convergence_summary   = conv_summary,
        physical_issues       = phys_issues,
        run_id                = run_id,
        input_sha256          = input_sha256,
        geometry_hash         = geom_hash,
        timestamp             = now_iso,
        metadata              = curves.metadata,
    )


@router.post("/benchmarks", response_model=list[dict],
             summary="Evaluate 5 canonical vehicle dynamics kinematics benchmarks")
async def evaluate_benchmarks(
    req: KinematicsSolveRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
) -> list[dict]:
    """Evaluate vehicle dynamics benchmarks against literature references."""
    from suspensionlab.physics.kinematics import get_kinematics_benchmarks
    from suspensionlab.physics.kinematics_facade import KinematicsBackendFactory
    backend = KinematicsBackendFactory.create(
        mode=req.backend,
        topology="double_wishbone",
        strict_mode=req.strict_mode,
    )
    hp_dict = req.hardpoints.to_dict()
    curves = backend.sweep(
        hp_dict,
        z_min_mm=req.z_min_mm,
        z_max_mm=req.z_max_mm,
        n_steps=req.n_steps,
    )
    d = curves.to_dict()
    return get_kinematics_benchmarks(hp_dict, d)


@router.post("/solve-point", response_model=KinematicPointResponse,
             summary="Fast single-point kinematics solve for interactive travel slider")
async def solve_point(
    req: KinematicsSinglePointRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
) -> KinematicPointResponse:
    """Solve kinematics at a single wheel travel position, returning full 3D nodal coordinates."""
    from suspensionlab.physics.kinematics_facade import KinematicsBackendFactory
    backend = KinematicsBackendFactory.create(
        mode=req.backend,
        topology="double_wishbone",
        strict_mode=req.strict_mode,
    )
    pt = backend.solve_single(
        hardpoints=req.hardpoints.to_dict(),
        dz_mm=req.dz_mm,
        roll_deg=req.roll_deg,
        steer_deg=req.steer_deg,
        pitch_deg=req.pitch_deg,
        tire_radius_m=req.tire_radius_m,
    )
    return KinematicPointResponse(
        wheel_travel_mm       = pt.wheel_travel_mm,
        camber_deg            = pt.camber_deg,
        toe_deg               = pt.toe_deg,
        caster_deg            = pt.caster_deg,
        kpi_deg               = pt.kpi_deg,
        track_change_mm       = pt.track_change_mm,
        wheelbase_change_mm   = pt.wheelbase_change_mm,
        roll_center_height_mm = pt.roll_center_height_mm,
        motion_ratio          = pt.motion_ratio,
        scrub_radius_mm       = pt.scrub_radius_mm,
        converged             = pt.converged,
        anti_dive_pct         = pt.anti_dive_pct,
        anti_squat_pct        = pt.anti_squat_pct,
        anti_lift_pct         = pt.anti_lift_pct,
        jacking_force_coeff   = pt.jacking_force_coeff,
        ic_y_mm               = pt.ic_y_mm,
        ic_z_mm               = pt.ic_z_mm,
        ic_sv_x_mm            = pt.ic_sv_x_mm,
        ic_sv_z_mm            = pt.ic_sv_z_mm,
        geometry              = pt.geometry,
        metadata              = pt.metadata,
    )


class SteerGridRequest(BaseModel):
    """2-D (bump, rack travel) motion-ratio / steer sweep. Python 5-DOF solver, no C++ path."""
    hardpoints: HardpointSetInput = Field(default_factory=HardpointSetInput)
    z_min_mm: float = Field(-50.0, ge=-200.0, le=0.0)
    z_max_mm: float = Field(50.0, ge=0.0, le=200.0)
    n_bump: int = Field(11, ge=3, le=41)
    rack_min_mm: float = Field(-5.0, ge=-100.0, le=0.0)
    rack_max_mm: float = Field(5.0, ge=0.0, le=100.0)
    n_steer: int = Field(5, ge=3, le=21)
    tire_radius_m: Optional[float] = Field(None, gt=0.1, lt=1.0)
    wheelbase_mm: Optional[float] = Field(None, gt=500.0, lt=6000.0,
        description="Needed only for Ackermann. Omit and Ackermann is returned as NOT_MODELED.")


@router.post("/mr-field", summary="Alias of /steer-grid (MR field MR(bump, steer))", include_in_schema=True)
@router.post("/steer-grid", summary="2-D motion-ratio field MR(bump, steer) plus steer-induced camber/caster/toe and Ackermann")
async def steer_grid(
    req: SteerGridRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
) -> dict:
    from suspensionlab.physics.kinematics import solve_steer_grid
    try:
        return solve_steer_grid(
            req.hardpoints.to_dict(),
            z_min_mm=req.z_min_mm, z_max_mm=req.z_max_mm, n_bump=req.n_bump,
            rack_min_mm=req.rack_min_mm, rack_max_mm=req.rack_max_mm, n_steer=req.n_steer,
            tire_radius=req.tire_radius_m, wheelbase_mm=req.wheelbase_mm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/validate", summary="CAE hardpoint admissibility check with diagnostic remediation")
async def validate_geometry(
    req: HardpointValidationRequest,
) -> dict:
    """Check geometric feasibility and return actionable engineering remediation."""
    from suspensionlab.physics.kinematics import validate_hardpoints_py
    return validate_hardpoints_py(
        topology=req.topology,
        hardpoints=req.hardpoints.to_dict(),
        tire_radius_m=req.tire_radius_m,
    )


@router.get("/benchmarks", summary="Standard motorsport/automotive benchmark geometries")
async def get_benchmarks() -> dict:
    """Return catalog of validated benchmark vehicle geometries."""
    return BENCHMARK_PRESETS


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


@router.post("/compare", summary="A/B Comparative Kinematic Analysis & Causal Attribution")
async def compare_setups_endpoint(
    req: KinematicsCompareRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
) -> dict:
    """
    Run independent sweeps for Setup A and Setup B and compute:
    1. Direct hardpoint & link length differences.
    2. Overlaid curves & rate metrics.
    3. Channel statistics: max diff, static diff, bump diff, droop diff, RMS diff.
    4. Causal attribution categorized into [DIRECTLY COMPUTED], [INFERRED], and [HYPOTHESIZED].
    5. Comparison provenance.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService
    return KinematicsStudyService.compare(
        setup_a=req.setup_a,
        setup_b=req.setup_b,
        sweep_config={
            "z_min_mm": req.z_min_mm,
            "z_max_mm": req.z_max_mm,
            "n_steps": req.n_steps,
            "backend": req.backend,
            "vehicle_id": req.vehicle_id,
        },
    )


def _resolve_sweep_data_for_export(req: KinematicsExportRequest) -> dict:
    """Return existing sweep_data or compute a sweep on the fly when hardpoints are supplied."""
    from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService
    if req.sweep_data:
        return req.sweep_data
    if req.hardpoints:
        return KinematicsStudyService.run_sweep(
            hardpoints=req.hardpoints,
            z_min_mm=req.z_min_mm,
            z_max_mm=req.z_max_mm,
            n_steps=req.n_steps,
            tire_radius_m=req.tire_radius_m,
            setup_id=req.setup_name or "export",
        )
    raise HTTPException(
        status_code=422,
        detail="Either 'sweep_data' or 'hardpoints' must be provided for kinematics export.",
    )


@router.post("/export", summary="Export Kinematic Sweep Data as CSV or JSON")
async def export_sweep_endpoint(
    req: KinematicsExportRequest,
):
    """Unified kinematics export supporting precomputed sweep_data or on-the-fly hardpoints."""
    from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService
    sweep_data = _resolve_sweep_data_for_export(req)
    fmt = (req.format or "csv").strip().lower()
    if fmt == "json":
        return KinematicsStudyService.export_json(sweep_data)
    csv_content = KinematicsStudyService.export_csv(sweep_data)
    run_id = sweep_data.get("run_id", "sweep")
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="kinematics_{run_id}.csv"'},
    )


@router.post("/export/csv", summary="Export Kinematic Sweep Data as RFC-4180 CSV")
async def export_sweep_csv_endpoint(
    req: KinematicsExportRequest,
) -> Response:
    """Generate downloadable CSV containing sweep channels, rates, and provenance headers."""
    from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService
    sweep_data = _resolve_sweep_data_for_export(req)
    csv_content = KinematicsStudyService.export_csv(sweep_data)
    run_id = sweep_data.get("run_id", "sweep")
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="kinematics_{run_id}.csv"'},
    )


@router.post("/export/json", summary="Export Kinematic Sweep Data as Canonical JSON")
async def export_sweep_json_endpoint(
    req: KinematicsExportRequest,
) -> dict:
    """Generate structured JSON schema dictionary containing sweep data and metadata."""
    from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService
    sweep_data = _resolve_sweep_data_for_export(req)
    return KinematicsStudyService.export_json(sweep_data)


@router.get("/setups", summary="List Available Persisted Setups and Benchmarks")
async def list_setups_endpoint() -> list[dict]:
    """Retrieve catalog of standard benchmarks and user-saved setups."""
    from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService
    return KinematicsStudyService.get_all_setups()


@router.post("/setups/save", summary="Persist Named Kinematic Setup")
async def save_setup_endpoint(
    req: KinematicsSaveSetupRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
) -> dict:
    """Save custom hardpoint set to persisted catalog."""
    from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService
    return KinematicsStudyService.save_setup(
        setup_id=req.setup_id,
        name=req.name,
        hardpoints=req.hardpoints,
        category=req.category,
        description=req.description,
        wheel_travel_range=req.wheel_travel_range,
        tire_radius_m=req.tire_radius_m,
    )


@router.post("/sensitivity", summary="Compute Real Hardpoint Finite-Difference Jacobian Sensitivity Matrix")
async def compute_sensitivity_endpoint(
    req: KinematicsSensitivityRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
) -> dict:
    """
    Computes finite-difference sensitivities (dOutput/dHardpoint) for selected hardpoints and axes
    using real kinematics solver executions.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.backend.services.kinematics_optimization_service import KinematicsOptimizationService
    return KinematicsOptimizationService.compute_sensitivity(
        hardpoints=req.hardpoints,
        target_hardpoints=req.target_hardpoints,
        axes=req.axes,
        step_size_mm=req.step_size_mm,
        z_min_mm=req.z_min_mm,
        z_max_mm=req.z_max_mm,
        n_steps=req.n_steps,
    )


@router.post("/recommend", summary="Evaluate Engineering Question with Sensitivity-Based Recommendations")
async def recommend_hardpoints_endpoint(
    req: KinematicsRecommendRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
) -> dict:
    """
    Answers natural engineering questions by testing real perturbations on candidate hardpoints,
    ranking candidates, and providing physical causal mechanism explanations.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.backend.services.kinematics_optimization_service import KinematicsOptimizationService
    return KinematicsOptimizationService.answer_engineering_question(
        hardpoints=req.hardpoints,
        question_preset_id=req.question_preset_id,
        custom_objective=req.custom_objective,
        custom_constraints=req.custom_constraints,
        custom_candidates=req.custom_candidates,
        perturbation_steps_mm=req.perturbation_steps_mm,
        z_min_mm=req.z_min_mm,
        z_max_mm=req.z_max_mm,
        n_steps=req.n_steps,
    )


@router.post("/optimize", summary="Bounded Hardpoint Multi-Objective Optimization & Pareto View")
async def optimize_hardpoints_endpoint(
    req: KinematicsOptimizeRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
) -> dict:
    """
    Bounded multi-objective optimization using the real kinematics engine.
    Extracts non-dominated Pareto frontier and explicitly computes best compromise.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.backend.services.kinematics_optimization_service import KinematicsOptimizationService
    return KinematicsOptimizationService.run_optimization(
        hardpoints=req.hardpoints,
        target_hardpoints=req.target_hardpoints,
        allowed_axes=req.allowed_axes,
        hardpoint_bounds_mm=req.hardpoint_bounds_mm,
        objectives=req.objectives,
        constraints=req.constraints,
        n_samples=req.n_samples,
        z_min_mm=req.z_min_mm,
        z_max_mm=req.z_max_mm,
        n_steps=req.n_steps,
    )


@router.post("/apply-to-experiment", summary="Transfer Optimized Candidate to Scientific Experiment Pipeline")
async def apply_to_experiment_endpoint(
    req: KinematicsApplyToExperimentRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
) -> dict:
    """
    Seamlessly transfers an optimized hardpoint candidate into the scientific Experiment system,
    preserving full provenance, SHA-256 geometry hashes, and parameter deltas.
    """
    from suspensionlab.backend.services.kinematics_optimization_service import KinematicsOptimizationService
    return KinematicsOptimizationService.apply_candidate_to_experiment(
        baseline_hardpoints=req.baseline_hardpoints,
        candidate_hardpoints=req.candidate_hardpoints,
        question=req.question,
        hypothesis=req.hypothesis,
        candidate_id=req.candidate_id,
        optimization_id=req.optimization_id,
        author=getattr(user, "username", "Lead Kinematics CAE Engineer"),
    )

