import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any

from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.lap_sim import LapSimVehicle

router = APIRouter(prefix="/telemetry", tags=["Telemetry Digital Twin"])

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
vehicle = LapSimVehicle() # For Digital Twin comparisons

from fastapi import Query, status
from suspensionlab.backend.security.jwt_utils import decode_access_token

MAX_CONNECTIONS = 50

@router.websocket("/live")
async def websocket_telemetry_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="Bearer JWT for authentication")
):
    """
    F1-Grade Digital Twin WebSocket Endpoint.
    Ingests live DAQ sensor data (JSON) and computes divergence
    between actual G-forces and the theoretical physical limit.
    """
    # 1. Authenticate before accepting the connection
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Connection limit
    if len(manager.active_connections) >= MAX_CONNECTIONS:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    await manager.connect(websocket)
    user_id = payload.get("sub")

    try:
        while True:
            # Expecting generic JSON: {"speed_ms": 50, "lat_g": 1.2, "long_g": 0.5, "steer_rad": 0.1}
            data = await websocket.receive_text()
            
            # Enforce message size limit (prevent memory exhaustion)
            if len(data) > 4096:
                await websocket.send_json({"error": "Message too large"})
                continue
                
            payload_data = json.loads(data)
            
            speed = payload_data.get("speed_ms", 10.0)
            actual_lat_g = abs(payload_data.get("lat_g", 0.0))
            actual_long_g = payload_data.get("long_g", 0.0)
            
            # Run the digital twin model
            theoretical_max_lat_g = vehicle.max_lateral_g(speed)
            
            divergence_lat = 0.0
            if theoretical_max_lat_g > 0:
                divergence_lat = (theoretical_max_lat_g - actual_lat_g) / theoretical_max_lat_g
                
            # If they are under-utilizing grip by more than 5%, flag it
            grip_status = "Optimal"
            if divergence_lat > 0.05:
                grip_status = "Under-utilizing front grip"
            elif divergence_lat < -0.05:
                # Actual G's exceed theoretical max (model calibration needed or sliding)
                grip_status = "Exceeding theoretical grip (Sliding/Calibration needed)"

            response = {
                "theoretical_max_lat_g": round(theoretical_max_lat_g, 3),
                "actual_lat_g": round(actual_lat_g, 3),
                "divergence_pct": round(divergence_lat * 100, 1),
                "grip_status": grip_status
            }
            
            await websocket.send_json(response)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except (json.JSONDecodeError, Exception) as e:
        manager.disconnect(websocket)
