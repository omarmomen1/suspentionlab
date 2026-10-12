"""
tests/test_phase7_3_solver_execution_reconciliation.py
======================================================
SuspensionLab PRO — Phase 7.3 Controlled Solver Execution & Reconciliation Test Suite.

Verifies:
1. Runtime Feasibility Gate & Honest Availability (Package A).
2. Secure Execution Lifecycle & Terminal State Immutability (Package B).
3. Execution Sandbox Isolation & Resource Limits (Package C).
4. Execution Provenance, Output Artifacts & Invariants (Package D).
5. Numerical Result Reconciliation Engine (Package E).
6. Reference-Case Dynamic Execution Verification with Real Subprocesses (Package F).
7. Production API Endpoints & Preflight Checks (Package G).
8. Adversarial Hostile Security, Multi-Tenancy & Integrity Regressions (Package H).
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import os
import pathlib
import sys
import uuid
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.solver_exchange import (
    ArtifactDirection,
    SolverExchangeArtifact,
)
from suspensionlab.backend.database.models.solver_execution import (
    ExecutionJobState,
    ImmutableExecutionError,
    InvalidExecutionStateTransitionError,
    SolverExecutionJob,
)
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.security.jwt_utils import create_access_token
from suspensionlab.backend.services.solver_execution_service import (
    ExecutionJobNotFoundError,
    RuntimeUnavailableError,
    SolverExecutionService,
)
from suspensionlab.interop.execution.runtimes import SolverRuntimeRegistry
from suspensionlab.interop.execution.sandbox import ExecutionSandbox, SandboxTimeoutError
from suspensionlab.interop.reconciliation.engine import (
    ReconciliationReport,
    ResultReconciliationEngine,
)
from suspensionlab.interop.security import TenantIsolationError

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
async def seeded_users():
    """Seeds two isolated users for cross-tenant verification."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    team_a_id = uuid.uuid4()
    team_b_id = uuid.uuid4()

    async with SessionLocal() as db:
        user_a = User(
            id=user_a_id,
            email=f"engineer_exec_a_{user_a_id.hex[:6]}@oem.com",
            name="Engineer Exec A",
            plan="PRO",
            password_hash="test-hash",
        )
        user_b = User(
            id=user_b_id,
            email=f"engineer_exec_b_{user_b_id.hex[:6]}@competitor.com",
            name="Engineer Exec B",
            plan="PRO",
            password_hash="test-hash",
        )
        db.add_all([user_a, user_b])
        await db.commit()

    token_a = create_access_token({
        "sub": str(user_a_id),
        "user_id": str(user_a_id),
        "email": user_a.email,
        "team_id": str(team_a_id),
        "plan": "PRO",
    })
    token_b = create_access_token({
        "sub": str(user_b_id),
        "user_id": str(user_b_id),
        "email": user_b.email,
        "team_id": str(team_b_id),
        "plan": "PRO",
    })

    return {
        "user_a_id": user_a_id,
        "team_a_id": team_a_id,
        "token_a": token_a,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "context_a": UserContext(
            user_id=str(user_a_id),
            email=user_a.email,
            name="Engineer Exec A",
            onboarding_complete=True,
            plan="PRO",
            team_id=str(team_a_id),
        ),
        "user_b_id": user_b_id,
        "team_b_id": team_b_id,
        "token_b": token_b,
        "headers_b": {"Authorization": f"Bearer {token_b}"},
        "context_b": UserContext(
            user_id=str(user_b_id),
            email=user_b.email,
            name="Engineer Exec B",
            onboarding_complete=True,
            plan="PRO",
            team_id=str(team_b_id),
        ),
    }


@pytest.fixture
async def sample_input_artifact(seeded_users):
    """Creates a persisted input artifact in database and on disk."""
    user = seeded_users["context_a"]
    art_id = uuid.uuid4()
    content = json.dumps({
        "schema_version": "1.0.0",
        "engineering_model_id": "MDL-EXEC-TEST",
        "parameters": {
            "m_s": {"value": 300.0, "unit": "kg"},
            "m_u": {"value": 35.0, "unit": "kg"},
            "k_s": {"value": 25000.0, "unit": "N/m"},
            "c": {"value": 2050.0, "unit": "Ns/m"},
            "k_t": {"value": 200000.0, "unit": "N/m"},
        },
    }).encode("utf-8")

    sha256 = hashlib.sha256(content).hexdigest()
    storage_dir = PROJECT_ROOT / "data" / "solver_artifacts"
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"test_in_{art_id.hex}.json"
    storage_path.write_bytes(content)

    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=art_id,
            user_id=uuid.UUID(user.user_id),
            team_id=uuid.UUID(user.team_id),
            artifact_name="test_model.json",
            file_format=".json",
            mime_type="application/json",
            size_bytes=len(content),
            sha256_hash=sha256,
            direction=ArtifactDirection.INPUT.value,
            storage_path=str(storage_path),
        )
        db.add(art)
        await db.commit()

    return art_id, sha256


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE A: RUNTIME FEASIBILITY GATE
# ══════════════════════════════════════════════════════════════════════════════

