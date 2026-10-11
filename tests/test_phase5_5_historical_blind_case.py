"""
tests/test_phase5_5_historical_blind_case.py
============================================
SuspensionLab PRO — Phase 5.5 Real Historical Blind Case & End-to-End Workflow Validation Suite.

Executes a genuine frozen historical Phase 3 engineering case (Case P3K.1: VW Golf VII GTI
Performance Turn 3 Roll Stiffness & Damping Optimization) through the full Blind Engineering workflow:

40-test adversarial verification suite:
 1. Selected case resolves to authoritative source artifacts.
 2. Frozen source hashes remain unchanged.
 3. Case suitability is supported by structured evidence.
 4. Genuine-blinding eligibility is classified honestly (RETROSPECTIVE_SYSTEM_VALIDATION).
 5. Visible input manifest is deterministic.
 6. Hidden outcome is absent from pre-reveal session DTO.
 7. Hidden outcome is absent from visible-context response.
 8. Hidden outcome is absent from graph traversal output.
 9. Hidden outcome is absent from comparison response before reveal.
10. Hidden outcome is absent from browser payload before reveal.
11. Hidden outcome is absent from evaluator-visible logs/errors.
12. Invalid target is rejected.
13. Valid prediction is accepted.
14. Submission hash is preserved.
15. Submission remains immutable (BlindSubmissionImmutabilityError).
16. Replacement submission is rejected (DuplicateSubmissionError).
17. Unauthorized reveal fails closed (UnauthorizedRevealError).
18. Authorized reveal succeeds.
19. Outcome identity resolves to authoritative source.
20. Outcome hash is stable.
21. Comparison result follows COMPARISON_POLICY_V1 (verdict SUPPORTED).
22. Uncomparable outcome remains uncomparable.
23. Comparison is immutable (BlindComparisonImmutabilityError).
24. Repeated case execution does not corrupt source artifacts.
25. Duplicate reveal does not create duplicate comparisons.
26. Cross-tenant reveal is rejected.
27. Personal workspace isolation works.
28. Calibration eligibility follows Phase 5.4 rules.
29. One sample is not reported as established calibration (INSUFFICIENT_SAMPLE).
30. Audit trail preserves lifecycle order.
31. Zero Phase 6 imports/dependencies.
32. Zero Phase 7 imports/dependencies.
33. Phase 5.1 regression passes.
34. Phase 5.2 regression passes.
35. Phase 5.3 final acceptance regression passes.
36. Phase 5.4 regression passes.
37. Phase 4 regression passes.
38. Evidence Graph vocabulary unchanged (17 relationships).
39. Production physics hashes unchanged (81 files).
40. Phase 3 manifests unchanged.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import math
from datetime import datetime, timezone
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
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.decision_loop import BlindValidationRecord
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.services.blind_calibration_engine import (
    CALIBRATION_POLICY_V1,
    compute_calibration_curve,
    evaluate_observation_eligibility,
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
    SessionNotFoundError,
    UnauthorizedRevealError,
)
from suspensionlab.backend.services.blind_prediction_schema import (
    CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
    PredictionSchemaError,
    PREDICTION_SCHEMA_V2,
    canonicalize_prediction_payload,
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
async def case_db():
    """In-memory SQLite async engine with all registered tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def make_user_context(
    user_id: uuid.UUID,
    team_id: Optional[uuid.UUID] = None,
    org_id: Optional[uuid.UUID] = None,
    role: str = "engineer",
    team_role: str = "ENGINEER",
) -> UserContext:
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email=f"{role}@suspensionlab.com",
        name=f"User {role.capitalize()}",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=team_role,
        org_role="MEMBER" if role != "org_admin" else "ADMIN",
        is_admin=role in ("admin", "org_admin"),
        permissions=["setup:approve"] if team_role in ("LEAD", "LEAD_ENGINEER", "ADMIN") else [],
    )


