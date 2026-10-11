import os
import sys
import time
import json
import uuid
import math
import asyncio
import statistics
import concurrent.futures
import psutil
import numpy as np

# Set environment for DEV testing
os.environ["ENVIRONMENT"] = "DEV"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/suspensionlab.db"
os.environ["API_KEY"] = "dev_secret_key"
os.environ["JWT_SECRET_KEY"] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

from suspensionlab.backend.config import settings
settings.rate_limit_simulate = "50000/minute"
settings.rate_limit_auth = "50000/minute"
settings.rate_limit_optimize = "50000/minute"
settings.rate_limit_login = "50000/minute"

from fastapi.testclient import TestClient
from sqlalchemy import select, text, func, insert, delete
from sqlalchemy.orm import selectinload, joinedload

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import engine, SessionLocal, Base
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.database.models.setup_proposal import SetupProposal
from suspensionlab.backend.database.models.user_api_key import UserApiKey
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.seed import seed_demo_users
from suspensionlab.backend.security.jwt_utils import create_access_token

from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
from suspensionlab.physics.half_car import HalfCarParams, run_half_car_analysis
from suspensionlab.physics.full_car import FullCarParams, FourCornerRoadProfile, run_full_car_analysis
from suspensionlab.physics.handling_model import HandlingParams, simulate_maneuver
from suspensionlab.physics.optimizer import optimize_setup
from suspensionlab.physics.kinematics import solve_kinematics, DEFAULT_HARDPOINTS

def percentile(data, pct):
    if not data:
        return 0.0
    sorted_d = sorted(data)
    k = (len(sorted_d) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_d[int(k)]
    d0 = sorted_d[int(f)] * (c - k)
    d1 = sorted_d[int(c)] * (k - f)
    return d0 + d1

def print_header(title):
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)

def print_table(headers, rows):
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))
    
    header_str = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_str = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    print(header_str)
    print(sep_str)
    for row in rows:
        print(" | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)))

async def init_benchmark_db():
    await seed_demo_users()
    async with SessionLocal() as db:
        res = await db.execute(select(User).where(User.email == "demo@suspensionlab.io"))
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.UUID("11613267-b5f6-4927-b3e0-4ad64434c40b"),
                email="demo@suspensionlab.io",
                password_hash="mock",
                plan="ENTERPRISE",
                name="Demo Engineer",
                onboarding_complete=True
            )
            db.add(user)
        else:
            user.plan = "ENTERPRISE"
        uid = str(user.id)
        # Reset any stuck pending/running jobs for clean benchmarking
        await db.execute(
            delete(JobRecord).where(
                JobRecord.user_id == user.id,
                JobRecord.status.in_(["PENDING", "RUNNING"])
            )
        )
        await db.commit()
        return uid

