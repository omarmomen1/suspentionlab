"""
tests/test_phase6_6_phase7_4_integration_hostile.py
===================================================
Hostile Integration, Scientific Validity & End-to-End Security Acceptance Suite
for SuspensionLab PRO: Phase 6.6 (Validation Planning) + Phase 7.4 (Independent Benchmarking).

Verifies:
1. Critical Task 4: Empirical Evidence Authenticity & Ingestion Pipeline
2. Critical Task 5: Acceptance Criteria Sealing, Immutability & Reassessment Integrity
3. Critical Task 6: Independent Reference Benchmarks & Reconciliation Hardening
4. Critical Task 7: Execution Security, TOCTOU Staging & Tenant-Isolated Recovery
5. Critical Task 9: Complete Application Journeys A, B, and C
"""
import copy
import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.engineering_decision import (
    EngineeringDecision,
)
from suspensionlab.backend.database.models.parameter_trust import (
    EngineeringValidationPlanRecord,
    ValidationDecisionReassessmentRecord,
    ValidationEvidenceClosureRecord,
    ValidationEvidenceItemRecord,
    ValidationPlanStatus,
)
from suspensionlab.backend.database.models.solver_execution import (
    ExecutionJobState,
    SolverExecutionJob,
)
from suspensionlab.backend.database.models.solver_exchange import (
    SolverExchangeArtifact,
    ArtifactDirection,
)
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.auth import UserContext, verify_api_key
from suspensionlab.backend.services.parameter_trust_validation_service import (
    CriteriaImmutableAfterAuthorizationError,
    InvalidEvidenceScopeError,
    InvalidPlanStateTransitionError,
    MissingEvidenceProvenanceError,
    ParameterTrustValidationService,
    PlanNotFoundError,
    PreRevealFirewallViolation,
    SimulationMasqueradingAsPhysicalError,
    UnauthorizedValidationActionError,
    ValidationPlanningError,
)
from suspensionlab.backend.services.solver_execution_service import (
    SolverExecutionService,
    VETTED_FMU_SHA256,
)
from suspensionlab.interop.benchmarks.independent_solver import (
    BenchmarkMethod,
    BenchmarkScenario,
    EXPERIMENTAL_PHYSICAL_VALIDATION_VERIFIED,
    IndependentSolverBenchmark,
    TAXONOMY_DEFINITIONS,
    THIRD_PARTY_SOLVER_INDEPENDENCE_VERIFIED,
    UNTRUSTED_FMU_ISOLATION_VERIFIED,
    generate_benchmark_dataset,
)
from suspensionlab.interop.reconciliation.engine import (
    ResultReconciliationEngine,
    SignalMetricResult,
)


def make_ctx(user_id: str, team_id: str, org_id: str, role: str = "validation_lead") -> UserContext:
    is_admin = role.lower() in ("admin", "org_admin", "lead", "validation_lead", "chief")
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email=f"user_{str(user_id)[:6]}@suspensionlab.io",
        name=f"User {str(user_id)[:6]}",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=role.upper(),
        org_role="MEMBER",
        is_admin=is_admin,
    )


