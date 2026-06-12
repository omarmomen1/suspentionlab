import asyncio
import httpx
import uuid
import time
import json
import hmac
import hashlib

# Webhook secret must match settings.stripe_webhook_secret (default 'whsec_test')
WEBHOOK_SECRET = "whsec_test"
API_URL = "http://localhost:8000"

def generate_stripe_signature(payload: str, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload}"
    mac = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={mac}"

from fastapi.testclient import TestClient
from suspensionlab.backend.api.main import app
from unittest.mock import AsyncMock, patch

def test_webhook():
    # 1. Create a dummy user directly via the API to test webhook logic
    with patch("suspensionlab.backend.security.rate_limit.RateLimiter.__call__", new_callable=AsyncMock) as mock_limit:
        with TestClient(app) as client:
            test_email = f"webhook_test_{uuid.uuid4().hex[:8]}@suspensionlab.io"
            reg_resp = client.post(
                "/auth/register",
                json={"email": test_email, "password": "testpassword", "name": "Webhook Tester"}
            )
        assert reg_resp.status_code == 201, f"Register failed: {reg_resp.text}"
        user_id = reg_resp.json()["user_id"]
        print(f"Created user {user_id} ({test_email})")

        # 2. Simulate a Stripe 'checkout.session.completed' webhook
        # Need to provide client_reference_id = user_id
        payload = {
            "id": "evt_test_123",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_a1b2c3",
                    "object": "checkout.session",
                    "client_reference_id": user_id,
                    "customer": "cus_test_123",
                    "mode": "subscription",
                    "payment_status": "paid",
                    "status": "complete",
                    "subscription": "sub_test_123"
                }
            }
        }
        payload_str = json.dumps(payload)
        sig = generate_stripe_signature(payload_str, WEBHOOK_SECRET)

        webhook_resp = client.post(
            "/billing/webhooks/stripe",
            content=payload_str,
            headers={
                "Stripe-Signature": sig,
                "Content-Type": "application/json"
            }
        )
        assert webhook_resp.status_code == 200, f"Webhook failed: {webhook_resp.text}"
        print("Webhook 'checkout.session.completed' processed successfully.")

        # 3. Simulate customer.subscription.updated (e.g. upgraded to ENTERPRISE)
        payload_sub = {
            "id": "evt_test_456",
            "object": "event",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "customer": "cus_test_123",
                    "status": "active",
                    "items": {
                        "data": [
                            {
                                "price": {
                                    "id": "price_enterprise_test"
                                }
                            }
                        ]
                    }
                }
            }
        }
        payload_sub_str = json.dumps(payload_sub)
        sig_sub = generate_stripe_signature(payload_sub_str, WEBHOOK_SECRET)

        webhook_resp_2 = client.post(
            "/billing/webhooks/stripe",
            content=payload_sub_str,
            headers={
                "Stripe-Signature": sig_sub,
                "Content-Type": "application/json"
            }
        )
        assert webhook_resp_2.status_code == 200, f"Webhook failed: {webhook_resp_2.text}"
        print("Webhook 'customer.subscription.updated' processed successfully.")

if __name__ == "__main__":
    test_webhook()