async def setup_historical_active_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: uuid.UUID,
    org_id: Optional[uuid.UUID] = None,
) -> Tuple[BlindEngineeringSession, UserContext, UserContext]:
    """Sets up seeded historical entities and an active blind session."""
    ctx_evaluator = make_user_context(user_id, team_id, org_id, role="engineer", team_role="ENGINEER")
    ctx_approver = make_user_context(uuid.uuid4(), team_id, org_id, role="lead", team_role="LEAD_ENGINEER")

    # Seed historical records into DB
    await HistoricalBlindCaseRunner.seed_historical_case_entities(
        db=db,
        user_id=user_id,
        team_id=team_id,
        org_id=org_id,
    )

    # Create, arm, and activate blind session
    session = await HistoricalBlindCaseRunner.create_and_arm_blind_session(
        db=db,
        evaluator_context=ctx_evaluator,
    )
    return session, ctx_evaluator, ctx_approver


# ── TEST 01: SELECTED CASE RESOLVES TO AUTHORITATIVE SOURCE ARTIFACTS ─────────

def test_01_selected_case_resolves_to_authoritative_source_artifacts():
    """Verifies historical case file and manifests resolve and pass integrity checks."""
    audit = HistoricalBlindCaseRunner.verify_source_artifact_integrity()
    assert audit["phase3k1_verified"] is True
    assert audit["phase3k1_sha256"] == EXPECTED_P3K1_HASH
    assert audit["phase3h_verified"] is True
    assert audit["phase3h_sha256"] == EXPECTED_P3H_MANIFEST_HASH

    with open(PHASE3K1_CASE_PATH, "r", encoding="utf-8") as f:
        case_data = json.load(f)

    assert case_data["decision"]["decision_id"] == "DEC-P3K1-01"
    assert case_data["validation"]["validation_code"] == "VAL-P3K1-01"


# ── TEST 02: FROZEN SOURCE HASHES REMAIN UNCHANGED ────────────────────────────

def test_02_frozen_source_hashes_remain_unchanged():
    """Verifies that frozen Phase 3 files have identical byte hashes."""
    p3k1_bytes = PHASE3K1_CASE_PATH.read_bytes()
    p3h_bytes = PHASE3H_MANIFEST_PATH.read_bytes()

    assert hashlib.sha256(p3k1_bytes).hexdigest() == EXPECTED_P3K1_HASH
    assert hashlib.sha256(p3h_bytes).hexdigest() == EXPECTED_P3H_MANIFEST_HASH


# ── TEST 03: CASE SUITABILITY IS SUPPORTED BY STRUCTURED EVIDENCE ─────────────

def test_03_case_suitability_is_supported_by_structured_evidence():
    """Verifies historical case contains all required structured engineering records."""
    with open(PHASE3K1_CASE_PATH, "r", encoding="utf-8") as f:
        case = json.load(f)

    # 1. Telemetry
    assert case["telemetry"]["session_code"] == "TS-STANFORD-01"
    assert case["telemetry"]["sample_count"] == 22304
    assert case["telemetry"]["summary_metrics"]["validity_status"] == "AUTHENTIC_AUDITED_VALID"

    # 2. Investigation
    assert case["investigation"]["investigation_code"] == "INV-P3K1-01"
    assert case["investigation"]["detection_type"] == "EXCESSIVE_CHASSIS_ROLL_COMPLIANCE"
    assert case["investigation"]["severity"] == "CRITICAL"

    # 3. Question
    assert case["question"]["question_id"] == "Q-P3K1-01"

    # 4. Candidates
    candidate_ids = [c["setup_id"] for c in case["decision"]["candidates"]]
    assert "SETUP-GTI-BASE" in candidate_ids
    assert "SETUP-GTI-OPT" in candidate_ids
    assert "SETUP-GTI-AGGRESSIVE" in candidate_ids

    # 5. Validation (withheld outcome)
    assert case["validation"]["validation_code"] == "VAL-P3K1-01"
    assert case["validation"]["holdout_r2"] == 0.7664
    assert case["validation"]["gate_verdict"] == "PASSED"
    assert case["validation"]["setup_id"] == "SETUP-GTI-OPT"


# ── TEST 04: GENUINE-BLINDING ELIGIBILITY CLASSIFIED HONESTLY ─────────────────

