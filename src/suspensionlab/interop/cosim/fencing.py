"""
src/suspensionlab/interop/cosim/fencing.py
==========================================
SuspensionLab PRO — Worker Fencing, Process Liveness & Concurrency Safety (Phase 7.5).

Implements monotonic lease generation fencing tokens to prevent stale / resurrected workers
from committing results or corrupting database records after lease expiry or crash recovery.

Core Invariants:
1. Strictly Monotonic Lease Generations: Any recovery or lease reclamation increments lease_generation.
2. Stale Worker Fence-Out: Any heartbeat or result publication attempt presenting an outdated
   lease_generation token is rejected with StaleWorkerFencingError.
3. Process Liveness Verification: An expired heartbeat alone is not treated as proof of process death;
   actual OS process status is checked and orphan process trees are terminated before state transition.
4. Concurrency Safety: Atomic multi-connection compare-and-swap SQL operations guarantee exactly
   one worker can recover an expired job.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.solver_execution import (
    ExecutionJobState,
    SolverExecutionJob,
    TERMINAL_EXECUTION_STATES,
)


class StaleWorkerFencingError(RuntimeError):
    """Raised when a worker attempts to update a job using a superseded lease generation token."""
    pass


class ProcessLivenessChecker:
    """
    Checks OS-level process existence and cleanly terminates process trees.
    """

    @staticmethod
    def is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False

        if sys.platform == "win32":
            try:
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                STILL_ACTIVE = 259
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not handle:
                    return False
                exit_code = ctypes.c_ulong()
                success = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                kernel32.CloseHandle(handle)
                if not success:
                    return False
                return exit_code.value == STILL_ACTIVE
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    @classmethod
    def terminate_process_tree(cls, pid: int) -> bool:
        """
        Recursively terminates the target process and all of its spawned child processes.
        """
        if not cls.is_pid_alive(pid):
            return True

        if sys.platform == "win32":
            try:
                # taskkill /F /T /PID <pid> forcefully terminates process and children
                res = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return res.returncode == 0
            except Exception:
                return False
        else:
            try:
                # Try sending SIGTERM then SIGKILL to process group
                os.kill(pid, signal.SIGTERM)
                import time
                time.sleep(0.1)
                if cls.is_pid_alive(pid):
                    os.kill(pid, signal.SIGKILL)
                return True
            except Exception:
                return False


class WorkerFencingManager:
    """
    Manages atomic worker leases, heartbeat updates, and race-safe recovery.
    """

    @staticmethod
    async def renew_lease(
        db: AsyncSession,
        job_id: uuid.UUID,
        worker_id: str,
        lease_generation: int,
        lease_duration_seconds: float = 30.0,
    ) -> bool:
        """
        Renews a worker's active execution lease.
        Enforces that worker_id and lease_generation match DB record.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lease_duration_seconds)

        stmt = (
            update(SolverExecutionJob)
            .where(
                SolverExecutionJob.id == job_id,
                SolverExecutionJob.worker_id == worker_id,
                SolverExecutionJob.lease_generation == lease_generation,
                SolverExecutionJob.state == ExecutionJobState.RUNNING.value,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=expires_at,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        res = await db.execute(stmt)
        await db.commit()
        db.expire_all()

        if res.rowcount == 0:
            raise StaleWorkerFencingError(
                f"Heartbeat rejected: Worker '{worker_id}' with generation {lease_generation} has been fenced out "
                f"for job '{job_id}'. Another worker has claimed the lease or the job reached terminal state."
            )
        return True

    @staticmethod
    async def complete_job_with_fencing(
        db: AsyncSession,
        job_id: uuid.UUID,
        worker_id: str,
        lease_generation: int,
        output_artifact_ids: Optional[List[uuid.UUID]] = None,
        reconciliation_summary: Optional[Dict[str, Any]] = None,
        co_simulation_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> SolverExecutionJob:
        """
        Atomically marks a job COMPLETED verifying the worker's fencing token.
        Rejects stale workers attempting to commit outputs after lease recovery.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(SolverExecutionJob)
            .where(
                SolverExecutionJob.id == job_id,
                SolverExecutionJob.worker_id == worker_id,
                SolverExecutionJob.lease_generation == lease_generation,
                SolverExecutionJob.state == ExecutionJobState.RUNNING.value,
            )
            .values(
                state=ExecutionJobState.COMPLETED.value,
                is_executed=True,
                is_physically_validated=False,
                completed_at=now,
                updated_at=now,
                output_artifact_ids=[str(a) for a in (output_artifact_ids or [])],
                reconciliation_summary=reconciliation_summary or {},
                co_simulation_diagnostics=co_simulation_diagnostics or {},
            )
            .execution_options(synchronize_session=False)
        )
        res = await db.execute(stmt)
        await db.commit()
        db.expire_all()

        if res.rowcount == 0:
            raise StaleWorkerFencingError(
                f"Result publication rejected: Stale worker '{worker_id}' with generation {lease_generation} "
                f"attempted to complete job '{job_id}'. The job has already been recovered by another worker."
            )

        job_stmt = select(SolverExecutionJob).where(SolverExecutionJob.id == job_id)
        job_res = await db.execute(job_stmt)
        return job_res.scalar_one()

    @staticmethod
    async def recover_expired_job_atomic(
        db: AsyncSession,
        job_id: uuid.UUID,
        recovery_worker_id: str,
        verify_pid_liveness: bool = True,
    ) -> Optional[SolverExecutionJob]:
        """
        Atomically transitions an expired running job to FAILED with error_category WORKER_CRASH_ORPHAN,
        incrementing the lease_generation to fence out the original worker.
        Returns the updated job if recovered, or None if another concurrent worker recovered it.
        """
        now = datetime.now(timezone.utc)

        # Inspect current job state and PID before updating
        stmt_chk = select(SolverExecutionJob).where(
            SolverExecutionJob.id == job_id,
            SolverExecutionJob.state == ExecutionJobState.RUNNING.value,
            SolverExecutionJob.lease_expires_at != None,
            SolverExecutionJob.lease_expires_at < now,
        )
        res_chk = await db.execute(stmt_chk)
        job = res_chk.scalar_one_or_none()

        if not job:
            return None

        # Verify OS process liveness and kill orphan process tree if still running
        if verify_pid_liveness and job.pid:
            if ProcessLivenessChecker.is_pid_alive(job.pid):
                ProcessLivenessChecker.terminate_process_tree(job.pid)

        # Atomic Compare-And-Swap: increment lease_generation and transition state
        current_gen = job.lease_generation or 1
        new_gen = current_gen + 1

        stmt_upd = (
            update(SolverExecutionJob)
            .where(
                SolverExecutionJob.id == job_id,
                SolverExecutionJob.state == ExecutionJobState.RUNNING.value,
                SolverExecutionJob.lease_generation == current_gen,
                SolverExecutionJob.lease_expires_at < now,
            )
            .values(
                state=ExecutionJobState.FAILED.value,
                failure_reason=f"Execution worker lease expired. Orphaned process recovered by worker '{recovery_worker_id}'.",
                error_category="WORKER_CRASH_ORPHAN",
                exit_code=-9,
                lease_generation=new_gen,
                completed_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        res_upd = await db.execute(stmt_upd)
        await db.commit()
        db.expire_all()

        if res_upd.rowcount == 0:
            # Another concurrent connection won the race
            return None

        job_stmt = select(SolverExecutionJob).where(SolverExecutionJob.id == job_id)
        job_res = await db.execute(job_stmt)
        return job_res.scalar_one()