# ==============================================================================
# 1. API BENCHMARKS (p50, p95, p99, Min, Max, RPS)
# ==============================================================================
def benchmark_apis(auth_headers):
    print_header("1. API PERFORMANCE FORENSICS (p50, p95, p99 LATENCY & THROUGHPUT)")
    client = TestClient(app)

    endpoints = [
        ("GET /health (Middleware baseline)", "GET", "/health", None, 100),
        ("POST /api/v1/simulate (Quarter car enqueue)", "POST", "/api/v1/simulate", {
            "params": {"m_s": 300.0, "m_u": 40.0, "k_s": 25000.0, "c": 1500.0, "k_t": 190000.0, "MR": 1.0},
            "profile": {"profile_type": "step", "amplitude": 0.05, "duration": 2.0}
        }, 50),
        ("POST /api/v1/simulate/half-car (4-DOF Pitch solve)", "POST", "/api/v1/simulate/half-car", {
            "params": {"m_s": 1200.0, "I_y": 1800.0, "m_uf": 40.0, "m_ur": 40.0, "k_sf": 30000.0, "k_sr": 35000.0, "c_f": 2500.0, "c_r": 3000.0, "k_tf": 190000.0, "k_tr": 190000.0, "a": 1.2, "b": 1.4},
            "profile": {"profile_type": "sine", "amplitude": 0.02, "duration": 2.0}
        }, 40),
        ("POST /api/v1/simulate/full-car (7-DOF 4-Corner solve)", "POST", "/api/v1/simulate/full-car", {
            "params": {
                "m_s": 1200.0, "I_x": 300.0, "I_y": 800.0,
                "m_ufl": 40.0, "m_ufr": 40.0, "m_url": 40.0, "m_urr": 40.0,
                "k_sfl": 25000.0, "k_sfr": 25000.0, "k_srl": 28000.0, "k_srr": 28000.0,
                "c_fl": 1500.0, "c_fr": 1500.0, "c_rl": 1600.0, "c_rr": 1600.0,
                "k_arb_f": 5000.0, "k_arb_r": 4000.0,
                "k_tfl": 190000.0, "k_tfr": 190000.0, "k_trl": 190000.0, "k_trr": 190000.0,
                "L": 2.6, "a": 1.2, "b": 1.4, "tw_f": 1.5, "tw_r": 1.5, "speed_mps": 20.0
            },
            "profile": {"profile_type": "step", "amplitude": 0.05, "duration": 2.0}
        }, 30),
        ("POST /api/v1/simulate/handling (Enqueue Maneuver)", "POST", "/api/v1/simulate/handling", {
            "params": {"m": 1200.0, "I_z": 2000.0, "h_cg": 0.4, "roll_dist": 0.55},
            "maneuver_type": "Step Steer (J-Turn)", "v_init_kph": 80.0
        }, 30),
        ("POST /api/v1/kinematics/solve (Sweep 33 steps)", "POST", "/api/v1/kinematics/solve", {
            "hardpoints": DEFAULT_HARDPOINTS,
            "z_min_mm": -80.0, "z_max_mm": 80.0, "n_steps": 33
        }, 40),
        ("POST /api/v1/sensitivity (6-param Perturbation)", "POST", "/api/v1/sensitivity", {
            "params": {"m_s": 300.0, "m_u": 40.0, "k_s": 25000.0, "c": 1500.0, "k_t": 190000.0, "MR": 1.0},
            "profile": {"profile_type": "step", "amplitude": 0.05, "duration": 2.0}
        }, 20),
        ("POST /api/v1/optimize (Job Enqueue)", "POST", "/api/v1/optimize", {
            "params": {"m_s": 300.0, "m_u": 40.0, "k_s": 25000.0, "c": 1500.0, "k_t": 190000.0, "MR": 1.0},
            "profile": {"profile_type": "step", "amplitude": 0.05, "duration": 2.0},
            "objective_type": "comfort",
            "max_travel": 0.08
        }, 30),
        ("POST /api/v1/auth/login (Argon2 Verify)", "POST", "/api/v1/auth/login", {
            "email": "demo@suspensionlab.io",
            "password": "demo1234"
        }, 25),
    ]

    results = []
    for name, method, path, payload, iterations in endpoints:
        durations = []
        status_codes = []
        for i in range(iterations):
            req_headers = auth_headers.copy()
            req_headers["X-Forwarded-For"] = f"10.0.{i // 256}.{i % 256}"
            t0 = time.perf_counter()
            if method == "GET":
                res = client.get(path, headers=req_headers)
            else:
                res = client.post(path, json=payload, headers=req_headers)
            t1 = time.perf_counter()
            durations.append((t1 - t0) * 1000.0)
            status_codes.append(res.status_code)

        p50 = percentile(durations, 50)
        p95 = percentile(durations, 95)
        p99 = percentile(durations, 99)
        avg = statistics.mean(durations)
        min_d = min(durations)
        max_d = max(durations)
        rps = 1000.0 / avg if avg > 0 else 0.0
        success_rate = (sum(1 for s in status_codes if s < 400) / len(status_codes)) * 100.0

        results.append([
            name,
            f"{p50:.2f} ms",
            f"{p95:.2f} ms",
            f"{p99:.2f} ms",
            f"{avg:.2f} ms",
            f"{min_d:.2f} ms",
            f"{max_d:.2f} ms",
            f"{rps:.1f}",
            f"{success_rate:.0f}%"
        ])

    headers_table = ["Endpoint", "p50", "p95", "p99", "Mean", "Min", "Max", "Est. RPS", "Success"]
    print_table(headers_table, results)

