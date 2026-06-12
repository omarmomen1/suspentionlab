# No pytest
import os
os.environ["DATABASE_URL"] = "postgresql+asyncpg://dummy:dummy@localhost/dummy"
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from suspensionlab.backend.security.idempotency import IdempotencyMiddleware
import json

app = FastAPI()
app.add_middleware(IdempotencyMiddleware)

# Mock async_redis_conn
class MockRedis:
    def __init__(self):
        self.store = {}
    async def get(self, key):
        return self.store.get(key)
    async def setex(self, key, ttl, val):
        self.store[key] = val

import sys
sys.modules['suspensionlab.backend.api.routes.optimize'] = type('mock', (), {'async_redis_conn': MockRedis()})()

@app.post("/billing/webhook")
async def webhook(request: Request):
    # This proves the body can still be read inside the endpoint after middleware consumption
    body = await request.body()
    assert body is not None
    data = json.loads(body)
    return {"status": "ok", "read_id": data.get("id")}

@app.post("/optimize/test")
async def optimize_endpoint(request: Request):
    # Simulates Pydantic parsing natively reading the stream
    data = await request.json()
    return {"optimized": True, "data": data}

client = TestClient(app)

def test_webhook_body_reinjection():
    payload = {"id": "evt_123", "type": "payment_intent.succeeded"}
    
    # First request
    resp1 = client.post("/billing/webhook", json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["read_id"] == "evt_123"
    
    # Replay request
    resp2 = client.post("/billing/webhook", json=payload)
    assert resp2.status_code == 200
    assert resp2.headers.get("x-idempotent-replay") == "true"
    assert resp2.json()["read_id"] == "evt_123"

def test_optimize_payload_reinjection():
    payload = {"params": {"mass": 100}, "profile": {"type": "step"}}
    headers = {"Idempotency-Key": "test_idem_abc", "X-API-Key": "test_key"}
    
    # First request
    resp1 = client.post("/optimize/test", json=payload, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["optimized"] is True
    
    # Replay request
    resp2 = client.post("/optimize/test", json=payload, headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("x-idempotent-replay") == "true"
    assert resp2.json()["optimized"] is True
    
    # Body collision (different body, same key)
    payload_diff = {"params": {"mass": 200}, "profile": {"type": "step"}}
    resp3 = client.post("/optimize/test", json=payload_diff, headers=headers)
    assert resp3.status_code == 409
if __name__ == "__main__":
    print("Running webhook test...")
    test_webhook_body_reinjection()
    print("Running optimize payload test...")
    test_optimize_payload_reinjection()
    print("All body reinjection tests passed!")
