"""
tests/test_phase5_6_redteam_acceptance.py
=========================================
SuspensionLab PRO — Phase 5.6 Blind Engineering Red-Team & Final Acceptance Suite.

Hostile, adversarial release audit covering Phases 5.1 through 5.5:
- Vector 1: Pre-Reveal Information Firewall & Leakage Attacks (Tests 01-08)
- Vector 2: Authentication, Authorization & Multi-Tenant Boundary Attacks (Tests 09-15)
- Vector 3: State Machine, Submission Immutability & Concurrency Attacks (Tests 16-23)
- Vector 4: Comparison & Outcome Identity Integrity Attacks (Tests 24-29)
- Vector 5: Calibration & Longitudinal Track Record Governance Attacks (Tests 30-35)
- Vector 6: Historical Case Classification & Manifest Audit (Tests 36-37)
- Vector 7: System Architecture, Vocabulary & Physics Immutability (Tests 38-40)
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.database.models.blind_engineering import (
    BlindComparisonImmutabilityError,
    BlindComparisonResult,
    BlindEngineeringSession,
    BlindSessionStatus,
    BlindSubmission,
    BlindSubmissionImmutabilityError,
)
from suspensionlab.backend.database.models.decision_loop import BlindValidationRecord
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.services.blind_calibration_engine import (
    CALIBRATION_POLICY_V1,
    CALIBRATION_POLICY_V1_SPEC,
    IneligibilityReason,
    compute_brier_score,
    compute_calibration_curve,
    evaluate_observation_eligibility,
)
from suspensionlab.backend.services.blind_calibration_service import (
    BlindCalibrationService,
    UnauthorizedTeamAccessError,
    TeamNotFoundError,
)
from suspensionlab.backend.services.blind_comparison_engine import (
    COMPARISON_POLICY_V1,
    ComparisonVerdict,
    compute_canonical_comparison_hash,
    compute_canonical_outcome_identity,
    evaluate_prediction_comparison,
)
from suspensionlab.backend.services.blind_engineering_service import (
    BlindEngineeringService,
    DuplicateComparisonError,
    DuplicateSubmissionError,
    InformationFirewallViolationError,
    InvalidStateTransitionError,
    InvalidSubmissionError,
    SessionAbortedError,
    SessionNotFoundError,
    UnauthorizedRevealError,
)
from suspensionlab.backend.services.blind_prediction_schema import (
    CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
    PREDICTION_SCHEMA_V1,
    PREDICTION_SCHEMA_V2,
    PredictionSchemaError,
    validate_prediction_contract,
)
from suspensionlab.backend.services.evidence_graph_service import EvidenceGraphService
from suspensionlab.backend.services.historical_blind_case_runner import (
    CASE_MANIFEST_OUTPUT_PATH,
    EXPECTED_P3H_MANIFEST_HASH,
    EXPECTED_P3K1_HASH,
    HistoricalBlindCaseRunner,
    PHASE3H_MANIFEST_PATH,
    PHASE3K1_CASE_PATH,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


# ── FIXTURES & HELPERS ────────────────────────────────────────────────────────

@pytest.fixture
async def red_db():
    """Isolated in-memory SQLite async database engine for red-team testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def make_context(
    user_id: uuid.UUID,
    team_id: Optional[uuid.UUID] = None,
    org_id: Optional[uuid.UUID] = None,
    role: str = "engineer",
    team_role: str = "ENGINEER",
    permissions: Optional[List[str]] = None,
) -> UserContext:
    perms = permissions or ([] if team_role not in ("LEAD", "LEAD_ENGINEER", "ADMIN") else ["setup:approve"])
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email=f"{role}_{user_id.hex[:4]}@suspensionlab.com",
        name=f"RedTeam {role.capitalize()}",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=team_role,
        org_role="MEMBER" if role != "org_admin" else "ADMIN",
        is_admin=role in ("admin", "org_admin"),
        permissions=perms,
    )


