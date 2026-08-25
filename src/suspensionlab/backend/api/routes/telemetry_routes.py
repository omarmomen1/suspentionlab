import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional

from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.lap_sim import LapSimVehicle
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.security.rate_limit import RateLimiter

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

class TelemetryConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

manager = TelemetryConnectionManager()
vehicle = LapSimVehicle()  # For live telemetry grip comparisons

from fastapi import Query, status
from suspensionlab.backend.security.jwt_utils import decode_access_token

MAX_CONNECTIONS = 50


@router.websocket("/live")
async def websocket_telemetry_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="Bearer JWT for authentication")
):
    """
    Live Telemetry Monitor WebSocket Endpoint.
    Ingests live DAQ sensor data (JSON) and computes divergence
    between actual G-forces and the theoretical physical limit.

    Input JSON format:
        {"speed_ms": float, "lat_g": float, "long_g": float, "steer_rad": float}

    Output JSON format:
        {"theoretical_max_lat_g": float, "actual_lat_g": float,
         "divergence_pct": float, "grip_status": str}
    """
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if len(manager.active_connections) >= MAX_CONNECTIONS:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > 4096:
                await websocket.send_json({"error": "Message too large"})
                continue

            payload_data = json.loads(data)
            speed = payload_data.get("speed_ms", 10.0)
            actual_lat_g = abs(payload_data.get("lat_g", 0.0))

            theoretical_max_lat_g = vehicle.max_lateral_g(speed)

            divergence_lat = 0.0
            if theoretical_max_lat_g > 0:
                divergence_lat = (theoretical_max_lat_g - actual_lat_g) / theoretical_max_lat_g

            grip_status = "Optimal"
            if divergence_lat > 0.05:
                grip_status = "Under-utilising front grip"
            elif divergence_lat < -0.05:
                grip_status = "Exceeding model limit — calibration needed"

            response = {
                "theoretical_max_lat_g": round(theoretical_max_lat_g, 3),
                "actual_lat_g": round(actual_lat_g, 3),
                "divergence_pct": round(divergence_lat * 100, 1),
                "grip_status": grip_status
            }
            await websocket.send_json(response)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except (json.JSONDecodeError, Exception):
        manager.disconnect(websocket)


@router.post(
    "/analyse",
    dependencies=[
        Depends(verify_api_key),
        Depends(RateLimiter("rate_limit_simulate")),
    ],
)
async def analyse_telemetry(
    file: UploadFile = File(..., description="Telemetry CSV file (AiM, MoTeC, generic)"),
    model_params: Optional[str] = Form(None, description="JSON string of quarter-car model parameters"),
):
    """
    Analyse an uploaded telemetry CSV session.

    Pipeline:
        Step 1 — Identify channels (40+ alias map)
        Step 2 — Validate data quality (dropouts, dead sensors, rate mismatch)
        Step 3 — Segment lap (straights, braking zones, corners)
        Step 4 — Compare simulation vs. telemetry (if model_params provided)

    Returns structured JSON with channel map, QA metrics, lap segments,
    and simulation comparison table.
    """
    # Validate file type
    if file.content_type not in ("text/csv", "text/plain", "application/octet-stream") and \
       not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    # File size limit: 50 MB
    MAX_SIZE = 50 * 1024 * 1024
    content_bytes = await file.read(MAX_SIZE + 1)
    if len(content_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum 50 MB.")

    try:
        csv_content = content_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot decode file: {exc}")

    # Parse optional model params
    params_dict: dict | None = None
    if model_params:
        try:
            params_dict = json.loads(model_params)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="model_params must be valid JSON.")

    # Run analysis pipeline
    try:
        from suspensionlab.physics.telemetry_analysis import analyse_session
        result = analyse_session(csv_content, params_dict)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    # Serialise result to JSON-safe dict
    qa = result.qa
    qa_dict = None
    if qa:
        qa_dict = {
            "n_samples":         qa.n_samples,
            "duration_s":        qa.duration_s,
            "sample_rate_hz":    qa.sample_rate_hz,
            "channels_found":    qa.channels_found,
            "channels_missing":  qa.channels_missing,
            "dead_channels":     qa.dead_channels,
            "dropout_intervals": qa.dropout_intervals,
            "rate_mismatch_pct": qa.rate_mismatch_pct,
            "total_warnings":    qa.total_warnings,
        }

    segments_list = [
        {
            "label":       s.label,
            "t_start":     s.t_start,
            "t_end":       s.t_end,
            "duration_s":  round(s.t_end - s.t_start, 3),
            "peak_lat_g":  s.peak_lat_g,
            "peak_long_g": s.peak_long_g,
            "peak_speed":  s.peak_speed,
        }
        for s in result.segments
    ]

    comparison_list = [
        {
            "channel":     row.channel,
            "description": row.description,
            "unit":        row.unit,
            "sim_value":   row.sim_value,
            "telem_value": row.telem_value,
            "error_abs":   row.error_abs,
            "error_pct":   row.error_pct,
            "status":      row.status,
        }
        for row in result.comparison
    ]

    # Truncate channel data arrays for response (max 2000 points)
    channels_preview: dict = {}
    for key, arr in result.channels.items():
        if isinstance(arr, list) and len(arr) > 0:
            step = max(1, len(arr) // 2000)
            channels_preview[key] = arr[::step]

    return JSONResponse(content={
        "summary": {
            "n_samples":      result.n_samples,
            "duration_s":     result.duration_s,
            "sample_rate_hz": result.sample_rate_hz,
            "mean_speed_ms":  result.mean_speed_ms,
            "peak_lat_g":     result.peak_lat_g,
            "peak_long_g":    result.peak_long_g,
            "peak_vert_g":    result.peak_vert_g,
        },
        "channel_map":  result.channel_info,
        "qa":           qa_dict,
        "segments":     segments_list,
        "comparison":   comparison_list,
        "model_note":   result.model_note,
        "channels_preview": channels_preview,
    })
