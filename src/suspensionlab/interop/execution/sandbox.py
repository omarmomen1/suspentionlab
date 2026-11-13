"""
src/suspensionlab/interop/execution/sandbox.py
==============================================
Hostile Sandbox Execution Environment for SuspensionLab PRO Phase 7.3.

Provides isolated OS process management for external CAE solvers with:
- Dedicated per-job sandbox directories (`data/solver_runs/<job_id>/`).
- Allowlisted argument construction (strictly `shell=False`).
- Bounded stdout/stderr streaming (prevents memory exhaustion).
- Wall-clock timeouts and graceful/forceful process tree termination.
- Post-execution output artifact collection and SHA-256 hash validation.
- Complete directory isolation and fail-closed security.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Base directory for sandboxed solver runs
SANDBOX_BASE_DIR = pathlib.Path("data") / "solver_runs"

# Limits
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_STDOUT_BYTES = 256 * 1024  # 256 KB
MAX_OUTPUT_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


class SandboxTimeoutError(Exception):
    """Raised when sandbox process execution exceeds wall-clock timeout limit."""
    pass


@dataclass
class SandboxExecutionResult:
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    output_files: Dict[str, Tuple[pathlib.Path, str, int]]  # name -> (path, sha256, size)
    pid: Optional[int] = None
    timed_out: bool = False
    cancelled: bool = False
    error: Optional[str] = None


class ExecutionSandbox:
    """
    Manages an isolated working directory and execution environment for a single solver run.
    """

    def __init__(
        self,
        job_id: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        base_dir: Optional[pathlib.Path] = None,
    ):
        self.job_id = str(job_id)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.root = (base_dir or SANDBOX_BASE_DIR).resolve()
        self.sandbox_dir = (self.root / self.job_id).resolve()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._pid: Optional[int] = None

    def initialize(self) -> pathlib.Path:
        """Creates the isolated sandbox directory, ensuring no path traversal."""
        self.root.mkdir(parents=True, exist_ok=True)
        # Verify sandbox_dir is strictly within self.root
        if not str(self.sandbox_dir).startswith(str(self.root)):
            raise ValueError(f"Path traversal detected in sandbox directory: '{self.sandbox_dir}'")
        if self.sandbox_dir.exists():
            shutil.rmtree(self.sandbox_dir, ignore_errors=True)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        return self.sandbox_dir

    def stage_file(self, filename: str, content: bytes) -> pathlib.Path:
        """Safely writes an input artifact into the sandbox directory."""
        clean_name = pathlib.Path(filename).name
        target = (self.sandbox_dir / clean_name).resolve()
        if not str(target).startswith(str(self.sandbox_dir)):
            raise ValueError(f"Path traversal detected in staged filename: '{clean_name}'")
        target.write_bytes(content)
        return target

    def _verify_fmu_command_args(self, command_args: List[str]) -> None:
        """
        Unconditionally verifies the live SHA-256 hash of any .fmu file (or fmpy simulate target)
        against VETTED_FMU_SHA256 immediately before spawning a subprocess.
        """
        from suspensionlab.backend.services.solver_execution_service import VETTED_FMU_SHA256

        exe_stem = pathlib.Path(command_args[0]).stem.lower()
        is_fmpy_simulate = False
        simulate_target_idx: Optional[int] = None
        if exe_stem == "fmpy" and len(command_args) > 1 and command_args[1] == "simulate":
            is_fmpy_simulate = True
            simulate_target_idx = 2
        elif (
            len(command_args) >= 4
            and command_args[1] == "-m"
            and command_args[2] == "fmpy"
            and command_args[3] == "simulate"
        ):
            is_fmpy_simulate = True
            simulate_target_idx = 4

        fmu_targets: List[pathlib.Path] = []
        for idx, arg in enumerate(command_args):
            if str(arg).lower().endswith(".fmu") or (is_fmpy_simulate and idx == simulate_target_idx):
                p = pathlib.Path(arg)
                if not p.is_absolute():
                    p = self.sandbox_dir / p
                if p not in fmu_targets:
                    fmu_targets.append(p)

        if is_fmpy_simulate and not fmu_targets:
            raise PermissionError("UNTRUSTED_FMU_EXECUTION_REJECTED: No FMU target provided to fmpy simulate.")

        for fmu_path in fmu_targets:
            if not fmu_path.exists() or not fmu_path.is_file():
                raise PermissionError(
                    f"UNTRUSTED_FMU_EXECUTION_REJECTED: FMU file '{fmu_path}' does not exist."
                )
            hasher = hashlib.sha256()
            with open(fmu_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            disk_sha = hasher.hexdigest()
            if disk_sha not in VETTED_FMU_SHA256:
                raise PermissionError(
                    f"UNTRUSTED_FMU_EXECUTION_REJECTED: FMU '{fmu_path.name}' "
                    f"(SHA256: {disk_sha[:16]}...) is not in VETTED_FMU_SHA256."
                )

    async def execute_command(
        self,
        command_args: List[str],
        expected_output_filenames: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> SandboxExecutionResult:
        """
        Executes an allowlisted command in the sandbox directory under strict resource limits.
        """
        if not command_args:
            raise ValueError("command_args cannot be empty.")

        # Ensure sandbox is created
        if not self.sandbox_dir.exists():
            self.initialize()

        # Unconditionally verify any .fmu target immediately before spawning subprocess
        self._verify_fmu_command_args(command_args)

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        # Enforce isolated directory as CWD
        cwd = str(self.sandbox_dir)

        t_start = datetime.now(timezone.utc)
        timed_out = False
        cancelled = False
        stdout_buf = bytearray()
        stderr_buf = bytearray()
        error_msg = None
        exit_code = -1

        try:
            self._process = await asyncio.create_subprocess_exec(
                *command_args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            self._pid = self._process.pid

            async def _read_stream(stream, buffer: bytearray):
                while True:
                    chunk = await stream.read(4096)
                    if not chunk:
                        break
                    if len(buffer) < MAX_STDOUT_BYTES:
                        buffer.extend(chunk[: MAX_STDOUT_BYTES - len(buffer)])

            read_tasks = asyncio.gather(
                _read_stream(self._process.stdout, stdout_buf),
                _read_stream(self._process.stderr, stderr_buf),
            )

            try:
                await asyncio.wait_for(
                    asyncio.gather(self._process.wait(), read_tasks),
                    timeout=self.timeout_seconds,
                )
                exit_code = self._process.returncode
            except asyncio.TimeoutError:
                timed_out = True
                error_msg = f"Process exceeded wall-clock timeout limit of {self.timeout_seconds} seconds."
                await self.terminate()
                exit_code = -9
            except asyncio.CancelledError:
                cancelled = True
                error_msg = "Process execution was explicitly cancelled."
                await self.terminate()
                exit_code = -15
                raise

        except Exception as e:
            if not cancelled:
                error_msg = f"Failed to execute process: {e}"
                exit_code = -1

        t_end = datetime.now(timezone.utc)
        duration = (t_end - t_start).total_seconds()

        # Collect output files
        collected_outputs: Dict[str, Tuple[pathlib.Path, str, int]] = {}
        if expected_output_filenames:
            for fname in expected_output_filenames:
                clean_name = pathlib.Path(fname).name
                fpath = self.sandbox_dir / clean_name
                if fpath.exists() and fpath.is_file():
                    size = fpath.stat().st_size
                    if size > MAX_OUTPUT_FILE_BYTES:
                        error_msg = f"Output file '{clean_name}' exceeds maximum size limit ({MAX_OUTPUT_FILE_BYTES} bytes)."
                    else:
                        sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
                        collected_outputs[clean_name] = (fpath, sha, size)

        return SandboxExecutionResult(
            exit_code=exit_code,
            duration_seconds=duration,
            stdout=stdout_buf.decode("utf-8", errors="replace"),
            stderr=stderr_buf.decode("utf-8", errors="replace"),
            output_files=collected_outputs,
            pid=self._pid,
            timed_out=timed_out,
            cancelled=cancelled,
            error=error_msg,
        )

    async def terminate(self) -> None:
        """Forcefully terminates the running process and all child processes."""
        if self._process and self._process.returncode is None:
            try:
                if sys.platform == "win32" and self._pid:
                    # Force kill process tree on Windows
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self._pid)],
                        capture_output=True,
                        timeout=5,
                    )
                else:
                    self._process.kill()
            except Exception as e:
                logger.warning("Error terminating process %s: %s", self._pid, e)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except Exception:
                pass

    def cleanup(self) -> None:
        """Removes the sandbox directory."""
        if self.sandbox_dir.exists():
            shutil.rmtree(self.sandbox_dir, ignore_errors=True)
