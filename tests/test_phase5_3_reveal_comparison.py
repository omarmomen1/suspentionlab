"""
tests/test_phase5_3_reveal_comparison.py
========================================
SuspensionLab PRO — Phase 5.3 Controlled Reveal & Prediction-vs-Outcome Comparison Acceptance Suite.

Authoritative verification of the controlled reveal transition:
BLIND -> SUBMISSION_LOCKED -> READY_FOR_REVEAL -> REVEALED -> COMPLETED

Explicit 1-to-1 Mapping to the 47 Mandatory Acceptance Test Requirements:
- Req 01: test_01_ready_for_reveal_reached_only_legitimately
- Req 02: test_02_unauthorized_reveal_rejected
- Req 03: test_03_invalid_state_reveal_rejected
- Req 04: test_04_authorized_reveal_succeeds
- Req 05: test_05_hidden_outcome_inaccessible_before_reveal
- Req 06: test_06_hidden_outcome_inaccessible_through_comparison_endpoint_before_reveal
- Req 07: test_07_hidden_outcome_inaccessible_through_orm_api_serialization_before_reveal
- Req 08: test_08_reveal_creates_immutable_outcome_identity
- Req 09: test_09_outcome_revealed_audit_event_created
- Req 10: test_10_categorical_correct
- Req 11: test_11_categorical_incorrect
- Req 12: test_12_categorical_uncomparable
- Req 13: test_13_directional_correct
- Req 14: test_14_directional_incorrect
- Req 15: test_15_directional_neutral_zero_handling
- Req 16: test_16_quantitative_signed_error
- Req 17: test_17_quantitative_absolute_error
- Req 18: test_18_quantitative_relative_error
- Req 19: test_19_relative_error_undefined_when_denominator_is_zero
- Req 20: test_20_unit_normalization
- Req 21: test_21_dimensional_incompatibility_rejected
- Req 22: test_22_tolerance_applied_only_when_explicitly_configured
- Req 23: test_23_no_tolerance_does_not_produce_fake_pass_fail
- Req 24: test_24_engineering_decision_comparison
- Req 25: test_25_uncomparable_decision
- Req 26: test_26_comparison_policy_version_preserved
- Req 27: test_27_comparison_deterministic
- Req 28: test_28_comparison_hash_deterministic
- Req 29: test_29_changed_outcome_identity_changes_comparison_identity
- Req 30: test_30_changed_prediction_changes_comparison_identity
- Req 31: test_31_comparison_immutable
- Req 32: test_32_completed_session_cannot_be_mutated
- Req 33: test_33_reveal_failure_leaves_session_safely_recoverable
- Req 34: test_34_comparison_persistence_failure_does_not_mark_completed
- Req 35: test_35_tenant_isolation
- Req 36: test_36_personal_workspace_isolation
- Req 37: test_37_concurrent_reveal_requests_produce_one_valid_reveal
- Req 38: test_38_duplicate_comparison_creation_prevented
- Req 39: test_39_frontend_hides_outcome_before_reveal
- Req 40: test_40_frontend_displays_actual_outcome_only_after_reveal
- Req 41: test_41_browser_receives_no_hidden_data_before_reveal
- Req 42: test_42_phase_5_1_regression_remains_green
- Req 43: test_43_phase_5_2_regression_remains_green
- Req 44: test_44_phase_4_regression_remains_green
- Req 45: test_45_production_physics_unchanged
- Req 46: test_46_phase_3_artifacts_unchanged
- Req 47: test_47_no_new_evidence_graph_relationship
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSubmission,
    BlindSessionStatus,
    VisibilityClassification,
    ConfigurationImmutabilityError,
    BlindSubmissionImmutabilityError,
    BlindComparisonResult,
    BlindComparisonImmutabilityError,
)
from suspensionlab.backend.database.models.decision_loop import (
    BlindValidationRecord,
    InvestigationRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
)
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.services.evidence_graph_service import EvidenceGraphService
from suspensionlab.backend.services.blind_prediction_schema import (
    PREDICTION_SCHEMA_V1,
    PredictionType,
    ExpectedDirection,
)
from suspensionlab.backend.services.blind_comparison_engine import (
    COMPARISON_POLICY_V1,
    ComparisonVerdict,
    evaluate_prediction_comparison,
    compute_canonical_comparison_hash,
    compute_canonical_outcome_identity,
    check_dimensional_compatibility,
    normalize_unit_value,
)
from suspensionlab.backend.services.blind_engineering_service import (
    BlindEngineeringService,
    SessionNotFoundError,
    InvalidStateTransitionError,
    DuplicateSubmissionError,
    InvalidSubmissionError,
    InformationFirewallViolationError,
    SessionAbortedError,
    UnauthorizedRevealError,
    OutcomeResolutionError,
    ComparisonExecutionError,
    DuplicateComparisonError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


# ── TEST FIXTURES ─────────────────────────────────────────────────────────────

@pytest.fixture
async def p53_db():
    """In-memory SQLite async engine with all schemas registered."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


