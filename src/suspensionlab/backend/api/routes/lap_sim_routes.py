from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from typing import List, Dict, Any
import gpxpy
import numpy as np

from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.physics.lap_sim import LapSimVehicle, parse_track_from_gps, solve_lap

router = APIRouter(prefix="/lapsim", tags=["Lap Simulation"])

@router.post("/run")
async def run_lap_sim(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key)
):
    """
    Run the quasi-steady lap simulator using JSON array track data.
    request_data should contain 'latitudes', 'longitudes', and optionally 'elevations'.
    """
    latitudes = request_data.get("latitudes")
    longitudes = request_data.get("longitudes")
    
    MAX_GPS_POINTS = 10_000

    if not latitudes or not longitudes:
        raise HTTPException(status_code=400, detail="GPS arrays are required.")
    if len(latitudes) != len(longitudes):
        raise HTTPException(status_code=400, detail="Latitude and longitude arrays must be the same length.")
    if len(latitudes) > MAX_GPS_POINTS:
        raise HTTPException(
            status_code=422,
            detail=f"GPS track too long. Maximum {MAX_GPS_POINTS:,} points. "
                   f"Decimate the GPX file using Douglas-Peucker before uploading."
        )
        
    elevations = request_data.get("elevations")
    
    segments = parse_track_from_gps(latitudes, longitudes, elevations)
    vehicle = LapSimVehicle() # Defaults or parse from request_data
    
    # Optional override vehicle params
    if "vehicle" in request_data:
        v_data = request_data["vehicle"]
        if "mass" in v_data: vehicle.mass = v_data["mass"]
        if "aero_cl" in v_data: vehicle.aero_cl = v_data["aero_cl"]
        if "aero_cd" in v_data: vehicle.aero_cd = v_data["aero_cd"]
        if "max_power" in v_data: vehicle.max_power = v_data["max_power"]
    
    result = solve_lap(vehicle, segments)
    
    return {
        "status": "success",
        "total_time_s": result.total_time,
        "max_speed_kmh": result.max_speed_kmh,
        "avg_speed_kmh": result.avg_speed_kmh,
        "telemetry": {
            "distances": result.distances.tolist(),
            "speeds": result.speeds.tolist(),
            "lateral_g": result.lateral_g.tolist(),
            "longitudinal_g": result.longitudinal_g.tolist()
        }
    }

@router.post("/upload_gpx")
async def upload_gpx(
    file: UploadFile = File(...),
    user=Depends(verify_api_key)
):
    """Parse a GPX file into latitudes and longitudes."""
    if not file.filename.endswith('.gpx'):
        raise HTTPException(status_code=400, detail="Only .gpx files are supported.")
        
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 5MB.")

    try:
        gpx = gpxpy.parse(content)
        lats, lons, elevs = [], [], []
        point_count = 0
        
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    point_count += 1
                    if point_count > 10_000:
                        raise ValueError("GPX track too long. Maximum 10,000 points.")
                    lats.append(point.latitude)
                    lons.append(point.longitude)
                    elevs.append(point.elevation or 0.0)
                    
        return {
            "latitudes": lats,
            "longitudes": lons,
            "elevations": elevs
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse GPX: {str(e)}")
