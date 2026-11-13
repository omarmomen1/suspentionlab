"""
tests/test_fmu_vetting_hardening.py
===================================
Security regression suite verifying:
1. Complete removal of bypass_fmu_vetting from external API schemas, OpenAPI spec,
   job submission payloads, and SolverExecutionService.
2. Unconditional SHA-256 verification against VETTED_FMU_SHA256 immediately before
   loading or executing any .fmu file in SolverExecutionService, ExecutionSandbox,
   and CoSimulationMasterOrchestrator.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import pathlib
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from suspensionlab.backend.api.main import app
from suspensionlab.backend.api.routes import solver_interop_routes
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.solver_exchange import (
    ArtifactDirection,
    SolverExchangeArtifact,
)
from suspensionlab.backend.database.models.solver_execution import (
    ExecutionJobState,
    SolverExecutionJob,
)
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.security.jwt_utils import create_access_token
from suspensionlab.backend.services import cosimulation_service, solver_execution_service
from suspensionlab.backend.services.solver_execution_service import (
    SolverExecutionService,
    VETTED_FMU_SHA256,
)
from suspensionlab.interop.cosim import orchestrator as cosim_orchestrator
from suspensionlab.interop.cosim.components.road_generator import RoadProfileGenerator
from suspensionlab.interop.cosim.contract import (
    CoSimulationCouplingContract,
    ModelParticipantSpec,
    SignalConnection,
)
from suspensionlab.interop.cosim.orchestrator import CoSimulationMasterOrchestrator
from suspensionlab.interop.execution import sandbox as execution_sandbox
from suspensionlab.interop.execution.runtimes import SolverRuntimeRegistry
from suspensionlab.interop.execution.sandbox import ExecutionSandbox

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
async def fmu_hardening_user():
    """Seeds an isolated user and auth context for FMU hardening tests."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    email = f"fmu_sec_{user_id.hex[:6]}@oem.com"

    async with SessionLocal() as db:
        user = User(
            id=user_id,
            email=email,
            name="FMU Security Tester",
            plan="PRO",
            password_hash="test-hash",
        )
        db.add(user)
        await db.commit()

    token = create_access_token({
        "sub": str(user_id),
        "user_id": str(user_id),
        "email": email,
        "team_id": str(team_id),
        "plan": "PRO",
    })
    ctx = UserContext(
        user_id=str(user_id),
        email=email,
        name="FMU Security Tester",
        onboarding_complete=True,
        plan="PRO",
        team_id=str(team_id),
    )
    return {
        "user_id": user_id,
        "team_id": team_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
        "context": ctx,
    }


def test_bypass_fmu_vetting_absent_from_backend_and_openapi():
    """Verify bypass_fmu_vetting does not exist in backend modules or interop API schemas."""
    from fastapi.openapi.utils import get_openapi

    forbidden = "bypass_fmu_vetting"
    for mod in (
        solver_execution_service,
        solver_interop_routes,
        execution_sandbox,
        cosimulation_service,
        cosim_orchestrator,
    ):
        src = inspect.getsource(mod)
        assert forbidden not in src, f"Forbidden bypass key found in {mod.__name__}"

    for model_cls in (
        solver_interop_routes.SolverExecutionConfigSchema,
        solver_interop_routes.ResourceLimitsSchema,
        solver_interop_routes.ExecuteJobRequest,
        solver_interop_routes.JobResponseDTO,
        solver_interop_routes.JobPreflightRequest,
        solver_interop_routes.ExecuteCoSimJobRequest,
        solver_interop_routes.CreateCoSimContractRequest,
        solver_interop_routes.ImportOperationRequest,
        solver_interop_routes.ExportOperationRequest,
    ):
        assert forbidden not in json.dumps(model_cls.model_json_schema())

    interop_openapi = get_openapi(
        title="interop",
        version="1.0.0",
        routes=solver_interop_routes.router.routes,
    )
    assert forbidden not in json.dumps(interop_openapi)