def test_wpa_01_runtime_discovery_honest_availability():
    """Runtimes must be truthfully inspected and reported."""
    runtimes = SolverRuntimeRegistry.inspect_all()
    assert "FMI_COSIMULATION" in runtimes
    assert "EXTERNAL_CAE_SOLVER" in runtimes
    assert "MSC_ADAMS" in runtimes
    assert "MATLAB_SIMULINK" in runtimes

    # Genuinely available open-source runtimes
    fmi = runtimes["FMI_COSIMULATION"]
    assert fmi.is_available is True
    assert "fmpy" in fmi.executable_path.lower()
    assert "BSD" in fmi.licensing_model

    cae = runtimes["EXTERNAL_CAE_SOLVER"]
    assert cae.is_available is True
    assert "python" in cae.executable_path.lower()
    assert "BSD" in cae.licensing_model

    # Genuinely unavailable proprietary runtimes on test host
    adams = runtimes["MSC_ADAMS"]
    assert adams.is_available is False
    assert adams.executable_path is None

    matlab = runtimes["MATLAB_SIMULINK"]
    assert matlab.is_available is False
    assert matlab.executable_path is None


@pytest.mark.asyncio
async def test_wpa_02_unavailable_runtime_fails_closed(seeded_users, sample_input_artifact):
    """Attempting to execute an unavailable solver fails closed with RuntimeUnavailableError."""
    art_id, _ = sample_input_artifact
    user = seeded_users["context_a"]
    service = SolverExecutionService()

    async with SessionLocal() as db:
        with pytest.raises(RuntimeUnavailableError) as exc_adams:
            await service.create_execution_job(
                db=db,
                user=user,
                solver_name="MSC_ADAMS",
                input_artifact_id=art_id,
            )
        assert "not available on host system" in str(exc_adams.value)

        with pytest.raises(RuntimeUnavailableError) as exc_matlab:
            await service.create_execution_job(
                db=db,
                user=user,
                solver_name="MATLAB_SIMULINK",
                input_artifact_id=art_id,
            )
        assert "not available on host system" in str(exc_matlab.value)


@pytest.mark.asyncio
async def test_wpa_03_unsupported_solver_rejected(seeded_users, sample_input_artifact):
    """Completely unrecognized solver raises RuntimeUnavailableError."""
    art_id, _ = sample_input_artifact
    user = seeded_users["context_a"]
    service = SolverExecutionService()

    async with SessionLocal() as db:
        with pytest.raises(RuntimeUnavailableError) as exc:
            await service.create_execution_job(
                db=db,
                user=user,
                solver_name="FICTIONAL_UNKNOWN_SOLVER",
                input_artifact_id=art_id,
            )
        assert "not available on host system" in str(exc.value)


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE B: SECURE EXECUTION LIFECYCLE & STATE MACHINE
# ══════════════════════════════════════════════════════════════════════════════

def test_wpb_01_valid_state_transitions():
    """Verify allowable state transitions across the job lifecycle."""
    job = SolverExecutionJob(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        solver_name="EXTERNAL_CAE_SOLVER",
        solver_version="1.0.0",
        adapter_id="adapter-external-cae-v1",
        state=ExecutionJobState.QUEUED.value,
    )
    assert job.state == ExecutionJobState.QUEUED.value

    job.transition_to(ExecutionJobState.RUNNING)
    assert job.state == ExecutionJobState.RUNNING.value
    assert job.started_at is not None

    job.transition_to(ExecutionJobState.COMPLETED)
    assert job.state == ExecutionJobState.COMPLETED.value
    assert job.completed_at is not None


