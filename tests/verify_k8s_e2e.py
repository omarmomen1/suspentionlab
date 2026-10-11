import os
import asyncio
import sys
import time
import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

async def main():
    print("=================================================================")
    print("SUSPENSIONLAB PRO — KUBERNETES RUNTIME CERTIFICATION (K3S / HELM)")
    print("=================================================================")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Health and Readiness
        print("\n[Step 1] Checking Kubernetes /health and /ready endpoints...")
        r = await client.get("/health")
        assert r.status_code == 200, f"/health failed: {r.status_code} {r.text}"
        print(f"  -> /health: {r.status_code} {r.json()}")

        r = await client.get("/ready")
        assert r.status_code == 200, f"/ready failed: {r.status_code} {r.text}"
        ready_data = r.json()
        print(f"  -> /ready: {r.status_code} {ready_data}")
        assert ready_data.get("database") == "healthy", "Database not healthy in /ready"
        assert ready_data.get("redis") == "healthy", "Redis not healthy in /ready"

        # 2. User Registration & Auth
        email = f"k8s_audit_engineer_{int(time.time())}@suspensionlab.com"
        password = "Pr0d_Secur3_K8s_Audit_Us3r_2026!"
        print(f"\n[Step 2] Registering production audit user: {email}...")
        r = await client.post("/auth/register", json={
            "email": email,
            "password": password,
            "name": "K8s Verification Engineer"
        })
        assert r.status_code == 201, f"Registration failed: {r.status_code} {r.text}"
        auth_data = r.json()
        token = auth_data["token"]
        user_id = auth_data["user_id"]
        print(f"  -> Registered user_id: {user_id}")

        # Promote audit user in DB to ENTERPRISE Admin
        print("  -> Promoting user to ENTERPRISE Administrator in PostgreSQL DB...")
        from suspensionlab.backend.database.core import SessionLocal
        from suspensionlab.backend.database.models.user import User
        from sqlalchemy import update
        import uuid as _uuid
        async with SessionLocal() as db:
            await db.execute(
                update(User)
                .where(User.id == _uuid.UUID(user_id))
                .values(is_admin=True, plan="ENTERPRISE", team_role="OWNER", org_role="ORG_ADMIN")
            )
            await db.commit()
        print("  -> User permissions elevated (is_admin=True, plan=ENTERPRISE, team_role=OWNER)")

        print(f"  -> Acquired JWT access token: {token[:20]}...")
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 3. Native C++ Kinematics Solve inside Kubernetes
        print("\n[Step 3] Submitting Kinematics Solve request to API (Strict C++ Enforcement)...")
        r = await client.get("/kinematics/default", headers=auth_headers)
        assert r.status_code == 200, f"Failed to get defaults: {r.status_code} {r.text}"
        hardpoints = r.json()["hardpoints"]
        
        solve_payload = {
            "hardpoints": hardpoints,
            "wheel_travel_range": [-50.0, 50.0],
            "n_points": 21,
            "backend": "cpp"
        }
        r = await client.post("/kinematics/solve", json=solve_payload, headers=auth_headers)
        assert r.status_code == 200, f"Kinematics solve failed: {r.status_code} {r.text}"
        kin_data = r.json()
        
        print("  -> Kinematics solve response received:")
        print(f"     * active_backend: {kin_data.get('active_backend')}")
        print(f"     * requested_backend: {kin_data.get('requested_backend')}")
        print(f"     * solver_version: {kin_data.get('solver_version')}")
        print(f"     * build_identifier: {kin_data.get('build_identifier')}")
        print(f"     * all_converged: {kin_data.get('all_converged')}")
        print(f"     * n_points computed: {kin_data.get('n_points')}")
        print(f"     * camber_deg sample: {kin_data.get('camber_deg')[:3]}...")
        
        assert kin_data.get("active_backend") == "cpp", f"Expected active_backend 'cpp', got {kin_data.get('active_backend')}"
        assert kin_data.get("all_converged") is True, "Kinematics solver did not converge for all points"
        assert "eigen" in kin_data.get("build_identifier", ""), f"Unexpected build ID: {kin_data.get('build_identifier')}"

        # 4. Background Async Optimization Job (API -> Redis -> Worker -> DB)
        print("\n[Step 4] Submitting Asynchronous Optimization Job to Worker Queue...")
        opt_payload = {
            "params": {
                "m_s": 300.0,
                "m_u": 40.0,
                "k_s": 35000.0,
                "c_s": 2500.0,
                "k_t": 200000.0
            },
            "profile": {
                "profile_type": "step",
                "bump_height": 0.05,
                "velocity": 20.0
            },
            "objective_type": "comfort",
            "max_travel": 0.08
        }
        r = await client.post("/optimize", json=opt_payload, headers=auth_headers)
        assert r.status_code == 200, f"Optimization submission failed: {r.status_code} {r.text}"
        job_info = r.json()
        job_id = job_info["job_id"]
        print(f"  -> Job submitted successfully. job_id: {job_id}, status: {job_info.get('status')}")

        print(f"\n[Step 5] Polling /jobs/{job_id} for asynchronous worker processing in Kubernetes...")
        completed = False
        result_data = None
        for attempt in range(40):
            await asyncio.sleep(1.0)
            r = await client.get(f"/jobs/{job_id}", headers=auth_headers)
            assert r.status_code == 200, f"Job polling failed: {r.status_code} {r.text}"
            poll_res = r.json()
            status = poll_res.get("status")
            print(f"  -> Poll attempt {attempt + 1}: status = {status}")
            if "COMPLETED" in status:
                completed = True
                result_data = poll_res
                break
            elif status == "FAILED":
                raise RuntimeError(f"Job failed during execution: {poll_res.get('error')}")

        assert completed, f"Job {job_id} did not complete within timeout"
        print(f"  -> Job COMPLETED successfully by RQ Worker in Kubernetes!")
        print(f"     * Result keys: {list(result_data.get('result', {}).keys())}")
        if "optimized_params" in result_data.get("result", {}):
            print(f"     * Optimized parameters: {result_data['result']['optimized_params']}")

        print("\n=================================================================")
        print("ALL KUBERNETES TOPOLOGY & NATIVE RUNTIME CHECKS: PASSED")
        print("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