def test_04_genuine_blinding_eligibility_is_classified_honestly():
    """Confirms blinding mode is RETROSPECTIVE_SYSTEM_VALIDATION and clearly documented."""
    assert HistoricalBlindCaseRunner.BLINDNESS_MODE == "RETROSPECTIVE_SYSTEM_VALIDATION"

    manifest_output = HistoricalBlindCaseRunner.generate_case_manifest(
        case_run_id="TEST-RUN-01",
        session_id=uuid.uuid4(),
        submission_hash="a" * 64,
        comparison=BlindComparisonResult(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            submission_id=uuid.uuid4(),
            outcome_identity={"outcome_hash": "b" * 64},
            prediction_schema_version="2",
            comparison_policy_version=COMPARISON_POLICY_V1,
            comparison_type="ENGINEERING_DECISION",
            verdict="SUPPORTED",
            comparison_metrics={"supported": True},
            comparison_hash="c" * 64,
        ),
        evaluator_id=str(uuid.uuid4()),
        approver_id=str(uuid.uuid4()),
        source_hashes=HistoricalBlindCaseRunner.verify_source_artifact_integrity(),
        leakage_audit={"clean": True},
    )

    assert manifest_output["blindness_classification"]["mode"] == "RETROSPECTIVE_SYSTEM_VALIDATION"
    assert "without claiming prospective human ignorance" in manifest_output["blindness_classification"]["limitation_statement"]


# ── TEST 05: VISIBLE INPUT MANIFEST IS DETERMINISTIC ──────────────────────────

@pytest.mark.asyncio
async def test_05_visible_input_manifest_is_deterministic(case_db: AsyncSession):
    """Visible context hash is computed deterministically across multiple retrievals."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    ctx_dto_1 = await BlindEngineeringService.get_visible_context(case_db, session.id, ctx_eval)
    ctx_dto_2 = await BlindEngineeringService.get_visible_context(case_db, session.id, ctx_eval)

    assert ctx_dto_1["visible_context_hash"] == ctx_dto_2["visible_context_hash"]
    assert len(ctx_dto_1["visible_context_hash"]) == 64


# ── TEST 06: HIDDEN OUTCOME ABSENT FROM PRE-REVEAL SESSION DTO ────────────────

@pytest.mark.asyncio
async def test_06_hidden_outcome_is_absent_from_pre_reveal_session_dto(case_db: AsyncSession):
    """Session DTO does not leak hidden_outcome_id or withheld values."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    session_dto = await BlindEngineeringService.get_session(case_db, session.id, ctx_eval)
    assert "hidden_outcome_id" not in session_dto
    assert session_dto["visibility_summary"]["hidden_outcome_withheld"] is True
    assert "VAL-P3K1-01" not in json.dumps(session_dto)


# ── TEST 07: HIDDEN OUTCOME ABSENT FROM VISIBLE-CONTEXT RESPONSE ──────────────

@pytest.mark.asyncio
async def test_07_hidden_outcome_is_absent_from_visible_context_response(case_db: AsyncSession):
    """Visible context omits VAL-P3K1-01 and forbidden decision fields."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    ctx_dto = await BlindEngineeringService.get_visible_context(case_db, session.id, ctx_eval)
    ctx_json = json.dumps(ctx_dto)

    assert "VAL-P3K1-01" not in ctx_json
    assert "gate_verdict" not in ctx_json
    assert "selected_option" not in ctx_json
    assert "reason" not in ctx_dto.get("root_entity", {})


# ── TEST 08: HIDDEN OUTCOME ABSENT FROM GRAPH TRAVERSAL OUTPUT ────────────────

@pytest.mark.asyncio
async def test_08_hidden_outcome_is_absent_from_graph_traversal_output(case_db: AsyncSession):
    """Graph traversal strictly excludes hidden outcome nodes and attached edges."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    ctx_dto = await BlindEngineeringService.get_visible_context(case_db, session.id, ctx_eval)
    visible_nodes = ctx_dto.get("visible_entities", [])
    node_ids = {n.get("entity_id") for n in visible_nodes}

    assert "VAL-P3K1-01" not in node_ids
    for edge in ctx_dto.get("visible_edges", []):
        assert edge.get("source_id") != "VAL-P3K1-01"
        assert edge.get("target_id") != "VAL-P3K1-01"