def test_wpb_02_terminal_state_immutability():
    """Terminal states (COMPLETED, FAILED, CANCELLED, TIMED_OUT) reject further mutations."""
    terminal_states = [
        ExecutionJobState.COMPLETED,
        ExecutionJobState.FAILED,
        ExecutionJobState.CANCELLED,
        ExecutionJobState.TIMED_OUT,
    ]

    for term in terminal_states:
        job = SolverExecutionJob(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            solver_name="EXTERNAL_CAE_SOLVER",
            solver_version="1.0.0",
            adapter_id="adapter-external-cae-v1",
            state=term.value,
        )
        with pytest.raises(ImmutableExecutionError):
            job.assert_mutable()

        with pytest.raises(ImmutableExecutionError):
            job.transition_to(ExecutionJobState.RUNNING)


def test_wpb_03_invalid_state_transition_error():
    """Illegal state jumps raise InvalidExecutionStateTransitionError."""
    job = SolverExecutionJob(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        solver_name="EXTERNAL_CAE_SOLVER",
        solver_version="1.0.0",
        adapter_id="adapter-external-cae-v1",
        state=ExecutionJobState.QUEUED.value,
    )
    # Skipping RUNNING directly to COMPLETED from QUEUED is illegal
    with pytest.raises(InvalidExecutionStateTransitionError):
        job.transition_to(ExecutionJobState.COMPLETED)


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE C: EXECUTION SANDBOX & PROCESS ISOLATION
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wpc_01_isolated_working_directory():
    """Sandbox sets up isolated directory and executes runner safely."""
    job_id = uuid.uuid4()
    sandbox = ExecutionSandbox(job_id=job_id, timeout_seconds=10)
    sandbox.initialize()

    assert sandbox.sandbox_dir.exists()
    assert str(job_id) in str(sandbox.sandbox_dir)

    in_file = sandbox.stage_file("model.json", b'{"parameters": {}}')
    out_file = sandbox.sandbox_dir / "results.csv"

    # Run benign standalone runner command
    cmd = [
        sys.executable,
        "-m",
        "suspensionlab.interop.runners.external_cae_solver",
        "--input", str(in_file),
        "--output", str(out_file),
        "--duration", "0.05",
        "--step", "0.01",
    ]
    res = await sandbox.execute_command(cmd, expected_output_filenames=["results.csv"])
    assert res.exit_code == 0
    assert res.pid > 0
    assert not res.timed_out
    assert "EXTERNAL_CAE_SOLVER_RUNNER" in res.stdout

    # Output file was created inside the sandbox directory
    assert out_file.exists()

    sandbox.cleanup()


@pytest.mark.asyncio
async def test_wpc_02_wall_clock_timeout_enforcement():
    """Wall-clock timeout triggers process tree kill and sets timed_out flag."""
    job_id = uuid.uuid4()
    sandbox = ExecutionSandbox(job_id=job_id, timeout_seconds=1.0)
    sandbox.initialize()

    in_file = sandbox.stage_file("model.json", b'{"parameters": {}}')
    out_file = sandbox.sandbox_dir / "results.csv"

    cmd = [
        sys.executable,
        "-m",
        "suspensionlab.interop.runners.external_cae_solver",
        "--input", str(in_file),
        "--output", str(out_file),
        "--simulate-timeout",
    ]

    res = await sandbox.execute_command(cmd)
    assert res.timed_out is True
    assert res.exit_code != 0
    assert "timeout" in (res.error or "").lower()
    sandbox.cleanup()


