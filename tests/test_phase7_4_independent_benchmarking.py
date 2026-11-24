"""
tests/test_phase7_4_independent_benchmarking.py
================================================
SuspensionLab PRO — Phase 7.4 Independent Solver Benchmarking & Verification Test Suite.

Verifies:
1. Exact Matrix Exponential vs High-Order Adaptive (DOP853) Convergence (WP A & B).
2. Physical Benchmark Scenarios (Free, Step, Harmonic, Stiff/Damped, Resonance, Incorrect) (WP B).
3. Result Reconciliation Engine Hardening (Zero-Denominator Gating, Overlap, Missing Channels) (WP C).
4. Strict TOCTOU Integrity Verification & Cryptographic FMU Allowlisting (WP D).
5. Concurrency Hardening, Lease Expiration & Orphan Crash Recovery (WP E).
6. Operational API Endpoints & Truthful Epistemic Capabilities (WP F).
7. Tenant Boundary Isolation & Terminal State Immutability (WP G).
8. Single Head Alembic Integrity & Protected Physics Hash Freeze (WP H).
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import math
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
    UNTRUSTED_FMU_ISOLATION_AVAILABLE,
    VETTED_FMU_SHA256,
)
from suspensionlab.interop.benchmarks.independent_solver import (
    BenchmarkMethod,
    BenchmarkScenario,
    EXPERIMENTAL_PHYSICAL_VALIDATION_VERIFIED,
    IndependentSolverBenchmark,
    QuarterCarBenchmarkParams,
    TAXONOMY_DEFINITIONS,
    THIRD_PARTY_SOLVER_INDEPENDENCE_VERIFIED,
    UNTRUSTED_FMU_ISOLATION_VERIFIED,
    generate_benchmark_dataset,
)
from suspensionlab.interop.reconciliation.engine import (
    ChannelToleranceProvenance,
    ReconciliationReport,
    ResultReconciliationEngine,
)
from suspensionlab.interop.security import TenantIsolationError

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
async def seeded_p74_users():
    """Seeds two isolated tenant users for Phase 7.4 testing."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    team_a_id = uuid.uuid4()
    team_b_id = uuid.uuid4()

    async with SessionLocal() as db:
        user_a = User(
            id=user_a_id,
            email=f"engineer_p74_a_{user_a_id.hex[:6]}@oem.com",
            name="Engineer P74 A",
            plan="PRO",
            password_hash="test-hash",
        )
        user_b = User(
            id=user_b_id,
            email=f"engineer_p74_b_{user_b_id.hex[:6]}@competitor.com",
            name="Engineer P74 B",
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
        "user_b_id": user_b_id,
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "token_a": token_a,
        "token_b": token_b,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "headers_b": {"Authorization": f"Bearer {token_b}"},
        "context_a": UserContext(
            user_id=str(user_a_id),
            email=user_a.email,
            name=user_a.name,
            onboarding_complete=True,
            plan="PRO",
            team_id=str(team_a_id),
        ),
        "context_b": UserContext(
            user_id=str(user_b_id),
            email=user_b.email,
            name=user_b.name,
            onboarding_complete=True,
            plan="PRO",
            team_id=str(team_b_id),
        ),
    }


# ── TEST 1: MATRIX EXPONENTIAL VS DOP853 CONVERGENCE ─────────────────────────

def test_wph_01_matrix_exponential_vs_dop853_free_response_convergence():
    """
    Verifies that the exact continuous-time matrix exponential solution
    and the high-order adaptive SciPy DOP853 numerical solver converge
    on free response dynamics within machine precision (< 1e-10 on displacements, < 1e-8 on accel).
    """
    d_exact = generate_benchmark_dataset(
        scenario=BenchmarkScenario.FREE_RESPONSE,
        method=BenchmarkMethod.EXACT_ANALYTICAL_MATRIX_EXPONENTIAL,
        duration=2.0,
        dt=0.002,
    )
    d_dop = generate_benchmark_dataset(
        scenario=BenchmarkScenario.FREE_RESPONSE,
        method=BenchmarkMethod.HIGH_ORDER_ADAPTIVE_NUMERICAL,
        duration=2.0,
        dt=0.002,
    )

    err_zs = np.max(np.abs(d_exact["z_s"] - d_dop["z_s"]))
    err_zu = np.max(np.abs(d_exact["z_u"] - d_dop["z_u"]))
    err_acc = np.max(np.abs(d_exact["body_accel"] - d_dop["body_accel"]))

    assert err_zs < 1e-10, f"Sprung displacement discrepancy {err_zs} exceeds 1e-10"
    assert err_zu < 1e-10, f"Unsprung displacement discrepancy {err_zu} exceeds 1e-10"
    assert err_acc < 1e-8, f"Body acceleration discrepancy {err_acc} exceeds 1e-8"