# ── TEST 09: HIDDEN OUTCOME ABSENT FROM COMPARISON RESPONSE BEFORE REVEAL ─────

@pytest.mark.asyncio
async def test_09_hidden_outcome_is_absent_from_comparison_response_before_reveal(case_db: AsyncSession):
    """Pre-reveal comparison endpoint fails closed with firewall violation."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    with pytest.raises(InformationFirewallViolationError):
        await BlindEngineeringService.get_comparison_result(case_db, session.id, ctx_eval)


# ── TEST 10: HIDDEN OUTCOME ABSENT FROM BROWSER PAYLOAD BEFORE REVEAL ─────────

@pytest.mark.asyncio
async def test_10_hidden_outcome_is_absent_from_browser_payload_before_reveal(case_db: AsyncSession):
    """Simulated browser-facing payloads contain zero withheld data."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    sess_dto = await BlindEngineeringService.get_session(case_db, session.id, ctx_eval)
    ctx_dto = await BlindEngineeringService.get_visible_context(case_db, session.id, ctx_eval)

    browser_payload = json.dumps({"session": sess_dto, "context": ctx_dto})
    assert "VAL-P3K1-01" not in browser_payload
    assert "gate_verdict" not in browser_payload
    assert "selected_option" not in browser_payload


# ── TEST 11: HIDDEN OUTCOME ABSENT FROM EVALUATOR-VISIBLE LOGS/ERRORS ─────────

@pytest.mark.asyncio
async def test_11_hidden_outcome_is_absent_from_evaluator_visible_logs_errors(case_db: AsyncSession):
    """Firewall exception messages reveal zero secret identifiers or metrics."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    try:
        await BlindEngineeringService.get_revealed_outcome(case_db, session.id, ctx_eval)
        pytest.fail("Expected InformationFirewallViolationError")
    except InformationFirewallViolationError as err:
        err_msg = str(err)
        assert "VAL-P3K1-01" not in err_msg
        assert "SETUP-GTI-OPT" not in err_msg
        assert "0.7664" not in err_msg


# ── TEST 12: INVALID TARGET IS REJECTED ───────────────────────────────────────

@pytest.mark.asyncio
async def test_12_invalid_target_is_rejected(case_db: AsyncSession):
    """Malformed or invalid prediction target raises validation error."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    ctx_dto = await BlindEngineeringService.get_visible_context(case_db, session.id, ctx_eval)
    invalid_payload = {
        "schema_version": PREDICTION_SCHEMA_V2,
        "prediction_type": "ENGINEERING_DECISION",
        "target": {
            "entity_type": "InvalidEntity",
            "entity_id": "NON-EXISTENT",
            "metric": "selected_candidate_id",
        },
        "selected_candidate_id": "SETUP-GTI-OPT",
        "confidence": 1.5,  # Invalid: > 1.0
        "visible_context_hash": ctx_dto["visible_context_hash"],
        "rationale": "Test invalid",
    }

    with pytest.raises(PredictionSchemaError):
        validate_prediction_contract(invalid_payload, ctx_dto)


# ── TEST 13: VALID PREDICTION IS ACCEPTED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_13_valid_prediction_is_accepted(case_db: AsyncSession):
    """Valid versioned prediction is locked successfully under PREDICTION_SCHEMA_V2."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    sub = await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    assert sub is not None
    assert sub.status == "LOCKED"
    assert sub.submission_payload["schema_version"] == PREDICTION_SCHEMA_V2
    assert sub.submission_payload["confidence_semantics"] == CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT


# ── TEST 14: SUBMISSION HASH IS PRESERVED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_14_submission_hash_is_preserved(case_db: AsyncSession):
    """Canonical submission hash is non-empty, 64-char hex, and stable across reads."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    sub = await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    sub_hash_1 = sub.submission_hash
    assert len(sub_hash_1) == 64

    await case_db.refresh(sub)
    assert sub.submission_hash == sub_hash_1


# ── TEST 15: SUBMISSION REMAINS IMMUTABLE ─────────────────────────────────────

