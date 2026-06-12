import asyncio
import websockets
import json
import math
import time

async def stream_telemetry():
    uri = "ws://localhost:8000/telemetry/live"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to Live Telemetry Digital Twin!")
            for i in range(100):
                # Simulate a car going through a corner
                speed = 20.0 + i * 0.1
                actual_lat_g = 1.0 * math.sin(i * 0.1) # Oscillating G
                
                payload = {
                    "speed_ms": speed,
                    "lat_g": abs(actual_lat_g),
                    "long_g": 0.2,
                    "steer_rad": 0.05
                }
                
                await websocket.send(json.dumps(payload))
                response = await websocket.recv()
                data = json.loads(response)
                
                print(f"[{i}] Speed: {speed:.1f} m/s | Actual G: {data['actual_lat_g']} | "
                      f"Max Grip: {data['theoretical_max_lat_g']} | "
                      f"Status: {data['grip_status']} ({data['divergence_pct']}%)")
                
                await asyncio.sleep(0.1) # 10Hz
    except Exception as e:
        print(f"Failed to connect or stream: {e}")

if __name__ == "__main__":
    asyncio.run(stream_telemetry())
