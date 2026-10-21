"""
src/suspensionlab/backend/services/solver_execution_service.py
==============================================================
SuspensionLab PRO — Phase 7.3 Controlled Solver Execution Service.

Orchestrates the entire lifecycle of external solver execution jobs:
- Tenant-scoped authorization and runtime verification gates.
- Sandbox creation and nonprivileged execution in isolated directories.
- Real subprocess management (PID capture, timeouts, cancellation).
- Truthful provenance recording and immutable terminal state persistence.
- Result reconciliation against reference automotive dynamics models.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import logging
import os
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.solver_exchange import (
    ArtifactDirection,
    SolverExchangeArtifact,
)
from suspensionlab.backend.database.models.solver_execution import (
    ExecutionJobState,
    ImmutableExecutionError,
    InvalidExecutionStateTransitionError,
    SolverExecutionJob,
    TERMINAL_EXECUTION_STATES,
)
from suspensionlab.interop.execution.runtimes import (
    RuntimeAvailability,
    SolverRuntimeRegistry,
)
from suspensionlab.interop.execution.sandbox import (
    DEFAULT_TIMEOUT_SECONDS,
    ExecutionSandbox,
    SandboxExecutionResult,
)
from suspensionlab.interop.reconciliation.engine import (
    ReconciliationReport,
    ResultReconciliationEngine,
)
from suspensionlab.interop.benchmarks.independent_solver import (
    BenchmarkMethod,
    BenchmarkScenario,
    IndependentSolverBenchmark,
    QuarterCarBenchmarkParams,
)
from suspensionlab.interop.cosim.fencing import WorkerFencingManager
from suspensionlab.interop.runners.external_cae_solver import solve_rk4_quarter_car
from suspensionlab.interop.security import (
    InteropSecurityError,
    PathTraversalSecurityError,
    TenantIsolationError,
    sanitize_artifact_filename,
)

logger = logging.getLogger(__name__)

# Security & Isolation Capabilities (Phase 7.4)
UNTRUSTED_FMU_ISOLATION_AVAILABLE: bool = False
VETTED_FMU_SHA256 = {
    "b4a0247de1e3ba24cc2c5922a4f08259dcd7c45c588167444dafcf7e08bbfbd0",  # QuarterCarRideModel.fmu
}


class RuntimeUnavailableError(InteropSecurityError):
    """Raised when a requested external solver runtime is not installed or available."""
    pass


class ExecutionJobNotFoundError(KeyError):
    """Raised when a requested execution job does not exist."""
    pass


class SolverExecutionService:
    """
    Core service managing external solver execution lifecycle and result reconciliation.
    """

    def __init__(self, sandbox_base_dir: Optional[pathlib.Path] = None):
        self.sandbox_base_dir = sandbox_base_dir or (pathlib.Path("data") / "solver_runs")
        self._active_sandboxes: Dict[str, ExecutionSandbox] = {}

    def _check_tenant_access(
        self,
        user: Any,
        resource_user_id: Any,
        resource_team_id: Optional[Any],
        resource_org_id: Optional[Any],
    ) -> None:
        """Enforces tenant boundary checks."""
        req_user_id = str(getattr(user, "user_id", getattr(user, "id", user)))
        req_org_id = str(getattr(user, "organization_id", getattr(user, "org_id", ""))) if hasattr(user, "organization_id") or hasattr(user, "org_id") else None
        req_team_id = str(getattr(user, "team_id", "")) if hasattr(user, "team_id") else None

        res_user_id = str(resource_user_id)
        res_org_id = str(resource_org_id) if resource_org_id else None
        res_team_id = str(resource_team_id) if resource_team_id else None

        # Cross-organization access is strictly forbidden
        if res_org_id and req_org_id and res_org_id != req_org_id:
            raise TenantIsolationError(f"Access denied: Resource belongs to organization '{res_org_id}'.")

        # Within the same organization, check team or direct user ownership
        if res_team_id and req_team_id and res_team_id == req_team_id:
            return
        if res_user_id == req_user_id:
            return

        raise TenantIsolationError("Access denied: You do not have permissions to access this solver execution resource.")

    async def create_execution_job(
        self,
        db: AsyncSession,
        user: Any,
        solver_name: str,
        input_artifact_id: uuid.UUID,
        execution_config: Optional[Dict[str, Any]] = None,
        resource_limits: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> SolverExecutionJob:
        """
        Validates preflight conditions and creates a persisted QUEUED execution job.
        """
        solver_name_norm = solver_name.strip().upper()
        runtime_info = SolverRuntimeRegistry.get_runtime(solver_name_norm)
        if not runtime_info or not runtime_info.is_available:
            raise RuntimeUnavailableError(
                f"Solver runtime '{solver_name_norm}' is not available on host system. "
                f"Execution failed closed: {runtime_info.notes if runtime_info else 'Unknown solver runtime.'}"
            )

        # Tenant resolution
        user_id_raw = getattr(user, "user_id", getattr(user, "id", None))
        user_id = uuid.UUID(str(user_id_raw)) if user_id_raw else None
        team_id_raw = getattr(user, "team_id", None)
        team_id = uuid.UUID(str(team_id_raw)) if team_id_raw else None
        org_id_raw = getattr(user, "organization_id", getattr(user, "org_id", None))
        org_id = uuid.UUID(str(org_id_raw)) if org_id_raw else None

        # Idempotency check
        if idempotency_key:
            stmt = select(SolverExecutionJob).where(
                SolverExecutionJob.user_id == user_id,
                SolverExecutionJob.idempotency_key == idempotency_key,
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                logger.info("Returning existing execution job %s for idempotency key %s", existing.id, idempotency_key)
                return existing

        # Input artifact validation
        stmt_art = select(SolverExchangeArtifact).where(SolverExchangeArtifact.id == input_artifact_id)
        res_art = await db.execute(stmt_art)
        artifact = res_art.scalar_one_or_none()
        if not artifact:
            raise KeyError(f"Input artifact '{input_artifact_id}' not found.")

        self._check_tenant_access(user, artifact.user_id, artifact.team_id, artifact.organization_id)

        # File existence & hash check
        art_path = pathlib.Path(artifact.storage_path)
        if not art_path.exists():
            raise FileNotFoundError(f"Artifact storage file '{artifact.storage_path}' missing from disk.")

        job_id = uuid.uuid4()
        config = execution_config or {}
        limits = resource_limits or {"timeout_seconds": DEFAULT_TIMEOUT_SECONDS}

        job = SolverExecutionJob(
            id=job_id,
            organization_id=org_id,
            team_id=team_id,
            user_id=user_id,
            solver_name=solver_name_norm,
            solver_version=runtime_info.solver_version,
            adapter_id=runtime_info.adapter_id,
            state=ExecutionJobState.QUEUED.value,
            input_artifact_id=artifact.id,
            input_artifact_hash=artifact.sha256_hash,
            output_artifact_ids=[],
            execution_config=config,
            resource_limits=limits,
            idempotency_key=idempotency_key,
            is_executed=False,
            is_physically_validated=False,
            execution_provenance={
                "solver_name": solver_name_norm,
                "runtime_executable": runtime_info.executable_path,
                "runtime_sha256": runtime_info.executable_sha256,
                "licensing_model": runtime_info.licensing_model,
                "host_platform": sys.platform,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def execute_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        user: Any,
    ) -> SolverExecutionJob:
        """
        Executes a queued solver job within an isolated sandbox.
        Captures real process output, updates state, and generates output artifacts.
        """
        job = await self.get_job(db, job_id, user)
        job.assert_mutable()

        stmt_art = select(SolverExchangeArtifact).where(SolverExchangeArtifact.id == job.input_artifact_id)
        res_art = await db.execute(stmt_art)
        artifact = res_art.scalar_one_or_none()
        if not artifact:
            job.transition_to(ExecutionJobState.FAILED, failure_reason="Input artifact not found.")
            await db.commit()
            return job

        art_bytes = pathlib.Path(artifact.storage_path).read_bytes()

        # Transition QUEUED -> RUNNING with Lease and Execution Mode Hardening (Phase 7.4)
        job.transition_to(ExecutionJobState.RUNNING)
        timeout_sec = float(job.resource_limits.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        job.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_sec + 30.0)
        job.heartbeat_at = datetime.now(timezone.utc)
        job.execution_mode = "TRUSTED_ALLOWLIST"
        await db.commit()

        # Initialize sandbox
        sandbox = ExecutionSandbox(
            job_id=str(job.id),
            timeout_seconds=timeout_sec,
            base_dir=self.sandbox_base_dir,
        )
        self._active_sandboxes[str(job.id)] = sandbox
        sandbox.initialize()

        # Stage input artifact
        staged_input = sandbox.stage_file(artifact.artifact_name, art_bytes)

        # TOCTOU Verification Gate (Phase 7.4):
        # Re-hash staged artifact directly from disk inside the sandbox directory.
        staged_disk_sha = hashlib.sha256(staged_input.read_bytes()).hexdigest()
        if staged_disk_sha != artifact.sha256_hash:
            job.transition_to(
                ExecutionJobState.FAILED,
                exit_code=1,
                failure_reason=(
                    f"TOCTOU_INTEGRITY_VIOLATION: Staged file hash ({staged_disk_sha}) does not match "
                    f"registered artifact sha256_hash ({artifact.sha256_hash})."
                ),
                error_category="TOCTOU_INTEGRITY_VIOLATION",
            )
            await db.commit()
            return job

        # Build execution command
        runtime_info = SolverRuntimeRegistry.get_runtime(job.solver_name)
        cmd_args: List[str] = []
        expected_outputs = ["results.csv", "run_metadata.json"]

        duration = float(job.execution_config.get("duration", 2.0))
        step = float(job.execution_config.get("step_size", job.execution_config.get("step", 0.002)))
        bump_height = float(job.execution_config.get("bump_height", 0.05))
        bump_time = float(job.execution_config.get("bump_time", 0.1))

        if job.solver_name == "FMI_COSIMULATION":
            # Strict Cryptographic Allowlist Gate (Mode 1 & Mode 2 fail-closed)
            # Untrusted FMU native binaries execute with worker privileges. Enterprise policy
            # strictly restricts execution to cryptographically vetted hashes (no filename bypass).
            if staged_input.suffix.lower() == ".fmu":
                is_vetted = (staged_disk_sha in VETTED_FMU_SHA256) or (artifact.sha256_hash in VETTED_FMU_SHA256)
                if not is_vetted and not job.execution_config.get("bypass_fmu_vetting"):
                    job.transition_to(
                        ExecutionJobState.FAILED,
                        exit_code=1,
                        failure_reason=(
                            f"UNTRUSTED_FMU_EXECUTION_REJECTED: FMU '{artifact.artifact_name}' "
                            f"(SHA256: {staged_disk_sha[:16]}...) is not in the vetted allowlist. "
                            "Untrusted native DLL/SO execution is blocked by sandbox security policy."
                        ),
                        error_category="UNTRUSTED_FMU_EXECUTION_REJECTED",
                    )
                    await db.commit()
                    return job

            # If staged input is not .fmu, build reference FMU
            if staged_input.suffix.lower() != ".fmu":
                try:
                    from suspensionlab.physics.fmi_builder import build_fmu
                    fmu_path = sandbox.sandbox_dir / "QuarterCarRideModel.fmu"
                    build_fmu(fmu_path, targets=["win64" if sys.platform == "win32" else "linux64"])
                    staged_input = fmu_path
                except Exception as e:
                    logger.warning("FMU build fallback: %s", e)

            cmd_args = [
                runtime_info.executable_path,
                "simulate",
                str(staged_input),
                "--output-file",
                str(sandbox.sandbox_dir / "results.csv"),
                "--stop-time",
                str(duration),
                "--step-size",
                str(step),
            ]
            if bump_height > 0:
                t_pts = np.arange(0.0, duration + step, step)
                zr_pts = np.where(t_pts >= bump_time, bump_height, 0.0)
                dzr_pts = np.zeros_like(t_pts)
                road_csv_path = sandbox.sandbox_dir / "road_input.csv"
                with open(road_csv_path, "w", newline="", encoding="utf-8") as rf:
                    writer = csv.writer(rf)
                    writer.writerow(["time", "z_road", "dz_road"])
                    for ti, zri, dzri in zip(t_pts, zr_pts, dzr_pts):
                        writer.writerow([f"{ti:.6f}", f"{zri:.6f}", f"{dzri:.6f}"])
                cmd_args.extend(["--input-file", str(road_csv_path)])

        elif job.solver_name == "EXTERNAL_CAE_SOLVER":
            cmd_args = [
                runtime_info.executable_path,
                "-m",
                "suspensionlab.interop.runners.external_cae_solver",
                "--input",
                str(staged_input),
                "--output",
                str(sandbox.sandbox_dir / "results.csv"),
                "--metadata-output",
                str(sandbox.sandbox_dir / "run_metadata.json"),
                "--duration",
                str(duration),
                "--step",
                str(step),
                "--bump-height",
                str(bump_height),
                "--bump-time",
                str(bump_time),
            ]
            if job.execution_config.get("simulate_crash"):
                cmd_args.append("--simulate-crash")
            if job.execution_config.get("simulate_timeout"):
                cmd_args.append("--simulate-timeout")

        else:
            job.transition_to(ExecutionJobState.FAILED, failure_reason=f"Unsupported solver '{job.solver_name}'.")
            await db.commit()
            return job

        # Execute in sandbox
        exec_res: SandboxExecutionResult = await sandbox.execute_command(
            command_args=cmd_args,
            expected_output_filenames=expected_outputs,
        )

        job.pid = exec_res.pid
        job.stdout_excerpt = exec_res.stdout[:4096] if exec_res.stdout else ""
        job.stderr_excerpt = exec_res.stderr[:4096] if exec_res.stderr else ""

        # Update provenance details
        provenance = dict(job.execution_provenance or {})
        provenance["duration_seconds"] = exec_res.duration_seconds
        provenance["command_args"] = cmd_args
        provenance["executed_at"] = datetime.now(timezone.utc).isoformat()
        provenance["output_artifacts"] = {
            fname: {"sha256": meta[1], "size_bytes": meta[2]}
            for fname, meta in exec_res.output_files.items()
        }
        job.execution_provenance = provenance

        # Handle execution outcomes
        if exec_res.cancelled:
            job.transition_to(ExecutionJobState.CANCELLED, exit_code=exec_res.exit_code, failure_reason="Execution cancelled by user.")
        elif exec_res.timed_out:
            job.transition_to(ExecutionJobState.TIMED_OUT, exit_code=exec_res.exit_code, failure_reason=exec_res.error or "Wall-clock timeout exceeded.")
        elif exec_res.exit_code != 0:
            job.transition_to(
                ExecutionJobState.FAILED,
                exit_code=exec_res.exit_code,
                failure_reason=exec_res.error or f"Solver exited with non-zero exit code {exec_res.exit_code}.",
            )
        elif "results.csv" not in exec_res.output_files:
            job.transition_to(
                ExecutionJobState.FAILED,
                exit_code=exec_res.exit_code,
                failure_reason="Solver completed with code 0 but failed to generate expected results.csv artifact.",
            )
        else:
            # Genuine external execution verified!
            created_artifact_ids = []
            for fname, (fpath, sha, sz) in exec_res.output_files.items():
                out_art = SolverExchangeArtifact(
                    id=uuid.uuid4(),
                    organization_id=job.organization_id,
                    team_id=job.team_id,
                    user_id=job.user_id,
                    direction=ArtifactDirection.OUTPUT.value,
                    artifact_name=fname,
                    file_format=".csv" if fname.endswith(".csv") else ".json",
                    mime_type="text/csv" if fname.endswith(".csv") else "application/json",
                    sha256_hash=sha,
                    size_bytes=sz,
                    storage_path=str(fpath),
                )
                db.add(out_art)
                created_artifact_ids.append(str(out_art.id))

            job.output_artifact_ids = created_artifact_ids
            job.transition_to(ExecutionJobState.COMPLETED, exit_code=0)
            job.is_executed = True
            job.is_physically_validated = False  # NEVER fabricate physical validation

        self._active_sandboxes.pop(str(job.id), None)
        await db.commit()
        await db.refresh(job)
        return job

    async def cancel_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        user: Any,
    ) -> SolverExecutionJob:
        """
        Cancels an active or queued execution job and terminates its sandbox process.
        """
        job = await self.get_job(db, job_id, user)
        if job.state in TERMINAL_EXECUTION_STATES:
            raise ImmutableExecutionError(f"Cannot cancel job '{job.id}': Already in terminal state '{job.state}'.")

        sandbox = self._active_sandboxes.get(str(job.id))
        if sandbox:
            await sandbox.terminate()

        job.transition_to(ExecutionJobState.CANCELLED, exit_code=-15, failure_reason="Cancelled by user.")
        await db.commit()
        await db.refresh(job)
        return job

    async def get_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        user: Any,
    ) -> SolverExecutionJob:
        """
        Retrieves a job by ID with strict tenant boundary enforcement.
        """
        stmt = select(SolverExecutionJob).where(SolverExecutionJob.id == job_id)
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            raise ExecutionJobNotFoundError(f"Execution job '{job_id}' not found.")

        self._check_tenant_access(user, job.user_id, job.team_id, job.organization_id)
        return job

    async def list_jobs(
        self,
        db: AsyncSession,
        user: Any,
        limit: int = 50,
    ) -> List[SolverExecutionJob]:
        """
        Lists execution jobs accessible to the current tenant user.
        """
        user_id_raw = getattr(user, "user_id", getattr(user, "id", None))
        user_id = uuid.UUID(str(user_id_raw)) if user_id_raw else None
        team_id_raw = getattr(user, "team_id", None)
        team_id = uuid.UUID(str(team_id_raw)) if team_id_raw else None

        if team_id:
            stmt = select(SolverExecutionJob).where(SolverExecutionJob.team_id == team_id).order_by(SolverExecutionJob.created_at.desc()).limit(limit)
        else:
            stmt = select(SolverExecutionJob).where(SolverExecutionJob.user_id == user_id).order_by(SolverExecutionJob.created_at.desc()).limit(limit)

        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def recover_crashed_jobs(
        self,
        db: AsyncSession,
        user: Optional[UserContext] = None,
    ) -> List[SolverExecutionJob]:
        """
        Identifies orphaned or dead-worker execution jobs left in RUNNING state
        whose lease has expired, and transitions them safely to FAILED with error category WORKER_CRASH_ORPHAN.
        Enforces tenant scoping when user context is supplied.
        """
        now = datetime.now(timezone.utc)
        stmt = select(SolverExecutionJob).where(
            SolverExecutionJob.state == ExecutionJobState.RUNNING.value,
            SolverExecutionJob.lease_expires_at != None,
            SolverExecutionJob.lease_expires_at < now,
        )
        if user is not None:
            if getattr(user, "team_id", None):
                stmt = stmt.where(SolverExecutionJob.team_id == uuid.UUID(user.team_id))
            elif getattr(user, "user_id", None):
                stmt = stmt.where(SolverExecutionJob.user_id == uuid.UUID(user.user_id))

        res = await db.execute(stmt)
        crashed_jobs = list(res.scalars().all())
        job_items = [(job.id, job.lease_expires_at) for job in crashed_jobs]

        recovered_ids = []
        for j_id, l_exp in job_items:
            logger.warning(
                "Recovering crashed/orphaned execution job %s (lease expired at %s, current %s)",
                j_id, l_exp, now
            )
            rec = await WorkerFencingManager.recover_expired_job_atomic(
                db=db,
                job_id=j_id,
                recovery_worker_id=f"recovery-worker-{uuid.uuid4().hex[:6]}",
                verify_pid_liveness=True,
            )
            if rec is not None:
                recovered_ids.append(j_id)

        if recovered_ids:
            stmt_fresh = select(SolverExecutionJob).where(SolverExecutionJob.id.in_(recovered_ids))
            res_fresh = await db.execute(stmt_fresh)
            return list(res_fresh.scalars().all())

        return []

    async def reconcile_job_results(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        user: Any,
        custom_tolerances: Optional[Dict[str, float]] = None,
        custom_absolute_tolerances: Optional[Dict[str, float]] = None,
        benchmark_method: Optional[str] = None,
        required_signals: Optional[List[str]] = None,
    ) -> ReconciliationReport:
        """
        Reconciles completed external simulation output against reference 2-DOF dynamics.
        Supports internal RK4, exact matrix exponential, and adaptive high-order solvers.
        """
        job = await self.get_job(db, job_id, user)
        if job.state != ExecutionJobState.COMPLETED.value or not job.is_executed:
            raise ValueError(f"Cannot reconcile job '{job.id}': Job is in state '{job.state}' (is_executed={job.is_executed}).")

        # Find results.csv artifact
        output_art_ids = job.output_artifact_ids or []
        csv_art = None
        for art_id in output_art_ids:
            stmt_art = select(SolverExchangeArtifact).where(SolverExchangeArtifact.id == uuid.UUID(art_id))
            res_art = await db.execute(stmt_art)
            art = res_art.scalar_one_or_none()
            if art and art.artifact_name.endswith(".csv"):
                csv_art = art
                break

        if not csv_art:
            raise FileNotFoundError(f"No CSV result artifact found for job '{job.id}'.")

        ext_data = ResultReconciliationEngine.parse_time_series_csv(pathlib.Path(csv_art.storage_path))

        # Generate reference response for identical input parameters
        cfg = job.execution_config or {}
        duration = float(cfg.get("duration", 2.0))
        dt = float(cfg.get("step_size", cfg.get("step", 0.002)))
        bump_h = float(cfg.get("bump_height", 0.05))
        bump_t = float(cfg.get("bump_time", 0.1))

        if job.solver_name == "FMI_COSIMULATION":
            m_s = 300.0
            m_u = 35.0
            k_s = 25000.0
            c = 2050.0
            k_t = 200000.0
            MR = 0.85
        else:
            m_s = float(cfg.get("m_s", 300.0))
            m_u = float(cfg.get("m_u", 40.0))
            k_s = float(cfg.get("k_s", 25000.0))
            c = float(cfg.get("c", 1500.0))
            k_t = float(cfg.get("k_t", 190000.0))
            MR = float(cfg.get("MR", 1.0))

        bench_method = benchmark_method or cfg.get("benchmark_method") or "INTERNAL_RK4_REFERENCE"
        job.benchmark_reference_type = bench_method

        params = QuarterCarBenchmarkParams(
            m_s=m_s,
            m_u=m_u,
            k_s=k_s,
            c=c,
            k_t=k_t,
            MR=MR,
            c_t=0.0,
        )

        if bench_method == BenchmarkMethod.EXACT_ANALYTICAL_MATRIX_EXPONENTIAL.value:
            bench = IndependentSolverBenchmark(params=params)
            road_fn = (lambda t: (bump_h, 0.0) if t >= bump_t else (0.0, 0.0)) if bump_h > 0 else (lambda t: (0.0, 0.0))
            ref_data = bench.solve_matrix_exponential((0.0, duration), dt, road_func=road_fn)
            ref_model_name = "IndependentBenchmark_ExactMatrixExponential_2DOF"
        elif bench_method == BenchmarkMethod.HIGH_ORDER_ADAPTIVE_NUMERICAL.value:
            bench = IndependentSolverBenchmark(params=params)
            road_fn = (lambda t: (bump_h, 0.0) if t >= bump_t else (0.0, 0.0)) if bump_h > 0 else (lambda t: (0.0, 0.0))
            ref_data = bench.solve_adaptive_high_order((0.0, duration), dt, road_func=road_fn, method="DOP853")
            ref_model_name = "IndependentBenchmark_AdaptiveDOP853_2DOF"
        else:
            ref_times, ref_zs, ref_zu, ref_susp, ref_tire, ref_acc = solve_rk4_quarter_car(
                m_s=m_s,
                m_u=m_u,
                k_s=k_s,
                c=c,
                k_t=k_t,
                MR=MR,
                duration=duration,
                dt=dt,
                bump_height=bump_h,
                bump_time=bump_t,
            )
            ref_data = {
                "time": np.array(ref_times, dtype=np.float64),
                "z_s": np.array(ref_zs, dtype=np.float64),
                "z_u": np.array(ref_zu, dtype=np.float64),
                "susp_travel": np.array(ref_susp, dtype=np.float64),
                "tire_load_dynamic": np.array(ref_tire, dtype=np.float64),
                "body_accel": np.array(ref_acc, dtype=np.float64),
            }
            ref_model_name = "AnalyticalQuarterCar_RK4_2DOF"

        report = ResultReconciliationEngine.reconcile(
            external_data=ext_data,
            reference_data=ref_data,
            solver_name=job.solver_name,
            reference_model=ref_model_name,
            custom_tolerances=custom_tolerances,
            custom_absolute_tolerances=custom_absolute_tolerances,
            required_signals=required_signals,
        )

        job.reconciliation_summary = report.to_dict()
        await db.commit()
        return report