async def setup_redteam_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: Optional[uuid.UUID] = None,
    org_id: Optional[uuid.UUID] = None,
) -> Tuple[BlindEngineeringSession, UserContext, UserContext]:
    """Sets up an armed and activated historical blind evaluation session."""
    ctx_eval = make_context(user_id, team_id, org_id, role="engineer", team_role="ENGINEER")
    ctx_lead = make_context(uuid.uuid4(), team_id, org_id, role="lead", team_role="LEAD_ENGINEER")

    await HistoricalBlindCaseRunner.seed_historical_case_entities(
        db=db,
        user_id=user_id,
        team_id=team_id,
        org_id=org_id,
    )

    session = await HistoricalBlindCaseRunner.create_and_arm_blind_session(
        db=db,
        evaluator_context=ctx_eval,
    )
    return session, ctx_eval, ctx_lead


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR 1: PRE-REVEAL INFORMATION FIREWALL & LEAKAGE ATTACKS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_01_attack_session_dto_pre_reveal_does_not_leak_hidden_metadata(red_db: AsyncSession):
    """Attack 1.1: GET /sessions/{id} pre-reveal must not expose hidden entity ID or target."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    dto = await BlindEngineeringService.get_session(red_db, session.id, ctx_eval)
    assert "hidden_outcome_id" not in dto
    assert dto.get("visibility_summary", {}).get("hidden_outcome_withheld") is True
    assert "VAL-P3K1-01" not in json.dumps(dto)


@pytest.mark.asyncio
async def test_02_attack_visible_context_pre_reveal_purges_withheld_entity_and_edges(red_db: AsyncSession):
    """Attack 1.2: Visible context drops VAL-P3K1-01, connecting edges, and forbidden decision fields."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    ctx_dto = await BlindEngineeringService.get_visible_context(red_db, session.id, ctx_eval)
    ctx_json = json.dumps(ctx_dto)

    assert "VAL-P3K1-01" not in ctx_json
    assert "gate_verdict" not in ctx_json
    assert "selected_option" not in ctx_json
    assert "reason" not in ctx_dto.get("root_entity", {})


@pytest.mark.asyncio
async def test_03_attack_graph_traversal_bypass_strictly_filtered_by_firewall(red_db: AsyncSession):
    """Attack 1.3: Direct graph traversal forward/backward never traverses into withheld outcome."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    ctx_dto = await BlindEngineeringService.get_visible_context(red_db, session.id, ctx_eval)
    visible_node_ids = {n.get("entity_id") for n in ctx_dto.get("visible_entities", [])}
    assert "VAL-P3K1-01" not in visible_node_ids

    for edge in ctx_dto.get("visible_edges", []):
        assert edge.get("source_id") != "VAL-P3K1-01"
        assert edge.get("target_id") != "VAL-P3K1-01"


@pytest.mark.asyncio
async def test_04_attack_pre_reveal_comparison_access_blocked_fail_closed(red_db: AsyncSession):
    """Attack 1.4: Pre-reveal request for comparison result raises InformationFirewallViolationError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    with pytest.raises(InformationFirewallViolationError):
        await BlindEngineeringService.get_comparison_result(red_db, session.id, ctx_eval)


@pytest.mark.asyncio
async def test_05_attack_pre_reveal_revealed_outcome_access_blocked_fail_closed(red_db: AsyncSession):
    """Attack 1.5: Pre-reveal request for revealed outcome raises InformationFirewallViolationError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    with pytest.raises(InformationFirewallViolationError):
        await BlindEngineeringService.get_revealed_outcome(red_db, session.id, ctx_eval)


@pytest.mark.asyncio
async def test_06_attack_evaluator_error_messages_contain_zero_secret_data(red_db: AsyncSession):
    """Attack 1.6: Firewall violation exceptions do not disclose secret tokens or outcome IDs."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    try:
        await BlindEngineeringService.get_comparison_result(red_db, session.id, ctx_eval)
        pytest.fail("Expected InformationFirewallViolationError")
    except InformationFirewallViolationError as err:
        err_msg = str(err)
        assert "VAL-P3K1-01" not in err_msg
        assert "gate_verdict" not in err_msg
        assert "0.7664" not in err_msg


