import os
import subprocess
import time
import json
import uuid

KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"

def run_cmd(cmd):
    full_cmd = f"export KUBECONFIG={KUBECONFIG} && {cmd}"
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Command failed: {cmd}\nStderr: {res.stderr}")
    return res

def run_in_api_pod(py_code):
    cmd = ["kubectl", "exec", "-i", "-n", "suspensionlab", "deployment/suspensionlab-api", "--", "python3"]
    env = os.environ.copy()
    env["KUBECONFIG"] = KUBECONFIG
    res = subprocess.run(cmd, input=py_code, capture_output=True, text=True, env=env)
    return res.returncode == 0, res.stdout, res.stderr

def main():
    print("=================================================================")
    print("SUSPENSIONLAB PRO — KUBERNETES FAILURE INJECTION VERIFICATION")
    print("=================================================================")

    # -------------------------------------------------------------
    # TEST 1: Worker Pod Failure & Auto-Recovery (Kubernetes ReplicaSet)
    # -------------------------------------------------------------
    print("\n[Test 1] Testing Worker Pod Termination & Self-Healing...")
    # Get current worker pod name
    res = run_cmd("kubectl get pod -l component=worker -n suspensionlab -o jsonpath='{.items[0].metadata.name}'")
    old_worker = res.stdout.strip().replace("'", "")
    print(f"  -> Current worker pod: {old_worker}")
    
    print(f"  -> Terminating worker pod {old_worker} with SIGKILL via kubectl delete pod --force...")
    run_cmd(f"kubectl delete pod {old_worker} -n suspensionlab --grace-period=0 --force")
    
    print("  -> Waiting for Kubernetes to heal worker deployment...")
    time.sleep(6)
    
    # Wait for new worker pod to be Ready
    for i in range(20):
        res = run_cmd("kubectl get pod -l component=worker -n suspensionlab -o jsonpath='{.items[0].status.phase}'")
        phase = res.stdout.strip().replace("'", "")
        print(f"  -> Worker status check {i+1}: {phase}")
        if phase == "Running":
            break
        time.sleep(2)
    
    res = run_cmd("kubectl get pod -l component=worker -n suspensionlab -o jsonpath='{.items[0].metadata.name}'")
    new_worker = res.stdout.strip().replace("'", "")
    print(f"  -> Replacement worker running: {new_worker}")
    assert new_worker != old_worker, f"Worker pod did not get replaced! Still {new_worker}"
    
    # Verify new worker can process an optimization job
    print("  -> Submitting test job to verify new worker processing...")
    job_test_code = """
import httpx, asyncio
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.user import User
from sqlalchemy import update
import uuid as _uuid

async def test():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=20.0) as client:
        r = await client.post("/auth/register", json={"email": "worker_fail_k8s_%d@test.com" % asyncio.get_event_loop().time(), "password": "Password123!", "name": "WorkerTest"})
        res_data = r.json()
        token = res_data["token"]
        user_id = res_data["user_id"]
        
        async with SessionLocal() as db:
            await db.execute(
                update(User)
                .where(User.id == _uuid.UUID(user_id))
                .values(is_admin=True, plan="ENTERPRISE", team_role="OWNER", org_role="ORG_ADMIN")
            )
            await db.commit()
            
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.post("/optimize", json={
            "params": {"m_s": 300, "m_u": 40, "k_s": 35000, "c_s": 2500, "k_t": 200000},
            "profile": {"profile_type": "step", "bump_height": 0.05, "velocity": 20.0},
            "objective_type": "comfort", "max_travel": 0.08
        }, headers=headers)
        jid = r.json()["job_id"]
        for _ in range(30):
            await asyncio.sleep(1)
            r = await client.get(f"/jobs/{jid}", headers=headers)
            if "COMPLETED" in r.json().get("status", ""):
                print("JOB_SUCCESS")
                return
        print("JOB_TIMEOUT")
asyncio.run(test())
"""
    success, stdout, stderr = run_in_api_pod(job_test_code)
    assert "JOB_SUCCESS" in stdout, f"Job failed to complete on new worker: {stdout} {stderr}"
    print("  -> Worker auto-recovery & workload execution: VERIFIED")

    # -------------------------------------------------------------
    # TEST 2: Redis Pod Failure & Auto-Recovery
    # -------------------------------------------------------------
    print("\n[Test 2] Testing Redis Pod Termination & Reconnection...")
    res = run_cmd("kubectl get pod -l app=redis -n suspensionlab -o jsonpath='{.items[0].metadata.name}'")
    old_redis = res.stdout.strip().replace("'", "")
    print(f"  -> Current redis pod: {old_redis}")
    
    print(f"  -> Killing Redis pod {old_redis}...")
    run_cmd(f"kubectl delete pod {old_redis} -n suspensionlab --grace-period=0 --force")
    
    time.sleep(6)
    for i in range(20):
        res = run_cmd("kubectl get pod -l app=redis -n suspensionlab -o jsonpath='{.items[0].status.phase}'")
        phase = res.stdout.strip().replace("'", "")
        print(f"  -> Redis status check {i+1}: {phase}")
        if phase == "Running":
            break
        time.sleep(2)
        
    print("  -> Waiting for API readiness check to reconnect to Redis...")
    for i in range(25):
        time.sleep(2)
        code = """
import urllib.request, json
try:
    data = json.loads(urllib.request.urlopen("http://localhost:8000/ready", timeout=2).read().decode())
    print("REDIS_HEALTH:", data.get("redis"))
except Exception as e:
    print("ERR:", e)
"""
        _, out, _ = run_in_api_pod(code)
        print(f"  -> Poll {i+1}: {out.strip()}")
        if "REDIS_HEALTH: healthy" in out:
            break
    assert "REDIS_HEALTH: healthy" in out, "API failed to reconnect to Redis after pod restart"
    print("  -> Redis failure & auto-reconnection: VERIFIED")

    # -------------------------------------------------------------
    # TEST 3: PostgreSQL Pod Failure & Auto-Recovery
    # -------------------------------------------------------------
    print("\n[Test 3] Testing PostgreSQL Pod Termination & Reconnection...")
    res = run_cmd("kubectl get pod -l app=postgres -n suspensionlab -o jsonpath='{.items[0].metadata.name}'")
    old_pg = res.stdout.strip().replace("'", "")
    print(f"  -> Current postgres pod: {old_pg}")
    
    print(f"  -> Killing Postgres pod {old_pg}...")
    run_cmd(f"kubectl delete pod {old_pg} -n suspensionlab --grace-period=0 --force")
    
    time.sleep(6)
    for i in range(20):
        res = run_cmd("kubectl get pod -l app=postgres -n suspensionlab -o jsonpath='{.items[0].status.phase}'")
        phase = res.stdout.strip().replace("'", "")
        print(f"  -> Postgres status check {i+1}: {phase}")
        if phase == "Running":
            break
        time.sleep(2)
        
    print("  -> Waiting for API readiness check to reconnect to PostgreSQL...")
    for i in range(25):
        time.sleep(2)
        code = """
import urllib.request, json
try:
    data = json.loads(urllib.request.urlopen("http://localhost:8000/ready", timeout=2).read().decode())
    print("DB_HEALTH:", data.get("database"))
except Exception as e:
    print("ERR:", e)
"""
        _, out, _ = run_in_api_pod(code)
        print(f"  -> Poll {i+1}: {out.strip()}")
        if "DB_HEALTH: healthy" in out:
            break
    assert "DB_HEALTH: healthy" in out, "API failed to reconnect to PostgreSQL after pod restart"
    print("  -> PostgreSQL failure & auto-reconnection: VERIFIED")

    print("\n=================================================================")
    print("ALL KUBERNETES CHAOS & FAILURE INJECTION TESTS: PASSED")
    print("=================================================================")

if __name__ == "__main__":
    main()