@pytest.mark.asyncio
async def test_api_rejects_bypass_fmu_vetting_in_execution_payload(fmu_hardening_user, tmp_path):
    """External API rejects bypass_fmu_vetting inside execution_config and top-level payload."""
    headers = fmu_hardening_user["headers"]
    user_id = fmu_hardening_user["user_id"]
    team_id = fmu_hardening_user["team_id"]

    untrusted_fmu = tmp_path / "malicious.fmu"
    untrusted_fmu.write_bytes(b"PK\x03\x04UNTRUSTED_BINARY_FMU")
    sha = hashlib.sha256(untrusted_fmu.read_bytes()).hexdigest()

    art_id = uuid.uuid4()
    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=art_id,
            user_id=user_id,
            team_id=team_id,
            artifact_name="malicious.fmu",
            file_format=".fmu",
            mime_type="application/octet-stream",
            size_bytes=len(untrusted_fmu.read_bytes()),
            sha256_hash=sha,
            direction=ArtifactDirection.INPUT.value,
            storage_path=str(untrusted_fmu),
        )
        db.add(art)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Attempt 1: inside execution_config
        res_nested = await client.post(
            "/api/v1/interop/execute",
            headers=headers,
            json={
                "solver_name": "FMI_COSIMULATION",
                "input_artifact_id": str(art_id),
                "execution_config": {"duration": 0.5, "bypass_fmu_vetting": True},
                "wait_for_completion": True,
            },
        )
        assert res_nested.status_code == 422

        # Attempt 2: top-level field
        res_top = await client.post(
            "/api/v1/interop/execute",
            headers=headers,
            json={
                "solver_name": "FMI_COSIMULATION",
                "input_artifact_id": str(art_id),
                "bypass_fmu_vetting": True,
                "wait_for_completion": True,
            },
        )
        assert res_top.status_code == 422


@pytest.mark.asyncio
async def test_service_strips_bypass_flag_and_rejects_untrusted_fmu(fmu_hardening_user, tmp_path):
    """
    Even if bypass_fmu_vetting is supplied directly to create_execution_job or injected
    into the persisted job record, execute_job unconditionally rejects untrusted FMUs.
    """
    ctx = fmu_hardening_user["context"]
    user_id = fmu_hardening_user["user_id"]
    team_id = fmu_hardening_user["team_id"]

    untrusted_fmu = tmp_path / "QuarterCarRideModel.fmu"
    untrusted_fmu.write_bytes(b"PK\x03\x04UNTRUSTED_PAYLOAD")
    sha = hashlib.sha256(untrusted_fmu.read_bytes()).hexdigest()
    assert sha not in VETTED_FMU_SHA256

    art_id = uuid.uuid4()
    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=art_id,
            user_id=user_id,
            team_id=team_id,
            artifact_name="QuarterCarRideModel.fmu",
            file_format=".fmu",
            mime_type="application/octet-stream",
            size_bytes=len(untrusted_fmu.read_bytes()),
            sha256_hash=sha,
            direction=ArtifactDirection.INPUT.value,
            storage_path=str(untrusted_fmu),
        )
        db.add(art)
        await db.commit()

        service = SolverExecutionService(sandbox_base_dir=tmp_path / "sandboxes")
        job = await service.create_execution_job(
            db=db,
            user=ctx,
            solver_name="FMI_COSIMULATION",
            input_artifact_id=art_id,
            execution_config={"duration": 0.2, "bypass_fmu_vetting": True},
        )
        assert "bypass_fmu_vetting" not in (job.execution_config or {})

        # Simulate an attacker mutating DB execution_config directly before worker pickup
        job.execution_config = {"duration": 0.2, "bypass_fmu_vetting": True}
        await db.commit()

        with patch.object(ExecutionSandbox, "execute_command", new_callable=AsyncMock) as mock_exec:
            completed = await service.execute_job(db=db, job_id=job.id, user=ctx)
            mock_exec.assert_not_awaited()

        assert completed.state == ExecutionJobState.FAILED.value
        assert completed.error_category == "UNTRUSTED_FMU_EXECUTION_REJECTED"
        assert completed.is_executed is False