@pytest.mark.asyncio
async def test_07_attack_full_browser_payload_serialization_contains_zero_withheld_tokens(red_db: AsyncSession):
    """Attack 1.7: Deep search over serialized browser payloads confirms zero secret tokens."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    sess_dto = await BlindEngineeringService.get_session(red_db, session.id, ctx_eval)
    ctx_dto = await BlindEngineeringService.get_visible_context(red_db, session.id, ctx_eval)
    full_payload = json.dumps({"session": sess_dto, "context": ctx_dto})

    assert "VAL-P3K1-01" not in full_payload
    assert "gate_verdict" not in full_payload
    assert "selected_option" not in full_payload


@pytest.mark.asyncio
async def test_08_attack_nested_context_reflection_contains_zero_forbidden_fields(red_db: AsyncSession):
    """Attack 1.8: Recursive check of visible context structure verifies all forbidden keys are dropped."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    ctx_dto = await BlindEngineeringService.get_visible_context(red_db, session.id, ctx_eval)

    def scan_for_forbidden(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in ("selected_option", "gate_verdict", "validation_evidence")
                scan_for_forbidden(v)
        elif isinstance(obj, list):
            for item in obj:
                scan_for_forbidden(item)

    scan_for_forbidden(ctx_dto)


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR 2: AUTHENTICATION, AUTHORIZATION & MULTI-TENANT BOUNDARY ATTACKS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_09_attack_cross_tenant_session_inspection_fails_closed(red_db: AsyncSession):
    """Attack 2.1: Foreign tenant user cannot inspect session DTO."""
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()
    session, _, _ = await setup_redteam_session(red_db, user_id, team_a)

    foreign_ctx = make_context(uuid.uuid4(), team_id=uuid.uuid4(), role="engineer")
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_session(red_db, session.id, foreign_ctx)


@pytest.mark.asyncio
async def test_10_attack_cross_tenant_visible_context_access_fails_closed(red_db: AsyncSession):
    """Attack 2.2: Foreign tenant user cannot fetch visible context."""
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()
    session, _, _ = await setup_redteam_session(red_db, user_id, team_a)

    foreign_ctx = make_context(uuid.uuid4(), team_id=uuid.uuid4(), role="engineer")
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_visible_context(red_db, session.id, foreign_ctx)


@pytest.mark.asyncio
async def test_11_attack_cross_tenant_submission_injection_fails_closed(red_db: AsyncSession):
    """Attack 2.3: Foreign tenant user cannot lock a submission into session."""
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()
    session, _, _ = await setup_redteam_session(red_db, user_id, team_a)

    foreign_ctx = make_context(uuid.uuid4(), team_id=uuid.uuid4(), role="engineer")
    with pytest.raises(SessionNotFoundError):
        await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, foreign_ctx)


@pytest.mark.asyncio
async def test_12_attack_cross_tenant_reveal_execution_fails_closed(red_db: AsyncSession):
    """Attack 2.4: Foreign tenant lead cannot execute reveal on session."""
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_a)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)
    await BlindEngineeringService.prepare_reveal(red_db, session.id, ctx_eval)

    foreign_lead = make_context(uuid.uuid4(), team_id=uuid.uuid4(), role="lead", team_role="LEAD_ENGINEER")
    with pytest.raises((UnauthorizedRevealError, SessionNotFoundError)):
        await BlindEngineeringService.execute_reveal(red_db, session.id, foreign_lead)


@pytest.mark.asyncio
async def test_13_attack_unprivileged_engineer_reveal_attempt_rejected(red_db: AsyncSession):
    """Attack 2.5: Engineer lacking approval authorization cannot execute reveal."""
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_a)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)
    await BlindEngineeringService.prepare_reveal(red_db, session.id, ctx_eval)

    with pytest.raises(UnauthorizedRevealError):
        await BlindEngineeringService.execute_reveal(red_db, session.id, ctx_eval)

    await red_db.refresh(session)
    assert session.status != BlindSessionStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_14_attack_personal_workspace_cross_user_isolation(red_db: AsyncSession):
    """Attack 2.6: In personal workspace (team_id=None), other users cannot access session."""
    user_a = uuid.uuid4()
    ctx_a = make_context(user_a, team_id=None, role="engineer")

    await HistoricalBlindCaseRunner.seed_historical_case_entities(red_db, user_a, team_id=None)
    session = await HistoricalBlindCaseRunner.create_and_arm_blind_session(red_db, ctx_a)

    ctx_b = make_context(uuid.uuid4(), team_id=None, role="engineer")
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_session(red_db, session.id, ctx_b)