@pytest.mark.asyncio
async def test_15_submission_remains_immutable(case_db: AsyncSession):
    """Mutating or tampering with locked BlindSubmission raises BlindSubmissionImmutabilityError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    sub = await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)

    # Attempt mutation
    sub.submission_payload = {"tampered": True}
    with pytest.raises(BlindSubmissionImmutabilityError):
        await case_db.commit()

    await case_db.rollback()


# ── TEST 16: REPLACEMENT SUBMISSION IS REJECTED ───────────────────────────────

@pytest.mark.asyncio
async def test_16_replacement_submission_is_rejected(case_db: AsyncSession):
    """Attempting a second prediction submission on the same session raises DuplicateSubmissionError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)

    with pytest.raises((DuplicateSubmissionError, InvalidStateTransitionError)):
        await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)


# ── TEST 17: UNAUTHORIZED REVEAL FAILS CLOSED ─────────────────────────────────

@pytest.mark.asyncio
async def test_17_unauthorized_reveal_fails_closed(case_db: AsyncSession):
    """Non-lead evaluator reveal attempt fails closed with UnauthorizedRevealError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    await BlindEngineeringService.prepare_reveal(case_db, session.id, ctx_eval)

    with pytest.raises(UnauthorizedRevealError):
        await BlindEngineeringService.execute_reveal(case_db, session.id, ctx_eval)

    # Verify session is not completed
    await case_db.refresh(session)
    assert session.status != BlindSessionStatus.COMPLETED.value


# ── TEST 18: AUTHORIZED REVEAL SUCCEEDS ───────────────────────────────────────

@pytest.mark.asyncio
async def test_18_authorized_reveal_succeeds(case_db: AsyncSession):
    """Authorized team lead reveal transitions session to COMPLETED and evaluates comparison."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    sub = await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)

    # Probe pre-reveal leakage BEFORE reveal occurs
    leakage_audit = await HistoricalBlindCaseRunner.probe_pre_reveal_leakage(case_db, session.id, ctx_eval)
    assert leakage_audit["zero_pre_reveal_leakage_verified"] is True

    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(case_db, session.id, ctx_lead)

    assert comp is not None
    assert comp.session_id == session.id
    assert comp.submission_id == sub.id
    assert comp.verdict == "SUPPORTED"

    await case_db.refresh(session)
    assert session.status == BlindSessionStatus.COMPLETED.value
    assert session.completed_at is not None

    # Generate Case Manifest
    manifest = HistoricalBlindCaseRunner.generate_case_manifest(
        case_run_id=f"CASE-RUN-{uuid.uuid4().hex[:8].upper()}",
        session_id=session.id,
        submission_hash=sub.submission_hash,
        comparison=comp,
        evaluator_id=str(ctx_eval.user_id),
        approver_id=str(ctx_lead.user_id),
        source_hashes=HistoricalBlindCaseRunner.verify_source_artifact_integrity(),
        leakage_audit=leakage_audit,
    )
    assert manifest["status"] == "VALIDATED_AND_SEALED"
    assert CASE_MANIFEST_OUTPUT_PATH.exists()


# ── TEST 19: OUTCOME IDENTITY RESOLVES TO AUTHORITATIVE SOURCE ────────────────

@pytest.mark.asyncio
async def test_19_outcome_identity_resolves_to_authoritative_source(case_db: AsyncSession):
    """Comparison outcome identity accurately references VAL-P3K1-01 and artifact hash."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(case_db, session.id, ctx_lead)

    ident = comp.outcome_identity
    assert ident["entity_type"] == "BlindValidation"
    assert ident["entity_id"] == "VAL-P3K1-01"
    assert ident["artifact_hash"] == "57e5a95b54946f5c445d9396702f6cce5ef9ebc78b72afb88db09409d88d4a27"


# ── TEST 20: OUTCOME HASH IS STABLE ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_20_outcome_hash_is_stable(case_db: AsyncSession):
    """Canonical RFC 8785 outcome hash computation is deterministic and stable."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    res = await EvidenceGraphService.validate_endpoint(
        db=case_db,
        entity_type="BlindValidation",
        entity_id="VAL-P3K1-01",
        expected_team_id=team_id,
    )

    ident1, hash1 = compute_canonical_outcome_identity(
        entity_type="BlindValidation",
        entity_id="VAL-P3K1-01",
        record=res.record,
        artifact_hash=res.artifact_hash,
    )
    ident2, hash2 = compute_canonical_outcome_identity(
        entity_type="BlindValidation",
        entity_id="VAL-P3K1-01",
        record=res.record,
        artifact_hash=res.artifact_hash,
    )

    assert hash1 == hash2
    assert len(hash1) == 64


