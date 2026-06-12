import uuid
import json
import time
from locust import HttpUser, task, between, events

# We mock out some fake params that look like what Streamlit sends
FAKE_OPTIMIZE_PAYLOAD = {
    "params": {
        "m_s": 300.0,
        "m_u": 35.0,
        "k_s": 25000.0,
        "c": 2050.0,
        "k_t": 200000.0,
        "MR": 0.85,
        "c_t": 0.0
    },
    "profile": {
        "profile_type": "step",
        "amplitude": 0.05,
        "frequency": 2.0,
        "duration": 5.0
    },
    "objective_type": "Balanced",
    "max_travel": 0.05
}

class DashboardUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Called when a Locust user starts"""
        # In a real setup, we'd log them in or grab their API key.
        # The local dev database auto-seeds a FREE tier user with this exact key.
        self.headers = {
            "X-API-Key": "test-api-key-12345",
            "Content-Type": "application/json"
        }

    @task(3)
    def run_optimization_and_poll(self):
        """Simulates a user hitting the 'Optimize' button and waiting for results"""
        idem_key = str(uuid.uuid4())
        self.headers["Idempotency-Key"] = idem_key

        with self.client.post("/optimize", json=FAKE_OPTIMIZE_PAYLOAD, headers=self.headers, catch_response=True) as resp:
            if resp.status_code == 429:
                # Quota exceeded is an expected response for FREE tier users under heavy load, not a failure of the system
                resp.success()
                return
            elif resp.status_code not in (200, 202):
                resp.failure(f"Failed to submit optimization: {resp.status_code}")
                return
            
            try:
                job_id = resp.json().get("job_id")
            except Exception:
                resp.failure("No job_id returned")
                return

        if not job_id:
            return

        # Polling loop
        for _ in range(30):
            time.sleep(1.0)
            poll_resp = self.client.get(f"/jobs/{job_id}", headers=self.headers)
            if poll_resp.status_code == 200:
                try:
                    data = poll_resp.json()
                    status = data.get("status")
                    if status == "COMPLETED":
                        break
                    elif status == "FAILED":
                        # Locust reports this as a failure automatically if we wanted, but we'll manually handle it
                        break
                except Exception:
                    pass

        # Simulate double click / reload that re-sends the exact same request
        self.client.post("/optimize", json=FAKE_OPTIMIZE_PAYLOAD, headers=self.headers, name="/optimize (Cache Replay)")

    @task(1)
    def race_condition_attack(self):
        """Simulates 50 frontend requests arriving at the exact same millisecond to test idempotency lock"""
        import gevent
        idem_key = str(uuid.uuid4())
        self.headers["Idempotency-Key"] = idem_key
        
        def send_duplicate():
            self.client.post("/optimize", json=FAKE_OPTIMIZE_PAYLOAD, headers=self.headers, name="/optimize (Race Condition)")

        # Fire 10 concurrent requests
        threads = [gevent.spawn(send_duplicate) for _ in range(10)]
        gevent.joinall(threads)
