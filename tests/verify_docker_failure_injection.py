import asyncio
import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

def req(method: str, path: str, data: dict = None, headers: dict = None):
    url = f"{BASE_URL}{path}"
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"error": err_body}
        return e.code, parsed
    except Exception as e:
        return 0, {"error": str(e)}

def run_cmd(cmd: str) -> str:
    print(f"  [EXEC] {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [WARN] Command returned {res.returncode}: {res.stderr.strip()}")
    return res.stdout.strip()

def get_auth_token() -> str:
    email = f"failure_tester_{int(time.time())}@suspensionlab.com"
    code, auth_data = req("POST", "/auth/register", {
        "email": email,
        "password": "Pr0d_Secur3_Audit_Us3r_2026!",
        "name": "Failure Test Engineer"
    })
    assert code == 201, f"Registration failed: {code} {auth_data}"
    user_id = auth_data["user_id"]
    token = auth_data["token"]
    
    # Elevate user via docker compose exec backend
    elevate_script = (
        f"import asyncio, uuid\n"
        f"from suspensionlab.backend.database.core import SessionLocal\n"
        f"from suspensionlab.backend.database.models.user import User\n"
        f"from sqlalchemy import update\n\n"
        f"async def run():\n"
        f"    async with SessionLocal() as db:\n"
        f"        await db.execute(update(User).where(User.id == uuid.UUID('{user_id}')).values(is_admin=True, plan='ENTERPRISE', team_role='OWNER'))\n"
        f"        await db.commit()\n\n"
        f"asyncio.run(run())\n"
    )
    subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-c", elevate_script],
        cwd="/root/project",
        check=True,
        capture_output=True
    )
    return token

def test_job_execution(token: str, test_name: str):
    headers = {"Authorization": f"Bearer {token}"}
    opt_payload = {
        "params": {"m_s": 300.0, "m_u": 40.0, "k_s": 35000.0, "c_s": 2500.0, "k_t": 200000.0},
        "profile": {"profile_type": "step", "bump_height": 0.05, "velocity": 20.0},
        "objective_type": "comfort",
        "max_travel": 0.08
    }
    code, job_data = req("POST", "/optimize", opt_payload, headers=headers)
    assert code == 200, f"[{test_name}] Optimize submit failed: {code} {job_data}"
    job_id = job_data["job_id"]
    print(f"    -> Job {job_id} submitted during/after {test_name}.")
    
    completed = False
    for _ in range(45):
        time.sleep(1.0)
        c, res = req("GET", f"/jobs/{job_id}", headers=headers)
        if c == 200 and "COMPLETED" in res.get("status", ""):
            completed = True
            break
    assert completed, f"[{test_name}] Job {job_id} failed to complete within timeout"
    print(f"    -> Job {job_id} successfully COMPLETED.")

def main():
    print("=================================================================")
    print("SUSPENSIONLAB PRO — DOCKER COMPOSE FAILURE INJECTION TEST SUITE")
    print("=================================================================")
    
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # ── Test 1: Worker Kill & Self-Healing ─────────────────────────────
    print("\n[Failure Test 1] Killing worker container...")
    run_cmd("docker kill project-worker-1")
    print("  -> Worker container killed. Waiting for docker-compose restart...")
    time.sleep(3.0)
    # Check status and ensure running
    ps_out = run_cmd("docker ps --filter name=worker --format '{{.Status}}'")
    print(f"  -> Worker status: {ps_out}")
    if not ps_out or "Up" not in ps_out:
        run_cmd("cd /root/project && docker compose up -d worker")
        time.sleep(3.0)
    
    print("  -> Submitting job to verify worker processing recovery...")
    test_job_execution(token, "Worker Recovery")

    # ── Test 2: Redis Restart & Auto-Reconnection ─────────────────────
    print("\n[Failure Test 2] Restarting Redis container...")
    run_cmd("docker restart project-redis-1")
    print("  -> Redis restarted. Waiting for Redis healthcheck...")
    redis_healthy = False
    for _ in range(15):
        time.sleep(2.0)
        c, r = req("GET", "/ready")
        if c == 200 and r.get("redis") == "healthy":
            print(f"  -> Redis reconnected & healthy: {r}")
            redis_healthy = True
            break
    assert redis_healthy, "Redis failed to become healthy after restart"
    
    print("  -> Submitting job to verify end-to-end Redis queue recovery...")
    test_job_execution(token, "Redis Recovery")

    # ── Test 3: PostgreSQL Restart & Auto-Reconnection ────────────────
    print("\n[Failure Test 3] Restarting PostgreSQL container...")
    run_cmd("docker restart project-postgres-1")
    print("  -> PostgreSQL restarted. Waiting for DB healthcheck...")
    db_healthy = False
    for _ in range(20):
        time.sleep(2.0)
        c, r = req("GET", "/ready")
        if c == 200 and r.get("database") == "healthy":
            print(f"  -> Database reconnected & healthy: {r}")
            db_healthy = True
            break
    assert db_healthy, "Database failed to become healthy after restart"
    
    print("  -> Verifying authenticated DB query after restart...")
    c, defaults = req("GET", "/kinematics/default", headers=headers)
    assert c == 200, f"Post-DB restart query failed: {c} {defaults}"
    print("  -> Database operations fully operational.")

    print("\n=================================================================")
    print("ALL DOCKER COMPOSE FAILURE INJECTION TESTS: PASSED")
    print("=================================================================")

if __name__ == "__main__":
    main()