@pytest.mark.asyncio
async def test_fmi_cosimulation_rejects_non_fmu_extension_bypass(fmu_hardening_user, tmp_path):
    """Submitting a non-.fmu file (e.g. renamed .zip) to FMI_COSIMULATION fails closed."""
    ctx = fmu_hardening_user["context"]
    user_id = fmu_hardening_user["user_id"]
    team_id = fmu_hardening_user["team_id"]

    disguised = tmp_path / "payload.zip"
    disguised.write_bytes(b"PK\x03\x04DISGUISED_FMU")
    sha = hashlib.sha256(disguised.read_bytes()).hexdigest()

    art_id = uuid.uuid4()
    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=art_id,
            user_id=user_id,
            team_id=team_id,
            artifact_name="payload.zip",
            file_format=".zip",
            mime_type="application/zip",
            size_bytes=len(disguised.read_bytes()),
            sha256_hash=sha,
            direction=ArtifactDirection.INPUT.value,
            storage_path=str(disguised),
        )
        db.add(art)
        await db.commit()

        service = SolverExecutionService(sandbox_base_dir=tmp_path / "sandboxes")
        job = await service.create_execution_job(
            db=db,
            user=ctx,
            solver_name="FMI_COSIMULATION",
            input_artifact_id=art_id,
        )

        with patch.object(ExecutionSandbox, "execute_command", new_callable=AsyncMock) as mock_exec:
            completed = await service.execute_job(db=db, job_id=job.id, user=ctx)
            mock_exec.assert_not_awaited()

        assert completed.state == ExecutionJobState.FAILED.value
        assert completed.error_category == "UNTRUSTED_FMU_EXECUTION_REJECTED"
        assert completed.is_executed is False


@pytest.mark.asyncio
async def test_immediate_pre_execution_hash_verification_blocks_tamper_after_staging(
    fmu_hardening_user, tmp_path
):
    """
    Even if a vetted .fmu file is altered on disk inside the sandbox right before
    execution, the worker re-verifies SHA-256 immediately before executing it and fails closed.
    """
    ctx = fmu_hardening_user["context"]
    user_id = fmu_hardening_user["user_id"]
    team_id = fmu_hardening_user["team_id"]

    vetted_fmu = PROJECT_ROOT / "QuarterCarRideModel.fmu"
    assert vetted_fmu.exists()
    vetted_bytes = vetted_fmu.read_bytes()
    vetted_sha = hashlib.sha256(vetted_bytes).hexdigest()
    assert vetted_sha in VETTED_FMU_SHA256

    art_id = uuid.uuid4()
    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=art_id,
            user_id=user_id,
            team_id=team_id,
            artifact_name="QuarterCarRideModel.fmu",
            file_format=".fmu",
            mime_type="application/octet-stream",
            size_bytes=len(vetted_bytes),
            sha256_hash=vetted_sha,
            direction=ArtifactDirection.INPUT.value,
            storage_path=str(vetted_fmu),
        )
        db.add(art)
        await db.commit()

        service = SolverExecutionService(sandbox_base_dir=tmp_path / "sandboxes")
        job = await service.create_execution_job(
            db=db,
            user=ctx,
            solver_name="FMI_COSIMULATION",
            input_artifact_id=art_id,
            execution_config={"duration": 0.1, "step": 0.002, "bump_height": 0.05},
        )

        # Simulate mid-flight tampering of the staged .fmu during road_input.csv generation
        orig_writer = solver_execution_service.csv.writer

        def _tampering_writer(rf, *args, **kwargs):
            staged_fmu = tmp_path / "sandboxes" / str(job.id) / "QuarterCarRideModel.fmu"
            staged_fmu.write_bytes(b"PK\x03\x04TAMPERED_AFTER_STAGING")
            return orig_writer(rf, *args, **kwargs)

        with patch.object(solver_execution_service.csv, "writer", side_effect=_tampering_writer):
            with patch.object(ExecutionSandbox, "execute_command", new_callable=AsyncMock) as mock_exec:
                completed = await service.execute_job(db=db, job_id=job.id, user=ctx)
                mock_exec.assert_not_awaited()

        assert completed.state == ExecutionJobState.FAILED.value
        assert completed.error_category == "UNTRUSTED_FMU_EXECUTION_REJECTED"
        assert completed.is_executed is False


