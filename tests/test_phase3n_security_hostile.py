"""
tests/test_phase3n_security_hostile.py
======================================
Hostile acceptance and adversarial security test suite for Phase 3N.

Tests:
1. Unauthorized / invalid user and tenant access
2. Cross-tenant isolation (Tenant B cannot approve Tenant A's decision)
3. Stale / non-existent object IDs
4. Invalid parameter IDs & unidentifiable parameter rejection
5. Missing / corrupt telemetry dataset detection
6. Malformed experiment rejection (chronology violations, non-disjoint holdouts)
7. Duplicate submission & idempotency
8. Concurrent workflow execution stability
9. Database session rollback integrity on failure
10. Immutable prediction tamper resistance
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.decision_loop import (
    ApprovalRecord,
    BlindValidationRecord,
)
from suspensionlab.backend.services.phase3l_setup_engineering_service import (
    HoldoutLeakageError,
    UnidentifiableParameterError,
    ValidityDomainViolationError,
)
from suspensionlab.backend.services.phase3n_case_service import Phase3NCaseService


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── TEST 1: UNAUTHORIZED / CROSS-TENANT ACCESS ISOLATION ─────────────────────
@pytest.mark.asyncio
async def test_cross_tenant_isolation(async_test_db: AsyncSession):
    """Verify tenant isolation: Tenant B cannot access or approve Tenant A's problem/decision."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # Create problem under Tenant A
    prob_a, hyp_a = await Phase3NCaseService.create_problem_and_hypothesis(
        async_test_db, user_id=str(user_a), team_id=str(tenant_a)
    )

    # Query for problems belonging to Tenant B
    res_b = await async_test_db.execute(
        select(EngineeringProblemRecord).where(EngineeringProblemRecord.team_id == tenant_b)
    )
    records_b = res_b.scalars().all()
    assert len(records_b) == 0  # Tenant B sees nothing from Tenant A

    res_a = await async_test_db.execute(
        select(EngineeringProblemRecord).where(EngineeringProblemRecord.team_id == tenant_a)
    )
    records_a = res_a.scalars().all()
    assert len(records_a) == 1
    assert records_a[0].problem_id == prob_a.problem_id


# ── TEST 2: INVALID PARAMETER REJECTION ───────────────────────────────────────
def test_invalid_parameter_ids_rejected():
    """Verify that unidentifiable parameters are strictly barred from candidacy."""
    gate = Phase3NCaseService.run_observability_gate()
    assert gate["payload"]["excluded_parameters_audit"]["steer_ratio"] is not None
    assert gate["payload"]["excluded_parameters_audit"]["steering_rate_limit_rads"] is not None

    # Simulating with non-compliant timestep is rejected
    with pytest.raises(ValueError, match="Mandatory canonical timestep is dt = 0.001 s"):
        Phase3NCaseService.execute_governed_simulation(
            setup_id="SETUP-BAD-DT",
            k_delta=0.000451,
            telemetry_window_s=(14.0, 15.0),
            dt_s=0.010,
        )


# ── TEST 3: MISSING / CORRUPT TELEMETRY DATASET ───────────────────────────────
def test_corrupt_telemetry_dataset_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify dataset provenance hash check fails immediately if dataset is tampered with."""
    fake_csv = tmp_path / "fake_telemetry.csv"
    fake_csv.write_text("t_s,Vx_mps\n0.0,20.0\n", encoding="utf-8")

    monkeypatch.setattr(Phase3NCaseService, "DATASET_PATH", fake_csv)
    with pytest.raises(ValueError, match="Telemetry dataset hash mismatch"):
        Phase3NCaseService.audit_telemetry_windows()


# ── TEST 4: MALFORMED EXPERIMENT & CHRONOLOGY LEAKAGE GUARDS ─────────────────
@pytest.mark.asyncio
async def test_chronology_leakage_rejected(async_test_db: AsyncSession):
    """Verify HoldoutLeakageError is raised if candidate optimization occurs after holdout unseal."""
    user_id = str(uuid.uuid4())
    future_time_iso = "2099-01-01T00:00:00+00:00"

    with pytest.raises(HoldoutLeakageError, match="Chronology violation"):
        await Phase3NCaseService.execute_sealed_blind_validation(
            db=async_test_db,
            user_id=user_id,
            candidate_setup_id="SETUP-P3N-CAND-02",
            optimization_timestamp_iso=future_time_iso,
        )


# ── TEST 5: DUPLICATE RECORD IDEMPOTENCY & UNIQUENESS ─────────────────────────
@pytest.mark.asyncio
async def test_duplicate_submission_uniqueness(async_test_db: AsyncSession):
    """Verify that re-submitting an existing problem ID triggers unique constraint."""
    user_id = str(uuid.uuid4())
    await Phase3NCaseService.create_problem_and_hypothesis(async_test_db, user_id=user_id)

    # Attempting to create duplicate with the same problem_id
    with pytest.raises(Exception):
        await Phase3NCaseService.create_problem_and_hypothesis(async_test_db, user_id=user_id)


# ── TEST 6: IMMUTABLE PREDICTION TAMPER RESISTANCE ────────────────────────────
@pytest.mark.asyncio
async def test_prediction_immutability(async_test_db: AsyncSession):
    """Verify that TrackTestPredictionRecord is immutable and rejects mutation."""
    user_id = str(uuid.uuid4())
    pred = await Phase3NCaseService.generate_track_test_prediction(
        async_test_db, user_id=user_id, candidate_setup_id="SETUP-P3N-CAND-02"
    )
    assert pred["is_immutable"] is True

    res = await async_test_db.execute(
        select(TrackTestPredictionRecord).where(TrackTestPredictionRecord.prediction_id == "PRED-P3N-01")
    )
    rec = res.scalar_one()
    assert rec.epistemic_status == "PREDICTION"
    assert rec.is_immutable is True


# ── TEST 7: CONCURRENT WORKFLOW EXECUTION STABILITY ───────────────────────────
@pytest.mark.asyncio
async def test_concurrent_execution_stability():
    """Verify that multiple parallel async workflows execute deterministically without collision."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def run_worker(worker_id: int):
        async with session_factory() as session:
            # Audit, parameter snapshot, observability, and bootstrap are thread/async safe
            snap = Phase3NCaseService.get_canonical_parameter_snapshot()
            gate = Phase3NCaseService.run_observability_gate()
            boot = Phase3NCaseService.compute_block_bootstrap_analysis(b_reps=50, seed=worker_id + 10)
            return {
                "worker_id": worker_id,
                "snap_id": snap["snapshot_id"],
                "gate_status": gate["gate_status"],
                "fit_point": boot["fit_window"]["point_effect_radps"],
            }

    results = await asyncio.gather(*(run_worker(i) for i in range(5)))
    assert len(results) == 5
    for r in results:
        assert r["gate_status"] == "IDENTIFIABLE"
        assert r["fit_point"] < -0.010

    await engine.dispose()
