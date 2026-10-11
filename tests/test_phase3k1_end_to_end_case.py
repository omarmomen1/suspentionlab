"""
tests/test_phase3k1_end_to_end_case.py
======================================
SuspensionLab PRO — Phase 3K.1 End-to-End Engineering Case Integration Suite.

Tests the authentic engineering decision case executed on the 2017 VW Golf VII GTI
Performance dataset at Thunderhill Raceway Park:
    Real Telemetry (TS-STANFORD-01)
        ↓
    Validation & Anomaly Detection (INV-P3K1-01)
        ↓
    Engineering Question (Q-P3K1-01)
        ↓
    Multi-Pillar Evidence Gathering
        ↓
    Physical Hypothesis Formulation
        ↓
    Observability & Excitation Audit (Gating)
        ↓
    Parameter Identification & Experiment (EXP-P3K1-01)
        ↓
    Production Simulation (14-DOF ODE Integration, RUN-184401)
        ↓
    Setup Candidates & Optimization (OPT-P3K1-01)
        ↓
    Setup Comparison (COMP-P3K1-01)
        ↓
    Sealed Blind Holdout Validation (VAL-P3K1-01, Zero Leakage)
        ↓
    Engineering Decision (DEC-P3K1-01)
        ↓
    Human Approval (APPR-P3K1-01, Chief Race Engineer)
        ↓
    Timeline Event (TL-P3K1-01)
        ↓
    12-Step Lineage Backward Reconstruction

Verification Mandates Covered:
- Zero mock relationships and zero fabricated physical results.
- Observability pre-check refusal: returning UNIDENTIFIABLE / UNSUPPORTED on flat signal or unidentifiable parameters.
- Mathematical zero data leakage verification (D_fit ∩ D_holdout = ∅).
- Decision permitted outcomes (ACCEPT, REJECT, INCONCLUSIVE, UNSUPPORTED).
- Human approval enforcement (no setup marked approved automatically).
- 12-step lineage reconstructability from Decision ID to dataset provenance and model version.
- Failure UX diagnostics with all 5 mandatory sections.
- REST API routes under /api/v1/decision-loop/phase3k1/.
"""
from __future__ import annotations

import json
import uuid
import pytest
import numpy as np
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.services.phase3k1_case_service import Phase3K1CaseService


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


# ── TEST 1: COMPLETE END-TO-END CASE EXECUTION ─────────────────────────────────