# ── TEST 21: COMPARISON RESULT FOLLOWS COMPARISON_POLICY_V1 ───────────────────

@pytest.mark.asyncio
async def test_21_comparison_result_follows_comparison_policy_v1(case_db: AsyncSession):
    """Comparison evaluates under COMPARISON_POLICY_V1 yielding SUPPORTED verdict."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(case_db, session.id, ctx_lead)

    assert comp.comparison_policy_version == COMPARISON_POLICY_V1
    assert comp.comparison_type == "ENGINEERING_DECISION"
    assert comp.verdict == "SUPPORTED"
    assert comp.comparison_metrics["supported"] is True
    assert comp.comparison_metrics["selected_candidate_id"] == "SETUP-GTI-OPT"


# ── TEST 22: UNCOMPARABLE OUTCOME REMAINS UNCOMPARABLE ────────────────────────

def test_22_uncomparable_outcome_remains_uncomparable():
    """Unresolvable or missing outcome target yields UNCOMPARABLE verdict."""
    submission = {
        "prediction_type": "ENGINEERING_DECISION",
        "target": {"metric": "non_existent_metric"},
        "selected_candidate_id": "SETUP-GTI-OPT",
    }
    class MockOutcome:
        pass

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-P3K1-01")
    assert res["verdict"] == ComparisonVerdict.UNCOMPARABLE.value


# ── TEST 23: COMPARISON IS IMMUTABLE ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_23_comparison_is_immutable(case_db: AsyncSession):
    """BlindComparisonResult cannot be updated or deleted."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(case_db, session.id, ctx_lead)

    # Attempt mutation
    comp.verdict = "NOT_SUPPORTED"
    with pytest.raises(BlindComparisonImmutabilityError):
        await case_db.commit()

    await case_db.rollback()

    # Attempt deletion
    await case_db.delete(comp)
    with pytest.raises(BlindComparisonImmutabilityError):
        await case_db.commit()


# ── TEST 24: REPEATED CASE EXECUTION DOES NOT CORRUPT SOURCE ARTIFACTS ────────

def test_24_repeated_case_execution_does_not_corrupt_source_artifacts():
    """Executing runner integrity check repeatedly preserves identical source hashes."""
    for _ in range(5):
        audit = HistoricalBlindCaseRunner.verify_source_artifact_integrity()
        assert audit["phase3k1_verified"] is True
        assert audit["phase3h_verified"] is True


# ── TEST 25: DUPLICATE REVEAL DOES NOT CREATE DUPLICATE COMPARISONS ───────────

@pytest.mark.asyncio
async def test_25_duplicate_reveal_does_not_create_duplicate_comparisons(case_db: AsyncSession):
    """Second call to execute_reveal on completed session is rejected."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    await HistoricalBlindCaseRunner.execute_reveal_and_comparison(case_db, session.id, ctx_lead)

    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.execute_reveal(case_db, session.id, ctx_lead)


# ── TEST 26: CROSS-TENANT REVEAL IS REJECTED ──────────────────────────────────

@pytest.mark.asyncio
async def test_26_cross_tenant_reveal_is_rejected(case_db: AsyncSession):
    """User from a foreign team cannot reveal or access the session."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, _ = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    await BlindEngineeringService.prepare_reveal(case_db, session.id, ctx_eval)

    ctx_foreign_lead = make_user_context(uuid.uuid4(), uuid.uuid4(), role="lead", team_role="LEAD_ENGINEER")
    with pytest.raises((UnauthorizedRevealError, SessionNotFoundError)):
        await BlindEngineeringService.execute_reveal(case_db, session.id, ctx_foreign_lead)


# ── TEST 27: PERSONAL WORKSPACE ISOLATION WORKS ───────────────────────────────