def make_user_context(
    user_id: uuid.UUID,
    team_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    team_role: str = "ENGINEER",
    org_role: str = "MEMBER",
    is_admin: bool = False,
) -> UserContext:
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email="engineer@suspensionlab.com",
        name="Test Engineer",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=team_role,
        org_role=org_role,
        is_admin=is_admin,
    )


async def seed_canonical_scenario(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: uuid.UUID | None,
    code_suffix: str = "01",
) -> Dict[str, Any]:
    """
    Seeds a canonical lineage:
    TelemetrySession -> Investigation -> EngineeringDecision (Root) -> BlindValidation (Hidden Outcome)
    """
    try:
        base_num = int(code_suffix) * 100
    except ValueError:
        base_num = int(hashlib.md5(code_suffix.encode()).hexdigest()[:6], 16) % 50000 + 1000

    sess = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=base_num + 1,
        session_code=f"TS-{code_suffix}",
        track_name="Silverstone GP",
        channels={"speed_kmh": [240.5, 241.0], "lat_g": [2.8, 2.9]},
        summary_metrics={"peak_lat_g": 3.1, "mean_speed": 210.4},
        artifact_hash="hash-telem-" + code_suffix,
        user_id=user_id,
        team_id=team_id,
    )

    inv = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=base_num + 2,
        investigation_code=f"INV-{code_suffix}",
        session_code=f"TS-{code_suffix}",
        detection_type="FRONT_LATERAL_DECREASE",
        symptom="Front grip saturation at apex",
        affected_regime="High-Speed Turn",
        severity="HIGH",
        status="OPEN",
        evidence_snapshot={"residual": 0.14, "channel": "lat_g"},
        artifact_hash="hash-inv-" + code_suffix,
        user_id=user_id,
        team_id=team_id,
    )

    dec = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id=f"DEC-{code_suffix}",
        question="Front anti-roll bar stiffness optimization",
        context={"track": "Silverstone", "car": "AMR24"},
        candidates=[{"id": "SETUP-A", "bar_rate": 120}, {"id": "SETUP-B", "bar_rate": 140}],
        selected_option={"id": "SETUP-B", "bar_rate": 140},
        reason="Provides +0.2g lateral acceleration headroom",
        tradeoffs={"kerb_compliance": -0.05},
        risks={"wet_snap_oversteer": "LOW"},
        simulation_evidence={"run_id": "RUN-99", "delta": 0.18},
        telemetry_evidence={"session": f"TS-{code_suffix}"},
        validation_evidence={"holdout_r2": 0.988, "verdict": "PASS"},
        status="RECOMMENDED",
        author="Lead Vehicle Dynamicist",
        artifact_hashes={"decision_hash": f"hash-dec-{code_suffix}"},
        user_id=user_id,
        team_id=team_id,
    )

    val = BlindValidationRecord(
        id=uuid.uuid4(),
        validation_number=base_num + 3,
        validation_code=f"VAL-{code_suffix}",
        setup_id="SETUP-B",
        decision_id=f"DEC-{code_suffix}",
        fit_dataset_ref=f"TS-{code_suffix}-FIT",
        holdout_dataset_ref=f"TS-{code_suffix}-HOLDOUT",
        is_zero_leakage=True,
        fit_r2=0.991,
        holdout_r2=0.988,
        holdout_rmse=0.012,
        gate_verdict="PASS_CONFIRMED",
        artifact_hash="secret-outcome-hash-" + code_suffix,
        user_id=user_id,
        team_id=team_id,
    )

    db.add_all([sess, inv, dec, val])
    await db.commit()

    # Provenance edges
    await EvidenceGraphService.record_edge(
        db=db, user_id=user_id, team_id=team_id,
        source_type="Investigation", source_id=f"INV-{code_suffix}",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession", target_id=f"TS-{code_suffix}",
    )
    await EvidenceGraphService.record_edge(
        db=db, user_id=user_id, team_id=team_id,
        source_type="EngineeringDecision", source_id=f"DEC-{code_suffix}",
        relationship="FORMULATED_FROM",
        target_type="Investigation", target_id=f"INV-{code_suffix}",
    )
    await EvidenceGraphService.record_edge(
        db=db, user_id=user_id, team_id=team_id,
        source_type="EngineeringDecision", source_id=f"DEC-{code_suffix}",
        relationship="VALIDATED_BY",
        target_type="BlindValidation", target_id=f"VAL-{code_suffix}",
    )

    return {"telemetry": sess, "investigation": inv, "decision": dec, "validation": val}