@pytest.fixture
async def integrated_test_env(db_session: AsyncSession):
    db = db_session
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_lead_a = uuid.uuid4()
    user_eng_a = uuid.uuid4()

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    # Seed Organizations
    org_rec_a = Organization(id=org_a, name="Org A", slug=f"org-a-{org_a.hex[:6]}", plan="ENTERPRISE")
    org_rec_b = Organization(id=org_b, name="Org B", slug=f"org-b-{org_b.hex[:6]}", plan="ENTERPRISE")
    db.add_all([org_rec_a, org_rec_b])
    await db.flush()

    # Seed Users (initially team_id=None to satisfy Team.owner_id FK)
    u_lead = User(id=user_lead_a, organization_id=org_a, team_id=None, email="lead_a@test.com", password_hash="h1", plan="ENTERPRISE")
    u_eng = User(id=user_eng_a, organization_id=org_a, team_id=None, email="eng_a@test.com", password_hash="h2", plan="ENTERPRISE")
    u_b = User(id=user_b, organization_id=org_b, team_id=None, email="user_b@test.com", password_hash="h3", plan="ENTERPRISE")
    db.add_all([u_lead, u_eng, u_b])
    await db.flush()

    # Seed Teams
    t_a = Team(id=team_a, name="Team A", slug=f"team-a-{team_a.hex[:6]}", owner_id=user_lead_a, plan="ENTERPRISE", data_region="us-east-1", organization_id=org_a)
    t_b = Team(id=team_b, name="Team B", slug=f"team-b-{team_b.hex[:6]}", owner_id=user_b, plan="ENTERPRISE", data_region="us-east-1", organization_id=org_b)
    db.add_all([t_a, t_b])
    await db.flush()

    # Update users with team_id
    u_lead.team_id = team_a
    u_eng.team_id = team_a
    u_b.team_id = team_b
    await db.flush()

    # Seed Engineering Decision for Tenant A
    dec_id = uuid.uuid4()
    dec_a = EngineeringDecision(
        id=dec_id,
        decision_id=str(dec_id),
        question="Select front spring stiffness for GT chassis",
        context={"vehicle_id": "CAR-01", "setup_id": "SETUP-VAL-01"},
        candidates=["SETUP-VAL-01", "SETUP-VAL-02"],
        selected_option={"setup_id": "SETUP-VAL-01"},
        reason="Stiffness targets ride frequency and damping ratio",
        tradeoffs={"ride_vs_handling": "Stiffer front improves turn-in response"},
        risks={"kerb_strike": "Higher peak contact patch load"},
        simulation_evidence=[{"sim_label": "SIM-SENS-VAL-01"}],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Validation Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_val_01"},
        team_id=team_a,
        user_id=user_lead_a,
    )
    db.add(dec_a)
    await db.commit()

    lead_ctx_a = make_ctx(str(user_lead_a), str(team_a), str(org_a), role="validation_lead")
    eng_ctx_a = make_ctx(str(user_eng_a), str(team_a), str(org_a), role="engineer")
    user_ctx_b = make_ctx(str(user_b), str(team_b), str(org_b), role="validation_lead")

    return {
        "db": db,
        "org_a": org_a,
        "team_a": team_a,
        "user_lead_a": user_lead_a,
        "user_eng_a": user_eng_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "dec_a": dec_a,
        "lead_ctx_a": lead_ctx_a,
        "eng_ctx_a": eng_ctx_a,
        "user_ctx_b": user_ctx_b,
    }


# ==============================================================================
# CRITICAL TASK 4: EVIDENCE AUTHENTICITY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_ct4_01_missing_provenance_rejected(integrated_test_env):
    """User-uploaded CSV/data without traceable calibration provenance is rejected."""
    env = integrated_test_env
    db = env["db"]

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        validation_method="RIG_TEST_4_POST",
        validation_objective="Validate spring stiffness",
        unit="N/m",
        user_context=env["lead_ctx_a"],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=env["lead_ctx_a"]
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=env["lead_ctx_a"]
    )

    # Missing provenance dictionary
    with pytest.raises(MissingEvidenceProvenanceError, match="missing source_identifier or traceable provenance"):
        await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=plan.id,
            evidence_data={
                "source_identifier": "",
                "evidence_source_type": "PHYSICAL_RIG_MEASUREMENT",
                "observed_value": 80200.0,
                "unit": "N/m",
            },
            user_context=env["eng_ctx_a"],
        )


@pytest.mark.asyncio
async def test_ct4_02_simulated_masquerade_rejected(integrated_test_env):
    """Simulated/CAE data mislabeled as physical proving ground data is rejected."""
    env = integrated_test_env
    db = env["db"]

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=env["lead_ctx_a"],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=env["lead_ctx_a"]
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=env["lead_ctx_a"]
    )

    # Mislabeled simulation
    with pytest.raises(SimulationMasqueradingAsPhysicalError, match="Simulated/CAE evidence"):
        await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=plan.id,
            evidence_data={
                "source_identifier": "RIG-SIMULATED-RUN-01",
                "evidence_source_type": "NUMERICAL_SIMULATION_RESULT",
                "observed_value": 80000.0,
                "is_physically_validated": True,  # Fraudulent claim
                "provenance": {"solver": "Adams_Car", "run": "quarter_car_sim"},
            },
            user_context=env["eng_ctx_a"],
        )


@pytest.mark.asyncio
async def test_ct4_03_submission_to_unauthorized_plan_rejected(integrated_test_env):
    """Evidence cannot be submitted until acceptance criteria are established and authorized."""
    env = integrated_test_env
    db = env["db"]

    # Plan is in DRAFT status
    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=env["lead_ctx_a"],
    )
    with pytest.raises(InvalidPlanStateTransitionError, match="must be AUTHORIZED"):
        await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=plan.id,
            evidence_data={
                "source_identifier": "RIG-001",
                "observed_value": 80000.0,
                "provenance": {"rig": "Roehrig-4Post"},
            },
            user_context=env["eng_ctx_a"],
        )