# ==============================================================================
# 2. WORKERS BENCHMARKS (Queue, Execution, Throughput, CPU/RAM, Parallelism, Retry)
# ==============================================================================
def benchmark_workers():
    print_header("2. WORKERS PERFORMANCE FORENSICS (EXECUTION, THROUGHPUT, MEMORY & CONCURRENCY)")
    process = psutil.Process(os.getpid())

    job_types = [
        ("SIMULATE_QUARTER (10s ODE RK4)", lambda: run_quarter_car_analysis(
            QuarterCarParams(m_s=300.0, m_u=40.0, k_s=25000.0, c=1500.0, k_t=190000.0, MR=1.0),
            RoadProfile(profile_type="step", amplitude=0.05, duration=10.0)
        ), 50),
        ("SIMULATE_HALF (Pitch/Bounce 4-DOF)", lambda: run_half_car_analysis(
            HalfCarParams(m_s=1200.0, I_y=1800.0, m_uf=40.0, m_ur=40.0, k_sf=30000.0, k_sr=35000.0, c_f=2500.0, c_r=3000.0, k_tf=190000.0, k_tr=190000.0, a=1.2, b=1.4),
            RoadProfile(profile_type="sine", amplitude=0.02, duration=5.0)
        ), 30),
        ("SIMULATE_FULL (7-DOF 4-Corner)", lambda: run_full_car_analysis(
            FullCarParams(
                m_s=1200.0, I_x=300.0, I_y=800.0,
                m_uf=40.0, m_ur=40.0,
                k_sf=25000.0, k_sr=28000.0,
                c_f=1500.0, c_r=1600.0,
                k_arb_f=5000.0, k_arb_r=4000.0,
                k_tf=190000.0, k_tr=190000.0,
                L=2.6, a=1.2, b=1.4, tw_f=1.5, tw_r=1.5, speed_mps=20.0
            ),
            FourCornerRoadProfile(time=np.arange(0, 5.0, 0.002), z_rfl=np.zeros(2500), z_rfr=np.zeros(2500), z_rrl=np.zeros(2500), z_rrr=np.zeros(2500))
        ), 20),
        ("SIMULATE_HANDLING (Bicycle Pacejka)", lambda: simulate_maneuver(
            HandlingParams(m=1200.0, I_z=2000.0, a=1.2, b=1.4),
            80.0 / 3.6, lambda t: 0.05 if t > 1.0 else 0.0, lambda t: 0.0, lambda t: 0.0, 5.0
        ), 30),
        ("OPTIMIZE_QUARTER (Nelder-Mead)", lambda: optimize_setup(
            QuarterCarParams(m_s=300.0, m_u=40.0, k_s=25000.0, c=1500.0, k_t=190000.0, MR=1.0),
            RoadProfile(profile_type="step", amplitude=0.05, duration=2.0),
            "comfort", 0.08, None
        ), 15),
        ("KINEMATICS_SWEEP (Double Wishbone)", lambda: solve_kinematics(
            DEFAULT_HARDPOINTS, -80.0, 80.0, 33
        ), 40)
    ]

    worker_results = []
    for name, fn, iters in job_types:
        durations = []
        cpu_start = process.cpu_percent(interval=None)
        mem_before = process.memory_info().rss / (1024 * 1024)

        for _ in range(iters):
            t0 = time.perf_counter()
            fn()
            t1 = time.perf_counter()
            durations.append((t1 - t0) * 1000.0)

        cpu_end = process.cpu_percent(interval=None)
        mem_after = process.memory_info().rss / (1024 * 1024)

        avg_ms = statistics.mean(durations)
        p50 = percentile(durations, 50)
        p95 = percentile(durations, 95)
        p99 = percentile(durations, 99)
        throughput = 1000.0 / avg_ms if avg_ms > 0 else 0.0

        worker_results.append([
            name,
            f"{p50:.2f} ms",
            f"{p95:.2f} ms",
            f"{p99:.2f} ms",
            f"{throughput:.1f} jobs/s",
            f"{mem_after - mem_before:+.2f} MB",
            f"{(cpu_start + cpu_end)/2:.1f}%"
        ])

    print_table(["Job Payload", "p50 Execution", "p95 Execution", "p99 Execution", "Single-Worker Tput", "RAM Delta", "Avg CPU"], worker_results)

    # Parallelism Scaling Benchmark (1, 2, 4, 8 concurrent workers)
    print("\n--- Parallelism Scaling (Quarter Car Simulation Jobs) ---")
    parallelism_results = []
    test_fn = lambda: run_quarter_car_analysis(
        QuarterCarParams(m_s=300.0, m_u=40.0, k_s=25000.0, c=1500.0, k_t=190000.0, MR=1.0),
        RoadProfile(profile_type="step", amplitude=0.05, duration=3.0)
    )

    total_batch_jobs = 40
    base_t_total = None
    for workers in [1, 2, 4, 8]:
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(test_fn) for _ in range(total_batch_jobs)]
            concurrent.futures.wait(futures)
        t_total = time.perf_counter() - t0
        if base_t_total is None:
            base_t_total = t_total
        tput = total_batch_jobs / t_total
        speedup = base_t_total / t_total
        parallelism_results.append([
            f"{workers} Workers",
            f"{total_batch_jobs} jobs",
            f"{t_total:.2f} s",
            f"{tput:.1f} jobs/s",
            f"{speedup:.2f}x"
        ])

    print_table(["Concurrency", "Batch Size", "Total Wall Time", "Aggregate Tput", "Speedup Factor"], parallelism_results)

    # Retry Cost & Fault Recovery Measurement
    print("\n--- Retry Cost & Exception Overhead ---")
    def failing_job_sim():
        try:
            raise ValueError("Numerical convergence failure in tire saturation solver")
        except Exception as e:
            err_dict = {"status": "FAILED", "error": str(e), "traceback": "Simulated traceback trace for line 42", "retry_count": 3}
            json_err = json.dumps(err_dict)
            return json_err

    retry_durations = []
    for _ in range(1000):
        t0 = time.perf_counter()
        failing_job_sim()
        t1 = time.perf_counter()
        retry_durations.append((t1 - t0) * 1000.0)

    print(f"  Retry Serialization & Exception Trap: p50={percentile(retry_durations, 50):.4f} ms, p99={percentile(retry_durations, 99):.4f} ms")