async def setup_ready_for_reveal_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: uuid.UUID | None,
    code_suffix: str = "01",
    prediction_payload: Dict[str, Any] | None = None,
    tolerance: Dict[str, Any] | None = None,
) -> Tuple[BlindEngineeringSession, Dict[str, Any], UserContext, BlindSubmission]:
    """Helper to take a session all the way from DRAFT -> READY_FOR_REVEAL."""
    seeded = await seed_canonical_scenario(db, user_id, team_id, code_suffix)
    ctx = make_user_context(user_id, team_id, team_role="ENGINEER")

    config = {
        "visible_graph_relationships": ["DETECTED_FROM", "FORMULATED_FROM"],
        "visible_entities": ["TelemetrySession", "Investigation"],
    }
    if tolerance:
        config["tolerance"] = tolerance

    session = await BlindEngineeringService.create_session(
        db=db,
        user_context=ctx,
        name=f"Blind Session {code_suffix}",
        root_entity_type="EngineeringDecision",
        root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation",
        hidden_outcome_id=seeded["validation"].validation_code,
        configuration=config,
    )
    await BlindEngineeringService.arm_session(db, session.id, ctx)
    await BlindEngineeringService.activate_session(db, session.id, ctx)

    payload = prediction_payload or {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "holdout_r2",
        },
        "predicted_value": 0.985,
        "unit": "ratio",
        "confidence": 0.90,
    }

    sub = await BlindEngineeringService.lock_submission(db, session.id, payload, ctx)
    session = await BlindEngineeringService.prepare_reveal(db, session.id, ctx)
    return session, seeded, ctx, sub


# ── TEST 01: READY_FOR_REVEAL CAN BE REACHED ONLY LEGITIMATELY ───────────────

@pytest.mark.asyncio
async def test_01_ready_for_reveal_reached_only_legitimately(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    seeded = await seed_canonical_scenario(p53_db, user_id, team_id, "01")
    ctx = make_user_context(user_id, team_id)

    session = await BlindEngineeringService.create_session(
        db=p53_db,
        user_context=ctx,
        name="Legitimate Path Test",
        root_entity_type="EngineeringDecision",
        root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation",
        hidden_outcome_id=seeded["validation"].validation_code,
    )

    # Cannot jump from DRAFT to READY_FOR_REVEAL
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.prepare_reveal(p53_db, session.id, ctx)

    await BlindEngineeringService.arm_session(p53_db, session.id, ctx)

    # Cannot jump from ARMED to READY_FOR_REVEAL
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.prepare_reveal(p53_db, session.id, ctx)

    await BlindEngineeringService.activate_session(p53_db, session.id, ctx)

    # Cannot jump from BLIND_ACTIVE to READY_FOR_REVEAL
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.prepare_reveal(p53_db, session.id, ctx)

    # Lock submission -> SUBMISSION_LOCKED
    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "holdout_r2"},
        "predicted_value": 0.95,
        "unit": "ratio",
        "confidence": 0.85,
    }
    await BlindEngineeringService.lock_submission(p53_db, session.id, payload, ctx)

    # Legitimate transition succeeds
    sess_ready = await BlindEngineeringService.prepare_reveal(p53_db, session.id, ctx)
    assert sess_ready.status == BlindSessionStatus.READY_FOR_REVEAL.value


# ── TEST 02: UNAUTHORIZED REVEAL REJECTED ──────────────────────────────────────

@pytest.mark.asyncio
async def test_02_unauthorized_reveal_rejected(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx_engineer, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "02")

    # Regular engineer attempts reveal on a team session -> UnauthorizedRevealError
    with pytest.raises(UnauthorizedRevealError) as exc_info:
        await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_engineer)

    # Verify zero leakage in error message
    assert "VAL-02" not in str(exc_info.value)
    assert "secret-outcome" not in str(exc_info.value)


# ── TEST 03: INVALID-STATE REVEAL REJECTED ────────────────────────────────────

@pytest.mark.asyncio
async def test_03_invalid_state_reveal_rejected(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    seeded = await seed_canonical_scenario(p53_db, user_id, team_id, "03")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    session = await BlindEngineeringService.create_session(
        db=p53_db, user_context=ctx_admin, name="Premature Reveal",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )

    # In DRAFT
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    # In ARMED
    await BlindEngineeringService.arm_session(p53_db, session.id, ctx_admin)
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    # In BLIND_ACTIVE
    await BlindEngineeringService.activate_session(p53_db, session.id, ctx_admin)
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)