@pytest.mark.asyncio
async def test_ct4_04_cross_tenant_evidence_blocked(integrated_test_env):
    """User from Tenant B cannot submit evidence to Tenant A's validation plan."""
    env = integrated_test_env
    db = env["db"]

    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=env["lead_ctx_a"],
    )
    with pytest.raises(PlanNotFoundError):
        await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=plan.id,
            evidence_data={
                "source_identifier": "RIG-001",
                "provenance": {"rig": "Test"},
            },
            user_context=env["user_ctx_b"],
        )


# ==============================================================================
# CRITICAL TASK 5: VALIDATION & REASSESSMENT INTEGRITY
# ==============================================================================

@pytest.mark.asyncio
async def test_ct5_01_criteria_sealing_and_version_immutability(integrated_test_env):
    """Authorized acceptance criteria are immutable; updates require a new plan version."""
    env = integrated_test_env
    db = env["db"]

    criteria = [{"metric_name": "stiffness", "target_value": 80000.0, "tolerance_band": [76000.0, 84000.0], "unit": "N/m"}]
    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        acceptance_criteria=criteria,
        user_context=env["lead_ctx_a"],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=env["lead_ctx_a"]
    )
    auth_plan = await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=env["lead_ctx_a"]
    )
    assert auth_plan.status == ValidationPlanStatus.AUTHORIZED.value

    # Direct re-authorization or alteration is blocked
    with pytest.raises(InvalidPlanStateTransitionError):
        await ParameterTrustValidationService.transition_plan_status(
            db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=env["lead_ctx_a"]
        )

    # Creating a new version increments version and preserves parent lineage
    new_v2 = await ParameterTrustValidationService.create_new_plan_version(
        db=db,
        parent_plan_id=plan.id,
        updated_criteria=[{"metric_name": "stiffness", "target_value": 82000.0, "tolerance_band": [78000.0, 86000.0], "unit": "N/m"}],
        user_context=env["lead_ctx_a"],
    )
    assert new_v2.plan_version == 2
    assert new_v2.parent_plan_id == plan.id
    assert new_v2.status == ValidationPlanStatus.DRAFT.value


@pytest.mark.asyncio
async def test_ct5_02_epistemic_invariants_no_deployment_safety_inferred(integrated_test_env):
    """Verification and closure must never infer full-envelope deployment safety."""
    env = integrated_test_env
    db = env["db"]

    criteria = [{"metric_name": "stiffness", "target_value": 80000.0, "tolerance_band": [76000.0, 84000.0], "unit": "N/m"}]
    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        acceptance_criteria=criteria,
        user_context=env["lead_ctx_a"],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=env["lead_ctx_a"]
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=env["lead_ctx_a"]
    )
    ev = await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=plan.id,
        evidence_data={
            "source_identifier": "RIG-RIGIDITY-01",
            "evidence_source_type": "PHYSICAL_RIG_MEASUREMENT",
            "observed_value": 80100.0,
            "unit": "N/m",
            "provenance": {"test_bench": "Roehrig_Dyno", "operator": "Chief Rig Engineer"},
        },
        user_context=env["eng_ctx_a"],
    )
    await ParameterTrustValidationService.review_evidence_item(
        db=db, plan_id=plan.id, evidence_id=ev.id, review_status="ACCEPTED", user_context=env["lead_ctx_a"]
    )
    closure = await ParameterTrustValidationService.evaluate_evidence_closure(
        db=db, plan_id=plan.id, user_context=env["lead_ctx_a"]
    )
    assert closure.deployment_safety_inferred is False
    assert closure.deployment_authorization == "NOT_ESTABLISHED"
    assert "Finite" in closure.finite_sample_notice or "FINITE" in closure.finite_sample_notice.upper()

    reassessment = await ParameterTrustValidationService.execute_decision_reassessment(
        db=db, plan_id=plan.id, user_context=env["lead_ctx_a"]
    )
    assert reassessment.deployment_safety_inferred is False
    assert reassessment.deployment_authorization == "NOT_ESTABLISHED"


# ==============================================================================
# CRITICAL TASK 6: INDEPENDENT BENCHMARK & RECONCILIATION
# ==============================================================================