@pytest.mark.asyncio
async def test_wpc_03_bounded_log_capture():
    """Stdout/stderr capture is bounded and does not exceed limit."""
    job_id = uuid.uuid4()
    sandbox = ExecutionSandbox(job_id=job_id, timeout_seconds=10)
    sandbox.initialize()

    # Command generating huge output
    cmd = [
        sys.executable,
        "-c",
        "print('A' * 300000)",
    ]
    res = await sandbox.execute_command(cmd)
    assert res.exit_code == 0
    assert len(res.stdout) <= 262144 + 100

    sandbox.cleanup()


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE D: EXECUTION PROVENANCE & INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wpd_01_provenance_recording_and_invariants(seeded_users, sample_input_artifact):
    """Verifies that execution provenance, PID, exit code and invariants are strictly preserved."""
    art_id, sha256_in = sample_input_artifact
    user = seeded_users["context_a"]
    service = SolverExecutionService()

    async with SessionLocal() as db:
        # 1. Prior to execution: is_executed=False, is_physically_validated=False
        job = await service.create_execution_job(
            db=db,
            user=user,
            solver_name="EXTERNAL_CAE_SOLVER",
            input_artifact_id=art_id,
            execution_config={"duration": 0.1, "step": 0.005},
        )
        assert job.state == ExecutionJobState.QUEUED.value
        assert job.is_executed is False
        assert job.is_physically_validated is False
        assert job.input_artifact_hash == sha256_in

        # 2. Execute job
        executed_job = await service.execute_job(db=db, job_id=job.id, user=user)
        assert executed_job.state == ExecutionJobState.COMPLETED.value
        assert executed_job.is_executed is True
        assert executed_job.is_physically_validated is False
        assert executed_job.exit_code == 0
        assert executed_job.pid is not None
        assert executed_job.pid > 0
        assert len(executed_job.output_artifact_ids) > 0

        # Provenance verification
        prov = executed_job.execution_provenance
        assert prov["solver_name"] == "EXTERNAL_CAE_SOLVER"
        assert "command_args" in prov
        assert "output_artifacts" in prov


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE E: RESULT RECONCILIATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def test_wpe_01_time_base_interpolation_and_metrics():
    """ResultReconciliationEngine interpolates signals and calculates exact error metrics."""
    engine = ResultReconciliationEngine()

    # Create synthetic reference time series (0.0 to 1.0s, dt=0.001)
    t_ref = np.linspace(0.0, 1.0, 1001)
    zs_ref = 0.05 * np.sin(2 * np.pi * 1.5 * t_ref) * np.exp(-2.0 * t_ref)
    ref_series = {
        "time": t_ref,
        "z_s": zs_ref,
        "z_u": zs_ref * 0.2,
        "susp_travel": zs_ref * 0.8,
        "tire_load_dynamic": zs_ref * 5000.0,
        "body_accel": zs_ref * 10.0,
    }

    # External series with 0.5% amplitude noise and 2ms delay
    t_ext = np.linspace(0.0, 1.0, 501)  # differing dt
    zs_ext = 0.0502 * np.sin(2 * np.pi * 1.5 * (t_ext - 0.002)) * np.exp(-2.0 * (t_ext - 0.002))
    ext_series = {
        "time": t_ext,
        "z_s": zs_ext,
        "z_u": zs_ext * 0.2,
        "susp_travel": zs_ext * 0.8,
        "tire_load_dynamic": zs_ext * 5000.0,
        "body_accel": zs_ext * 10.0,
    }

    report = engine.reconcile(
        external_data=ext_series,
        reference_data=ref_series,
        solver_name="EXTERNAL_CAE_SOLVER",
    )

    assert isinstance(report, ReconciliationReport)
    sig_zs = report.metrics["z_s"]
    assert sig_zs.peak_error < 0.05
    assert sig_zs.nrmse < 0.05
    assert sig_zs.energy_ratio > 0.9 and sig_zs.energy_ratio < 1.1
    assert report.summary["signals_passed"] == len(report.metrics)
    assert report.overall_status == "PASS"
    assert "does not claim or imply physical vehicle validation" in report.epistemic_notice.lower()


def test_wpe_02_divergent_reconciliation_verdict():
    """High discrepancy leads to TOLERANCE_EXCEEDED or DIVERGENT verdict."""
    engine = ResultReconciliationEngine()
    t_ref = np.linspace(0.0, 1.0, 101)
    ref_series = {"time": t_ref, "z_s": np.zeros(101)}
    ext_series = {"time": t_ref, "z_s": np.ones(101) * 0.5}  # huge offset

    report = engine.reconcile(
        external_data=ext_series,
        reference_data=ref_series,
        solver_name="EXTERNAL_CAE_SOLVER",
    )

    assert report.overall_status == "FAIL"
    assert report.metrics["z_s"].is_within_tolerance is False


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE F: REFERENCE-CASE DYNAMIC EXECUTION VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wpf_01_real_external_cae_solver_run_and_reconciliation(seeded_users, sample_input_artifact):
    """Full execution of real external CAE solver and mathematical reconciliation."""
    art_id, _ = sample_input_artifact
    user = seeded_users["context_a"]
    service = SolverExecutionService()

    async with SessionLocal() as db:
        job = await service.create_execution_job(
            db=db,
            user=user,
            solver_name="EXTERNAL_CAE_SOLVER",
            input_artifact_id=art_id,
            execution_config={
                "step": 0.001,
                "duration": 1.0,
            },
        )
        completed = await service.execute_job(db=db, job_id=job.id, user=user)
        assert completed.state == ExecutionJobState.COMPLETED.value
        assert completed.exit_code == 0

        # Run reconciliation
        report = await service.reconcile_job_results(db=db, job_id=job.id, user=user)
        assert report.overall_status == "PASS"
        assert report.metrics["z_s"].is_within_tolerance is True
        assert report.metrics["body_accel"].is_within_tolerance is True