@pytest.mark.asyncio
async def test_sandbox_execute_command_unconditionally_verifies_fmu_before_spawn(tmp_path):
    """Direct calls to ExecutionSandbox.execute_command reject unvetted FMUs before subprocess spawn."""
    untrusted_fmu = tmp_path / "untrusted.fmu"
    untrusted_fmu.write_bytes(b"PK\x03\x04DIRECT_SANDBOX_UNVETTED")

    sandbox = ExecutionSandbox(job_id=str(uuid.uuid4()), base_dir=tmp_path / "sandboxes")
    sandbox.initialize()

    runtime = SolverRuntimeRegistry.get_runtime("FMI_COSIMULATION")
    assert runtime is not None and runtime.executable_path

    with pytest.raises(PermissionError, match="UNTRUSTED_FMU_EXECUTION_REJECTED"):
        await sandbox.execute_command([
            runtime.executable_path,
            "simulate",
            str(untrusted_fmu),
            "--output-file",
            str(sandbox.sandbox_dir / "results.csv"),
        ])


def test_cosim_orchestrator_rejects_untrusted_fmu_before_loading(tmp_path):
    """CoSimulationMasterOrchestrator rejects unvetted .fmu files prior to extraction or loading."""
    untrusted_fmu = tmp_path / "evil.fmu"
    untrusted_fmu.write_bytes(b"PK\x03\x04UNTRUSTED_COSIM_FMU")
    untrusted_sha = hashlib.sha256(untrusted_fmu.read_bytes()).hexdigest()

    road_spec = ModelParticipantSpec(
        model_id="road",
        name="RoadProfileGenerator",
        role="EXCITATION_SOURCE",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash=RoadProfileGenerator.get_component_hash(),
        variables=[{"name": "z_r", "causality": "output", "unit": "m", "type": "Real"}],
    )
    fmu_spec = ModelParticipantSpec(
        model_id="plant",
        name="EvilModel",
        role="SUSPENSION_PLANT",
        model_type="FMI_2_0_COSIM",
        sha256_hash=untrusted_sha,
        variables=[{"name": "z_road", "causality": "input", "unit": "m", "type": "Real"}],
    )
    contract = CoSimulationCouplingContract(
        contract_id="COSIM-EVIL-TEST",
        name="Untrusted FMU Rejection Test",
        participants=[road_spec, fmu_spec],
        connections=[SignalConnection("road", "z_r", "plant", "z_road", "m", "m")],
    )
    orch = CoSimulationMasterOrchestrator(
        contract=contract,
        fmu_lookup={"plant": untrusted_fmu},
        workspace_base_dir=tmp_path / "cosim_ws",
    )
    with pytest.raises(PermissionError, match="vetted allowlist"):
        orch.execute(duration=0.1)


@pytest.mark.asyncio
async def test_api_vetted_fmu_executes_successfully(fmu_hardening_user):
    """Legitimate vetted QuarterCarRideModel.fmu executes cleanly through POST /api/v1/interop/execute."""
    headers = fmu_hardening_user["headers"]
    user_id = fmu_hardening_user["user_id"]
    team_id = fmu_hardening_user["team_id"]

    vetted_fmu = PROJECT_ROOT / "QuarterCarRideModel.fmu"
    assert vetted_fmu.exists()
    content = vetted_fmu.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    assert sha in VETTED_FMU_SHA256

    art_id = uuid.uuid4()
    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=art_id,
            user_id=user_id,
            team_id=team_id,
            artifact_name="QuarterCarRideModel.fmu",
            file_format=".fmu",
            mime_type="application/octet-stream",
            size_bytes=len(content),
            sha256_hash=sha,
            direction=ArtifactDirection.INPUT.value,
            storage_path=str(vetted_fmu),
        )
        db.add(art)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/interop/execute",
            headers=headers,
            json={
                "solver_name": "FMI_COSIMULATION",
                "input_artifact_id": str(art_id),
                "execution_config": {"duration": 0.2, "step_size": 0.002},
                "wait_for_completion": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "COMPLETED"
        assert data["exit_code"] == 0
        assert data["is_executed"] is True