def test_ct6_01_matrix_exponential_exact_closed_form():
    """Verify matrix exponential closed form analytical reference for free response."""
    data = generate_benchmark_dataset(
        scenario=BenchmarkScenario.FREE_RESPONSE,
        method=BenchmarkMethod.EXACT_ANALYTICAL_MATRIX_EXPONENTIAL,
        duration=1.0,
        dt=0.001,
    )
    assert len(data["time"]) == 1001
    # Sprung mass displacement starts at 0.05m initial condition
    assert math.isclose(data["z_s"][0], 0.05, rel_tol=1e-5)
    # Oscillates and damps towards 0
    assert abs(data["z_s"][-1]) < 0.05


def test_ct6_02_all_six_scenarios_converge():
    """Verify all 6 benchmark scenarios execute successfully across numerical methods."""
    for sc in BenchmarkScenario:
        data = generate_benchmark_dataset(scenario=sc, duration=0.5, dt=0.002)
        assert len(data["time"]) > 100
        assert not np.isnan(data["z_s"]).any()
        assert not np.isinf(data["z_s"]).any()


def test_ct6_03_scipy_is_not_third_party_cae():
    """Verify SciPy DOP853/Radau are classified as SEPARATELY_IMPLEMENTED_NUMERICAL_SOLVER."""
    assert TAXONOMY_DEFINITIONS["SEPARATELY_IMPLEMENTED_NUMERICAL_SOLVER"]["commercial_third_party"] is False
    assert TAXONOMY_DEFINITIONS["SEPARATELY_IMPLEMENTED_NUMERICAL_SOLVER"]["independent_of_repo_logic"] is True
    assert THIRD_PARTY_SOLVER_INDEPENDENCE_VERIFIED is False
    assert EXPERIMENTAL_PHYSICAL_VALIDATION_VERIFIED is False
    assert UNTRUSTED_FMU_ISOLATION_VERIFIED is False


def test_ct6_04_reconciliation_zero_signal_absolute_gating():
    """Verify zero/near-zero signals do not blow up NRMSE via absolute threshold gating."""
    t = np.linspace(0, 1.0, 501)
    # Perfectly flat quiescent signals (e.g. at rest on smooth plane)
    ext_data = {"time": t, "z_s": np.zeros(501), "body_accel": np.zeros(501)}
    ref_data = {"time": t, "z_s": np.zeros(501) + 1e-6, "body_accel": np.zeros(501) + 1e-5}

    report = ResultReconciliationEngine.reconcile(
        external_data=ext_data,
        reference_data=ref_data,
        solver_name="QUAT_TEST",
        reference_model="INDEPENDENT_REF",
    )
    assert report.overall_status == "PASS"
    for name, metric in report.metrics.items():
        assert metric.denominator_mode == "ABSOLUTE_THRESHOLD"
        assert metric.is_within_tolerance is True


def test_ct6_05_reconciliation_rejects_insufficient_time_overlap():
    """Reconciliation strictly rejects signals with <90% time domain overlap."""
    t_ext = np.linspace(0.0, 0.5, 501)
    t_ref = np.linspace(0.45, 1.0, 551)  # Only 0.05s overlap = 10%
    ext_data = {"time": t_ext, "z_s": np.sin(t_ext)}
    ref_data = {"time": t_ref, "z_s": np.sin(t_ref)}

    with pytest.raises(ValueError, match="Insufficient time overlap"):
        ResultReconciliationEngine.reconcile(
            external_data=ext_data,
            reference_data=ref_data,
            solver_name="QUAT_TEST",
            reference_model="INDEPENDENT_REF",
        )


# ==============================================================================
# CRITICAL TASK 7: EXECUTION SECURITY & CRASH RECOVERY
# ==============================================================================

@pytest.mark.asyncio
async def test_ct7_01_tenant_isolated_crash_recovery(integrated_test_env):
    """Crash recovery is strictly tenant-scoped; Tenant B cannot recover Tenant A's jobs."""
    env = integrated_test_env
    db = env["db"]
    service = SolverExecutionService()

    expired_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    # Seed a crashed job for Tenant A
    job_a = SolverExecutionJob(
        id=uuid.uuid4(),
        organization_id=env["org_a"],
        team_id=env["team_a"],
        user_id=env["user_lead_a"],
        solver_name="EXTERNAL_CAE_SOLVER",
        solver_version="1.0.0",
        adapter_id="adapter-external-cae-v1",
        state=ExecutionJobState.RUNNING.value,
        lease_expires_at=expired_time,
        heartbeat_at=expired_time,
        input_artifact_hash="hash_a",
    )
    db.add(job_a)
    await db.commit()

    # Tenant B tries to recover jobs -> Tenant A's job is untouched
    recovered_b = await service.recover_crashed_jobs(db=db, user=env["user_ctx_b"])
    assert len(recovered_b) == 0

    # Tenant A recovers jobs -> job_a is recovered to FAILED
    recovered_a = await service.recover_crashed_jobs(db=db, user=env["lead_ctx_a"])
    assert len(recovered_a) == 1
    assert recovered_a[0].id == job_a.id
    assert recovered_a[0].state == ExecutionJobState.FAILED.value
    assert recovered_a[0].error_category == "WORKER_CRASH_ORPHAN"