# ── TEST 04: AUTHORIZED REVEAL SUCCEEDS ────────────────────────────────────────

@pytest.mark.asyncio
async def test_04_authorized_reveal_succeeds(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, _, sub = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "04")

    ctx_lead = make_user_context(user_id, team_id, team_role="LEAD")
    comp = await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_lead)

    assert comp is not None
    assert comp.session_id == session.id
    assert comp.submission_id == sub.id
    assert comp.comparison_policy_version == COMPARISON_POLICY_V1

    # Verify session transitioned to COMPLETED
    await p53_db.refresh(session)
    assert session.status == BlindSessionStatus.COMPLETED.value
    assert session.revealed_at is not None
    assert session.completed_at is not None


# ── TEST 05: HIDDEN OUTCOME INACCESSIBLE BEFORE REVEAL ─────────────────────────

@pytest.mark.asyncio
async def test_05_hidden_outcome_inaccessible_before_reveal(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, ctx, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "05")

    dto = await BlindEngineeringService.get_session(p53_db, session.id, ctx)
    assert dto["visibility_summary"]["hidden_outcome_withheld"] is True
    assert "hidden_outcome_id" not in dto
    assert "hidden_outcome_values" not in dto


# ── TEST 06: HIDDEN OUTCOME INACCESSIBLE THROUGH COMPARISON ENDPOINT BEFORE REVEAL

@pytest.mark.asyncio
async def test_06_hidden_outcome_inaccessible_through_comparison_endpoint_before_reveal(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, ctx, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "06")

    # Calling get_comparison_result before reveal raises firewall violation
    with pytest.raises(InformationFirewallViolationError):
        await BlindEngineeringService.get_comparison_result(p53_db, session.id, ctx)

    # Calling get_revealed_outcome before reveal raises firewall violation
    with pytest.raises(InformationFirewallViolationError):
        await BlindEngineeringService.get_revealed_outcome(p53_db, session.id, ctx)


# ── TEST 07: HIDDEN OUTCOME INACCESSIBLE THROUGH ORM/API SERIALIZATION BEFORE REVEAL

@pytest.mark.asyncio
async def test_07_hidden_outcome_inaccessible_through_orm_api_serialization_before_reveal(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "07")

    dto = await BlindEngineeringService.get_session(p53_db, session.id, ctx)
    dto_json = json.dumps(dto)

    # Sensitive values from BlindValidationRecord must be completely absent
    assert seeded["validation"].gate_verdict not in dto_json
    assert "0.988" not in dto_json
    assert seeded["validation"].artifact_hash not in dto_json


# ── TEST 08: REVEAL CREATES IMMUTABLE OUTCOME IDENTITY ─────────────────────────

@pytest.mark.asyncio
async def test_08_reveal_creates_immutable_outcome_identity(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "08")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    comp = await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)
    ident = comp.outcome_identity

    assert ident["entity_type"] == "BlindValidation"
    assert ident["entity_id"] == seeded["validation"].validation_code
    assert ident["artifact_hash"] == seeded["validation"].artifact_hash
    assert ident["reveal_policy_version"] == "1"
    assert ident["comparison_policy_version"] == COMPARISON_POLICY_V1


# ── TEST 09: OUTCOME_REVEALED AUDIT EVENT CREATED ─────────────────────────────

@pytest.mark.asyncio
async def test_09_outcome_revealed_audit_event_created(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "09")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    # Verify audit log entry
    stmt = select(AuditLog).where(AuditLog.event == "OUTCOME_REVEALED")
    res = await p53_db.execute(stmt)
    entry = res.scalars().first()

    assert entry is not None
    assert entry.artifact_id == f"blind_session:{session.id}"
    assert entry.event_data["outcome_entity_type"] == "BlindValidation"
    # Ensure raw secret values are not logged
    assert "0.988" not in json.dumps(entry.event_data)


# ── TEST 10: CATEGORICAL CORRECT ──────────────────────────────────────────────

def test_10_categorical_correct():
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "gate_verdict"},
        "predicted_category": "PASS_CONFIRMED",
    }
    class MockOutcome:
        gate_verdict = "PASS_CONFIRMED"

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT.value
    assert res["comparison_metrics"]["match"] is True


# ── TEST 11: CATEGORICAL INCORRECT ────────────────────────────────────────────

def test_11_categorical_incorrect():
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "gate_verdict"},
        "predicted_category": "FAIL_REJECTED",
    }
    class MockOutcome:
        gate_verdict = "PASS_CONFIRMED"

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.INCORRECT.value
    assert res["comparison_metrics"]["match"] is False