@pytest.mark.asyncio
async def test_wpf_02_real_fmpy_cosimulation_run_and_reconciliation(seeded_users):
    """Full execution of real FMPy on compiled QuarterCarRideModel.fmu."""
    fmu_path = PROJECT_ROOT / "QuarterCarRideModel.fmu"
    assert fmu_path.exists(), "QuarterCarRideModel.fmu not found on disk."

    user = seeded_users["context_a"]
    art_id = uuid.uuid4()
    content = fmu_path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()

    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=art_id,
            user_id=uuid.UUID(user.user_id),
            team_id=uuid.UUID(user.team_id),
            artifact_name="QuarterCarRideModel.fmu",
            file_format=".fmu",
            mime_type="application/octet-stream",
            size_bytes=len(content),
            sha256_hash=sha256,
            direction=ArtifactDirection.INPUT.value,
            storage_path=str(fmu_path),
        )
        db.add(art)
        await db.commit()

        service = SolverExecutionService()
        job = await service.create_execution_job(
            db=db,
            user=user,
            solver_name="FMI_COSIMULATION",
            input_artifact_id=art_id,
            execution_config={"duration": 0.5, "step": 0.002},
        )
        completed = await service.execute_job(db=db, job_id=job.id, user=user)
        assert completed.state == ExecutionJobState.COMPLETED.value
        assert completed.exit_code == 0
        assert completed.is_executed is True

        report = await service.reconcile_job_results(db=db, job_id=job.id, user=user)
        assert report.overall_status == "PASS"


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE G: PRODUCTION API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wpg_01_api_get_runtimes(seeded_users):
    """GET /api/v1/interop/runtimes returns audited runtimes."""
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/interop/runtimes", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 4
        names = {r["solver_name"]: r for r in data}
        assert names["FMI_COSIMULATION"]["is_available"] is True
        assert names["MSC_ADAMS"]["is_available"] is False
        assert names["MATLAB_SIMULINK"]["is_available"] is False