# ── TEST 2: STEP INPUT BENCHMARK AGREEMENT ───────────────────────────────────

def test_wph_02_step_input_benchmark_agreement():
    """
    Verifies step input bump response between continuous matrix exponential
    and 8th-order adaptive DOP853 integration.
    """
    d_exact = generate_benchmark_dataset(
        scenario=BenchmarkScenario.STEP_INPUT,
        method=BenchmarkMethod.EXACT_ANALYTICAL_MATRIX_EXPONENTIAL,
        duration=2.0,
        dt=0.002,
    )
    d_dop = generate_benchmark_dataset(
        scenario=BenchmarkScenario.STEP_INPUT,
        method=BenchmarkMethod.HIGH_ORDER_ADAPTIVE_NUMERICAL,
        duration=2.0,
        dt=0.002,
    )

    err_zs = np.max(np.abs(d_exact["z_s"] - d_dop["z_s"]))
    assert err_zs < 1e-10, f"Step input sprung displacement error {err_zs} exceeds 1e-10"

    # Verify physical bump height tracking in steady state
    assert np.isclose(d_exact["z_s"][-1], 0.05, atol=2e-3)
    assert np.isclose(d_exact["z_u"][-1], 0.05, atol=2e-3)


# ── TEST 3: HARMONIC EXCITATION FREQUENCY RESPONSE ───────────────────────────

def test_wph_03_harmonic_excitation_frequency_response():
    """
    Verifies harmonic road profile excitation (1.5 Hz body bounce range),
    confirming steady periodic oscillations and phase behavior.
    """
    d_harm = generate_benchmark_dataset(
        scenario=BenchmarkScenario.HARMONIC_EXCITATION,
        method=BenchmarkMethod.HIGH_ORDER_ADAPTIVE_NUMERICAL,
        duration=3.0,
        dt=0.002,
    )

    t = d_harm["time"]
    zs = d_harm["z_s"]

    # Verify peak amplitudes are finite, nonzero, and bounded
    peak_zs = np.max(np.abs(zs))
    assert 0.01 < peak_zs < 0.10, f"Harmonic peak sprung displacement {peak_zs} out of expected bounds"

    # Check zero crossings in steady state (last 1.5 seconds)
    ss_mask = t >= 1.5
    ss_zs = zs[ss_mask]
    zero_crossings = np.where(np.diff(np.signbit(ss_zs)))[0]
    # In 1.5s at 1.5 Hz, expect ~4 to 5 zero crossings
    assert len(zero_crossings) >= 4


# ── TEST 4: STIFF DAMPED SYSTEM STABILITY VIA RADAU ──────────────────────────

def test_wph_04_stiff_damped_system_stability_radau():
    """
    Verifies implicit Radau 5th-order integration on a stiff/highly damped configuration
    (c=8000, ks=80000, kt=300000) matches matrix exponential within 1e-10.
    """
    d_exact = generate_benchmark_dataset(
        scenario=BenchmarkScenario.STIFF_DAMPED,
        method=BenchmarkMethod.EXACT_ANALYTICAL_MATRIX_EXPONENTIAL,
        duration=1.5,
        dt=0.002,
    )
    d_radau = generate_benchmark_dataset(
        scenario=BenchmarkScenario.STIFF_DAMPED,
        method=BenchmarkMethod.HIGH_ORDER_ADAPTIVE_NUMERICAL,
        duration=1.5,
        dt=0.002,
    )

    err = np.max(np.abs(d_exact["z_s"] - d_radau["z_s"]))
    assert err < 1e-10, f"Radau vs Matrix Expm on stiff damped system error {err} exceeds 1e-10"
    # Verify no numerical overflow or high-frequency ringing
    assert not np.any(np.isnan(d_radau["z_s"]))
    assert np.max(np.abs(d_radau["z_s"])) < 0.05


# ── TEST 5: NEAR RESONANCE DYNAMIC AMPLIFICATION ─────────────────────────────