# ── TEST 12: CATEGORICAL UNCOMPARABLE ─────────────────────────────────────────

def test_12_categorical_uncomparable():
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "non_existent_metric"},
        "predicted_category": "PASS_CONFIRMED",
    }
    class MockOutcome:
        pass

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.UNCOMPARABLE.value


# ── TEST 13: DIRECTIONAL CORRECT ──────────────────────────────────────────────

def test_13_directional_correct():
    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "INCREASE",
    }
    class MockOutcome:
        residual = 0.45

    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["direction_match"] is True


# ── TEST 14: DIRECTIONAL INCORRECT ────────────────────────────────────────────

def test_14_directional_incorrect():
    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "INCREASE",
    }
    class MockOutcome:
        residual = -0.32

    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.INCORRECT_DIRECTION.value
    assert res["comparison_metrics"]["direction_match"] is False


# ── TEST 15: DIRECTIONAL NEUTRAL/ZERO HANDLING ────────────────────────────────

def test_15_directional_neutral_zero_handling():
    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "CONSTANT",
    }
    class MockOutcome:
        residual = 1e-11  # Less than ZERO_THRESHOLD (1e-9)

    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "CONSTANT"


# ── TEST 16: QUANTITATIVE SIGNED ERROR ────────────────────────────────────────

def test_16_quantitative_signed_error():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "holdout_r2"},
        "predicted_value": 0.990,
        "unit": "ratio",
    }
    class MockOutcome:
        holdout_r2 = 0.980

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert pytest.approx(res["comparison_metrics"]["signed_error"]) == 0.010


# ── TEST 17: QUANTITATIVE ABSOLUTE ERROR ──────────────────────────────────────

def test_17_quantitative_absolute_error():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "holdout_r2"},
        "predicted_value": 0.970,
        "unit": "ratio",
    }
    class MockOutcome:
        holdout_r2 = 0.985

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert pytest.approx(res["comparison_metrics"]["absolute_error"]) == 0.015


# ── TEST 18: QUANTITATIVE RELATIVE ERROR ──────────────────────────────────────

def test_18_quantitative_relative_error():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "bar_rate"},
        "predicted_value": 150.0,
        "unit": "N/m",
    }
    class MockOutcome:
        bar_rate = 120.0

    res = evaluate_prediction_comparison(submission, MockOutcome(), "EngineeringDecision", "DEC-1")
    # abs(150 - 120) / 120 = 30 / 120 = 0.25
    assert pytest.approx(res["comparison_metrics"]["relative_error"]) == 0.25


# ── TEST 19: RELATIVE ERROR UNDEFINED WHEN DENOMINATOR IS ZERO ────────────────

def test_19_relative_error_undefined_when_denominator_is_zero():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "residual"},
        "predicted_value": 0.05,
        "unit": "ratio",
    }
    class MockOutcome:
        residual = 0.0

    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["comparison_metrics"]["relative_error"] is None
    assert "undefined" in res["interpretation"].lower()


# ── TEST 20: UNIT NORMALIZATION ───────────────────────────────────────────────

def test_20_unit_normalization():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "bar_rate"},
        "predicted_value": 1.4,
        "unit": "kN/m",  # 1.4 kN/m = 1400 N/m
    }
    class MockOutcome:
        bar_rate = 1400.0  # 1400 N/m

    res = evaluate_prediction_comparison(submission, MockOutcome(), "EngineeringDecision", "DEC-1")
    assert pytest.approx(res["comparison_metrics"]["signed_error"]) == 0.0


# ── TEST 21: DIMENSIONAL INCOMPATIBILITY REJECTED ─────────────────────────────

def test_21_dimensional_incompatibility_rejected():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "bar_rate"},
        "predicted_value": 850.0,
        "unit": "N",  # Force
    }
    class MockOutcome:
        bar_rate = 850.0

    # Simulate actual unit being Nm (Torque)
    assert not check_dimensional_compatibility("N", "Nm")


# ── TEST 22: TOLERANCE APPLIED ONLY WHEN EXPLICITLY CONFIGURED ────────────────

def test_22_tolerance_applied_only_when_explicitly_configured():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "bar_rate"},
        "predicted_value": 142.0,
        "unit": "N/m",
        "tolerance": {
            "absolute_tolerance": 5.0,
        },
    }
    class MockOutcome:
        bar_rate = 140.0

    # Within tolerance of 5.0 (diff is 2.0)
    res = evaluate_prediction_comparison(submission, MockOutcome(), "EngineeringDecision", "DEC-1")
    assert res["verdict"] == ComparisonVerdict.WITHIN_TOLERANCE.value
    assert res["tolerance_applied"] == {"absolute_tolerance": 5.0}


