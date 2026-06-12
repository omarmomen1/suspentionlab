import sys
import asyncio
from fastapi.testclient import TestClient
from suspensionlab.backend.api.main import app

def test_headers():
    with TestClient(app) as client:
        # 1. Test security headers
        resp = client.get("/")
        print("Security Headers:")
        print("X-Content-Type-Options:", resp.headers.get("X-Content-Type-Options"))
        print("Referrer-Policy:", resp.headers.get("Referrer-Policy"))
        print("X-Frame-Options:", resp.headers.get("X-Frame-Options"))
        
        # 2. Test fail-open rate limiting if Redis is unmocked/down 
        # (It will return True in the Exception block since Redis is down)
        resp2 = client.post("/optimize", json={"params":{}, "profile":{}}, headers={"X-API-Key": "dev_secret_key"})
        
        # We don't have Redis running in this test, so headers might not be present if it failed open,
        # but the request should pass through idempotency and hit rate limit logic.
        print("Optimize status code:", resp2.status_code)

if __name__ == "__main__":
    test_headers()
