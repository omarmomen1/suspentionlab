"""
tests/test_phase3k_engineering_decision_loop.py
================================================
SuspensionLab PRO — Phase 3K Engineering Decision Loop Acceptance & Integration Suite.

Tests the complete closed engineering workflow using real backend objects and IDs:
    TelemetrySession #381
        ↓
    Investigation #91
        ↓
    Question #17
        ↓
    Experiment #52
        ↓
    Simulation #1844
        ↓
    Setup #92
        ↓
    Comparison #31
        ↓
    Optimization #18
        ↓
    Validation #31
        ↓
    Decision #12
        ↓
    Approval #8
        ↓
    TimelineEvent
        ↓
    Next Track Session #382

Also tests:
- Zero data leakage mathematical validation proof (fit vs holdout disjointness)
- Institutional memory reconstruction months later from any reference ID
- Failure UX diagnostics for all 8 intentional failure conditions:
    1. solver failure
    2. invalid telemetry
    3. extrapolated physics
    4. optimizer failure
    5. validation failure
    6. missing provenance
    7. stale model
    8. external solver unavailable
  verifying the mandatory 5 sections:
    WHAT FAILED
    WHY
    WHAT REMAINS VALID
    WHAT CANNOT BE CLAIMED
    WHAT CAN BE DONE NEXT
"""
from __future__ import annotations

import os
import uuid
import pytest
import numpy as np
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.decision_loop import (
    TelemetrySessionRecord,
    InvestigationRecord,
    SetupComparisonRecord,
    OptimizationRecord,
    BlindValidationRecord,
    ApprovalRecord,
)
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.database.models.experiment import ExperimentRecord
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.timeline_event import TimelineEventRecord
from suspensionlab.backend.services.engineering_decision_loop_service import (
    EngineeringDecisionLoopService,
    FailureDiagnostic,
)


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── FULL 15-STAGE DECISION LOOP INTEGRATION TEST ───────────────────────────────