@pytest.mark.asyncio
async def test_15_attack_personal_workspace_creator_reveal_authorized(red_db: AsyncSession):
    """Attack 2.7: In personal workspace, creator is authorized to reveal when ready."""
    user_a = uuid.uuid4()
    ctx_a = make_context(user_a, team_id=None, role="engineer")

    await HistoricalBlindCaseRunner.seed_historical_case_entities(red_db, user_a, team_id=None)
    session = await HistoricalBlindCaseRunner.create_and_arm_blind_session(red_db, ctx_a)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_a)
    await BlindEngineeringService.prepare_reveal(red_db, session.id, ctx_a)

    comp = await BlindEngineeringService.execute_reveal(red_db, session.id, ctx_a)
    assert comp is not None
    assert comp.verdict == "SUPPORTED"


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR 3: STATE MACHINE, SUBMISSION IMMUTABILITY & CONCURRENCY ATTACKS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_16_attack_submission_rejected_in_draft_state(red_db: AsyncSession):
    """Attack 3.1: Submissions to DRAFT session are rejected fail-closed."""
    user_id = uuid.uuid4()
    ctx_eval = make_context(user_id, team_id=None, role="engineer")

    await HistoricalBlindCaseRunner.seed_historical_case_entities(red_db, user_id, team_id=None)
    session = await BlindEngineeringService.create_session(
        db=red_db,
        user_context=ctx_eval,
        name="Draft Session",
        root_entity_type="EngineeringDecision",
        root_entity_id="DEC-P3K1-01",
        hidden_outcome_type="BlindValidation",
        hidden_outcome_id="VAL-P3K1-01",
        configuration={"allowed_candidates": ["SETUP-GTI-BASE", "SETUP-GTI-OPT"]},
    )

    with pytest.raises(InvalidStateTransitionError):
        await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)


@pytest.mark.asyncio
async def test_17_attack_submission_rejected_in_aborted_state(red_db: AsyncSession):
    """Attack 3.2: Submissions to ABORTED session are rejected fail-closed."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    await BlindEngineeringService.abort_session(red_db, session.id, ctx_eval, "Aborting session")

    with pytest.raises((SessionAbortedError, InvalidStateTransitionError, InformationFirewallViolationError)):
        await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)


@pytest.mark.asyncio
async def test_18_attack_duplicate_submission_rejected(red_db: AsyncSession):
    """Attack 3.3: Attempting replacement submission raises DuplicateSubmissionError or InvalidStateTransitionError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)

    with pytest.raises((DuplicateSubmissionError, InvalidStateTransitionError)):
        await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)


@pytest.mark.asyncio
async def test_19_attack_submission_in_place_mutation_raises_immutability_error(red_db: AsyncSession):
    """Attack 3.4: Directly mutating locked submission payload raises BlindSubmissionImmutabilityError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    sub = await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)

    sub.submission_payload = {"tampered": True}
    with pytest.raises(BlindSubmissionImmutabilityError):
        await red_db.commit()

    await red_db.rollback()


@pytest.mark.asyncio
async def test_20_attack_submission_deletion_raises_immutability_error(red_db: AsyncSession):
    """Attack 3.5: Directly deleting locked submission raises BlindSubmissionImmutabilityError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_redteam_session(red_db, user_id, team_id)

    sub = await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)

    await red_db.delete(sub)
    with pytest.raises(BlindSubmissionImmutabilityError):
        await red_db.commit()

    await red_db.rollback()


@pytest.mark.asyncio
async def test_21_attack_premature_reveal_from_blind_active_rejected(red_db: AsyncSession):
    """Attack 3.6: Attempting execute_reveal without prior submission and preparation raises InvalidStateTransitionError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, ctx_lead = await setup_redteam_session(red_db, user_id, team_id)

    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.execute_reveal(red_db, session.id, ctx_lead)


@pytest.mark.asyncio
async def test_22_attack_reveal_without_locked_submission_rejected(red_db: AsyncSession):
    """Attack 3.7: Attempting reveal when no locked submission exists fails closed."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_redteam_session(red_db, user_id, team_id)

    # Force invalid state transition to READY_FOR_REVEAL without submission
    session.status = BlindSessionStatus.READY_FOR_REVEAL.value
    await red_db.commit()

    with pytest.raises(InvalidSubmissionError):
        await BlindEngineeringService.execute_reveal(red_db, session.id, ctx_lead)


