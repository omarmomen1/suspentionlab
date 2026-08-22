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
import numpy as np

from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.physics.lap_sim import (
    LapSimVehicle, MassProperties, AeroMap, PowertrainModel,
    parse_track_from_gps, parse_track_from_curvature, solve_lap, TrackSegment,
)
from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.suspension_aero_coupling import (
    SuspensionConfig,
    CoupledVehicleModel,
)

router = APIRouter(prefix="/lapsim", tags=["Lap Simulation"])

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


class VehicleInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    # Legacy scalar overrides (backwards-compatible)
    mass:      Optional[float] = None
    aero_cl:   Optional[float] = None
    aero_cd:   Optional[float] = None
    max_power: Optional[float] = None   # W — scales torque curve proportionally

    # Sub-model overrides
    mass_props:  Optional[MassPropertiesInput]  = None
    aero:        Optional[AeroMapInput]         = None
    powertrain:  Optional[PowertrainInput]      = None
    tire_coeffs: Optional[TireCoeffsInput]      = None
    suspension:  Optional[SuspensionInput]      = None
    use_coupling: bool = False   # enable ride-height/aero coupling iteration


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


def _result_to_dict(result) -> Dict:
    """Serialise LapSimResult to JSON-safe dict."""
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
        },
        # GGV envelope
        "ggv": {
            "speeds_ms":    result.ggv_speeds.tolist()   if len(result.ggv_speeds)   else [],
            "ay_max_ms2":   result.ggv_ay_max.tolist()   if len(result.ggv_ay_max)   else [],
            "ax_accel_ms2": result.ggv_ax_accel.tolist() if len(result.ggv_ax_accel) else [],
            "ax_brake_ms2": result.ggv_ax_brake.tolist() if len(result.ggv_ax_brake) else [],
        },
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



# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_lap_sim(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Run a QSS lap simulation from GPS arrays or pre-computed curvature data.

    Request body (JSON)
    -------------------
    Either GPS mode:
        latitudes  : [float, ...]
        longitudes : [float, ...]
        elevations : [float, ...] (optional)

    Or curvature mode:
        distances   : [float, ...] in metres
        curvatures  : [float, ...] in 1/m
        elevations  : [float, ...] (optional)
        bank_angles : [float, ...] in radians (optional)
        sectors     : [int, ...] 1-based (optional)

    Plus optional vehicle config:
        vehicle : { mass, aero_cl, aero_cd, max_power, mass_props, aero, powertrain, tire_coeffs }
    """
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
            segments = parse_track_from_gps(latitudes, longitudes, elevations)
        except Exception as e:
            raise HTTPException(422, f"Failed to parse GPS track: {e}")

    elif distances and curvatures:
        if len(distances) != len(curvatures):
            raise HTTPException(400, "distances and curvatures must be the same length.")
        elevations  = request_data.get("elevations")
        bank_angles = request_data.get("bank_angles")
        sectors     = request_data.get("sectors")
        try:
            segments = parse_track_from_curvature(distances, curvatures, elevations, bank_angles, sectors)
        except Exception as e:
            raise HTTPException(422, f"Failed to parse curvature track: {e}")

    else:
        raise HTTPException(400, "Provide either (latitudes + longitudes) or (distances + curvatures).")

    # Build vehicle
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
        result = await loop.run_in_executor(None, solve_lap, vehicle, segments)
    except Exception as e:
        raise HTTPException(500, f"Lap simulation failed: {e}")

    return _result_to_dict(result)


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
        "speeds_ms":    vehicle._ggv_speeds.tolist(),
        "speeds_kmh":   (vehicle._ggv_speeds * 3.6).tolist(),
        "ay_max_ms2":   vehicle._ggv_ay_max.tolist(),
        "ax_accel_ms2": vehicle._ggv_ax_accel[:, 0].tolist(),
        "ax_brake_ms2": vehicle._ggv_ax_brake[:, 0].tolist(),
        "terminal_velocity_kmh": float(vehicle.terminal_velocity() * 3.6),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Setup sensitivity endpoint — the "intelligence platform" core
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/sensitivity",
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
    K_theta = sus.pitch_stiffness(mp.wheelbase)

    q_dyn = 0.5 * vehicle.aero.rho_air * vehicle.aero.frontal_area * speed_ms ** 2

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