# ==============================================================================
# 3. DATABASE BENCHMARKS (Queries, N+1, Indexes, Connection Pools, Locks, JSON)
# ==============================================================================
async def benchmark_database_async():
    print_header("3. DATABASE PERFORMANCE FORENSICS (SLOW QUERIES, N+1, INDEXES, POOLS, JSON)")
    
    test_user_id = uuid.uuid4()
    test_team_id = uuid.uuid4()
    
    async with SessionLocal() as session:
        user = User(id=test_user_id, email=f"bench_{uuid.uuid4().hex[:8]}@example.com", password_hash="argon2id$mockhash", plan="PRO")
        session.add(user)
        await session.flush()
        team = Team(id=test_team_id, name="Performance Benchmark Team", slug=f"bench-team-{uuid.uuid4().hex[:8]}", owner_id=test_user_id)
        session.add(team)
        await session.commit()

        sample_result = {
            "time": [i*0.001 for i in range(1000)],
            "z_s": [math.sin(i*0.01)*0.02 for i in range(1000)],
            "z_u": [math.sin(i*0.05)*0.01 for i in range(1000)],
            "susp_travel": [0.01 for _ in range(1000)],
            "metrics": {"rms_body_accel": 0.42, "max_susp_travel": 0.038, "ptp_body_accel": 1.25}
        }
        
        base_seq = int(time.time() * 100) % 80000000 + 100000
        runs = []
        for i in range(100):
            r = SimulationRun(
                id=uuid.uuid4(),
                seq=base_seq + i,
                label=f"RUN-{base_seq + i:08d}",
                user_id=test_user_id,
                team_id=test_team_id,
                simulation_type="quarter_car",
                title=f"Benchmark Run #{i}",
                params={"m_s": 300.0, "k_s": 25000.0, "c": 1500.0},
                profile={"profile_type": "step", "amplitude": 0.05},
                result=sample_result,
                software_version="1.0.0",
                physics_version="1.0.0",
                solver_version="1.0.0",
                params_hash=f"hash_p_{i}",
                result_hash=f"hash_r_{i}"
            )
            runs.append(r)
        session.add_all(runs)

        for i in range(50):
            j = JobRecord(
                id=uuid.uuid4(),
                user_id=test_user_id,
                team_id=test_team_id,
                job_type="OPTIMIZE_QUARTER",
                status="COMPLETED" if i % 2 == 0 else "PENDING",
                params={"m_s": 300.0},
                result=sample_result
            )
            session.add(j)
        await session.commit()

    # Benchmark A: N+1 vs Eager Loading
    durations_lazy = []
    durations_eager = []

    async with SessionLocal() as session:
        for _ in range(10):
            t0 = time.perf_counter()
            result = await session.execute(select(JobRecord).limit(30))
            jobs = result.scalars().all()
            for job in jobs:
                if job.user_id:
                    u_res = await session.execute(select(User).where(User.id == job.user_id))
                    _ = u_res.scalars().first()
            durations_lazy.append((time.perf_counter() - t0) * 1000.0)

        for _ in range(10):
            t0 = time.perf_counter()
            result = await session.execute(select(JobRecord).options(joinedload(JobRecord.user)).limit(30))
            jobs = result.scalars().all()
            for job in jobs:
                _ = job.user
            durations_eager.append((time.perf_counter() - t0) * 1000.0)

    # Benchmark B: Indexed Lookup vs Unindexed Scan
    durations_indexed = []
    durations_scan = []
    target_label = f"RUN-{base_seq + 42:08d}"

    async with SessionLocal() as session:
        for _ in range(50):
            t0 = time.perf_counter()
            res = await session.execute(select(SimulationRun).where(SimulationRun.label == target_label))
            _ = res.scalars().first()
            durations_indexed.append((time.perf_counter() - t0) * 1000.0)

        for _ in range(50):
            t0 = time.perf_counter()
            res = await session.execute(select(SimulationRun).where(SimulationRun.title == "Benchmark Run #42"))
            _ = res.scalars().first()
            durations_scan.append((time.perf_counter() - t0) * 1000.0)

    # Benchmark C: JSON Column Serialization, Storage & Extraction
    json_sizes = [("10 KB", 100), ("100 KB", 1000), ("1 MB", 10000)]
    json_results = []
    for label, count in json_sizes:
        data_blob = {"chassis_accel": [math.sin(x)*9.81 for x in range(count)], "timestamps": [x*0.001 for x in range(count)]}
        t0 = time.perf_counter()
        encoded = json.dumps(data_blob)
        t_enc = (time.perf_counter() - t0) * 1000.0
        
        t0 = time.perf_counter()
        decoded = json.loads(encoded)
        t_dec = (time.perf_counter() - t0) * 1000.0
        json_results.append([label, f"{len(encoded)/1024:.1f} KB", f"{t_enc:.3f} ms", f"{t_dec:.3f} ms"])

    # Benchmark D: Connection Pool Contention Simulation (10, 20, 50, 100 concurrent async sessions)
    pool_results = []
    for concurrency in [10, 20, 50, 100]:
        async def mock_db_tx():
            t_acq = time.perf_counter()
            async with SessionLocal() as session:
                t_got = time.perf_counter()
                res = await session.execute(select(func.count(SimulationRun.id)))
                _ = res.scalar()
                t_done = time.perf_counter()
                return (t_got - t_acq) * 1000.0, (t_done - t_got) * 1000.0

        t_start_batch = time.perf_counter()
        tasks = [mock_db_tx() for _ in range(concurrency)]
        out = await asyncio.gather(*tasks, return_exceptions=True)
        t_total_batch = (time.perf_counter() - t_start_batch) * 1000.0
        
        acq_times = [o[0] for o in out if isinstance(o, tuple)]
        exec_times = [o[1] for o in out if isinstance(o, tuple)]
        failures = sum(1 for o in out if isinstance(o, Exception))
        
        pool_results.append([
            f"{concurrency} Sessions",
            f"{percentile(acq_times, 50):.2f} ms",
            f"{percentile(acq_times, 95):.2f} ms",
            f"{percentile(exec_times, 50):.2f} ms",
            f"{t_total_batch:.1f} ms",
            f"{failures} errors"
        ])

    print("\n--- A. N+1 Query vs Eager Loading Overhead ---")
    print_table(["Strategy", "Queries Executed", "p50 Latency", "p95 Latency", "Speedup"], [
        ["N+1 Lazy Queries", "31 SQL queries", f"{percentile(durations_lazy, 50):.2f} ms", f"{percentile(durations_lazy, 95):.2f} ms", "1.0x (Baseline)"],
        ["Eager joinedload()", "1 SQL query", f"{percentile(durations_eager, 50):.2f} ms", f"{percentile(durations_eager, 95):.2f} ms", f"{statistics.mean(durations_lazy)/statistics.mean(durations_eager):.2f}x Faster"]
    ])

    print("\n--- B. Index Lookup vs Unindexed Table Scan ---")
    print_table(["Query Type", "Target Column", "p50 Latency", "p95 Latency", "Ratio"], [
        ["Unique Indexed Lookup", "label (ix_simruns_label)", f"{percentile(durations_indexed, 50):.2f} ms", f"{percentile(durations_indexed, 95):.2f} ms", "1.0x"],
        ["Unindexed Full Scan", "title (no index)", f"{percentile(durations_scan, 50):.2f} ms", f"{percentile(durations_scan, 95):.2f} ms", f"{statistics.mean(durations_scan)/statistics.mean(durations_indexed):.2f}x Slower"]
    ])

    print("\n--- C. JSON Payload Processing Overhead ---")
    print_table(["Telemetry Size", "Payload Wire Size", "Serialization", "Deserialization"], json_results)

    print("\n--- D. Connection Pool & Concurrency Scaling ---")
    print_table(["Concurrency", "p50 Acquire", "p95 Acquire", "p50 Exec", "Total Batch Time", "Failures"], pool_results)