@pytest.mark.asyncio
async def test_23_attack_concurrent_reveal_requests_race_condition(red_db: AsyncSession):
    """Attack 3.8: Concurrent reveal requests resolve safely without duplicate comparison records."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_redteam_session(red_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)
    await BlindEngineeringService.prepare_reveal(red_db, session.id, ctx_lead)

    results: List[Any] = []
    errors: List[Exception] = []

    async def try_reveal() -> None:
        try:
            r = await BlindEngineeringService.execute_reveal(red_db, session.id, ctx_lead)
            results.append(r)
        except Exception as e:
            errors.append(e)

    await asyncio.gather(try_reveal(), try_reveal(), return_exceptions=True)

    # Exactly one succeeded
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], (InvalidStateTransitionError, DuplicateComparisonError))

    # Exactly one comparison result persisted
    stmt = select(BlindComparisonResult).where(BlindComparisonResult.session_id == session.id)
    comp_records = (await red_db.execute(stmt)).scalars().all()
    assert len(comp_records) == 1


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR 4: COMPARISON & OUTCOME IDENTITY INTEGRITY ATTACKS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_24_attack_comparison_in_place_mutation_raises_immutability_error(red_db: AsyncSession):
    """Attack 4.1: Direct update of BlindComparisonResult verdict raises BlindComparisonImmutabilityError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_redteam_session(red_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)
    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(red_db, session.id, ctx_lead)

    comp.verdict = "TAMPERED_VERDICT"
    with pytest.raises(BlindComparisonImmutabilityError):
        await red_db.commit()

    await red_db.rollback()


@pytest.mark.asyncio
async def test_25_attack_comparison_deletion_raises_immutability_error(red_db: AsyncSession):
    """Attack 4.2: Direct delete of BlindComparisonResult raises BlindComparisonImmutabilityError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_redteam_session(red_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)
    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(red_db, session.id, ctx_lead)

    await red_db.delete(comp)
    with pytest.raises(BlindComparisonImmutabilityError):
        await red_db.commit()

    await red_db.rollback()


def test_26_attack_canonical_comparison_hash_is_deterministic_and_tamper_evident():
    """Attack 4.3: Canonical RFC 8785 comparison hash is deterministic across identical evaluations."""
    h1 = compute_canonical_comparison_hash(
        session_id="sess-test",
        submission_id="sub-test",
        submission_hash="a" * 64,
        outcome_identity={"entity_type": "BlindValidation", "entity_id": "VAL-1"},
        comparison_policy_version="1",
        prediction_schema_version="2",
        comparison_type="ENGINEERING_DECISION",
        verdict="SUPPORTED",
        comparison_metrics={"supported": True},
    )
    h2 = compute_canonical_comparison_hash(
        session_id="sess-test",
        submission_id="sub-test",
        submission_hash="a" * 64,
        outcome_identity={"entity_type": "BlindValidation", "entity_id": "VAL-1"},
        comparison_policy_version="1",
        prediction_schema_version="2",
        comparison_type="ENGINEERING_DECISION",
        verdict="SUPPORTED",
        comparison_metrics={"supported": True},
    )
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.asyncio
async def test_27_attack_deterministic_comparison_replay_preserves_verdict(red_db: AsyncSession):
    """Attack 4.4: Replay evaluation of historical case produces identical verdict under COMPARISON_POLICY_V1."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_redteam_session(red_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(red_db, session.id, ctx_eval)
    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(red_db, session.id, ctx_lead)

    assert comp.verdict == "SUPPORTED"
    assert comp.comparison_policy_version == "1"
    assert comp.comparison_metrics["selected_candidate_id"] == "SETUP-GTI-OPT"