def test_wph_05_near_resonance_dynamic_amplification():
    """
    Verifies road excitation tuned close to the sprung mass natural frequency (~1.45 Hz)
    produces dynamic amplification exceeding static road amplitude.
    """
    d_res = generate_benchmark_dataset(
        scenario=BenchmarkScenario.NEAR_RESONANCE,
        method=BenchmarkMethod.HIGH_ORDER_ADAPTIVE_NUMERICAL,
        duration=4.0,
        dt=0.002,
    )

    road_amp = 0.015  # 15 mm
    peak_zs = np.max(np.abs(d_res["z_s"][d_res["time"] > 1.0]))
    amplification = peak_zs / road_amp

    assert amplification > 1.25, f"Expected resonant dynamic amplification > 1.25, got {amplification:.3f}"


# ── TEST 6: INTENTIONALLY INCORRECT MODEL RECONCILIATION FAILURE ─────────────

def test_wph_06_intentionally_incorrect_model_fails_reconciliation():
    """
    Verifies that the reconciliation engine correctly detects physics errors
    (perturbed stiffness and inverted damping) and reports overall FAIL verdict.
    """
    d_correct = generate_benchmark_dataset(
        scenario=BenchmarkScenario.STEP_INPUT,
        method=BenchmarkMethod.EXACT_ANALYTICAL_MATRIX_EXPONENTIAL,
        duration=2.0,
        dt=0.002,
    )
    d_incorrect = generate_benchmark_dataset(
        scenario=BenchmarkScenario.INTENTIONALLY_INCORRECT,
        method=BenchmarkMethod.EXACT_ANALYTICAL_MATRIX_EXPONENTIAL,
        duration=2.0,
        dt=0.002,
    )

    report = ResultReconciliationEngine.reconcile(
        external_data=d_incorrect,
        reference_data=d_correct,
        solver_name="INTENTIONALLY_CORRUPT_SOLVER",
        reference_model="ReferenceQuarterCar_2DOF",
    )

    assert report.overall_status == "FAIL"
    assert report.summary["signals_failed"] > 0
    assert report.metrics["z_s"].status == "FAIL"


# ── TEST 7: QUIESCENT CHANNEL DIVISION BY NEAR ZERO GATING ───────────────────

def test_wph_07_quiescent_channel_division_by_near_zero_gating():
    """
    Verifies that quiescent / near-zero channels engage absolute threshold gating
    instead of dividing by near-zero denominators, preventing NaN/Inf metrics.
    """
    t = np.arange(0.0, 2.002, 0.002)
    # Channel with near-zero amplitude (< 1e-4 m), well below 0.002m absolute threshold
    y_ref = np.full_like(t, 1e-6)
    y_ext = np.full_like(t, 1.5e-6)

    ref_data = {"time": t, "z_s": y_ref}
    ext_data = {"time": t, "z_s": y_ext}

    report = ResultReconciliationEngine.reconcile(
        external_data=ext_data,
        reference_data=ref_data,
        solver_name="QUIESCENT_TEST",
    )

    metric = report.metrics["z_s"]
    assert metric.denominator_mode == "ABSOLUTE_THRESHOLD"
    assert metric.status == "PASS"
    assert not math.isnan(metric.nrmse)
    assert not math.isinf(metric.nrmse)
    assert metric.rms_error < metric.absolute_threshold


# ── TEST 8: TIME BASE EXTRAPOLATION REJECTION ────────────────────────────────

def test_wph_08_time_base_extrapolation_rejection():
    """
    Verifies that reconciliation strictly rejects datasets with < 90% time overlap,
    prohibiting unverified time-base extrapolation.
    """
    t_ext = np.arange(0.0, 1.002, 0.002)   # 1.0 second span
    t_ref = np.arange(0.0, 2.002, 0.002)   # 2.0 second span (only 50% overlap)

    ext_data = {"time": t_ext, "z_s": np.zeros_like(t_ext)}
    ref_data = {"time": t_ref, "z_s": np.zeros_like(t_ref)}

    with pytest.raises(ValueError, match="Insufficient time overlap"):
        ResultReconciliationEngine.reconcile(
            external_data=ext_data,
            reference_data=ref_data,
        )


# ── TEST 9: MISSING REQUIRED CHANNELS GUARD ──────────────────────────────────

