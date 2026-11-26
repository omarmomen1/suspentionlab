"""
backend/api/routes/lap_sim_routes.py
=====================================
SuspensionLab PRO — Lap Simulator API Routes

Endpoints
---------
POST /lapsim/run         Run a QSS lap simulation from GPS arrays
POST /lapsim/upload_gpx  Parse a GPX file → lat/lon/elev arrays
GET  /lapsim/ggv         Pre-compute and return the GGV envelope for a vehicle
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field
import defusedxml.ElementTree as ET
import gpxpy
import logging
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.security.rate_limit import RateLimiter
from suspensionlab.physics.lap_sim import (
    LapSimVehicle, MassProperties, AeroMap, PowertrainModel,
    parse_track_from_gps, parse_track_from_curvature, solve_lap, TrackSegment,
    FAST_QUASI_STEADY,
    simulate_lap, compute_ggv_surface, get_builtin_track,
    parse_segments_array, parse_telemetry_csv, VehicleParameters,
)
from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicTrackModel,
    solve_dynamic_lap,
    DYNAMIC_TRANSIENT_14DOF,
    FAST_QSS,
    TRANSIENT_ENGINEERING,
    HIGH_FIDELITY_LAP,
    DifferentialType,
    DifferentialConfig,
    solve_transient_maneuver,
    compare_quasi_steady_vs_dynamic,
    cross_validate_qss_and_transient,
)
from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.suspension_aero_coupling import (
    SuspensionConfig,
    CoupledVehicleModel,
)

router = APIRouter(tags=["Lap Simulation"])

MAX_GPS_POINTS = 10_000


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic input models
# ─────────────────────────────────────────────────────────────────────────────

class MassPropertiesInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    total_mass:     Optional[float] = None   # kg
    h_cog:          Optional[float] = None   # m
    wheelbase:      Optional[float] = None   # m
    cog_dist_front: Optional[float] = None   # m
    track_front:    Optional[float] = None   # m
    track_rear:     Optional[float] = None   # m


class AeroMapInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    cl_base:      Optional[float] = None
    cd_base:      Optional[float] = None
    frontal_area: Optional[float] = None
    cop_fraction: Optional[float] = None
    cl_rh_sens:   Optional[float] = None


class PowertrainInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    gear_ratios:       Optional[List[float]] = None
    torque_curve_rpm:  Optional[List[float]] = None
    torque_curve_nm:   Optional[List[float]] = None
    rev_limit:         Optional[float]       = None
    wheel_radius:      Optional[float]       = None
    drivetrain_loss:   Optional[float]       = None
    shift_time_s:      Optional[float]       = None
    max_brake_force_n: Optional[float]       = None
    brake_front_bias:  Optional[float]       = None


class TireCoeffsInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    pCy1: Optional[float] = None
    pDy1: Optional[float] = None
    pEy1: Optional[float] = None
    pKy1: Optional[float] = None
    pKy2: Optional[float] = None
    pCx1: Optional[float] = None
    pDx1: Optional[float] = None
    pEx1: Optional[float] = None
    pKx1: Optional[float] = None


class SuspensionInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    k_spring_front:     Optional[float] = None   # N/m
    k_spring_rear:      Optional[float] = None   # N/m
    k_arb_front:        Optional[float] = None   # N/m
    k_arb_rear:         Optional[float] = None   # N/m
    motion_ratio_front: Optional[float] = None   # [-]
    motion_ratio_rear:  Optional[float] = None   # [-]
    ride_height_front:  Optional[float] = None   # mm
    ride_height_rear:   Optional[float] = None   # mm


class DifferentialInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    diff_type:            Optional[str]   = "OPEN"             # OPEN, LOCKED, LSD_TORQUE_BIASED, CLUTCH_PACK
    bias_ratio:           Optional[float] = 3.0                # Torque Bias Ratio for Torsen
    preload_nm:           Optional[float] = 60.0               # Static preload for Clutch Pack [N*m]
    ramp_angle_accel_deg: Optional[float] = 45.0               # Power ramp angle [deg]
    ramp_angle_decel_deg: Optional[float] = 60.0               # Coast ramp angle [deg]
    drivetrain_layout:    Optional[str]   = "RWD"              # RWD, FWD, AWD


class VehicleInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    # Legacy scalar overrides (backwards-compatible)
    mass:      Optional[float] = None
    aero_cl:   Optional[float] = None
    aero_cd:   Optional[float] = None
    max_power: Optional[float] = None   # W — scales torque curve proportionally

    # Sub-model overrides
    mass_props:   Optional[MassPropertiesInput] = None
    aero:         Optional[AeroMapInput]        = None
    powertrain:   Optional[PowertrainInput]     = None
    tire_coeffs:  Optional[TireCoeffsInput]     = None
    suspension:   Optional[SuspensionInput]     = None
    differential: Optional[DifferentialInput]   = None
    use_coupling: bool = False   # enable ride-height/aero coupling iteration
    tire_model:   Optional[str]  = None   # QUASI_STEADY or DYNAMIC
    tire_model_type: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_vehicle(vehicle_input: Optional[VehicleInput]) -> LapSimVehicle:
    """Construct a LapSimVehicle from API input overrides."""
    mp = MassProperties()
    ae = AeroMap()
    pt = PowertrainModel()
    tc = TireCoeffs()

    if vehicle_input is None:
        return LapSimVehicle(mass_props=mp, aero=ae, powertrain=pt, tire_coeffs=tc)

    v = vehicle_input

    # Legacy scalar overrides
    if v.mass is not None:
        mp.total_mass = v.mass
    if v.aero_cl is not None:
        ae.cl_base = v.aero_cl
    if v.aero_cd is not None:
        ae.cd_base = v.aero_cd
    if v.max_power is not None:
        # Scale torque curve to match requested peak power
        peak_current = PowertrainModel().max_power_w()
        scale = v.max_power / max(peak_current, 1.0)
        pt.torque_curve_nm = [t * scale for t in pt.torque_curve_nm]

    # Sub-model overrides
    if v.mass_props:
        m = v.mass_props
        if m.total_mass     is not None: mp.total_mass     = m.total_mass
        if m.h_cog          is not None: mp.h_cog          = m.h_cog
        if m.wheelbase      is not None: mp.wheelbase      = m.wheelbase
        if m.cog_dist_front is not None: mp.cog_dist_front = m.cog_dist_front
        if m.track_front    is not None: mp.track_front    = m.track_front
        if m.track_rear     is not None: mp.track_rear     = m.track_rear

    if v.aero:
        a = v.aero
        if a.cl_base      is not None: ae.cl_base      = a.cl_base
        if a.cd_base      is not None: ae.cd_base      = a.cd_base
        if a.frontal_area is not None: ae.frontal_area = a.frontal_area
        if a.cop_fraction is not None: ae.cop_fraction = a.cop_fraction
        if a.cl_rh_sens   is not None: ae.cl_rh_sens   = a.cl_rh_sens

    if v.powertrain:
        p = v.powertrain
        if p.gear_ratios       is not None: pt.gear_ratios       = p.gear_ratios
        if p.torque_curve_rpm  is not None: pt.torque_curve_rpm  = p.torque_curve_rpm
        if p.torque_curve_nm   is not None: pt.torque_curve_nm   = p.torque_curve_nm
        if p.rev_limit         is not None: pt.rev_limit         = p.rev_limit
        if p.wheel_radius      is not None: pt.wheel_radius      = p.wheel_radius
        if p.drivetrain_loss   is not None: pt.drivetrain_loss   = p.drivetrain_loss
        if p.shift_time_s      is not None: pt.shift_time_s      = p.shift_time_s
        if p.max_brake_force_n is not None: pt.max_brake_force_n = p.max_brake_force_n
        if p.brake_front_bias  is not None: pt.brake_front_bias  = p.brake_front_bias

    if v.tire_coeffs:
        t = v.tire_coeffs
        if t.pCy1 is not None: tc.pCy1 = t.pCy1
        if t.pDy1 is not None: tc.pDy1 = t.pDy1
        if t.pEy1 is not None: tc.pEy1 = t.pEy1
        if t.pKy1 is not None: tc.pKy1 = t.pKy1
        if t.pKy2 is not None: tc.pKy2 = t.pKy2
        if t.pCx1 is not None: tc.pCx1 = t.pCx1
        if t.pDx1 is not None: tc.pDx1 = t.pDx1
        if t.pEx1 is not None: tc.pEx1 = t.pEx1
        if t.pKx1 is not None: tc.pKx1 = t.pKx1

    sc = SuspensionConfig()
    if v.suspension:
        s = v.suspension
        if s.k_spring_front     is not None: sc.k_spring_front     = s.k_spring_front
        if s.k_spring_rear      is not None: sc.k_spring_rear      = s.k_spring_rear
        if s.k_arb_front        is not None: sc.k_arb_front        = s.k_arb_front
        if s.k_arb_rear         is not None: sc.k_arb_rear         = s.k_arb_rear
        if s.motion_ratio_front is not None: sc.motion_ratio_front = s.motion_ratio_front
        if s.motion_ratio_rear  is not None: sc.motion_ratio_rear  = s.motion_ratio_rear
        if s.ride_height_front  is not None: sc.ride_height_front  = s.ride_height_front
        if s.ride_height_rear   is not None: sc.ride_height_rear   = s.ride_height_rear

    return LapSimVehicle(
        mass_props=mp, aero=ae, powertrain=pt, tire_coeffs=tc,
        suspension=sc, use_coupling=v.use_coupling,
    )


def _get_track_coordinates(distances, curvatures) -> Dict[str, Any]:
    """Numerically integrate track coordinates for 2D map visualization."""
    try:
        from suspensionlab.physics.track_geometry import integrate_track_coordinates
        coords = integrate_track_coordinates(distances, curvatures)
        return coords.to_dict()
    except Exception:
        return {"x": [], "y": [], "heading_rad": [], "is_closed": False, "closure_error_m": 0.0}


def _result_to_dict(result) -> Dict:
    """Serialise LapSimResult to JSON-safe dict."""
    # Dynamic 14-DOF results carry their own honest serialiser: always expose
    # lap_completed / outcome, and never let an aborted run surface as a
    # converged lap with a lap time (Wave 5A-2).
    from suspensionlab.physics.dynamic_lap_sim import DynamicLapResult
    if isinstance(result, DynamicLapResult):
        d = result.to_dict()
        if not result.lap_completed:
            d["solver_converged"] = False
            d["lap_time_s"] = None
            d["total_time_s"] = None
            d["status"] = "terminated"
        return d
    d = {
        "status": "success",
        "model_version": result.model_version,
        # Scalars
        "total_time_s":           result.total_time,
        "sector_times_s":         result.sector_times,
        "max_speed_kmh":          result.max_speed_kmh,
        "min_speed_kmh":          result.min_speed_kmh,
        "avg_speed_kmh":          result.avg_speed_kmh,
        "energy_used_kj":         result.energy_used_kj,
        "avg_power_kw":           result.avg_power_kw,
        "terminal_velocity_kmh":  result.terminal_velocity_kmh,
        "arb_balance":            result.arb_balance,
        # Per-segment arrays
        "telemetry": {
            "distances":           result.distances.tolist(),
            "speeds_ms":           result.speeds.tolist(),
            "speeds_kmh":          (result.speeds * 3.6).tolist(),
            "lateral_g":           result.lateral_g.tolist(),
            "longitudinal_g":      result.longitudinal_g.tolist(),
            "curvatures":          result.curvatures.tolist(),
            "gear_number":         result.gear_number.tolist(),
            "drive_force_n":       result.drive_force_n.tolist(),
            "aero_downforce_n":    result.aero_downforce_n.tolist(),
            "aero_drag_n":         result.aero_drag_n.tolist(),
            "wheel_load_fl_n":     result.wheel_loads_n[0].tolist(),
            "wheel_load_fr_n":     result.wheel_loads_n[1].tolist(),
            "wheel_load_rl_n":     result.wheel_loads_n[2].tolist(),
            "wheel_load_rr_n":     result.wheel_loads_n[3].tolist(),
            # Suspension attitude telemetry
            "pitch_deg":           result.pitch_deg.tolist(),
            "roll_deg":            result.roll_deg.tolist(),
            "ride_height_front_mm": result.ride_height_front.tolist(),
            "ride_height_rear_mm":  result.ride_height_rear.tolist(),
            # Tire utilization & force margins (Section 8)
            "tire_utilization_x":        result.tire_utilization_x.tolist() if len(result.tire_utilization_x) else [],
            "tire_utilization_y":        result.tire_utilization_y.tolist() if len(result.tire_utilization_y) else [],
            "tire_utilization_combined": result.tire_utilization_combined.tolist() if len(result.tire_utilization_combined) else [],
            "ax_available_ms2":          result.ax_available.tolist() if len(result.ax_available) else [],
            "ay_available_ms2":          result.ay_available.tolist() if len(result.ay_available) else [],
        },
        # GGV envelope & 3D surface
        "ggv": {
            "speeds_ms":          result.ggv_speeds.tolist()           if len(result.ggv_speeds)           else [],
            "ay_max_ms2":         result.ggv_ay_max.tolist()           if len(result.ggv_ay_max)           else [],
            "ax_accel_ms2":       result.ggv_ax_accel.tolist()         if len(result.ggv_ax_accel)         else [],
            "ax_brake_ms2":       result.ggv_ax_brake.tolist()         if len(result.ggv_ax_brake)         else [],
            "ay_frac":            result.ggv_ay_frac.tolist()          if hasattr(result, "ggv_ay_frac") and len(result.ggv_ay_frac) else [],
            "ax_accel_surface":   result.ggv_ax_accel_surface.tolist() if hasattr(result, "ggv_ax_accel_surface") and len(result.ggv_ax_accel_surface) else [],
            "ax_brake_surface":   result.ggv_ax_brake_surface.tolist() if hasattr(result, "ggv_ax_brake_surface") and len(result.ggv_ax_brake_surface) else [],
            "ggv_type":           getattr(result, "ggv_type", "INTERPOLATED_PRE_COMPUTED"),
        },
        # Diagnostics and transparency metadata
        "solver_converged":    result.solver_converged,
        "solver_warnings":     result.solver_warnings,
        "model_assumptions":   result.model_assumptions.to_dict() if hasattr(result, "model_assumptions") and hasattr(result.model_assumptions, "to_dict") else {},
        "simulation_metadata": result.simulation_metadata.to_dict() if hasattr(result, "simulation_metadata") and hasattr(result.simulation_metadata, "to_dict") else {},
        # 2D Circuit Track Coordinates (Phase 3)
        "track_coordinates": (
            _get_track_coordinates(result.distances, result.curvatures)
            if len(result.distances) >= 2 and len(result.curvatures) >= 2
            else {"x": [], "y": [], "heading_rad": [], "is_closed": False, "closure_error_m": 0.0}
        ),
    }
    # ERS telemetry (only if ERS was active — i.e. arrays are non-zero)
    import numpy as _np
    if len(result.ers_soc) > 0 and _np.any(result.ers_soc != 0):
        d["ers"] = {
            "lap_time_delta_s":   result.ers_lap_time_delta_s,
            "soc":                result.ers_soc.tolist(),
            "deploy_force_n":     result.ers_deploy_force_n.tolist(),
            "deploy_kw":          result.ers_deploy_kw.tolist(),
            "regen_kw":           result.ers_regen_kw.tolist(),
        }
    # Tire thermal telemetry (only if active)
    if len(result.tire_temp_fl) > 0 and _np.any(result.tire_temp_fl != 0):
        d["tire_thermal"] = {
            "temp_fl_c":  result.tire_temp_fl.tolist(),
            "temp_fr_c":  result.tire_temp_fr.tolist(),
            "temp_rl_c":  result.tire_temp_rl.tolist(),
            "temp_rr_c":  result.tire_temp_rr.tolist(),
            "mu_scale":   result.tire_mu_scale.tolist(),
        }
    return d



def _build_dynamic_vehicle_params(
    vehicle: LapSimVehicle,
    v_input: Optional[VehicleInput],
    tire_model: Optional[str] = None,
) -> DynamicVehicleParams:
    """Map LapSimVehicle and VehicleInput into authoritative DynamicVehicleParams."""
    mp = vehicle.mass_props
    ae = vehicle.aero
    pt = vehicle.powertrain
    sc = vehicle.suspension

    diff_cfg = DifferentialConfig()
    drivetrain = "RWD"
    tm = tire_model
    if v_input and v_input.differential:
        d = v_input.differential
        drivetrain = d.drivetrain_layout or "RWD"
        try:
            dtype = DifferentialType(d.diff_type)
        except Exception:
            dtype = DifferentialType.OPEN
        diff_cfg = DifferentialConfig(
            diff_type=dtype,
            bias_ratio=d.bias_ratio if d.bias_ratio is not None else 3.0,
            preload_nm=d.preload_nm if d.preload_nm is not None else 60.0,
            ramp_angle_accel_deg=d.ramp_angle_accel_deg if d.ramp_angle_accel_deg is not None else 45.0,
            ramp_angle_decel_deg=d.ramp_angle_decel_deg if d.ramp_angle_decel_deg is not None else 60.0,
        )

    if tm is None and v_input is not None:
        tm = v_input.tire_model or v_input.tire_model_type
    if tm is None:
        tm = "DYNAMIC"

    k_sp_f = sc.k_spring_front if sc and sc.k_spring_front else 65_000.0
    k_sp_r = sc.k_spring_rear if sc and sc.k_spring_rear else 85_000.0
    k_arb_f = sc.k_arb_front if sc and sc.k_arb_front else 25_000.0
    k_arb_r = sc.k_arb_rear if sc and sc.k_arb_rear else 18_000.0
    rh_f = sc.ride_height_front if sc and sc.ride_height_front else 30.0
    rh_r = sc.ride_height_rear if sc and sc.ride_height_rear else 55.0

    return DynamicVehicleParams(
        mass_kg=mp.total_mass,
        wheelbase_m=mp.wheelbase,
        a_m=mp.cog_dist_front,
        b_m=max(0.5, mp.wheelbase - mp.cog_dist_front),
        tw_f_m=mp.track_front,
        tw_r_m=mp.track_rear,
        cg_height_m=mp.h_cog,
        cd_base=ae.cd_base,
        cl_base=ae.cl_base,
        frontal_area_m2=ae.frontal_area,
        gear_ratios=pt.gear_ratios,
        shift_time_s=pt.shift_time_s,
        rev_limit_rpm=pt.rev_limit,
        wheel_radius_m=pt.wheel_radius,
        k_spring_front_nm=k_sp_f,
        k_spring_rear_nm=k_sp_r,
        k_arb_front_nm=k_arb_f,
        k_arb_rear_nm=k_arb_r,
        ref_ride_height_front_mm=rh_f,
        ref_ride_height_rear_mm=rh_r,
        diff_rear=diff_cfg,
        drivetrain_layout=drivetrain,
        tire_model_type=tm.upper(),
    )


def _extract_track_segments(request_data: Dict[str, Any]) -> List[TrackSegment]:
    """Parse track segments from request payload."""
    latitudes  = request_data.get("latitudes")
    longitudes = request_data.get("longitudes")
    distances  = request_data.get("distances")
    curvatures = request_data.get("curvatures")

    if latitudes and longitudes:
        if len(latitudes) != len(longitudes):
            raise HTTPException(400, "Latitude and longitude arrays must be the same length.")
        if len(latitudes) > MAX_GPS_POINTS:
            raise HTTPException(422, f"GPS track too long. Maximum {MAX_GPS_POINTS:,} points.")
        elevations = request_data.get("elevations")
        try:
            return parse_track_from_gps(latitudes, longitudes, elevations)
        except Exception as e:
            raise HTTPException(422, f"Failed to parse GPS track: {e}")

    elif distances and curvatures:
        if len(distances) != len(curvatures) and len(distances) != len(curvatures) + 1:
            raise HTTPException(400, "distances and curvatures must be compatible lengths.")
        elevations  = request_data.get("elevations")
        bank_angles = request_data.get("bank_angles")
        sectors     = request_data.get("sectors")
        try:
            return parse_track_from_curvature(distances, curvatures, elevations, bank_angles, sectors)
        except Exception as e:
            raise HTTPException(422, f"Failed to parse curvature track: {e}")

    else:
        raise HTTPException(400, "Provide either (latitudes + longitudes) or (distances + curvatures).")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/lap-sim/simulate",
    summary="Coupled 3-Pass GGV & Closed-Loop QSS Lap Simulation",
    dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))],
)
async def simulate_lap_endpoint(
    request_data: Dict[str, Any],
    user: UserContext = Depends(verify_api_key),
    _limiter: Any = Depends(RateLimiter("rate_limit_simulate")),
):
    """
    Locked JSON Contract endpoint for Coupled 3-Pass GGV & Closed-Loop QSS Lap Solver.
    Supports:
      - Built-in tracks: 'spa', 'silverstone', 'monza', 'fsae_endurance'
      - Custom segment arrays: [{type, length_m, radius_m, banking_deg, grade_pct}]
      - Telemetry CSV / data: [{time_s, speed_ms, lat_g}]
      - Vehicle & Suspension parameters
    """
    # 1. Track resolution
    mode_arg = str(request_data.get("mode", "")).lower().strip()
    track_arg = request_data.get("track", "spa")
    segments_arg = request_data.get("segments")
    telemetry_arg = request_data.get("telemetry")
    csv_data = request_data.get("csv_data")

    if mode_arg == "custom" and segments_arg:
        track_arg = None
    elif mode_arg == "csv" and (telemetry_arg or csv_data):
        track_arg = None
    elif segments_arg is not None and len(segments_arg) > 0:
        track_arg = None

    if isinstance(csv_data, str) and len(csv_data.strip()) > 0:
        import io, csv
        reader = csv.DictReader(io.StringIO(csv_data.strip()))
        rows = list(reader)
        if len(rows) > 0 and "time_s" in rows[0]:
            telemetry_arg = {
                "time_s": [float(r["time_s"]) for r in rows],
                "speed_ms": [float(r["speed_ms"]) for r in rows],
                "lat_g": [float(r["lat_g"]) for r in rows],
            }
    elif isinstance(csv_data, list) and len(csv_data) > 0:
        telemetry_arg = {
            "time_s": [float(r["time_s"]) for r in csv_data],
            "speed_ms": [float(r["speed_ms"]) for r in csv_data],
            "lat_g": [float(r["lat_g"]) for r in csv_data],
        }

    KNOWN_PRESETS = {"spa", "silverstone", "monza", "fsae_endurance", "spa_francorchamps", "silverstone_gp", "autodromo_nazionale_monza", "fsae"}
    is_preset_requested = isinstance(track_arg, str) and track_arg.lower().strip() in KNOWN_PRESETS
    # V2 Phase 3: opt-in documented elevation profile (Spa only; other circuits stay z = 0).
    if is_preset_requested and request_data.get("with_elevation") is True:
        track_arg = get_builtin_track(track_arg, with_elevation=True)

    # Backward compatibility: top-level distances and curvatures
    if not is_preset_requested and not segments_arg and not telemetry_arg and "distances" in request_data and "curvatures" in request_data:
        dists = request_data["distances"]
        curvs = request_data["curvatures"]
        if len(dists) > 10_000:
            raise HTTPException(422, "Track point count exceeds maximum 10,000 points.")
        track_arg = parse_track_from_curvature(
            dists,
            curvs,
            elevations=request_data.get("elevations"),
            bank_angles=request_data.get("bank_angles"),
            sectors=request_data.get("sectors"),
        )
    elif not is_preset_requested and not segments_arg and not telemetry_arg and "latitudes" in request_data and "longitudes" in request_data:
        lats = request_data["latitudes"]
        lons = request_data["longitudes"]
        if len(lats) > 10_000:
            raise HTTPException(422, "GPS track too long. Maximum 10,000 points.")
        track_arg = parse_track_from_gps(
            lats,
            lons,
            request_data.get("elevations"),
        )

    # 2. Vehicle & Suspension parameters
    vehicle_dict = dict(request_data.get("vehicle", {})) if isinstance(request_data.get("vehicle"), dict) else {}
    if "suspension" in request_data and isinstance(request_data["suspension"], dict):
        if "suspension" not in vehicle_dict:
            vehicle_dict["suspension"] = {}
        vehicle_dict["suspension"].update(request_data["suspension"])

    # Also top-level vehicle and suspension overrides
    all_param_keys = (
        "mass_kg", "mass", "total_mass", "weight_dist_front", "weight_dist_f", "weight_dist",
        "cg_height_m", "h_cog", "wheelbase_m", "wheelbase",
        "track_front_m", "track_f_m", "track_front", "track_rear_m", "track_r_m", "track_rear",
        "cl_total", "cl", "aero_cl", "cl_base", "cd_total", "cd", "aero_cd", "cd_base",
        "frontal_area_m2", "frontal_area", "aero_balance_front", "cop_front", "cop_fraction",
        "rho_air", "c_rr", "crr", "rolling_resistance",
        "k_spring_front_n_m", "k_spring_f", "k_spring_front", "front_spring_rate",
        "k_spring_rear_n_m", "k_spring_r", "k_spring_rear", "rear_spring_rate",
        "motion_ratio_front", "mr_f", "motion_ratio_rear", "mr_r",
        "static_rh_front_mm", "static_rh_rear_mm", "front_ride_height", "rear_ride_height",
        "k_arb_front_nm_rad", "k_arb_f", "k_arb_front", "front_arb",
        "k_arb_rear_nm_rad", "k_arb_r", "k_arb_rear", "rear_arb",
        "roll_center_front_m", "roll_center_f_m", "roll_center_front", "front_rc_height",
        "roll_center_rear_m", "roll_center_r_m", "roll_center_rear", "rear_rc_height",
        "camber_gain_front", "camber_gain_rear",
        "mu_0", "fz_nom_n", "Fz_nom", "k_load_sensitivity", "k_load", "tire_mu", "mu",
        "max_power_kw", "max_power", "gear_ratios", "final_drive",
        "max_rpm", "rev_limit", "wheel_radius_m", "wheel_radius",
        "drivetrain_efficiency", "drivetrain_loss", "shift_time_s",
        "max_brake_force_n", "max_brake_force", "brake_bias_front", "brake_bias_f", "brake_front_bias",
    )
    for k in all_param_keys:
        if k in request_data and k not in vehicle_dict:
            vehicle_dict[k] = request_data[k]

    is_closed = bool(request_data.get("is_closed", True))

    import asyncio
    loop = asyncio.get_running_loop()

    # Interactive solves skip the ~25-lap setup-response surface unless the
    # caller explicitly asks for it (include_surface=true): ~0.5-1.5 s instead
    # of 21-51 s.
    include_surface = bool(request_data.get("include_surface", False))
    try:
        sim_res = await loop.run_in_executor(
            None,
            lambda: simulate_lap(
                vehicle=vehicle_dict,
                track=track_arg,
                segments=segments_arg,
                telemetry=telemetry_arg,
                is_closed=is_closed,
                compute_surface=include_surface,
            )
        )
    except HTTPException:
        raise
    except ValueError as e:
        # Structured 422 for unusable telemetry/segment input (never a silent
        # built-in-track substitution).
        raise HTTPException(422, f"Invalid track or telemetry input: {e}")
    except Exception as e:
        logger.error(f"Lap simulation failed: {e}")
        raise HTTPException(500, "Simulation failed due to numerical convergence or invalid input parameters.")

    # Build locked contract output
    response_payload = sim_res.to_contract_dict()

    # Add backward-compatible fields
    response_payload.update({
        "status": "success",
        "detected_speed_units": getattr(sim_res, "detected_speed_units", None),
        "total_time_s": sim_res.lap_time_s,
        "front_lltd_pct": round(float(sim_res.front_lltd_pct), 1),
        "min_rh_front_mm": sim_res.min_rh_front_mm,
        "min_rh_rear_mm": sim_res.min_rh_rear_mm,
        "bottoming_events_count": sim_res.bottoming_events_count,
        "setup_surface": sim_res.setup_surface,
        "aero_drag_energy_kj": sim_res.aero_drag_energy_kj,
        "rolling_energy_kj": sim_res.rolling_energy_kj,
        "braking_energy_kj": sim_res.braking_energy_kj,
        "energy_balance_error_pct": sim_res.energy_balance_error_pct,
        "max_roll_deg": sim_res.max_roll_deg,
        "max_pitch_deg": sim_res.max_pitch_deg,
        "telemetry": {
            "distances": sim_res.trace["s_m"],
            "speeds_ms": [s / 3.6 for s in sim_res.trace["speed_kmh"]],
            "speeds_kmh": sim_res.trace["speed_kmh"],
            "lateral_g": sim_res.trace["lat_g"],
            "longitudinal_g": sim_res.trace["long_g"],
            "throttle_pct": sim_res.trace["throttle_pct"],
            "brake_pct": sim_res.trace["brake_pct"],
            "gear_number": sim_res.trace["gear"],
            "aero_downforce_n": sim_res.trace["downforce_n"],
            "limiting_factor": sim_res.trace["limiting_factor"],
            "ride_height_front_mm": sim_res.trace.get("ride_height_front_mm", []),
            "ride_height_rear_mm": sim_res.trace.get("ride_height_rear_mm", []),
            "pitch_deg": sim_res.trace.get("pitch_deg", []),
            "roll_deg": sim_res.trace.get("roll_deg", []),
            "z_m": sim_res.trace.get("z_m", []),
            "dz_ds": sim_res.trace.get("dz_ds", []),
            "kappa_z_per_m": sim_res.trace.get("kappa_z_per_m", []),
            "vertical_g": sim_res.trace.get("vertical_g", []),
            "vertical_load_delta_n": sim_res.trace.get("vertical_load_delta_n", []),
            "compression_mm": sim_res.trace.get("compression_mm", []),
            "compression_front_mm": sim_res.trace.get("compression_front_mm", []),
            "compression_rear_mm": sim_res.trace.get("compression_rear_mm", []),
        },
        "ggv": {
            "speeds_kmh": sim_res.ggv_envelope["speeds_kmh"],
            "max_lat_g": sim_res.ggv_envelope["max_lat_g"],
            "max_accel_g": sim_res.ggv_envelope["max_accel_g"],
            "max_brake_g": sim_res.ggv_envelope["max_brake_g"],
            "ay_max_g": sim_res.ggv_envelope.get("ay_max_g", sim_res.ggv_envelope["max_lat_g"]),
            "ax_accel_g": sim_res.ggv_envelope.get("ax_accel_g", sim_res.ggv_envelope["max_accel_g"]),
            "ax_brake_g": sim_res.ggv_envelope.get("ax_brake_g", sim_res.ggv_envelope["max_brake_g"]),
        },
        "track_coordinates": {
            "x": sim_res.trace["x_m"],
            "y": sim_res.trace["y_m"],
        },
    })

    return response_payload


class WhyChainRequest(BaseModel):
    """Setup A vs B levers. Lever names are LapSimVehicleParams attributes."""
    model_config = ConfigDict(extra="forbid")
    setup_a: Dict[str, float]
    setup_b: Dict[str, float]
    track: str = "spa"
    corner: Optional[Dict[str, float]] = None
    base_vehicle: Optional[Dict[str, Any]] = None


@router.post(
    "/lap-sim/why-chain",
    summary="Deterministic coupled QSS Why Chain (Setup A vs B)",
    dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))],
)
async def why_chain_endpoint(
    body: WhyChainRequest,
    user: UserContext = Depends(verify_api_key),
    _limiter: Any = Depends(RateLimiter("rate_limit_simulate")),
):
    """Numbers, units and solver sources only. Unreachable links return NOT_MODELED."""
    from suspensionlab.physics.why_chain import compute_why_chain
    try:
        return compute_why_chain(body.setup_a, body.setup_b, track=body.track,
                                 corner=body.corner, base_vehicle=body.base_vehicle)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/lapsim/run")
@router.post("/lap-sim/run")
@router.post("/run")
async def run_lap_sim(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Run a QSS or 14-DOF Dynamic lap simulation from GPS arrays or pre-computed curvature data."""
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    segments = _extract_track_segments(request_data)

    # Build vehicle
    v_input = None
    if "vehicle" in request_data:
        try:
            v_input = VehicleInput(**request_data["vehicle"])
        except Exception as e:
            raise HTTPException(422, f"Invalid vehicle parameters: {e}")

    vehicle = _build_vehicle(v_input)

    # Solver Mode Selection
    solver_mode = request_data.get("solver_mode", FAST_QUASI_STEADY).upper()

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        if solver_mode in ("DYNAMIC", "DYNAMIC_TRANSIENT_14DOF", "TRANSIENT", "HIGH_FIDELITY_LAP"):
            track_dist = np.array([s.distance for s in segments])
            track_curv = np.array([s.curvature for s in segments])
            track_elev = np.array([s.elevation for s in segments])
            track_bank = np.array([s.bank_angle for s in segments])
            dyn_track = DynamicTrackModel(
                distances=track_dist,
                curvatures=track_curv,
                elevations=track_elev,
                bank_angles=track_bank,
            )
            dyn_params = _build_dynamic_vehicle_params(
                vehicle, v_input, tire_model=request_data.get("tire_model") or request_data.get("tire_model_type")
            )
            dyn_sim = DynamicLapSimulator(params=dyn_params)
            result = await loop.run_in_executor(None, solve_dynamic_lap, dyn_sim, dyn_track)
        else:
            result = await loop.run_in_executor(None, solve_lap, vehicle, segments)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(422, f"Invalid track or telemetry input: {e}")
    except Exception as e:
        logger.error(f"Lap simulation failed: {e}")
        raise HTTPException(500, "Simulation failed due to numerical convergence or invalid input parameters.")

    return _result_to_dict(result)


