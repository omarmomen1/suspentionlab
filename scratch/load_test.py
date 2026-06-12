import asyncio
import os
import sys

# Mock databases so we can test the ASGI app idempotency lock without real Postgres
os.environ["DATABASE_URL"] = "postgresql+asyncpg://dummy:dummy@localhost/dummy"
import suspensionlab.backend.security.idempotency as idem
class MockRedis:
    def __init__(self):
        self.store = {}
        self.lock = asyncio.Lock()
    async def get(self, key):
        async with self.lock:
            val = self.store.get(key)
            if val is not None:
                # Return bytes as if from real redis
                return val.encode() if isinstance(val, str) else val
            return None
            
    async def setex(self, key, ttl, val):
        async with self.lock:
            self.store[key] = val
            
    async def set(self, key, val, nx=False, ex=None):
        async with self.lock:
            if nx and key in self.store:
                return False
            self.store[key] = val
            return True

mock_redis = MockRedis()
idem.async_redis_conn = mock_redis
sys.modules['suspensionlab.backend.api.routes.optimize'] = type('mock', (), {'async_redis_conn': mock_redis})()

from fastapi import FastAPI, Request
from suspensionlab.backend.security.idempotency import IdempotencyMiddleware

app = FastAPI()
app.add_middleware(IdempotencyMiddleware)

@app.post("/optimize/test")
async def optimize_endpoint(request: Request):
    # Simulate a slow running job (quota lock scenario)
    await asyncio.sleep(0.1)
    body = await request.json()
    return {"optimized": True, "mass": body.get("mass", 0)}

from httpx import AsyncClient, ASGITransport

async def run_load_test():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Test 1: 50 concurrent identical requests (Idempotency replay)
        print("Starting Idempotency Replay Test: 50 concurrent requests")
        payload = {"mass": 100}
        headers = {"Idempotency-Key": "load_test_idem_1", "X-API-Key": "load_test_key"}
        
        # Fire 50 requests concurrently
        tasks = [
            client.post("/optimize/test", json=payload, headers=headers)
            for _ in range(50)
        ]
        responses = await asyncio.gather(*tasks)
        
        replays = sum(1 for r in responses if r.headers.get("x-idempotent-replay") == "true")
        actual_executions = 50 - replays
        
        print(f"Total Requests: {len(responses)}")
        print(f"Actual Executions: {actual_executions}")
        print(f"Cache Replays: {replays}")
        
        assert actual_executions == 1, f"Expected 1 execution, got {actual_executions}"
        assert replays == 49, f"Expected 49 replays, got {replays}"
        print("Idempotency concurrency test passed!")

if __name__ == "__main__":
    asyncio.run(run_load_test())
