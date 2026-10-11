import asyncio
import websockets
import json
import math
import time
from suspensionlab.telemetry.protocol import SLTPFrame, ChannelId, MAGIC_HEADER

async def stream_telemetry():
    uri = "ws://localhost:8000/api/v1/telemetry/live?token=demo&session_id=sess-live&format=binary"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to Live Telemetry Digital Twin Stream (Binary SLTP v1)!")
            t0 = time.monotonic()
            for i in range(100):
                speed = 20.0 + i * 0.1
                actual_lat_g = 1.0 * abs(math.sin(i * 0.1))

                payload = {
                    "seq": i + 1,
                    "ts": time.time(),
                    "speed_ms": speed,
                    "lat_g": actual_lat_g,
                    "long_g": 0.2,
                    "steer_rad": 0.05,
                }

                await websocket.send(json.dumps(payload))
                response = await websocket.recv()

                if isinstance(response, bytes) and response.startswith(MAGIC_HEADER):
                    frame = SLTPFrame.unpack(response)
                    twin = frame.twin
                    print(
                        f"[{i+1}] Speed: {speed:.1f} m/s | Actual G: {twin.actual_lat_g if twin else actual_lat_g:.3f} | "
                        f"Pacejka Max Grip: {twin.theoretical_max_lat_g if twin else 0:.3f}g | "
                        f"Status: {twin.grip_status.name if twin else 'N/A'} ({twin.divergence_pct if twin else 0}%)"
                    )
                else:
                    print(f"[{i+1}] Response: {response}")

                await asyncio.sleep(0.01) # 100 Hz

            total_time = time.monotonic() - t0
            print(f"Stream finished. 100 frames in {total_time:.3f}s ({100/total_time:.1f} Hz sustained).")
    except Exception as e:
        print(f"Failed to connect or stream: {e}")

if __name__ == "__main__":
    asyncio.run(stream_telemetry())