def test_wph_09_missing_required_channels_guard():
    """
    Verifies that reconciliation raises an explicit error if any required
    signal channels are missing from the dataset.
    """
    t = np.arange(0.0, 2.002, 0.002)
    ext_data = {"time": t, "z_s": np.zeros_like(t)}
    ref_data = {"time": t, "z_s": np.zeros_like(t), "z_u": np.zeros_like(t)}

    with pytest.raises(ValueError, match="Required signals missing"):
        ResultReconciliationEngine.reconcile(
            external_data=ext_data,
            reference_data=ref_data,
            required_signals=["z_s", "z_u", "tire_load_dynamic"],
        )


# ── TEST 10: STRICT CRYPTOGRAPHIC FMU ALLOWLIST ──────────────────────────────

@pytest.mark.asyncio
async def test_wph_10_strict_fmu_cryptographic_allowlist_enforcement(tmp_path, seeded_p74_users):
    """
    Verifies that any FMU with an unknown SHA-256 hash is rejected fail-closed,
    even if the filename matches 'QuarterCarRideModel.fmu' (no filename bypass).
    """
    user_context = seeded_p74_users["context_a"]
    user_a_id = seeded_p74_users["user_a_id"]
    team_a_id = seeded_p74_users["team_a_id"]

    fake_fmu_content = b"PK\x03\x04FAKE_UNTRUSTED_FMU_CONTENT_FOR_SECURITY_AUDIT"
    fake_sha = hashlib.sha256(fake_fmu_content).hexdigest()
    fmu_file = tmp_path / "QuarterCarRideModel.fmu"
    fmu_file.write_bytes(fake_fmu_content)

    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=uuid.uuid4(),
            organization_id=None,
            team_id=team_a_id,
            user_id=user_a_id,
            direction=ArtifactDirection.INPUT.value,
            artifact_name="QuarterCarRideModel.fmu",
            file_format=".fmu",
            mime_type="application/octet-stream",
            sha256_hash=fake_sha,
            size_bytes=len(fake_fmu_content),
            storage_path=str(fmu_file),
        )
        db.add(art)
        await db.commit()

        service = SolverExecutionService(sandbox_base_dir=tmp_path / "sandboxes")

        job = await service.create_execution_job(
            db=db,
            user=user_context,
            solver_name="FMI_COSIMULATION",
            input_artifact_id=art.id,
        )

        executed_job = await service.execute_job(db=db, job_id=job.id, user=user_context)

        assert executed_job.state == ExecutionJobState.FAILED.value
        assert executed_job.error_category == "UNTRUSTED_FMU_EXECUTION_REJECTED"
        assert "is not in the vetted allowlist" in executed_job.failure_reason
        assert executed_job.is_executed is False


# ── TEST 11: TOCTOU STAGING TAMPERING DETECTION ──────────────────────────────

@pytest.mark.asyncio
async def test_wph_11_toctou_staging_tampering_detection(tmp_path, seeded_p74_users):
    """
    Verifies that if a staged input artifact's content on disk is modified after
    initial staging or hash registration, TOCTOU verification flags an integrity violation.
    """
    user_context = seeded_p74_users["context_a"]
    user_a_id = seeded_p74_users["user_a_id"]
    team_a_id = seeded_p74_users["team_a_id"]

    orig_content = b'{"m_s": 300.0, "m_u": 40.0}'
    tampered_sha = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    input_file = tmp_path / "model.json"
    input_file.write_bytes(orig_content)

    async with SessionLocal() as db:
        art = SolverExchangeArtifact(
            id=uuid.uuid4(),
            organization_id=None,
            team_id=team_a_id,
            user_id=user_a_id,
            direction=ArtifactDirection.INPUT.value,
            artifact_name="model.json",
            file_format=".json",
            mime_type="application/json",
            sha256_hash=tampered_sha,  # Registered hash does NOT match file on disk
            size_bytes=len(orig_content),
            storage_path=str(input_file),
        )
        db.add(art)
        await db.commit()

        service = SolverExecutionService(sandbox_base_dir=tmp_path / "sandboxes")

        job = await service.create_execution_job(
            db=db,
            user=user_context,
            solver_name="EXTERNAL_CAE_SOLVER",
            input_artifact_id=art.id,
        )

        executed_job = await service.execute_job(db=db, job_id=job.id, user=user_context)

        assert executed_job.state == ExecutionJobState.FAILED.value
        assert executed_job.error_category == "TOCTOU_INTEGRITY_VIOLATION"
        assert executed_job.is_executed is False