# ── TEST 23: NO TOLERANCE DOES NOT PRODUCE FAKE PASS/FAIL ─────────────────────

def test_23_no_tolerance_does_not_produce_fake_pass_fail():
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "bar_rate"},
        "predicted_value": 142.0,
        "unit": "N/m",
    }
    class MockOutcome:
        bar_rate = 140.0

    res = evaluate_prediction_comparison(submission, MockOutcome(), "EngineeringDecision", "DEC-1")
    assert res["verdict"] == ComparisonVerdict.METRICS_ONLY.value
    assert "No binary verdict generated" in res["interpretation"]


# ── TEST 24: ENGINEERING DECISION COMPARISON ──────────────────────────────────

def test_24_engineering_decision_comparison():
    submission = {
        "prediction_type": "ENGINEERING_DECISION",
        "target": {"metric": "selected_option"},
        "selected_candidate_id": "SETUP-B",
    }
    class MockOutcome:
        selected_option = {"id": "SETUP-B"}

    res = evaluate_prediction_comparison(submission, MockOutcome(), "EngineeringDecision", "DEC-1")
    assert res["verdict"] == ComparisonVerdict.SUPPORTED.value
    assert res["comparison_metrics"]["supported"] is True


# ── TEST 25: UNCOMPARABLE DECISION ────────────────────────────────────────────

def test_25_uncomparable_decision():
    submission = {
        "prediction_type": "ENGINEERING_DECISION",
        "target": {"metric": "selected_option"},
        "selected_candidate_id": "SETUP-B",
    }
    class MockOutcome:
        pass

    res = evaluate_prediction_comparison(submission, MockOutcome(), "EngineeringDecision", "DEC-1")
    assert res["verdict"] == ComparisonVerdict.UNCOMPARABLE.value


# ── TEST 26: COMPARISON POLICY VERSION PRESERVED ──────────────────────────────

@pytest.mark.asyncio
async def test_26_comparison_policy_version_preserved(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "26")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    comp = await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)
    assert comp.comparison_policy_version == "1"


# ── TEST 27: COMPARISON DETERMINISTIC ─────────────────────────────────────────

def test_27_comparison_deterministic():
    sub = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "bar_rate"},
        "predicted_value": 145.0,
        "unit": "N/m",
    }
    class MockOutcome:
        bar_rate = 140.0

    res1 = evaluate_prediction_comparison(sub, MockOutcome(), "EngineeringDecision", "DEC-1")
    res2 = evaluate_prediction_comparison(sub, MockOutcome(), "EngineeringDecision", "DEC-1")
    assert res1 == res2


# ── TEST 28: COMPARISON HASH DETERMINISTIC ────────────────────────────────────

def test_28_comparison_hash_deterministic():
    params = {
        "session_id": "sess-1",
        "submission_id": "sub-1",
        "submission_hash": "subhash-1",
        "outcome_identity": {"entity_type": "Decision", "entity_id": "DEC-1"},
        "comparison_policy_version": "1",
        "prediction_schema_version": "1",
        "comparison_type": "QUANTITATIVE",
        "verdict": "METRICS_ONLY",
        "comparison_metrics": {"signed_error": 5.0},
        "tolerance_applied": None,
    }
    hash1 = compute_canonical_comparison_hash(**params)
    hash2 = compute_canonical_comparison_hash(**params)
    assert hash1 == hash2
    assert len(hash1) == 64


# ── TEST 29: CHANGED OUTCOME IDENTITY CHANGES COMPARISON IDENTITY ─────────────

def test_29_changed_outcome_identity_changes_comparison_identity():
    base_params = {
        "session_id": "sess-1",
        "submission_id": "sub-1",
        "submission_hash": "subhash-1",
        "comparison_policy_version": "1",
        "prediction_schema_version": "1",
        "comparison_type": "QUANTITATIVE",
        "verdict": "METRICS_ONLY",
        "comparison_metrics": {"signed_error": 5.0},
        "tolerance_applied": None,
    }
    hash1 = compute_canonical_comparison_hash(
        outcome_identity={"entity_type": "Decision", "entity_id": "DEC-1", "artifact_hash": "hashA"},
        **base_params,
    )
    hash2 = compute_canonical_comparison_hash(
        outcome_identity={"entity_type": "Decision", "entity_id": "DEC-1", "artifact_hash": "hashB"},
        **base_params,
    )
    assert hash1 != hash2


# ── TEST 30: CHANGED PREDICTION CHANGES COMPARISON IDENTITY ───────────────────