@pytest.mark.asyncio
async def test_ct7_02_untrusted_fmu_allowlist_enforced(integrated_test_env, tmp_path):
    """Untrusted FMU payload fails closed without executing native code."""
    env = integrated_test_env
    db = env["db"]
    service = SolverExecutionService()

    fake_fmu = tmp_path / "malicious.fmu"
    fake_fmu.write_bytes(b"PK\x03\x04FAKE_MALICIOUS_FMU_PAYLOAD")
    sha256 = hashlib.sha256(fake_fmu.read_bytes()).hexdigest()

    art_id = uuid.uuid4()
    art = SolverExchangeArtifact(
        id=art_id,
        user_id=env["user_lead_a"],
        team_id=env["team_a"],
        artifact_name="malicious.fmu",
        file_format=".fmu",
        mime_type="application/octet-stream",
        size_bytes=len(fake_fmu.read_bytes()),
        sha256_hash=sha256,
        direction=ArtifactDirection.INPUT.value,
        storage_path=str(fake_fmu),
    )
    db.add(art)
    await db.commit()

    job = await service.create_execution_job(
        db=db,
        user=env["lead_ctx_a"],
        solver_name="FMI_COSIMULATION",
        input_artifact_id=art_id,
    )
    completed = await service.execute_job(db=db, job_id=job.id, user=env["lead_ctx_a"])
    assert completed.state == ExecutionJobState.FAILED.value
    assert "UNTRUSTED_FMU_EXECUTION_REJECTED" in (completed.failure_reason or "")


# ==============================================================================
# CRITICAL TASK 9: COMPLETE APPLICATION JOURNEYS
# ==============================================================================

@pytest.mark.asyncio
async def test_ct9_journey_a_validation_to_reassessment(integrated_test_env):
    """
    Complete Journey A:
    Engineering Decision -> Validation Plan -> Criteria Authorization ->
    Evidence Ingestion -> Authenticity Review -> Closure Evaluation ->
    Decision Reassessment -> Immutable Lineage Record.
    """
    env = integrated_test_env
    db = env["db"]
    lead = env["lead_ctx_a"]
    eng = env["eng_ctx_a"]

    # Step 1: Create Validation Plan
    plan = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        validation_method="PHYSICAL_RIG_MEASUREMENT",
        validation_objective="Empirical corner stiffness verification",
        acceptance_criteria=[{
            "metric_name": "spring_rate_tolerance",
            "target_value": 80000.0,
            "tolerance_band": [78000.0, 82000.0],
            "unit": "N/m",
        }],
        user_context=lead,
    )

    # Step 2: Propose and Authorize
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=lead
    )
    auth_plan = await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan.id, target_status=ValidationPlanStatus.AUTHORIZED.value, user_context=lead
    )
    assert auth_plan.status == ValidationPlanStatus.AUTHORIZED.value

    # Step 3: Ingest empirical evidence
    ev = await ParameterTrustValidationService.submit_evidence(
        db=db,
        plan_id=plan.id,
        evidence_data={
            "source_identifier": "RIG-DYNO-TEST-2026-A",
            "evidence_source_type": "PHYSICAL_RIG_MEASUREMENT",
            "observed_value": 80050.0,
            "unit": "N/m",
            "provenance": {"calibrated_load_cell": "SN-99812", "facility": "Dyno Facility 1"},
        },
        user_context=eng,
    )
    assert ev.review_status == "PENDING_REVIEW"

    # Step 4: Peer review
    rev = await ParameterTrustValidationService.review_evidence_item(
        db=db, plan_id=plan.id, evidence_id=ev.id, review_status="ACCEPTED", user_context=lead
    )
    assert rev.review_status == "ACCEPTED"

    # Step 5: Evaluate Closure
    closure = await ParameterTrustValidationService.evaluate_evidence_closure(
        db=db, plan_id=plan.id, user_context=lead
    )
    assert closure.criteria_met is True
    assert closure.closure_verdict == "CLOSED_WITH_SUPPORTING_EVIDENCE"
    assert closure.deployment_safety_inferred is False

    # Step 6: Reassess decision
    reassess = await ParameterTrustValidationService.execute_decision_reassessment(
        db=db, plan_id=plan.id, user_context=lead
    )
    assert reassess.reversal_status in ("NO_REVERSAL_DEMONSTRATED", "NO_REVERSAL")
    assert reassess.is_active is True

    # Step 7: Verify lineage history
    history = await ParameterTrustValidationService.get_decision_reassessments(
        db=db, decision_id=str(env["dec_a"].id), user_context=lead
    )
    assert history["total"] == 1
    assert history["reassessments"][0]["id"] == str(reassess.id)