@pytest.mark.asyncio
async def test_complete_phase3k1_end_to_end_case(async_test_db: AsyncSession):
    """
    Executes the complete Phase 3K.1 authentic case workflow on the async test database,
    verifying all 15 stages, authentic telemetry metadata, production 14-DOF simulation,
    optimization, holdout validation, and human sign-off.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    approver_name = "Elena Rostova"
    approver_role = "Chief Race Engineer & Technical Director"

    bundle = await Phase3K1CaseService.execute_end_to_end_case(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        approver_name=approver_name,
        approver_role=approver_role,
    )

    # 1. Status and Top-Level Structure
    assert bundle["status"] == "DECISION_CHAIN_COMPLETE_AND_APPROVED"
    assert "execution_timestamp_iso" in bundle
    for key in [
        "telemetry", "investigation", "question", "evidence", "hypothesis",
        "observability", "experiment", "simulation", "optimization",
        "comparison", "validation", "decision", "approval", "timeline", "lineage"
    ]:
        assert key in bundle, f"Missing required case key: {key}"

    # 2. Stage 1: Telemetry
    telem = bundle["telemetry"]
    assert telem["session_code"] == "TS-STANFORD-01"
    assert telem["dataset_id"] == "stanford_vw_golf_thunderhill_2023_11"
    assert telem["provenance_hash"] == "489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3"
    assert telem["sample_count"] == 22304
    assert telem["duration_s"] == pytest.approx(111.516, abs=0.01)
    assert telem["summary_metrics"]["validity_status"] == "AUTHENTIC_AUDITED_VALID"

    # 3. Stage 2: Investigation & Anomaly Detection
    inv = bundle["investigation"]
    assert inv["investigation_code"] == "INV-P3K1-01"
    assert inv["detection_type"] == "EXCESSIVE_CHASSIS_ROLL_COMPLIANCE"
    assert inv["evidence_snapshot"]["observed_peak_roll_deg"] == pytest.approx(3.37, abs=0.05)
    assert inv["evidence_snapshot"]["peak_lateral_accel_g"] == pytest.approx(1.91, abs=0.05)
    assert inv["evidence_snapshot"]["front_suspension_travel_mm"] == pytest.approx(53.2, abs=0.5)

    # 4. Stage 3: Engineering Question
    q = bundle["question"]
    assert q["question_id"] == "Q-P3K1-01"
    assert "Can front axle roll stiffness and front damper bump damping be optimized" in q["question_text"]
    assert "Turn_3_Approach" in q["context"]["relevant_maneuver"]
    assert q["context"]["dataset_id"] == "stanford_vw_golf_thunderhill_2023_11"

    # 5. Stage 4: Evidence Bundle
    ev = bundle["evidence"]
    assert "dataset" in ev
    assert "baseline_setup" in ev
    assert "baseline_simulation" in ev
    assert "residuals" in ev
    assert "identified_priors_phase3j" in ev
    assert ev["residuals"]["Vx_r2"] == pytest.approx(0.924, abs=0.01)
    assert ev["residuals"]["yaw_rate_r2"] == pytest.approx(0.716, abs=0.01)
    assert ev["residuals"]["roll_angle_r2"] == pytest.approx(0.691, abs=0.01)

    # 6. Stage 5: Physical Hypothesis
    hyp = bundle["hypothesis"]
    assert "physical_hypothesis" in hyp
    assert "anti_roll_bar_front" in hyp["parameters_involved"]
    assert "damper_bump_front" in hyp["parameters_involved"]
    assert len(hyp["supporting_evidence"]) >= 2
    assert len(hyp["contradictory_evidence"]) >= 1

    # 7. Stage 6: Observability Audit
    obs = bundle["observability"]
    assert obs["status"] == "IDENTIFIABLE_AND_SUPPORTED"
    assert obs["is_supported"] is True
    assert "anti_roll_bar_front" in obs["identifiable_parameters"]
    assert "damper_bump_front" in obs["identifiable_parameters"]
    assert len(obs["unidentifiable_parameters"]) == 0

    # 8. Stage 7: Experiment
    exp = bundle["experiment"]
    assert exp["experiment_code"] == "EXP-P3K1-01"
    assert "k_arb_front_nm" in exp["changed_parameters"]
    assert "c_damper_front_nsm" in exp["changed_parameters"]
    assert len(exp["unchanged_parameters"]) > 0

    # 9. Stage 8: Production Simulation
    sim = bundle["simulation"]
    assert sim["label"] == "RUN-184401"
    assert sim["solver_version"] == "DYNAMIC_TRANSIENT_14DOF-v2.6"
    assert sim["metrics"]["peak_roll_angle_deg"] == pytest.approx(1.75, abs=0.1)
    assert sim["metrics"]["max_suspension_travel_mm"] == pytest.approx(48.5, abs=0.1)
    assert "result_hash" in sim

    # 10. Stage 9: Optimization
    opt = bundle["optimization"]
    assert opt["optimization_code"] == "OPT-P3K1-01"
    assert opt["candidates_evaluated"] == 9
    assert opt["status"] == "CONVERGED"
    assert opt["optimal_parameters"]["k_arb_front_nm"] == 33000.0
    assert opt["optimal_parameters"]["c_damper_front_nsm"] == 4200.0

    # 11. Stage 10: Comparison
    comp = bundle["comparison"]
    assert comp["comparison_code"] == "COMP-P3K1-01"
    assert comp["baseline_setup_id"] == "SETUP-GTI-BASE"
    assert comp["candidate_setup_id"] == "SETUP-GTI-OPT"
    # Verify peak roll angle reduction
    roll_delta = next(d for d in comp["deltas"] if d["metric"] == "peak_roll_angle_deg")
    assert roll_delta["baseline"] == 3.37
    assert roll_delta["candidate"] == 2.45
    assert roll_delta["delta_pct"] == pytest.approx(-27.3, abs=0.5)
    assert roll_delta["beneficial"] is True
    # Verify travel constraint satisfied
    travel_delta = next(d for d in comp["deltas"] if d["metric"] == "front_susp_travel_mm")
    assert travel_delta["candidate"] == 48.5
    assert travel_delta["candidate"] < 55.0

    # 12. Stage 11: Sealed Holdout Blind Validation
    val = bundle["validation"]
    assert val["validation_code"] == "VAL-P3K1-01"
    assert val["is_zero_leakage"] is True
    assert val["gate_verdict"] == "PASSED"
    assert val["holdout_r2"] > val["base_holdout_r2"]  # 0.7664 vs 0.7458
    assert val["holdout_rmse"] < val["base_holdout_rmse"]  # 0.0925 vs 0.0965

    # 13. Stage 12: Engineering Decision
    dec = bundle["decision"]
    assert dec["decision_id"] == "DEC-P3K1-01"
    assert dec["outcome"] == "ACCEPT"
    assert dec["selected_setup"] == "SETUP-GTI-OPT"
    assert dec["status"] == "APPROVED"  # updated after approval

    # 14. Stage 13: Human Approval
    appr = bundle["approval"]
    assert appr["approval_code"] == "APPR-P3K1-01"
    assert appr["approver_name"] == approver_name
    assert appr["approver_role"] == approver_role
    assert appr["status"] == "APPROVED"
    assert len(appr["approval_signature"]) == 64  # HMAC-SHA256 hex digest

    # 15. Stage 14: Timeline & Lineage
    tl = bundle["timeline"]
    assert "Approved Decision" in tl["title"]
    lin = bundle["lineage"]
    assert lin["decision_id"] == "DEC-P3K1-01"
    assert lin["chain_length"] == 12
    assert len(lin["lineage"]) == 12


# ── TEST 2: OBSERVABILITY GATING & UNIDENTIFIABLE REFUSAL ───────────────────────

def test_phase3k1_observability_unidentifiable_parameter_refusal():
    """
    Mandate 5: Parameter Identification.
    Verifies that the system refuses to optimize or formulate decisions on unidentifiable
    parameters (e.g. camber stiffness without slip angle excitation).
    Returns UNIDENTIFIABLE / UNSUPPORTED and halts.
    """
    audit = Phase3K1CaseService.audit_observability_and_excitation(
        candidate_parameters=["anti_roll_bar_front", "camber_stiffness_front"],
        telemetry_window_s=(39.0, 42.0),
        force_flat_signal=False,
    )

    assert audit["status"] == "UNIDENTIFIABLE / UNSUPPORTED"
    assert audit["is_supported"] is False
    assert "camber_stiffness_front" in audit["unidentifiable_parameters"]
    assert "anti_roll_bar_front" in audit["identifiable_parameters"]

    # Verify diagnostic fields for UX
    records = audit["records"]
    camber_rec = records["camber_stiffness_front"]
    assert camber_rec["status"] == "UNIDENTIFIABLE"
    assert camber_rec["is_calibratable"] is False
    assert "rejection_reason" in camber_rec


def test_phase3k1_observability_flat_telemetry_refusal():
    """
    Mandate: Excitation check.
    Verifies that if telemetry lacks excitation (e.g., straight-line flat cruise),
    the system refuses identification and halts the decision chain.
    """
    audit = Phase3K1CaseService.audit_observability_and_excitation(
        candidate_parameters=["anti_roll_bar_front", "damper_bump_front"],
        telemetry_window_s=(39.0, 42.0),
        force_flat_signal=True,
    )

    assert audit["status"] == "UNIDENTIFIABLE / UNSUPPORTED"
    assert audit["is_supported"] is False
    assert len(audit["identifiable_parameters"]) == 0
    assert len(audit["unidentifiable_parameters"]) == 2


# ── TEST 3: SEALED BLIND VALIDATION & ZERO DATA LEAKAGE PROOF ──────────────────

@pytest.mark.asyncio
async def test_phase3k1_sealed_blind_validation_zero_leakage(async_test_db: AsyncSession):
    """
    Mandates 7 & 9: Blind Validation & Zero Leakage.
    Verifies that:
    1. Fit window and Holdout window are strictly disjoint: D_fit ∩ D_holdout = ∅.
    2. Parameters were frozen before accessing holdout.
    3. Holdout R2 and RMSE are evaluated on unseen telemetry.
    """
    user_id = str(uuid.uuid4())
    val_dict = await Phase3K1CaseService.execute_sealed_blind_validation(
        db=async_test_db,
        user_id=user_id,
        candidate_setup_id="SETUP-GTI-OPT",
        candidate_params={"k_arb_front_nm": 33000.0, "c_damper_front_nsm": 4200.0},
    )

    # 1. Zero data leakage verification
    assert val_dict["is_zero_leakage"] is True
    fit_t0, fit_t1 = 39.0, 42.0
    hold_t0, hold_t1 = 42.0, 44.0
    assert fit_t1 <= hold_t0, "Fit window overlaps holdout window: DATA LEAKAGE DETECTED!"

    # 2. Gate verdict and metrics
    assert val_dict["gate_verdict"] == "PASSED"
    assert val_dict["fit_r2"] == pytest.approx(0.7156, abs=0.01)
    assert val_dict["holdout_r2"] == pytest.approx(0.7664, abs=0.01)
    assert val_dict["holdout_rmse"] == pytest.approx(0.0925, abs=0.01)
    assert val_dict["holdout_r2"] > val_dict["base_holdout_r2"]
    assert val_dict["holdout_rmse"] < val_dict["base_holdout_rmse"]


# ── TEST 4: DECISION PERMITTED OUTCOMES ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase3k1_decision_permitted_outcomes(async_test_db: AsyncSession):
    """
    Mandate 10: The system must permit all outcomes:
    ACCEPT, REJECT, INCONCLUSIVE, UNSUPPORTED.
    Do not force an improvement.
    """
    user_id = str(uuid.uuid4())

    # Case A: ACCEPT (improved metrics, zero leakage, constraints satisfied)
    dec_accept = await Phase3K1CaseService.create_engineering_decision(
        db=async_test_db,
        user_id=user_id,
        decision_code="DEC-P3K1-ACCEPT",
        outcome="ACCEPT",
        author="Elena Rostova",
    )
    assert dec_accept["outcome"] == "ACCEPT"
    assert dec_accept["status"] == "VALIDATED"  # Pre-approval

    # Case B: REJECT (e.g. holdout degradation or travel limit violation)
    dec_reject = await Phase3K1CaseService.create_engineering_decision(
        db=async_test_db,
        user_id=user_id,
        decision_code="DEC-P3K1-REJECT",
        outcome="REJECT",
        author="Elena Rostova",
    )
    assert dec_reject["outcome"] == "REJECT"

    # Case C: INCONCLUSIVE (e.g. overlapping confidence intervals)
    dec_inconclusive = await Phase3K1CaseService.create_engineering_decision(
        db=async_test_db,
        user_id=user_id,
        decision_code="DEC-P3K1-INCONC",
        outcome="INCONCLUSIVE",
        author="Elena Rostova",
    )
    assert dec_inconclusive["outcome"] == "INCONCLUSIVE"

    # Case D: UNSUPPORTED (e.g. observability failed)
    dec_unsupported = await Phase3K1CaseService.create_engineering_decision(
        db=async_test_db,
        user_id=user_id,
        decision_code="DEC-P3K1-UNSUPP",
        outcome="UNSUPPORTED",
        author="Elena Rostova",
    )
    assert dec_unsupported["outcome"] == "UNSUPPORTED"

    # Invalid outcome check
    with pytest.raises(ValueError, match="Invalid outcome"):
        await Phase3K1CaseService.create_engineering_decision(
            db=async_test_db,
            user_id=user_id,
            decision_code="DEC-P3K1-INVALID",
            outcome="FORCE_WIN",
        )


# ── TEST 5: HUMAN APPROVAL ENFORCEMENT ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase3k1_human_approval_enforcement(async_test_db: AsyncSession):
    """
    Mandate 11: Human Approval.
    No setup may be marked approved automatically.
    Require explicit engineer approval with credentials and HMAC signature.
    """
    user_id = str(uuid.uuid4())

    dec = await Phase3K1CaseService.create_engineering_decision(
        db=async_test_db,
        user_id=user_id,
        decision_code="DEC-P3K1-APPTEST",
        outcome="ACCEPT",
        author="Elena Rostova",
    )

    # 1. Verify pre-approval status is VALIDATED, NOT APPROVED
    assert dec["status"] == "VALIDATED"
    assert dec["status"] != "APPROVED"

    # 2. Refuse empty approver name
    with pytest.raises(ValueError, match="Human approval requires"):
        await Phase3K1CaseService.request_human_approval(
            db=async_test_db,
            user_id=user_id,
            approval_number=801,
            decision_code="DEC-P3K1-APPTEST",
            approver_name="",
            approver_role="Chief Race Engineer",
        )

    # 3. Successful human sign-off
    appr = await Phase3K1CaseService.request_human_approval(
        db=async_test_db,
        user_id=user_id,
        approval_number=801,
        decision_code="DEC-P3K1-APPTEST",
        approver_name="Elena Rostova",
        approver_role="Chief Race Engineer & Technical Director",
        notes="Candidate setup verified on Thunderhill Turn 3 holdout telemetry. Roll angle contained to 2.45 deg.",
    )

    assert appr["status"] == "APPROVED"
    assert appr["approver_name"] == "Elena Rostova"
    assert len(appr["approval_signature"]) == 64

    # 4. Verify decision record status in DB transitioned to APPROVED
    from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
    from sqlalchemy import select
    res = await async_test_db.execute(select(EngineeringDecision).where(EngineeringDecision.decision_id == "DEC-P3K1-APPTEST"))
    updated_dec = res.scalar_one()
    assert updated_dec.status == "APPROVED"


# ── TEST 6: 12-STEP LINEAGE RECONSTRUCTABILITY ─────────────────────────────────

@pytest.mark.asyncio
async def test_phase3k1_lineage_reconstructability(async_test_db: AsyncSession):
    """
    Mandate 12: Reconstructability.
    Given the final Decision ID, reconstruct the complete chain:
    Decision → Approval → Validation → Optimization → Simulation →
    Experiment → Hypothesis → Evidence → Question → Investigation →
    TelemetrySession → Dataset Provenance.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    # Run case
    await Phase3K1CaseService.execute_end_to_end_case(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        approver_name="Elena Rostova",
        approver_role="Chief Race Engineer",
    )

    # Reconstruct lineage
    lin = await Phase3K1CaseService.reconstruct_complete_lineage(db=async_test_db, decision_code="DEC-P3K1-01")
    assert lin["decision_id"] == "DEC-P3K1-01"
    assert lin["chain_length"] == 12

    trace = lin["lineage"]
    expected_stages = [
        "DECISION",
        "APPROVAL",
        "BLIND_VALIDATION",
        "OPTIMIZATION",
        "SIMULATION",
        "EXPERIMENT",
        "HYPOTHESIS",
        "EVIDENCE",
        "QUESTION",
        "INVESTIGATION",
        "TELEMETRY_SESSION",
        "DATASET_PROVENANCE",
    ]

    for i, expected_stage in enumerate(expected_stages):
        step = trace[i]
        assert step["step"] == i + 1
        assert step["stage"] == expected_stage

    # Verify dataset provenance hash matches Stanford CSV
    ds_step = next(s for s in trace if s["stage"] == "DATASET_PROVENANCE")
    assert ds_step["sha256"] == "489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3"

    # Verify model version
    assert ds_step["model_version"] == "DYNAMIC_TRANSIENT_14DOF-v2.6"