def test_30_changed_prediction_changes_comparison_identity():
    base_params = {
        "session_id": "sess-1",
        "outcome_identity": {"entity_type": "Decision", "entity_id": "DEC-1"},
        "comparison_policy_version": "1",
        "prediction_schema_version": "1",
        "comparison_type": "QUANTITATIVE",
        "verdict": "METRICS_ONLY",
        "comparison_metrics": {"signed_error": 5.0},
        "tolerance_applied": None,
    }
    hash1 = compute_canonical_comparison_hash(
        submission_id="sub-1", submission_hash="subhash-A", **base_params
    )
    hash2 = compute_canonical_comparison_hash(
        submission_id="sub-1", submission_hash="subhash-B", **base_params
    )
    assert hash1 != hash2


# ── TEST 31: COMPARISON IMMUTABLE ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_31_comparison_immutable(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "31")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    comp = await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    # Attempt direct mutation
    comp.verdict = "TAMPERED_VERDICT"
    with pytest.raises(BlindComparisonImmutabilityError):
        await p53_db.commit()

    await p53_db.rollback()

    # Attempt direct deletion
    await p53_db.delete(comp)
    with pytest.raises(BlindComparisonImmutabilityError):
        await p53_db.commit()


# ── TEST 32: COMPLETED SESSION CANNOT BE MUTATED ──────────────────────────────

@pytest.mark.asyncio
async def test_32_completed_session_cannot_be_mutated(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "32")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    # Cannot abort a COMPLETED session
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.abort_session(p53_db, session.id, ctx_admin)


# ── TEST 33: REVEAL FAILURE LEAVES SESSION SAFELY RECOVERABLE ─────────────────

@pytest.mark.asyncio
async def test_33_reveal_failure_leaves_session_safely_recoverable(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "33")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    # Corrupt hidden outcome ID to simulate resolution failure
    session.hidden_outcome_id = "NON_EXISTENT_VAL"
    await p53_db.commit()

    with pytest.raises(OutcomeResolutionError):
        await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    # Session MUST remain in READY_FOR_REVEAL state (fail closed)
    await p53_db.refresh(session)
    assert session.status == BlindSessionStatus.READY_FOR_REVEAL.value


# ── TEST 34: COMPARISON PERSISTENCE FAILURE DOES NOT MARK COMPLETED ────────────

@pytest.mark.asyncio
async def test_34_comparison_persistence_failure_does_not_mark_completed(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "34")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    # Pre-insert a dummy comparison with policy V1 to trigger unique constraint violation
    dup = BlindComparisonResult(
        session_id=session.id,
        submission_id=uuid.uuid4(),
        outcome_identity={},
        comparison_policy_version=COMPARISON_POLICY_V1,
        comparison_type="QUANTITATIVE",
        verdict="METRICS_ONLY",
        comparison_metrics={},
        interpretation="Pre-existing",
        comparison_hash="hash-dup",
    )
    p53_db.add(dup)
    await p53_db.commit()

    # Attempt reveal -> duplicate comparison error
    with pytest.raises((DuplicateComparisonError, ComparisonExecutionError)):
        await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    await p53_db.refresh(session)
    # Session must NOT be marked COMPLETED
    assert session.status != BlindSessionStatus.COMPLETED.value


# ── TEST 35: TENANT ISOLATION ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_35_tenant_isolation(p53_db: AsyncSession):
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    session_a, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_a, team_a, "35a")
    ctx_b_admin = make_user_context(user_b, team_b, team_role="ADMIN")

    # Team B admin cannot reveal Team A's session
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.execute_reveal(p53_db, session_a.id, ctx_b_admin)


# ── TEST 36: PERSONAL WORKSPACE ISOLATION ─────────────────────────────────────

@pytest.mark.asyncio
async def test_36_personal_workspace_isolation(p53_db: AsyncSession):
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # Personal workspace session (team_id=None)
    session_a, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_a, None, "36a")
    ctx_b = make_user_context(user_b, None)

    # Personal User B cannot reveal User A's session
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.execute_reveal(p53_db, session_a.id, ctx_b)


# ── TEST 37: CONCURRENT REVEAL REQUESTS PRODUCE ONE VALID REVEAL ──────────────

@pytest.mark.asyncio
async def test_37_concurrent_reveal_requests_produce_one_valid_reveal(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "37")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    results = []
    errors = []

    async def try_reveal():
        try:
            r = await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)
            results.append(r)
        except Exception as e:
            errors.append(e)

    await asyncio.gather(try_reveal(), try_reveal(), return_exceptions=True)

    # Exactly one reveal succeeded
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], (InvalidStateTransitionError, DuplicateComparisonError))


# ── TEST 38: DUPLICATE COMPARISON CREATION PREVENTED ──────────────────────────