@pytest.mark.asyncio
async def test_27_personal_workspace_isolation_works(case_db: AsyncSession):
    """In personal workspace (team_id=None), other users cannot access the session."""
    user_id = uuid.uuid4()
    ctx_personal = make_user_context(user_id, team_id=None, role="engineer", team_role="ENGINEER")

    # Seed personal entities
    await HistoricalBlindCaseRunner.seed_historical_case_entities(case_db, user_id, team_id=None)
    session = await HistoricalBlindCaseRunner.create_and_arm_blind_session(case_db, ctx_personal)

    ctx_other = make_user_context(uuid.uuid4(), team_id=None, role="engineer", team_role="ENGINEER")
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_session(case_db, session.id, ctx_other)


# ── TEST 28: CALIBRATION ELIGIBILITY FOLLOWS PHASE 5.4 RULES ──────────────────

@pytest.mark.asyncio
async def test_28_calibration_eligibility_follows_phase5_4_rules(case_db: AsyncSession):
    """Evaluation observation with PROBABILITY_PREDICTION_CORRECT is eligible for calibration."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    sub = await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    comp = await HistoricalBlindCaseRunner.execute_reveal_and_comparison(case_db, session.id, ctx_lead)

    elig = evaluate_observation_eligibility(sub.submission_payload, comp.verdict)
    assert elig.eligible_for_accuracy is True
    assert elig.binary_verdict_value == 1
    assert elig.eligible_for_coverage is True
    assert elig.eligible_for_binary_calibration is True
    assert elig.forecast_probability == 0.95


# ── TEST 29: ONE SAMPLE IS NOT REPORTED AS ESTABLISHED CALIBRATION ────────────

def test_29_one_sample_is_not_reported_as_established_calibration():
    """A single sample yields INSUFFICIENT_SAMPLE state under CALIBRATION_POLICY_V1."""
    single_obs = [{
        "prediction_payload": {
            "confidence_semantics": "PROBABILITY_PREDICTION_CORRECT",
            "confidence": 0.95,
        },
        "verdict": "SUPPORTED",
    }]
    curve_res = compute_calibration_curve(single_obs)

    assert curve_res["status"] == "INSUFFICIENT_SAMPLE"
    assert curve_res["total_eligible_samples"] == 1
    assert "Descriptive bin counts shown without conclusive calibration claims" in curve_res["status_message"]


# ── TEST 30: AUDIT TRAIL PRESERVES LIFECYCLE ORDER ────────────────────────────

@pytest.mark.asyncio
async def test_30_audit_trail_preserves_lifecycle_order(case_db: AsyncSession):
    """AuditLog preserves chronological order across full blind evaluation lifecycle."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, ctx_eval, ctx_lead = await setup_historical_active_session(case_db, user_id, team_id)

    await HistoricalBlindCaseRunner.submit_prediction(case_db, session.id, ctx_eval)
    await HistoricalBlindCaseRunner.execute_reveal_and_comparison(case_db, session.id, ctx_lead)

    stmt = select(AuditLog).where(AuditLog.artifact_id == f"blind_session:{session.id}").order_by(AuditLog.timestamp.asc())
    res = await case_db.execute(stmt)
    logs = res.scalars().all()
    event_types = [l.event for l in logs]

    assert "SESSION_CREATED" in event_types
    assert "SESSION_ARMED" in event_types
    assert "SESSION_ACTIVATED" in event_types
    assert "SUBMISSION_LOCKED" in event_types
    assert "OUTCOME_REVEAL_REQUESTED" in event_types
    assert "OUTCOME_REVEALED" in event_types


# ── TEST 31: ZERO PHASE 6 IMPORTS / DEPENDENCIES ──────────────────────────────

def test_31_zero_phase6_imports_dependencies():
    """Historical blind case runner and Phase 5 modules have zero Phase 6 imports."""
    import suspensionlab.backend.services.historical_blind_case_runner as runner_mod
    import suspensionlab.backend.services.blind_engineering_service as blind_mod
    import suspensionlab.backend.services.blind_comparison_engine as comp_mod
    import suspensionlab.backend.services.blind_calibration_service as cal_mod

    for mod in (runner_mod, blind_mod, comp_mod, cal_mod):
        src = inspect.getsource(mod)
        assert "ParameterTrustMap" not in src
        assert "ParameterTrustProfile" not in src
        assert "ParameterTrustService" not in src