def test_28_attack_uncomparable_outcome_never_treated_as_incorrect():
    """Attack 4.5: Target with missing metric resolves to UNCOMPARABLE and is never converted to incorrect."""
    sub_payload = {
        "prediction_type": "ENGINEERING_DECISION",
        "target": {"metric": "non_existent_metric"},
        "selected_candidate_id": "SETUP-GTI-OPT",
    }
    class EmptyOutcome:
        pass

    res = evaluate_prediction_comparison(sub_payload, EmptyOutcome(), "BlindValidation", "VAL-P3K1-01")
    assert res["verdict"] == ComparisonVerdict.UNCOMPARABLE.value
    assert res["verdict"] != "INCORRECT"
    assert res["verdict"] != "NOT_SUPPORTED"


def test_29_attack_malformed_structured_identity_yields_uncomparable():
    """Attack 4.6: Malformed structured ID payload yields UNCOMPARABLE."""
    sub_payload = {
        "prediction_type": "ENGINEERING_DECISION",
        "target": {"metric": "setup_id"},
        "selected_candidate_id": "",  # Empty
    }
    class MockRecord:
        setup_id = "SETUP-GTI-OPT"

    res = evaluate_prediction_comparison(sub_payload, MockRecord(), "BlindValidation", "VAL-P3K1-01")
    assert res["verdict"] == ComparisonVerdict.UNCOMPARABLE.value


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR 5: CALIBRATION & LONGITUDINAL TRACK RECORD GOVERNANCE ATTACKS
# ══════════════════════════════════════════════════════════════════════════════

def test_30_attack_generic_historical_confidence_excluded_from_calibration():
    """Attack 5.1: Observations without PROBABILITY_PREDICTION_CORRECT semantics are ineligible for calibration."""
    pred_payload = {
        "schema_version": PREDICTION_SCHEMA_V1,
        "prediction_type": "CATEGORICAL",
        "confidence": 0.90,  # Generic float, no declared semantics
    }
    elig = evaluate_observation_eligibility(pred_payload, "CORRECT")
    assert elig.eligible_for_binary_calibration is False
    assert IneligibilityReason.NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED.value in elig.ineligibility_reasons


def test_31_attack_insufficient_sample_size_reports_explicit_status():
    """Attack 5.2: Samples under N=5 report INSUFFICIENT_SAMPLE without false calibration claims."""
    single_obs = [{
        "prediction_payload": {
            "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
            "confidence": 0.95,
        },
        "verdict": "SUPPORTED",
    }]
    curve = compute_calibration_curve(single_obs)
    assert curve["status"] == "INSUFFICIENT_SAMPLE"
    assert curve["total_eligible_samples"] == 1
    assert "Descriptive bin counts shown without conclusive calibration claims" in curve["status_message"]


def test_32_attack_ineligible_observations_excluded_from_brier_score():
    """Attack 5.3: UNCOMPARABLE and METRICS_ONLY observations are excluded from Brier calculations."""
    obs = [
        {"prediction_payload": {"confidence_semantics": "PROBABILITY_PREDICTION_CORRECT", "confidence": 0.9}, "verdict": "UNCOMPARABLE"},
        {"prediction_payload": {"confidence_semantics": "PROBABILITY_PREDICTION_CORRECT", "confidence": 0.8}, "verdict": "METRICS_ONLY"},
    ]
    brier_res = compute_brier_score(obs)
    assert brier_res["status"] == "INSUFFICIENT_SAMPLE"
    assert brier_res["eligible_sample_size"] == 0
    assert brier_res["excluded_count"] == 2


def test_33_attack_zero_leaderboard_or_skill_rating_routes_exist():
    """Attack 5.4: Verifies codebase contains zero routes for engineer ranking or leaderboards."""
    from suspensionlab.backend.api.routes.blind_calibration_routes import router

    for route in router.routes:
        path = getattr(route, "path", "")
        assert "leaderboard" not in path.lower()
        assert "ranking" not in path.lower()
        assert "rank" not in path.lower()
        assert "skill" not in path.lower()


@pytest.mark.asyncio
async def test_34_attack_cross_tenant_longitudinal_summary_access_blocked(red_db: AsyncSession):
    """Attack 5.5: User cannot query longitudinal calibration record of other organizations/teams."""
    user_a = uuid.uuid4()
    team_a = uuid.uuid4()
    ctx_a = make_context(user_a, team_id=team_a, role="engineer")

    user_b = uuid.uuid4()
    team_b = uuid.uuid4()
    ctx_b = make_context(user_b, team_id=team_b, role="engineer")

    with pytest.raises(UnauthorizedTeamAccessError):
        await BlindCalibrationService.get_team_calibration_summary(red_db, team_a, ctx_b)