@router.post("/lapsim/cross_validate")
@router.post("/lap-sim/cross-validate")
async def cross_validate_lap_sim(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Execute and cross-validate Fast QSS with 14-DOF Dynamic simulation on the same circuit."""
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=2)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=2)

    segments = _extract_track_segments(request_data)

    v_input = None
    if "vehicle" in request_data:
        try:
            v_input = VehicleInput(**request_data["vehicle"])
        except Exception as e:
            raise HTTPException(422, f"Invalid vehicle parameters: {e}")

    vehicle = _build_vehicle(v_input)

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        # 1. Fast QSS Pass
        res_qss = await loop.run_in_executor(None, solve_lap, vehicle, segments)

        # 2. Dynamic 14-DOF Pass
        track_dist = np.array([s.distance for s in segments])
        track_curv = np.array([s.curvature for s in segments])
        track_elev = np.array([s.elevation for s in segments])
        track_bank = np.array([s.bank_angle for s in segments])
        dyn_track = DynamicTrackModel(
            distances=track_dist,
            curvatures=track_curv,
            elevations=track_elev,
            bank_angles=track_bank,
        )
        dyn_params = _build_dynamic_vehicle_params(
            vehicle, v_input, tire_model=request_data.get("tire_model") or request_data.get("tire_model_type")
        )
        dyn_sim = DynamicLapSimulator(params=dyn_params)
        res_dyn = await loop.run_in_executor(None, solve_dynamic_lap, dyn_sim, dyn_track)

        # 3. Cross-Validation Delta Decomposition
        cross_val = cross_validate_qss_and_transient(res_qss, res_dyn)

        return {
            "status": "success",
            "qss": _result_to_dict(res_qss),
            "dyn": _result_to_dict(res_dyn),
            "cross_validation": cross_val.to_dict(),
        }
    except Exception as e:
        raise HTTPException(500, f"Cross-validation simulation failed: {e}")


@router.post("/lapsim/maneuver")
@router.post("/lap-sim/maneuver")
async def run_handling_maneuver(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Execute standardized time-domain vehicle handling maneuver (step steer, ramp, sine sweep, etc.)."""
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    v_input = None
    if "vehicle" in request_data:
        try:
            v_input = VehicleInput(**request_data["vehicle"])
        except Exception as e:
            raise HTTPException(422, f"Invalid vehicle parameters: {e}")

    vehicle = _build_vehicle(v_input)
    dyn_params = _build_dynamic_vehicle_params(
        vehicle, v_input, tire_model=request_data.get("tire_model") or request_data.get("tire_model_type")
    )
    sim = DynamicLapSimulator(params=dyn_params)

    maneuver_type = request_data.get("maneuver_type", "STEP_STEER")
    initial_speed_mps = float(request_data.get("initial_speed_mps", 30.0))
    params = request_data.get("parameters", {})

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        res = await loop.run_in_executor(
            None,
            lambda: solve_transient_maneuver(sim, maneuver_type=maneuver_type, initial_speed_mps=initial_speed_mps, **params)
        )
        return res.to_dict()
    except Exception as e:
        raise HTTPException(500, f"Maneuver simulation failed: {e}")


@router.post("/lapsim/maneuver/compare")
@router.post("/lap-sim/maneuver/compare")
async def compare_handling_maneuver_endpoint(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Compare vehicle handling maneuver under QUASI_STEADY vs DYNAMIC tire relaxation."""
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    v_input = None
    if "vehicle" in request_data:
        try:
            v_input = VehicleInput(**request_data["vehicle"])
        except Exception as e:
            raise HTTPException(422, f"Invalid vehicle parameters: {e}")

    vehicle = _build_vehicle(v_input)
    dyn_params = _build_dynamic_vehicle_params(vehicle, v_input)
    sim = DynamicLapSimulator(params=dyn_params)

    maneuver_type = request_data.get("maneuver_type", "STEP_STEER")
    initial_speed_mps = float(request_data.get("initial_speed_mps", 30.0))
    params = request_data.get("parameters", {})

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        res = await loop.run_in_executor(
            None,
            lambda: compare_quasi_steady_vs_dynamic(sim, maneuver_type=maneuver_type, initial_speed_mps=initial_speed_mps, **params)
        )
        return res
    except Exception as e:
        raise HTTPException(500, f"Maneuver comparison failed: {e}")


@router.post("/lapsim/upload_gpx")
@router.post("/lap-sim/upload_gpx")
@router.post("/upload_gpx")
async def upload_gpx(
    file: UploadFile = File(...),
    user=Depends(verify_api_key),
):
    """Parse a GPX file into lat/lon/elevation arrays ready for /lapsim/run."""
    if not file.filename.lower().endswith(".gpx"):
        raise HTTPException(400, "Only .gpx files are supported.")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large. Maximum size is 5 MB.")

    try:
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, ET.fromstring, content)

        gpx = await loop.run_in_executor(None, gpxpy.parse, content)
        lats, lons, elevs = [], [], []
        point_count = 0

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    point_count += 1
                    if point_count > MAX_GPS_POINTS:
                        raise ValueError(f"GPX track too long. Maximum {MAX_GPS_POINTS:,} points.")
                    lats.append(point.latitude)
                    lons.append(point.longitude)
                    elevs.append(point.elevation or 0.0)

        return {"latitudes": lats, "longitudes": lons, "elevations": elevs, "n_points": point_count}

    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(400, f"Failed to parse GPX: {e}")


@router.get("/lapsim/ggv")
@router.get("/lap-sim/ggv")
@router.get("/ggv")
async def get_ggv_envelope(
    mass: float = 800.0,
    aero_cl: float = 1.8,
    aero_cd: float = 0.95,
    n_speeds: int = 40,
    user=Depends(verify_api_key),
):
    """Return the pre-computed GGV envelope for a vehicle configuration.

    Useful for visualising the performance envelope on the frontend
    without running a full lap simulation.
    """
    vehicle = LapSimVehicle()
    vehicle.mass_props.total_mass = mass
    vehicle.aero.cl_base = aero_cl
    vehicle.aero.cd_base = aero_cd

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        n_speeds = min(max(n_speeds, 10), 80)
        await loop.run_in_executor(None, lambda: vehicle.build_ggv(n_speeds=n_speeds))
    except Exception as e:
        raise HTTPException(500, f"GGV computation failed: {e}")

    return {
        "speeds_ms":          vehicle._ggv_speeds.tolist(),
        "speeds_kmh":         (vehicle._ggv_speeds * 3.6).tolist(),
        "ay_max_ms2":         vehicle._ggv_ay_max.tolist(),
        "ax_accel_ms2":       vehicle._ggv_ax_accel[:, 0].tolist(),
        "ax_brake_ms2":       vehicle._ggv_ax_brake[:, 0].tolist(),
        "ay_frac":            vehicle._ggv_ay_frac.tolist() if vehicle._ggv_ay_frac is not None else [],
        "ax_accel_surface":   vehicle._ggv_ax_accel.tolist() if vehicle._ggv_ax_accel is not None else [],
        "ax_brake_surface":   vehicle._ggv_ax_brake.tolist() if vehicle._ggv_ax_brake is not None else [],
        "ggv_type":           "INTERPOLATED_PRE_COMPUTED",
        "terminal_velocity_kmh": float(vehicle.terminal_velocity() * 3.6),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Setup sensitivity endpoint — the "intelligence platform" core
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/lapsim/sensitivity",
             summary="Vehicle setup sensitivity analysis (ARB, ride height, springs)")
@router.post("/lap-sim/sensitivity",
             summary="Vehicle setup sensitivity analysis (ARB, ride height, springs)")
async def setup_sensitivity(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Compute setup sensitivity: how does changing suspension settings affect
    load transfer, aero balance, and understeer tendency?

    This is the core of the Vehicle Dynamics Intelligence Platform (Issue 11).
    Does NOT run a full lap simulation — returns analytical sensitivity results
    in milliseconds, suitable for real-time setup tuning.

    Request body (JSON)
    -------------------
    vehicle           : { ... }           Vehicle config (same as /run)
    speed_ms          : float             Representative speed [m/s] (default 50)
    lateral_g         : float             Representative cornering g (default 2.0)
    delta_arb_front   : float             ARB stiffness perturbation [N/m] (default 5000)
    delta_ride_height : float             Ride height perturbation [mm] (default 5.0)

    Response
    --------
    {
        "arb_balance"              : { baseline, perturbed, delta_lt_front, understeer_tendency },
        "ride_height_sensitivity"  : { delta_downforce_total, delta_df_front, delta_df_rear },
        "suspension_info"          : { k_spring_front, k_spring_rear, k_arb_front, k_arb_rear,
                                       roll_stiffness_front, roll_stiffness_rear, ... },
        "operating_point"          : { speed_ms, lateral_g, q_dynamic },
    }
    """
    v_input = None
    if "vehicle" in request_data:
        try:
            v_input = VehicleInput(**request_data["vehicle"])
        except Exception as e:
            raise HTTPException(422, f"Invalid vehicle parameters: {e}")

    vehicle = _build_vehicle(v_input)
    mp  = vehicle.mass_props
    sus = vehicle.suspension

    speed_ms          = float(request_data.get("speed_ms",          50.0))
    lateral_g_val     = float(request_data.get("lateral_g",          2.0))
    delta_arb_front   = float(request_data.get("delta_arb_front",  5_000.0))
    delta_ride_height = float(request_data.get("delta_ride_height",    5.0))
    ay                = lateral_g_val * 9.81

    # ARB sensitivity
    arb_sens = vehicle.arb_sensitivity(
        v=speed_ms, ay=ay, delta_arb_front_nm=delta_arb_front
    )

    # Ride height sensitivity
    rh_sens = vehicle.ride_height_sensitivity(
        v=speed_ms, delta_rh_mm=delta_ride_height
    )

    # Suspension info
    K_phi_f = sus.roll_stiffness_front(mp.track_front)
    K_phi_r = sus.roll_stiffness_rear(mp.track_rear)
    K_theta = sus.pitch_stiffness(mp.wheelbase, a=mp.cog_dist_front, b=mp.b)


    q_dyn = 0.5 * vehicle.aero.rho_air * speed_ms ** 2

    return {
        "arb_balance":            arb_sens,
        "ride_height_sensitivity": rh_sens,
        "suspension_info": {
            "k_spring_front_nm":         sus.k_spring_front,
            "k_spring_rear_nm":          sus.k_spring_rear,
            "k_arb_front_nm":            sus.k_arb_front,
            "k_arb_rear_nm":             sus.k_arb_rear,
            "motion_ratio_front":        sus.motion_ratio_front,
            "motion_ratio_rear":         sus.motion_ratio_rear,
            "ride_height_front_mm":      sus.ride_height_front,
            "ride_height_rear_mm":       sus.ride_height_rear,
            "roll_stiffness_front_nmrad": round(K_phi_f, 0),
            "roll_stiffness_rear_nmrad":  round(K_phi_r, 0),
            "roll_stiffness_total_nmrad": round(K_phi_f + K_phi_r, 0),
            "pitch_stiffness_nmrad":      round(K_theta, 0),
            "arb_balance_fraction":       round(arb_sens["baseline_arb_balance"], 4),
        },
        "operating_point": {
            "speed_ms":     speed_ms,
            "speed_kmh":    round(speed_ms * 3.6, 1),
            "lateral_g":    lateral_g_val,
            "q_dynamic_pa": round(q_dyn, 1),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Corner Analysis & Setup Comparison Endpoints (Phase 1 Engineering APIs)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/lapsim/corners")
@router.post("/lap-sim/corners")
async def get_lap_corners(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Detect and analyze corners on a circuit with entry/apex/exit speeds and braking metrics."""
    from suspensionlab.physics.corner_analysis import analyze_lap_corners, classify_zones

    distances = request_data.get("distances")
    curvatures = request_data.get("curvatures")
    speeds = request_data.get("speeds")
    lat_g = request_data.get("lateral_g")
    long_g = request_data.get("longitudinal_g")
    sectors = request_data.get("sectors")

    if not distances or not curvatures:
        raise HTTPException(400, "Must provide distances and curvatures arrays.")

    # If speeds are not provided, run a quick QSS solve to compute them
    if not speeds or not lat_g or not long_g:
        v_input = None
        if "vehicle" in request_data:
            v_input = VehicleInput(**request_data["vehicle"])
        vehicle = _build_vehicle(v_input)
        segments = parse_track_from_curvature(distances, curvatures, sectors=sectors)
        result = solve_lap(vehicle, segments)
        speeds = result.speeds.tolist()
        lat_g = result.lateral_g.tolist()
        long_g = result.longitudinal_g.tolist()
        dt = np.zeros(len(distances))
        for i in range(1, len(distances)):
            ds = distances[i] - distances[i-1]
            v_avg = max(0.5 * (speeds[i] + speeds[i-1]), 0.1)
            dt[i] = ds / v_avg
    else:
        dt = np.zeros(len(distances))
        for i in range(1, len(distances)):
            ds = distances[i] - distances[i-1]
            v_avg = max(0.5 * (speeds[i] + speeds[i-1]), 0.1)
            dt[i] = ds / v_avg

    dist_arr = np.array(distances)
    curv_arr = np.array(curvatures)
    speed_arr = np.array(speeds)
    lat_g_arr = np.array(lat_g)
    long_g_arr = np.array(long_g)

    corners = analyze_lap_corners(
        dist_arr, speed_arr, curv_arr, lat_g_arr, long_g_arr, dt,
        sectors=np.array(sectors) if sectors else None,
    )
    zones = classify_zones(dist_arr, speed_arr, curv_arr, long_g_arr)

    return {
        "num_corners": len(corners),
        "corners": [c.to_dict() for c in corners],
        "track_zones": zones.tolist(),
    }


@router.post("/lapsim/compare")
@router.post("/lap-sim/compare")
async def compare_lap_setups(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Compare two vehicle setups (A vs B) on the same track with causal delta attribution."""
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.physics.lap_delta import compute_lap_delta
    from suspensionlab.physics.corner_analysis import analyze_lap_corners

    distances = request_data.get("distances")
    curvatures = request_data.get("curvatures")
    sectors = request_data.get("sectors")
    elevations = request_data.get("elevations")
    bank_angles = request_data.get("bank_angles")

    if not distances or not curvatures:
        raise HTTPException(400, "Must provide distances and curvatures arrays.")

    v_input_a = None
    if "vehicle_a" in request_data:
        v_input_a = VehicleInput(**request_data["vehicle_a"])
    elif "vehicle" in request_data:
        v_input_a = VehicleInput(**request_data["vehicle"])

    v_input_b = None
    if "vehicle_b" in request_data:
        v_input_b = VehicleInput(**request_data["vehicle_b"])
    else:
        raise HTTPException(400, "Must provide vehicle_b configuration for comparison.")

    vehicle_a = _build_vehicle(v_input_a)
    vehicle_b = _build_vehicle(v_input_b)

    segments = parse_track_from_curvature(
        distances, curvatures, elevations=elevations, bank_angles=bank_angles, sectors=sectors
    )

    res_a = solve_lap(vehicle_a, segments)
    res_b = solve_lap(vehicle_b, segments)

    # Compute corners for both
    dt_a = np.zeros(len(distances))
    dt_b = np.zeros(len(distances))
    for i in range(1, len(distances)):
        ds = distances[i] - distances[i-1]
        dt_a[i] = ds / max(0.5 * (res_a.speeds[i] + res_a.speeds[i-1]), 0.1)
        dt_b[i] = ds / max(0.5 * (res_b.speeds[i] + res_b.speeds[i-1]), 0.1)

    corners_a = analyze_lap_corners(
        res_a.distances, res_a.speeds, res_a.curvatures,
        res_a.lateral_g, res_a.longitudinal_g, dt_a,
    )
    corners_b = analyze_lap_corners(
        res_b.distances, res_b.speeds, res_b.curvatures,
        res_b.lateral_g, res_b.longitudinal_g, dt_b,
    )

    report = compute_lap_delta(res_a, res_b, corners_a=corners_a, corners_b=corners_b)

    return {
        "setup_a": {
            "total_time_s": round(res_a.total_time, 4),
            "max_speed_kmh": round(res_a.max_speed_kmh, 1),
            "avg_speed_kmh": round(res_a.avg_speed_kmh, 1),
        },
        "setup_b": {
            "total_time_s": round(res_b.total_time, 4),
            "max_speed_kmh": round(res_b.max_speed_kmh, 1),
            "avg_speed_kmh": round(res_b.avg_speed_kmh, 1),
        },
        "delta_report": report.to_dict(),
    }


@router.post("/lapsim/sweep")
@router.post("/lap-sim/sweep")
async def sweep_setup(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Evaluate parameter sensitivity sweep across a range of candidate values.
    Returns lap times, deltas, sector times, corner speeds, and numerical gradients (dT/dp).
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.physics.setup_sweep import run_parameter_sweep, SweepParameter

    distances = request_data.get("distances")
    curvatures = request_data.get("curvatures")
    sectors = request_data.get("sectors")
    elevations = request_data.get("elevations")
    bank_angles = request_data.get("bank_angles")

    parameter = request_data.get("parameter")
    values = request_data.get("values")
    baseline_value = request_data.get("baseline_value")
    ggv_resolution = request_data.get("ggv_resolution", [15, 11])

    if not distances or not curvatures:
        raise HTTPException(400, "Must provide distances and curvatures arrays.")
    if len(distances) > 10_000:
        raise HTTPException(422, "Track exceeds 10,000 points.")
    if not parameter or values is None:
        raise HTTPException(400, "Must provide 'parameter' and 'values' for sweep.")
    if len(values) > 50:
        raise HTTPException(422, "Parameter sweep supports a maximum of 50 values.")

    v_input = None
    if "vehicle" in request_data:
        v_input = VehicleInput(**request_data["vehicle"])
    baseline_vehicle = _build_vehicle(v_input)

    track = parse_track_from_curvature(
        distances, curvatures, elevations=elevations, bank_angles=bank_angles, sectors=sectors
    )

    try:
        sweep_result = run_parameter_sweep(
            baseline_vehicle=baseline_vehicle,
            track=track,
            parameter=parameter,
            values=values,
            baseline_val=baseline_value,
            ggv_resolution=tuple(ggv_resolution),
        )
        return sweep_result.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Parameter sweep failed: {str(e)}")


@router.post("/lapsim/correlate")
@router.post("/lap-sim/correlate")
async def correlate_telemetry(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Correlate simulation output against measured telemetry.
    Supports calculating simulation on the fly or passing precomputed simulation traces.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.physics.telemetry_analysis import compare_sim_vs_measured

    telemetry_data = request_data.get("telemetry")
    if not telemetry_data:
        raise HTTPException(400, "Must provide 'telemetry' dictionary with measured data.")

    distance_step_m = float(request_data.get("distance_step_m", 2.0))
    session_id = str(request_data.get("session_id", "telemetry_session_01"))

    # Determine simulation source
    if "sim_result" in request_data:
        sim_data = request_data["sim_result"]

        class SimResultProxy:
            distances = np.asarray(sim_data.get("distances", []), dtype=float)
            speeds = np.asarray(sim_data.get("speeds", sim_data.get("speeds_ms", [])), dtype=float)
            lateral_g = np.asarray(sim_data.get("lateral_g", []), dtype=float)
            longitudinal_g = np.asarray(sim_data.get("longitudinal_g", []), dtype=float)

        sim_obj = SimResultProxy()
    else:
        distances = request_data.get("distances")
        curvatures = request_data.get("curvatures")
        if not distances or not curvatures:
            raise HTTPException(400, "Must provide either 'sim_result' or 'distances' and 'curvatures' to run simulation.")
        sectors = request_data.get("sectors")
        elevations = request_data.get("elevations")
        bank_angles = request_data.get("bank_angles")

        v_input = None
        if "vehicle" in request_data:
            v_input = VehicleInput(**request_data["vehicle"])
        vehicle = _build_vehicle(v_input)
        track = parse_track_from_curvature(
            distances, curvatures, elevations=elevations, bank_angles=bank_angles, sectors=sectors
        )
        sim_obj = solve_lap(vehicle, track)

    try:
        report = compare_sim_vs_measured(
            sim_obj,
            telemetry_data,
            distance_step_m=distance_step_m,
            session_id=session_id,
        )
        return report.to_dict()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Telemetry correlation failed: {str(e)}")


@router.post("/lapsim/decision")
@router.post("/lap-sim/decision")
async def race_engineer_decision_endpoint(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Synthesizes an evidence-backed race engineering decision answering:
    "Where am I losing lap time, why, what setup change should I test, and what evidence supports that recommendation?"
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="decision")
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    from suspensionlab.physics.race_engineer_decision import synthesize_race_engineer_decision

    distances = request_data.get("distances")
    curvatures = request_data.get("curvatures")
    sectors = request_data.get("sectors")
    elevations = request_data.get("elevations")
    bank_angles = request_data.get("bank_angles")

    if not distances or not curvatures:
        raise HTTPException(400, "Must provide distances and curvatures arrays.")

    v_input_a = None
    if "vehicle_a" in request_data:
        v_input_a = VehicleInput(**request_data["vehicle_a"])
    elif "vehicle" in request_data:
        v_input_a = VehicleInput(**request_data["vehicle"])
    baseline_vehicle = _build_vehicle(v_input_a)

    v_input_b = None
    if "vehicle_b" in request_data:
        v_input_b = VehicleInput(**request_data["vehicle_b"])
    else:
        # Default perturbation if no candidate vehicle is given (e.g. baseline test)
        v_input_b = VehicleInput(mass=baseline_vehicle.mass_props.total_mass)
    candidate_vehicle = _build_vehicle(v_input_b)

    track = parse_track_from_curvature(
        distances, curvatures, elevations=elevations, bank_angles=bank_angles, sectors=sectors
    )

    try:
        res_a = solve_lap(baseline_vehicle, track)
        res_b = solve_lap(candidate_vehicle, track)

        decision = synthesize_race_engineer_decision(
            res_a,
            res_b,
            setup_baseline=request_data.get("setup_baseline"),
            setup_candidate=request_data.get("setup_candidate"),
            sensitivities=request_data.get("sensitivities"),
        )
        return decision.to_dict()
    except Exception as e:
        raise HTTPException(500, f"Race engineer decision synthesis failed: {str(e)}")