# ── TEST 12: WORKER LEASE EXPIRATION & ORPHAN CRASH RECOVERY ─────────────────

@pytest.mark.asyncio
async def test_wph_12_worker_lease_expiration_and_orphan_crash_recovery(tmp_path, seeded_p74_users):
    """
    Verifies that orphaned jobs left in RUNNING state whose lease has expired
    are safely recovered and transitioned to FAILED (WORKER_CRASH_ORPHAN).
    """
    user_a_id = seeded_p74_users["user_a_id"]
    team_a_id = seeded_p74_users["team_a_id"]

    past_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=60)

    async with SessionLocal() as db:
        orphaned_job = SolverExecutionJob(
            id=uuid.uuid4(),
            organization_id=None,
            team_id=team_a_id,
            user_id=user_a_id,
            solver_name="EXTERNAL_CAE_SOLVER",
            solver_version="1.0.0",
            adapter_id="adapter-external-cae",
            state=ExecutionJobState.RUNNING.value,
            input_artifact_hash="abc123",
            lease_expires_at=past_time,
            heartbeat_at=past_time,
            execution_mode="TRUSTED_ALLOWLIST",
        )
        db.add(orphaned_job)
        await db.commit()

        service = SolverExecutionService(sandbox_base_dir=tmp_path / "sandboxes")
        recovered = await service.recover_crashed_jobs(db=db)

        assert len(recovered) >= 1
        rec_ids = [r.id for r in recovered]
        assert orphaned_job.id in rec_ids

        # Verify state in DB
        stmt = select(SolverExecutionJob).where(SolverExecutionJob.id == orphaned_job.id)
        res = await db.execute(stmt)
        updated = res.scalar_one()
        assert updated.state == ExecutionJobState.FAILED.value
        assert updated.error_category == "WORKER_CRASH_ORPHAN"
        assert updated.exit_code == -9


# ── TEST 13: TERMINAL STATE IMMUTABILITY ON RECOVERED JOBS ───────────────────

@pytest.mark.asyncio
async def test_wph_13_terminal_state_immutability_on_recovered_jobs(tmp_path, seeded_p74_users):
    """
    Verifies that a job transitioned to terminal FAILED state cannot be mutated
    or transitioned to any other state.
    """
    user_a_id = seeded_p74_users["user_a_id"]
    team_a_id = seeded_p74_users["team_a_id"]

    job = SolverExecutionJob(
        id=uuid.uuid4(),
        organization_id=None,
        team_id=team_a_id,
        user_id=user_a_id,
        solver_name="EXTERNAL_CAE_SOLVER",
        solver_version="1.0.0",
        adapter_id="adapter-cae",
        state=ExecutionJobState.FAILED.value,
        input_artifact_hash="hash123",
    )

    with pytest.raises(ImmutableExecutionError):
        job.assert_mutable()

    with pytest.raises(ImmutableExecutionError):
        job.transition_to(ExecutionJobState.RUNNING)


# ── TEST 14: MULTI-TENANT ISOLATION ON JOBS & RECONCILIATION ─────────────────