@pytest.mark.asyncio
async def test_35_attack_non_member_team_aggregate_access_rejected(red_db: AsyncSession):
    """Attack 5.6: Non-member querying team calibration summary raises UnauthorizedTeamAccessError."""
    team_id = uuid.uuid4()
    ctx_outsider = make_context(uuid.uuid4(), team_id=uuid.uuid4(), role="engineer")

    with pytest.raises(UnauthorizedTeamAccessError):
        await BlindCalibrationService.get_team_calibration_summary(red_db, team_id, ctx_outsider)


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR 6: HISTORICAL CASE CLASSIFICATION & MANIFEST AUDIT
# ══════════════════════════════════════════════════════════════════════════════

def test_36_attack_genuine_blinding_eligibility_mode_is_honest():
    """Attack 6.1: Blinding classification is RETROSPECTIVE_SYSTEM_VALIDATION with honest disclaimer."""
    assert HistoricalBlindCaseRunner.BLINDNESS_MODE == "RETROSPECTIVE_SYSTEM_VALIDATION"
    assert CASE_MANIFEST_OUTPUT_PATH.exists()

    with open(CASE_MANIFEST_OUTPUT_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["blindness_classification"]["mode"] == "RETROSPECTIVE_SYSTEM_VALIDATION"
    assert "without claiming prospective human ignorance" in manifest["blindness_classification"]["limitation_statement"]


def test_37_attack_frozen_historical_source_files_remain_unmodified():
    """Attack 6.2: Historical source files match exact golden cryptographic hashes."""
    p3k1_bytes = PHASE3K1_CASE_PATH.read_bytes()
    p3h_bytes = PHASE3H_MANIFEST_PATH.read_bytes()

    assert hashlib.sha256(p3k1_bytes).hexdigest() == EXPECTED_P3K1_HASH
    assert hashlib.sha256(p3h_bytes).hexdigest() == EXPECTED_P3H_MANIFEST_HASH


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR 7: SYSTEM ARCHITECTURE, VOCABULARY & PHYSICS IMMUTABILITY
# ══════════════════════════════════════════════════════════════════════════════

def test_38_attack_evidence_graph_vocabulary_remains_canonical_17():
    """Attack 7.1: Evidence Graph vocabulary contains exactly 17 canonical relationships."""
    expected_rels = {
        "OBSERVED_IN", "DETECTED_FROM", "FORMULATED_FROM", "EVIDENCED_BY",
        "HYPOTHESIZED_FROM", "TESTED_BY", "EXECUTED_AS", "USES_SETUP",
        "PRODUCED_SETUP", "EVALUATED_IN", "OPTIMIZED_TO", "VALIDATED_BY",
        "JUSTIFIED_BY", "APPROVED_UNDER", "PREDICTED_FOR", "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual_rels = {r.value for r in EvidenceGraphRelationship}
    assert actual_rels == expected_rels


def test_39_attack_production_physics_files_remain_strictly_unchanged():
    """Attack 7.2: All 81 production physics source files match baseline SHA-256 digests."""
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing physics file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Physics file modified: {item['path']}"


def test_40_attack_phase6_and_phase7_independence_preserved():
    """Attack 7.3: Phase 5 modules contain zero imports or dependencies on Phase 6 or Phase 7."""
    import suspensionlab.backend.services.historical_blind_case_runner as runner_mod
    import suspensionlab.backend.services.blind_engineering_service as blind_mod
    import suspensionlab.backend.services.blind_comparison_engine as comp_mod
    import suspensionlab.backend.services.blind_calibration_engine as cal_engine
    import suspensionlab.backend.services.blind_calibration_service as cal_service

    for mod in (runner_mod, blind_mod, comp_mod, cal_engine, cal_service):
        src = inspect.getsource(mod)
        assert "ParameterTrustMap" not in src
        assert "ParameterTrustProfile" not in src
        assert "ParameterTrustService" not in src
        assert "adapter_registry" not in src