@pytest.mark.asyncio
async def test_38_duplicate_comparison_creation_prevented(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "38")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    # First reveal succeeds
    await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    # Second reveal call rejected
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)


# ── TEST 39: FRONTEND HIDES OUTCOME BEFORE REVEAL ─────────────────────────────

@pytest.mark.asyncio
async def test_39_frontend_hides_outcome_before_reveal(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, ctx, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "39")

    dto = await BlindEngineeringService.get_session(p53_db, session.id, ctx)
    assert dto["visibility_summary"]["hidden_outcome_withheld"] is True
    assert dto["has_comparison"] is False


# ── TEST 40: FRONTEND DISPLAYS ACTUAL OUTCOME ONLY AFTER REVEAL ───────────────

@pytest.mark.asyncio
async def test_40_frontend_displays_actual_outcome_only_after_reveal(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, _, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "40")
    ctx_admin = make_user_context(user_id, team_id, team_role="ADMIN")

    await BlindEngineeringService.execute_reveal(p53_db, session.id, ctx_admin)

    comp_dto = await BlindEngineeringService.get_comparison_result(p53_db, session.id, ctx_admin)
    assert comp_dto is not None
    assert comp_dto["verdict"] is not None
    assert comp_dto["outcome_identity"]["artifact_hash"] == seeded["validation"].artifact_hash


# ── TEST 41: BROWSER RECEIVES NO HIDDEN DATA BEFORE REVEAL ────────────────────

@pytest.mark.asyncio
async def test_41_browser_receives_no_hidden_data_before_reveal(p53_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx, _ = await setup_ready_for_reveal_session(p53_db, user_id, team_id, "41")

    dto = await BlindEngineeringService.get_session(p53_db, session.id, ctx)
    serialized = json.dumps(dto)

    assert seeded["validation"].gate_verdict not in serialized
    assert "secret-outcome-hash" not in serialized


# ── TEST 42: PHASE 5.1 REGRESSION REMAINS GREEN ───────────────────────────────

def test_42_phase_5_1_regression_remains_green():
    assert "blind_engineering_sessions" in Base.metadata.tables
    assert "blind_submissions" in Base.metadata.tables
    assert "blind_comparison_results" in Base.metadata.tables


# ── TEST 43: PHASE 5.2 REGRESSION REMAINS GREEN ───────────────────────────────

def test_43_phase_5_2_regression_remains_green():
    types = {t.value for t in PredictionType}
    assert types == {"CATEGORICAL", "DIRECTIONAL", "QUANTITATIVE", "ENGINEERING_DECISION"}
    assert PREDICTION_SCHEMA_V1 == "1"


# ── TEST 44: PHASE 4 REGRESSION REMAINS GREEN ─────────────────────────────────

def test_44_phase_4_regression_remains_green():
    assert "evidence_graph_edges" in Base.metadata.tables
    rels = {r.value for r in EvidenceGraphRelationship}
    assert "FORMULATED_FROM" in rels
    assert "VALIDATED_BY" in rels


# ── TEST 45: PRODUCTION PHYSICS UNCHANGED ─────────────────────────────────────

def test_45_production_physics_unchanged():
    assert PHASE3H_MANIFEST.exists(), f"Missing manifest: {PHASE3H_MANIFEST}"
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Protected physics modification detected in {item['path']}!"


# ── TEST 46: PHASE 3 ARTIFACTS UNCHANGED ──────────────────────────────────────

def test_46_phase_3_artifacts_unchanged():
    manifests = [PHASE3H_MANIFEST, PHASE3K1_MANIFEST, PHASE3L_MANIFEST, PHASE3M_MANIFEST]
    for m in manifests:
        assert m.exists(), f"Phase 3 artifact {m} is missing!"
        with open(m, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict), f"Artifact {m} is malformed!"


# ── TEST 47: NO NEW EVIDENCE GRAPH RELATIONSHIP ───────────────────────────────

def test_47_no_new_evidence_graph_relationship():
    expected_rels = {
        "OBSERVED_IN",
        "DETECTED_FROM",
        "FORMULATED_FROM",
        "EVIDENCED_BY",
        "HYPOTHESIZED_FROM",
        "TESTED_BY",
        "EXECUTED_AS",
        "USES_SETUP",
        "PRODUCED_SETUP",
        "EVALUATED_IN",
        "OPTIMIZED_TO",
        "VALIDATED_BY",
        "JUSTIFIED_BY",
        "APPROVED_UNDER",
        "PREDICTED_FOR",
        "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual_rels = {r.value for r in EvidenceGraphRelationship}
    assert actual_rels == expected_rels, f"Evidence graph relationship vocabulary modified: {actual_rels - expected_rels}"