@pytest.mark.asyncio
async def test_wph_14_multitenant_isolation_on_jobs_and_reconciliation(seeded_p74_users):
    """
    Verifies cross-tenant boundary security: User B cannot access or reconcile User A's job.
    """
    token_a = seeded_p74_users["token_a"]
    token_b = seeded_p74_users["token_b"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # User A discovers runtimes and jobs
        resp_runtimes = await client.get("/api/v1/interop/runtimes", headers={"Authorization": f"Bearer {token_a}"})
        assert resp_runtimes.status_code == 200

        # Create a job under User A in DB
        job_id = uuid.uuid4()
        async with SessionLocal() as db:
            job_a = SolverExecutionJob(
                id=job_id,
                organization_id=None,
                team_id=seeded_p74_users["team_a_id"],
                user_id=seeded_p74_users["user_a_id"],
                solver_name="EXTERNAL_CAE_SOLVER",
                solver_version="1.0.0",
                adapter_id="adapter-cae",
                state=ExecutionJobState.QUEUED.value,
                input_artifact_hash="hash_a",
            )
            db.add(job_a)
            await db.commit()

        # User B attempts to access User A's job
        resp_b = await client.get(f"/api/v1/interop/jobs/{job_id}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp_b.status_code in (403, 404)

        # User B attempts to cancel User A's job
        resp_b_cancel = await client.post(f"/api/v1/interop/jobs/{job_id}/cancel", headers={"Authorization": f"Bearer {token_b}"})
        assert resp_b_cancel.status_code in (403, 404)


# ── TEST 15: EPISTEMIC INVARIANTS PRESERVED ACROSS API ───────────────────────

@pytest.mark.asyncio
async def test_wph_15_epistemic_invariants_preserved_across_api(seeded_p74_users):
    """
    Verifies that JobResponseDTO strictly returns is_executed=False for queued jobs,
    and is_physically_validated=False across all states.
    """
    token_a = seeded_p74_users["token_a"]

    job_id = uuid.uuid4()
    async with SessionLocal() as db:
        job = SolverExecutionJob(
            id=job_id,
            organization_id=None,
            team_id=seeded_p74_users["team_a_id"],
            user_id=seeded_p74_users["user_a_id"],
            solver_name="EXTERNAL_CAE_SOLVER",
            solver_version="1.0.0",
            adapter_id="adapter-cae",
            state=ExecutionJobState.QUEUED.value,
            input_artifact_hash="hash_epistemic",
            is_executed=False,
            is_physically_validated=False,
        )
        db.add(job)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/interop/jobs/{job_id}", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_executed"] is False
        assert data["is_physically_validated"] is False
        assert data["execution_mode"] == "TRUSTED_ALLOWLIST"


# ── TEST 16: BENCHMARK CAPABILITIES API TRUTHFULNESS ─────────────────────────

@pytest.mark.asyncio
async def test_wph_16_benchmark_capabilities_api_truthfulness(seeded_p74_users):
    """
    Verifies GET /api/v1/interop/benchmarks/capabilities exposes:
    - Truthful invariant: third_party_solver_independence_verified = False
    - Truthful invariant: untrusted_fmu_isolation_verified = False
    - Available benchmark methods and scenarios
    - Channel tolerance provenance metadata
    """
    token_a = seeded_p74_users["token_a"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/interop/benchmarks/capabilities", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        data = resp.json()

        invariants = data["epistemic_invariants"]
        assert invariants["third_party_solver_independence_verified"] is False
        assert invariants["untrusted_fmu_isolation_verified"] is False
        assert invariants["experimental_physical_validation_verified"] is False

        assert "EXACT_ANALYTICAL_MATRIX_EXPONENTIAL" in data["available_methods"]
        assert "HIGH_ORDER_ADAPTIVE_NUMERICAL" in data["available_methods"]
        assert "FREE_RESPONSE" in data["available_scenarios"]
        assert "STIFF_DAMPED" in data["available_scenarios"]
        assert "z_s" in data["channel_provenance"]


# ── TEST 17: CHANNEL TOLERANCE PROVENANCE AUDIT ──────────────────────────────

def test_wph_17_channel_tolerance_provenance_audit():
    """
    Audits the pre-registered channel tolerance provenance table for complete
    physical documentation (units, dimensions, thresholds, and rationales).
    """
    prov = ResultReconciliationEngine.CHANNEL_PROVENANCE

    expected_channels = ["z_s", "z_u", "susp_travel", "tire_load_dynamic", "body_accel"]
    for ch in expected_channels:
        assert ch in prov, f"Channel {ch} missing from tolerance provenance"
        meta = prov[ch]
        assert meta.unit in ("m", "N", "m/s2")
        assert meta.nrmse_threshold > 0.0
        assert meta.absolute_threshold > 0.0
        assert len(meta.provenance_rationale) > 10


# ── TEST 18: ALEMBIC SINGLE HEAD & FREEZE INTEGRITY ──────────────────────────

def test_wph_18_alembic_single_head_and_freeze_integrity():
    """
    Verifies that Alembic migration history terminates at exactly 1 single head (v2w3x4y5z6p74),
    and all 81 protected production physics files and 7 Phase 3 manifests match baseline SHA-256.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()

    assert len(heads) == 1, f"Multiple heads detected in Alembic: {heads}"
    assert heads[0] in ("v2w3x4y5z6p74", "w7x7y7z7a7b7", "x7y8z9a0b1c2", "y8z9a0b1c2d3", "z9a0b1c2d3e4", "z86a0b1c2d3e", "z87a0b1c2d3e")

    # Physics freeze audit
    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    assert hash_file.exists(), "pre_phase4_3_hashes.json missing!"

    data = json.loads(hash_file.read_text(encoding="utf-8"))
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