# ==============================================================================
# 4. LOAD SIMULATION (1, 10, 50, 100, 500 Virtual Users)
# ==============================================================================
def benchmark_load(auth_headers):
    print_header("4. LOAD & CONCURRENCY FORENSICS (1, 10, 50, 100, 500 VIRTUAL USERS)")
    client = TestClient(app)

    def simulate_user_session(user_idx):
        latencies = []
        errors = 0
        req_headers = auth_headers.copy()
        req_headers["X-Forwarded-For"] = f"10.1.{user_idx // 256}.{user_idx % 256}"
        
        # 1. Simulation call (40% weight)
        t0 = time.perf_counter()
        r1 = client.post("/api/v1/simulate/half-car", json={
            "params": {"m_s": 1200.0, "I_y": 1800.0, "m_uf": 40.0, "m_ur": 40.0, "k_sf": 30000.0, "k_sr": 35000.0, "c_f": 2500.0, "c_r": 3000.0, "k_tf": 190000.0, "k_tr": 190000.0, "a": 1.2, "b": 1.4},
            "profile": {"profile_type": "sine", "amplitude": 0.02, "duration": 2.0}
        }, headers=req_headers)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        if r1.status_code >= 400: errors += 1

        # 2. Kinematics call (20% weight)
        t0 = time.perf_counter()
        r2 = client.post("/api/v1/kinematics/solve", json={
            "hardpoints": DEFAULT_HARDPOINTS,
            "z_min_mm": -80.0, "z_max_mm": 80.0, "n_steps": 33
        }, headers=req_headers)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        if r2.status_code >= 400: errors += 1

        # 3. Health / Metadata (20% weight)
        t0 = time.perf_counter()
        r3 = client.get("/health", headers=req_headers)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        if r3.status_code >= 400: errors += 1

        # 4. Simulation enqueue (20% weight)
        t0 = time.perf_counter()
        r4 = client.post("/api/v1/simulate", json={
            "params": {"m_s": 300.0, "m_u": 40.0, "k_s": 25000.0, "c": 1500.0, "k_t": 190000.0, "MR": 1.0},
            "profile": {"profile_type": "step", "amplitude": 0.05, "duration": 2.0}
        }, headers=req_headers)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        if r4.status_code >= 400: errors += 1

        return latencies, errors

    user_levels = [1, 10, 50, 100, 500]
    load_table = []

    for vusers in user_levels:
        t_start = time.perf_counter()
        all_latencies = []
        total_errors = 0
        total_requests = vusers * 4

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(vusers, 32)) as executor:
            futures = [executor.submit(simulate_user_session, i) for i in range(vusers)]
            for fut in concurrent.futures.as_completed(futures):
                lats, errs = fut.result()
                all_latencies.extend(lats)
                total_errors += errs

        t_elapsed = time.perf_counter() - t_start
        rps = total_requests / t_elapsed if t_elapsed > 0 else 0.0
        p50 = percentile(all_latencies, 50)
        p95 = percentile(all_latencies, 95)
        p99 = percentile(all_latencies, 99)
        err_pct = (total_errors / total_requests) * 100.0

        load_table.append([
            f"{vusers} Users",
            f"{total_requests} reqs",
            f"{t_elapsed:.2f} s",
            f"{rps:.1f} req/s",
            f"{p50:.2f} ms",
            f"{p95:.2f} ms",
            f"{p99:.2f} ms",
            f"{err_pct:.1f}%"
        ])

    print_table(["Concurrency Level", "Total Requests", "Wall Time", "Throughput (RPS)", "p50 Latency", "p95 Latency", "p99 Latency", "Error Rate"], load_table)

if __name__ == "__main__":
    user_id = asyncio.run(init_benchmark_db())
    token = create_access_token({"sub": user_id, "plan": "ENTERPRISE"})
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    benchmark_apis(auth_headers)
    benchmark_workers()
    asyncio.run(benchmark_database_async())
    benchmark_load(auth_headers)