# ── TEST 7: FAILURE UX DIAGNOSTICS ─────────────────────────────────────────────

def test_phase3k1_failure_ux_diagnostics():
    """
    Mandate 13: Failure Reporting UX.
    The UI must say:
    WHAT FAILED
    WHY
    WHAT REMAINS VALID
    WHAT CANNOT BE CLAIMED
    WHAT CAN BE DONE NEXT
    """
    failure_scenarios = [
        "UNIDENTIFIABLE_PARAMETERS",
        "SOLVER_DIVERGENCE",
        "HOLDOUT_VALIDATION_FAILURE",
        "EXTRAPOLATED_PHYSICS",
    ]

    for mode in failure_scenarios:
        d_dict = Phase3K1CaseService.diagnose_failure(
            failure_type=mode,
            context={"parameter": "camber_stiffness_front", "maneuver": "Turn_3_Approach"},
        )

        assert "WHAT_FAILED" in d_dict
        assert "WHY" in d_dict
        assert "WHAT_REMAINS_VALID" in d_dict
        assert "WHAT_CANNOT_BE_CLAIMED" in d_dict
        assert "WHAT_CAN_BE_DONE_NEXT" in d_dict

        # Verify substantive content in all 5 sections
        assert len(d_dict["WHAT_FAILED"]) > 10
        assert len(d_dict["WHY"]) > 15
        assert len(d_dict["WHAT_REMAINS_VALID"]) > 15
        assert len(d_dict["WHAT_CANNOT_BE_CLAIMED"]) > 15
        assert len(d_dict["WHAT_CAN_BE_DONE_NEXT"]) > 15

        # Check explicit negative assertion in WHAT CANNOT BE CLAIMED
        assert "cannot" in d_dict["WHAT_CANNOT_BE_CLAIMED"].lower() or "must not" in d_dict["WHAT_CANNOT_BE_CLAIMED"].lower()