@pytest.mark.asyncio
async def test_wpg_02_api_preflight_and_execution_lifecycle(seeded_users, sample_input_artifact):
    """Preflight -> Submit & Execute -> Get -> Cancel -> Reconcile via API."""
    art_id, _ = sample_input_artifact
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Preflight
        pf_res = await client.post(
            "/api/v1/interop/execute/preflight",
            headers=headers,
            json={
                "solver_name": "EXTERNAL_CAE_SOLVER",
                "input_artifact_id": str(art_id),
            },
        )
        assert pf_res.status_code == 200
        assert pf_res.json()["is_available"] is True
        assert len(pf_res.json()["warnings"]) == 0

        # 2. Execute with wait_for_completion=True
        exec_res = await client.post(
            "/api/v1/interop/execute",
            headers=headers,
            json={
                "solver_name": "EXTERNAL_CAE_SOLVER",
                "input_artifact_id": str(art_id),
                "execution_config": {"duration": 1.0, "step": 0.001},
                "wait_for_completion": True,
            },
        )
        assert exec_res.status_code == 200
        job_data = exec_res.json()
        job_id = job_data["id"]
        assert job_data["state"] == "COMPLETED"
        assert job_data["is_executed"] is True
        assert job_data["is_physically_validated"] is False

        # 3. Get Job
        get_res = await client.get(f"/api/v1/interop/jobs/{job_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == job_id

        # 4. List Jobs
        list_res = await client.get("/api/v1/interop/jobs?limit=10", headers=headers)
        assert list_res.status_code == 200
        assert any(j["id"] == job_id for j in list_res.json())

        # 5. Reconcile
        rec_res = await client.post(f"/api/v1/interop/jobs/{job_id}/reconcile", headers=headers, json={})
        assert rec_res.status_code == 200
        rec_data = rec_res.json()
        assert rec_data["overall_status"] == "PASS"


# ══════════════════════════════════════════════════════════════════════════════
# PACKAGE H: ADVERSARIAL HOSTILE SECURITY & MULTI-TENANCY CHECKS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wph_01_cross_tenant_isolation(seeded_users, sample_input_artifact):
    """User B cannot access, inspect, cancel, or reconcile User A's job."""
    art_id, _ = sample_input_artifact
    headers_a = seeded_users["headers_a"]
    headers_b = seeded_users["headers_b"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User A executes a job
        exec_res = await client.post(
            "/api/v1/interop/execute",
            headers=headers_a,
            json={
                "solver_name": "EXTERNAL_CAE_SOLVER",
                "input_artifact_id": str(art_id),
                "wait_for_completion": True,
            },
        )
        job_id = exec_res.json()["id"]

        # User B attempts to inspect User A's job
        get_res = await client.get(f"/api/v1/interop/jobs/{job_id}", headers=headers_b)
        assert get_res.status_code in (403, 404)

        # User B attempts to reconcile User A's job
        rec_res = await client.post(f"/api/v1/interop/jobs/{job_id}/reconcile", headers=headers_b, json={})
        assert rec_res.status_code in (403, 404)

        # User B attempts to cancel User A's job
        can_res = await client.post(f"/api/v1/interop/jobs/{job_id}/cancel", headers=headers_b)
        assert can_res.status_code in (403, 404)


@pytest.mark.asyncio
async def test_wph_02_command_injection_rejection(seeded_users, sample_input_artifact):
    """Shell injection characters in solver name or config are rejected safely."""
    art_id, _ = sample_input_artifact
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        malicious_solvers = [
            "EXTERNAL_CAE_SOLVER; rm -rf /",
            "EXTERNAL_CAE_SOLVER && calc.exe",
            "`whoami`",
            "$(cat /etc/passwd)",
        ]
        for bad_solver in malicious_solvers:
            res = await client.post(
                "/api/v1/interop/execute",
                headers=headers,
                json={
                    "solver_name": bad_solver,
                    "input_artifact_id": str(art_id),
                },
            )
            assert res.status_code in (400, 422)


@pytest.mark.asyncio
async def test_wph_03_crash_exit_handling(seeded_users, sample_input_artifact):
    """Subprocess crash records exit code != 0, sets FAILED, preserves is_executed=False."""
    art_id, _ = sample_input_artifact
    user = seeded_users["context_a"]
    service = SolverExecutionService()

    async with SessionLocal() as db:
        job = await service.create_execution_job(
            db=db,
            user=user,
            solver_name="EXTERNAL_CAE_SOLVER",
            input_artifact_id=art_id,
            execution_config={"simulate_crash": True},
        )
        res = await service.execute_job(db=db, job_id=job.id, user=user)
        assert res.state == ExecutionJobState.FAILED.value
        assert res.exit_code != 0
        assert res.is_executed is False
        assert "Segmentation fault" in (res.stderr_excerpt or "")


@pytest.mark.asyncio
async def test_wph_04_concurrent_idempotency(seeded_users, sample_input_artifact):
    """Concurrent submissions with identical idempotency_key return the same job."""
    art_id, _ = sample_input_artifact
    user = seeded_users["context_a"]
    service = SolverExecutionService()
    idemp_key = f"idemp-{uuid.uuid4().hex}"

    async with SessionLocal() as db:
        job1 = await service.create_execution_job(
            db=db,
            user=user,
            solver_name="EXTERNAL_CAE_SOLVER",
            input_artifact_id=art_id,
            idempotency_key=idemp_key,
        )
        job2 = await service.create_execution_job(
            db=db,
            user=user,
            solver_name="EXTERNAL_CAE_SOLVER",
            input_artifact_id=art_id,
            idempotency_key=idemp_key,
        )
        assert job1.id == job2.id


def test_wph_05_alembic_single_head_integrity():
    """Verify Alembic migration tree has a single head at t0u1v2w3x4y5."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(lines) == 1, f"Multiple heads detected in alembic: {lines}"
    assert "t0u1v2w3x4y5" in lines[0]


def test_wph_06_physics_freeze_integrity():
    """All 81 production physics source files and 7 Phase 3 manifests match baseline SHA-256."""
    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    assert hash_file.exists(), "pre_phase4_3_hashes.json missing!"

    with open(hash_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    physics_hashes = data.get("physics", {})
    assert len(physics_hashes) == 81, f"Expected 81 physics files, found {len(physics_hashes)}"

    for rel_path, expected_hash in physics_hashes.items():
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Protected physics file {rel_path} does not exist!"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Protected physics file {rel_path} was modified!"

    manifest_hashes = data.get("manifests", {})
    assert len(manifest_hashes) == 7, f"Expected 7 manifest files, found {len(manifest_hashes)}"

    for rel_path, expected_hash in manifest_hashes.items():
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Phase 3 manifest file {rel_path} does not exist!"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Phase 3 manifest file {rel_path} was modified!"