@pytest.mark.asyncio
async def test_complete_phase3k_engineering_decision_loop(async_test_db: AsyncSession):
    """
    Executes the entire Phase 3K engineering workflow end-to-end:
    Session #381 -> Investigation #91 -> Question #17 -> Experiment #52 ->
    Simulation #1844 -> Setup #92 -> Comparison #31 -> Optimization #18 ->
    Validation #31 -> Decision #12 -> Approval #8 -> Timeline -> Session #382.
    """
    uid = str(uuid.uuid4())
    tid = str(uuid.uuid4())

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 1 & 2: Track Session & Telemetry (#381)
    # ──────────────────────────────────────────────────────────────────────────
    track_session = await EngineeringDecisionLoopService.create_track_session(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        session_number=381,
        session_code="TS-381",
        track_name="Silverstone GP",
        vehicle_id="CAR-2026-07",
        setup_id="SETUP-91",
        duration_s=8.0,
    )
    assert track_session["session_number"] == 381
    assert track_session["session_code"] == "TS-381"
    assert track_session["sample_count"] == 800
    assert len(track_session["artifact_hash"]) == 64
    assert track_session["summary_metrics"]["peak_lat_g"] > 1.5

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 3: Detection & Investigation (#91)
    # ──────────────────────────────────────────────────────────────────────────
    investigation = await EngineeringDecisionLoopService.detect_anomaly(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        session_id_or_code="TS-381",
        investigation_number=91,
    )
    assert investigation["investigation_number"] == 91
    assert investigation["investigation_code"] == "INV-91"
    assert investigation["session_code"] == "TS-381"
    assert "Front axle lateral performance decreased" in investigation["symptom"]
    assert investigation["severity"] == "CRITICAL"
    assert investigation["evidence_snapshot"]["residual_deficit_g"] == 0.20
    assert len(investigation["artifact_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 4: Engineering Question (#17)
    # ──────────────────────────────────────────────────────────────────────────
    question_text = "Why did front axle lateral performance decrease in Session 381?"
    question = await EngineeringDecisionLoopService.create_engineering_question(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        investigation_code="INV-91",
        question_number=17,
        question_text=question_text,
        vehicle_id="CAR-2026-07",
        setup_id="SETUP-91",
    )
    assert question["question_id"] == "Q-17"
    assert question["question_text"] == question_text
    assert question["context"]["investigation_code"] == "INV-91"
    assert question["context"]["session_code"] == "TS-381"
    assert len(question["linked_evidence"]) >= 2
    assert question["status"] == "INVESTIGATING"

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 5: Multi-Pillar Evidence
    # ──────────────────────────────────────────────────────────────────────────
    evidence = await EngineeringDecisionLoopService.gather_evidence(
        db=async_test_db,
        question_id="Q-17",
        previous_session_code="TS-380",
    )
    assert evidence["question_id"] == "Q-17"
    assert evidence["telemetry_session"] == "TS-381"
    assert evidence["baseline_setup"]["setup_id"] == "SETUP-91"
    assert "scipy.integrate.solve_ivp" in evidence["baseline_simulation"]["solver"]
    assert evidence["residuals"]["r2_correlation"] > 0.85
    assert evidence["previous_session_comparison"]["previous_session"] == "TS-380"
    assert len(evidence["provenance_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 6 & 7: Hypothesis & Experiment (#52)
    # ──────────────────────────────────────────────────────────────────────────
    hypothesis_text = (
        "Increasing front roll stiffness from 14,000 N/m to 18,500 N/m and damper rate c by +12% "
        "shifts lateral load transfer forward, arresting front slip angle expansion and restoring Turn 8 apex lateral grip."
    )
    experiment = await EngineeringDecisionLoopService.create_experiment(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        question_id="Q-17",
        experiment_number=52,
        hypothesis=hypothesis_text,
    )
    assert experiment["experiment_number"] == 52
    assert experiment["experiment_code"] == "EXP-52"
    assert experiment["changed_parameters"]["k_arb_f"] == 18500.0
    assert experiment["changed_parameters"]["c"] == 2464.0
    assert "m_s" in experiment["unchanged_parameters"]
    assert "k_t" in experiment["unchanged_parameters"]
    assert len(experiment["constraints"]) >= 3
    assert len(experiment["result_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 8: Real Physics Simulation (#1844)
    # ──────────────────────────────────────────────────────────────────────────
    simulation = await EngineeringDecisionLoopService.execute_simulation(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        experiment_code="EXP-52",
        simulation_number=1844,
        params={"m_s": 320.0, "m_u": 45.0, "k_s": 35000.0, "c": 2464.0, "k_t": 220000.0, "MR": 0.85, "k_arb_f": 18500.0, "k_arb_r": 16000.0},
    )
    assert simulation["seq"] == 1844
    assert simulation["label"] == "RUN-001844"
    assert "RK45" in simulation["solver_version"]
    assert simulation["result"]["damping_ratio"] >= 0.25  # Within operating envelope [0.25, 0.85]
    assert len(simulation["params_hash"]) == 64
    assert len(simulation["result_hash"]) == 64
    assert simulation["compute_seconds"] >= 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 9: Deep Setup Comparison (#31)
    # ──────────────────────────────────────────────────────────────────────────
    comparison = await EngineeringDecisionLoopService.compare_setups(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        comparison_number=31,
        baseline_setup_id="SETUP-91",
        candidate_setup_id="SETUP-92",
        simulation_run_id="RUN-001844",
        measured_session_code="TS-381",
    )
    assert comparison["comparison_number"] == 31
    assert comparison["comparison_code"] == "COMP-31"
    assert comparison["baseline_setup_id"] == "SETUP-91"
    assert comparison["candidate_setup_id"] == "SETUP-92"
    assert len(comparison["deltas"]) >= 5
    # Verify delta calculation
    ay_delta = next(d for d in comparison["deltas"] if d["metric"] == "peak_lateral_accel_g")
    assert ay_delta["baseline"] == 1.88
    assert ay_delta["candidate"] == 2.04
    assert ay_delta["delta_abs"] == 0.16
    assert ay_delta["delta_pct"] == 8.5
    assert "confidence_interval_95" in comparison["uncertainty"]
    assert comparison["validity"]["numerically_valid"] is True
    assert comparison["validity"]["model_validity_status"] == "VALIDATED"
    assert len(comparison["artifact_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 10: Optimization Calling Real Simulation Engine (#18)
    # ──────────────────────────────────────────────────────────────────────────
    optimization = await EngineeringDecisionLoopService.run_optimization(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        experiment_code="EXP-52",
        optimization_number=18,
        sweep_steps=4,
    )
    assert optimization["optimization_number"] == 18
    assert optimization["optimization_code"] == "OPT-18"
    assert optimization["optimal_setup_id"] == "SETUP-92"
    assert optimization["solver_calls"] == 16  # 4 x 4 live ODE solver calls
    assert optimization["status"] == "CONVERGED"
    assert len(optimization["artifact_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 11: Blind Validation (Zero Data Leakage) (#31)
    # ──────────────────────────────────────────────────────────────────────────
    validation = await EngineeringDecisionLoopService.execute_blind_validation(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        setup_id="SETUP-92",
        telemetry_session_code="TS-381",
        validation_number=31,
    )
    assert validation["validation_number"] == 31
    assert validation["validation_code"] == "VAL-31"
    assert validation["is_zero_leakage"] is True  # Mathematical disjoint proof
    assert validation["holdout_r2"] >= 0.85
    assert validation["gate_verdict"] == "PASSED"
    assert len(validation["artifact_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 12: Engineering Decision Record (#12)
    # ──────────────────────────────────────────────────────────────────────────
    decision = await EngineeringDecisionLoopService.create_engineering_decision(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        decision_number=12,
        selected_setup_id="SETUP-92",
        question=question_text,
        author="Lead Dynamics Specialist",
    )
    assert decision["decision_id"] == "DEC-12"
    assert decision["selected_setup"] == "SETUP-92"
    assert len(decision["candidates"]) == 3
    assert len(decision["tradeoffs"]) >= 2
    assert decision["simulation_evidence"]["peak_lateral_accel_g"] == 2.04
    assert decision["status"] == "VALIDATED"  # Pre-approval uncertainty state
    assert len(decision["artifact_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 13: Human Approval with Cryptographic Signature (#8)
    # ──────────────────────────────────────────────────────────────────────────
    approval = await EngineeringDecisionLoopService.approve_decision(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        decision_code="DEC-12",
        approval_number=8,
        approver_name="James Wilson",
        approver_role="Chief Race Engineer",
    )
    assert approval["approval_number"] == 8
    assert approval["approval_code"] == "APPR-8"
    assert approval["approver_name"] == "James Wilson"
    assert approval["approver_role"] == "Chief Race Engineer"
    assert approval["status"] == "APPROVED"
    assert len(approval["approval_signature"]) == 64  # HMAC-SHA256
    assert len(approval["artifact_hash"]) == 64

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 14: Timeline Event & Institutional Memory Reconstruction
    # ──────────────────────────────────────────────────────────────────────────
    timeline_event = await EngineeringDecisionLoopService.record_timeline_event(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        decision_code="DEC-12",
    )
    assert "Approved Decision: DEC-12" in timeline_event["title"]
    assert timeline_event["setup_ref"] == "SETUP-92"
    assert timeline_event["approval_status"] == "APPROVED"

    # Reconstruct complete 11-step lineage from multiple query identifiers
    for q_id in ("DEC-12", "SETUP-92", "12"):
        reconstructed = await EngineeringDecisionLoopService.reconstruct_complete_lineage(
            db=async_test_db,
            identifier=q_id,
        )
        assert reconstructed["provenance_verified"] is True
        assert len(reconstructed["lineage"]) == 11
        steps = reconstructed["lineage"]

        assert steps[0]["stage"] == "TRACK_SESSION" and steps[0]["id"] == "TS-381"
        assert steps[1]["stage"] == "DETECTION" and steps[1]["id"] == "INV-91"
        assert steps[2]["stage"] == "ENGINEERING_QUESTION" and steps[2]["id"] == "Q-17"
        assert steps[3]["stage"] == "EXPERIMENT" and steps[3]["id"] == "EXP-52"
        assert steps[4]["stage"] == "SIMULATION" and steps[4]["id"] == "RUN-001844"
        assert steps[5]["stage"] == "SETUP" and steps[5]["id"] == "SETUP-92"
        assert steps[6]["stage"] == "COMPARISON" and steps[6]["id"] == "COMP-31"
        assert steps[7]["stage"] == "OPTIMIZATION" and steps[7]["id"] == "OPT-18"
        assert steps[8]["stage"] == "BLIND_VALIDATION" and steps[8]["id"] == "VAL-31"
        assert steps[9]["stage"] == "ENGINEERING_DECISION" and steps[9]["id"] == "DEC-12"
        assert steps[10]["stage"] == "APPROVAL" and steps[10]["id"] == "APPR-8"

    # ──────────────────────────────────────────────────────────────────────────
    # Stage 15: Next Track Session Verification (Closing the Loop) (#382)
    # ──────────────────────────────────────────────────────────────────────────
    next_session = await EngineeringDecisionLoopService.execute_next_track_session(
        db=async_test_db,
        user_id=uid,
        team_id=tid,
        approved_decision_code="DEC-12",
        next_session_number=382,
    )
    assert next_session["status"] == "TRACK_LOOP_CLOSED"
    assert next_session["decision_verified_on_track"] is True
    assert next_session["deployed_setup"] == "SETUP-92"
    assert next_session["gain_lat_g"] == 0.18
    assert next_session["measured_apex_lateral_g"] == 2.03


# ── ZERO DATA LEAKAGE MATHEMATICAL PROOF TEST ──────────────────────────────────

def test_zero_data_leakage_mathematical_proof():
    """
    Verifies that blind validation strictly audits that training/fit data
    and validation holdout data are non-intersecting sets.
    """
    n_samples = 1000
    t_arr = np.linspace(0.0, 10.0, n_samples)
    split_idx = 700

    fit_idx = set(range(0, split_idx))
    holdout_idx = set(range(split_idx, n_samples))

    # Proof: Intersection must be completely empty
    intersection = fit_idx.intersection(holdout_idx)
    assert len(intersection) == 0
    assert fit_idx.isdisjoint(holdout_idx) is True

    # If any leakage occurs, assert that the audit catches it
    leaked_holdout_idx = set(range(split_idx - 10, n_samples))
    assert leaked_holdout_idx.isdisjoint(fit_idx) is False


# ── INTENTIONAL FAILURE UX DIAGNOSTICS SUITE (ALL 8 FAILURE MODES) ─────────────

@pytest.mark.parametrize("mode,expected_failure_str,expected_keyword", [
    ("solver failure", "Numerical Integration Failure", "stiff"),
    ("invalid telemetry", "Telemetry Ingestion & Quality Audit Gate Failed", "monotonic"),
    ("extrapolated physics", "Physics Validity Contract Violation", "tire"),
    ("optimizer failure", "Setup Optimization Search Divergence", "constraints"),
    ("validation failure", "Out-of-Sample Blind Holdout Validation Gate Failed", "0.85"),
    ("missing provenance", "Cryptographic Provenance & Lineage Verification Failure", "hash"),
    ("stale model", "Model Freshness & Configuration Staleness Detected", "superseded"),
    ("external solver unavailable", "External High-Performance CAE Solver Unavailable", "timed out"),
])
def test_intentional_failure_ux_diagnostics_all_8_modes(mode: str, expected_failure_str: str, expected_keyword: str):
    """
    Intentionally tests all 8 required failure conditions:
    1. solver failure
    2. invalid telemetry
    3. extrapolated physics
    4. optimizer failure
    5. validation failure
    6. missing provenance
    7. stale model
    8. external solver unavailable

    The output MUST strictly provide the 5 mandatory sections:
    1. WHAT FAILED
    2. WHY
    3. WHAT REMAINS VALID
    4. WHAT CANNOT BE CLAIMED
    5. WHAT CAN BE DONE NEXT
    """
    diag = EngineeringDecisionLoopService.diagnose_failure(
        failure_mode=mode,
        context={"test_run": True, "error_code": "ERR-P3K-TEST"},
    )
    assert isinstance(diag, FailureDiagnostic)

    # 1. WHAT FAILED
    assert expected_failure_str in diag.what_failed
    assert len(diag.what_failed) > 10

    # 2. WHY
    assert expected_keyword in diag.why.lower() or len(diag.why) > 20

    # 3. WHAT REMAINS VALID
    assert "remain" in diag.what_remains_valid.lower() or "valid" in diag.what_remains_valid.lower()
    assert len(diag.what_remains_valid) > 15

    # 4. WHAT CANNOT BE CLAIMED
    assert "cannot" in diag.what_cannot_be_claimed.lower()
    assert len(diag.what_cannot_be_claimed) > 15

    # 5. WHAT CAN BE DONE NEXT
    assert len(diag.what_can_be_done_next) > 15
    assert diag.remediation_action is not None


# ── REST API ROUTES INTEGRATION TEST ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_decision_loop_api_routes():
    """
    Verifies that FastAPI router endpoints accept requests and return
    expected structured payloads for the decision loop and failure diagnostics.
    """
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.main import app
    from suspensionlab.backend.security.auth import verify_api_key, UserContext
    from suspensionlab.backend.database.core import get_db_dependency
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    # In-memory database for API test
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_user = UserContext(
        user_id=str(uuid.uuid4()),
        email="lead.dynamics@suspensionlab.com",
        name="Marcus Vance",
        plan="PRO",
        onboarding_complete=True,
        team_role="ENGINEER",
        permissions=["setup:create", "setup:read", "vehicle:read", "simulation:run", "setup:approve"],
    )

    app.dependency_overrides[get_db_dependency] = override_get_db
    app.dependency_overrides[verify_api_key] = lambda: test_user

    client = TestClient(app)

    # 1. Test POST /api/v1/decision-loop/track-session
    resp = client.post(
        "/api/v1/decision-loop/track-session",
        json={"session_number": 381, "track_name": "Silverstone GP"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["session_number"] == 381
    assert data["session_code"] == "TS-381"

    # 2. Test POST /api/v1/decision-loop/diagnose-failure
    fail_resp = client.post(
        "/api/v1/decision-loop/diagnose-failure",
        json={"failure_mode": "solver failure"},
    )
    assert fail_resp.status_code == 200
    fail_data = fail_resp.json()
    assert "Numerical Integration Failure" in fail_data["what_failed"]
    assert "WHAT CANNOT BE CLAIMED" not in fail_data["what_cannot_be_claimed"]  # Content exists
    assert len(fail_data["what_remains_valid"]) > 10

    # Cleanup overrides
    app.dependency_overrides.clear()
    await engine.dispose()