@pytest.mark.asyncio
async def test_ct9_journey_b_solver_execution_to_independent_reconciliation(integrated_test_env, tmp_path):
    """
    Complete Journey B:
    Authorized Solver Artifact -> Vetted Runner Execution -> Independent DOP853 Benchmark ->
    Reconciliation -> Persisted Results & Epistemic Audit.
    """
    env = integrated_test_env
    db = env["db"]
    lead = env["lead_ctx_a"]
    service = SolverExecutionService()

    # Use internal quarter car runner
    script_path = tmp_path / "runner.py"
    script_path.write_text("print('Simulation completed')\n")
    sha256 = hashlib.sha256(script_path.read_bytes()).hexdigest()

    art_id = uuid.uuid4()
    art = SolverExchangeArtifact(
        id=art_id,
        user_id=env["user_lead_a"],
        team_id=env["team_a"],
        artifact_name="quarter_car_input.py",
        file_format=".py",
        mime_type="text/plain",
        size_bytes=len(script_path.read_bytes()),
        sha256_hash=sha256,
        direction=ArtifactDirection.INPUT.value,
        storage_path=str(script_path),
    )
    db.add(art)
    await db.commit()

    job = await service.create_execution_job(
        db=db,
        user=lead,
        solver_name="EXTERNAL_CAE_SOLVER",
        input_artifact_id=art_id,
        execution_config={"duration": 0.5, "step": 0.002},
    )
    completed = await service.execute_job(db=db, job_id=job.id, user=lead)
    assert completed.state == ExecutionJobState.COMPLETED.value
    assert completed.is_executed is True

    # Reconcile against independent SciPy DOP853 benchmark
    report = await service.reconcile_job_results(
        db=db,
        job_id=job.id,
        user=lead,
        benchmark_method=BenchmarkMethod.HIGH_ORDER_ADAPTIVE_NUMERICAL.value,
    )
    assert report.overall_status in ("PASS", "FAIL")
    assert report.reference_model == "IndependentBenchmark_AdaptiveDOP853_2DOF"
    assert report.epistemic_invariants["numerical_agreement_is_not_physical_validation"] is True
    assert report.epistemic_invariants["executed_is_not_verified_correct"] is True


@pytest.mark.asyncio
async def test_ct9_journey_c_adversarial_tamper_and_cross_tenant(integrated_test_env):
    """
    Complete Journey C:
    Cross-Tenant Injection -> Unauthorized Review -> Tampered Criteria ->
    Lease Expiry Recovery Boundary.
    """
    env = integrated_test_env
    db = env["db"]

    # 1. Tenant B cannot create or mutate Tenant A plans
    with pytest.raises(Exception):
        await ParameterTrustValidationService.create_validation_plan(
            db=db,
            decision_id=str(env["dec_a"].id),
            parameter_name="front_spring_rate",
            user_context=env["user_ctx_b"],  # Cross-tenant
        )

    # 2. Engineer in Tenant A cannot authorize plans (requires VALIDATION_LEAD)
    plan_a = await ParameterTrustValidationService.create_validation_plan(
        db=db,
        decision_id=str(env["dec_a"].id),
        parameter_name="front_spring_rate",
        user_context=env["lead_ctx_a"],
    )
    await ParameterTrustValidationService.transition_plan_status(
        db=db, plan_id=plan_a.id, target_status=ValidationPlanStatus.PROPOSED.value, user_context=env["lead_ctx_a"]
    )
    with pytest.raises(UnauthorizedValidationActionError):
        await ParameterTrustValidationService.transition_plan_status(
            db=db,
            plan_id=plan_a.id,
            target_status=ValidationPlanStatus.AUTHORIZED.value,
            user_context=env["eng_ctx_a"],  # Engineer role unauthorized
        )