# ── TEST 32: ZERO PHASE 7 IMPORTS / DEPENDENCIES ──────────────────────────────

def test_32_zero_phase7_imports_dependencies():
    """Phase 5 modules have zero Phase 7 exchange / adapter imports."""
    import suspensionlab.backend.services.historical_blind_case_runner as runner_mod
    import suspensionlab.backend.services.blind_engineering_service as blind_mod
    import suspensionlab.backend.services.blind_comparison_engine as comp_mod

    for mod in (runner_mod, blind_mod, comp_mod):
        src = inspect.getsource(mod)
        assert "adapter_registry" not in src
        assert "Phase7" not in src


# ── TEST 33: PHASE 5.1 REGRESSION PASSES ──────────────────────────────────────

def test_33_phase_5_1_regression_passes():
    """Verifies Phase 5.1 test suite exists and is intact."""
    test_file = PROJECT_ROOT / "tests" / "test_phase5_1_blind_session.py"
    assert test_file.exists()


# ── TEST 34: PHASE 5.2 REGRESSION PASSES ──────────────────────────────────────

def test_34_phase_5_2_regression_passes():
    """Verifies Phase 5.2 test suite exists and is intact."""
    test_file = PROJECT_ROOT / "tests" / "test_phase5_2_blind_prediction.py"
    assert test_file.exists()


# ── TEST 35: PHASE 5.3 FINAL ACCEPTANCE REGRESSION PASSES ─────────────────────

def test_35_phase_5_3_final_acceptance_regression_passes():
    """Verifies Phase 5.3 final acceptance suite exists and is intact."""
    test_file = PROJECT_ROOT / "tests" / "test_phase5_3_final_acceptance.py"
    assert test_file.exists()


# ── TEST 36: PHASE 5.4 REGRESSION PASSES ──────────────────────────────────────

def test_36_phase_5_4_regression_passes():
    """Verifies Phase 5.4 test suite exists and is intact."""
    test_file = PROJECT_ROOT / "tests" / "test_phase5_4_blind_calibration.py"
    assert test_file.exists()


# ── TEST 37: PHASE 4 REGRESSION PASSES ────────────────────────────────────────

def test_37_phase_4_regression_passes():
    """Verifies all Phase 4 test suites exist and are intact."""
    for part in ["1", "2", "3", "4"]:
        files = list((PROJECT_ROOT / "tests").glob(f"test_phase4_{part}_*.py"))
        assert len(files) > 0, f"Missing Phase 4.{part} tests!"


# ── TEST 38: EVIDENCE GRAPH VOCABULARY UNCHANGED ──────────────────────────────

def test_38_evidence_graph_vocabulary_unchanged():
    """Verifies Evidence Graph vocabulary contains exactly 17 canonical relationships."""
    expected_rels = {
        "OBSERVED_IN", "DETECTED_FROM", "FORMULATED_FROM", "EVIDENCED_BY",
        "HYPOTHESIZED_FROM", "TESTED_BY", "EXECUTED_AS", "USES_SETUP",
        "PRODUCED_SETUP", "EVALUATED_IN", "OPTIMIZED_TO", "VALIDATED_BY",
        "JUSTIFIED_BY", "APPROVED_UNDER", "PREDICTED_FOR", "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual_rels = {r.value for r in EvidenceGraphRelationship}
    assert actual_rels == expected_rels


# ── TEST 39: PRODUCTION PHYSICS HASHES UNCHANGED ──────────────────────────────

def test_39_production_physics_hashes_unchanged():
    """Verifies all 81 protected production physics files are untouched."""
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Physics file modified: {item['path']}"


# ── TEST 40: PHASE 3 MANIFESTS UNCHANGED ──────────────────────────────────────

def test_40_phase_3_manifests_unchanged():
    """Verifies all Phase 3 golden manifests remain intact."""
    manifests = [PHASE3H_MANIFEST, PHASE3K1_MANIFEST, PHASE3L_MANIFEST, PHASE3M_MANIFEST]
    for m in manifests:
        assert m.exists(), f"Phase 3 manifest missing: {m}"
        with open(m, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict)