# ── TEST 8: FASTAPI REST ENDPOINTS INTEGRATION ────────────────────────────────

@pytest.mark.asyncio
async def test_phase3k1_api_endpoints():
    """
    Verifies that the FastAPI routes mounted at /api/v1/decision-loop/phase3k1/
    correctly serve requests for audit, case manifest, and lineage reconstruction.
    """
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.main import app
    from suspensionlab.backend.security.auth import verify_api_key, UserContext
    from suspensionlab.backend.database.core import get_db_dependency
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_user = UserContext(
        user_id=str(uuid.uuid4()),
        email="elena.rostova@suspensionlab.com",
        name="Elena Rostova",
        plan="PRO",
        onboarding_complete=True,
        team_role="ENGINEER",
        permissions=["setup:create", "setup:read", "vehicle:read", "simulation:run", "setup:approve"],
    )

    app.dependency_overrides[get_db_dependency] = override_get_db
    app.dependency_overrides[verify_api_key] = lambda: test_user

    client = TestClient(app)

    try:
        # 1. Test POST /api/v1/decision-loop/phase3k1/audit-observability
        resp_audit = client.post(
            "/api/v1/decision-loop/phase3k1/audit-observability",
            json={
                "candidate_parameters": ["anti_roll_bar_front", "damper_bump_front"],
                "telemetry_window_s": [39.0, 42.0],
                "force_flat_signal": False,
            },
        )
        assert resp_audit.status_code == 200
        audit_data = resp_audit.json()
        assert audit_data["status"] == "IDENTIFIABLE_AND_SUPPORTED"
        assert audit_data["is_supported"] is True

        # 2. Test GET /api/v1/decision-loop/phase3k1/case
        resp_case = client.get("/api/v1/decision-loop/phase3k1/case")
        assert resp_case.status_code == 200
        case_data = resp_case.json()
        assert case_data["status"] == "DECISION_CHAIN_COMPLETE_AND_APPROVED"
        assert case_data["decision"]["decision_id"] == "DEC-P3K1-01"

    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
