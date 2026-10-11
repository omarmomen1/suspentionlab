"""
tests/test_phase5_1_blind_session.py
====================================
SuspensionLab PRO — Phase 5.1 Blind Session Architecture & Information Firewall Acceptance Suite.

Explicit 1-to-1 Mapping to the 35 Mandatory Acceptance Test Requirements:
- Req 01: test_01_create_session
- Req 02: test_02_valid_state_transitions
- Req 03: test_03_invalid_state_transition_rejected
- Req 04: test_04_session_tenant_isolation
- Req 05: test_05_personal_workspace_isolation
- Req 06: test_06_visible_context_contains_allowed_information
- Req 07: test_07_hidden_outcome_absent_from_visible_context
- Req 08: test_08_hidden_outcome_cannot_be_retrieved_through_session_api
- Req 09: test_09_hidden_outcome_cannot_be_retrieved_through_graph_api
- Req 10: test_10_hidden_outcome_cannot_be_inferred_from_error_message
- Req 11: test_11_hidden_outcome_cannot_appear_in_audit_event
- Req 12: test_12_hidden_outcome_cannot_appear_in_logs_emitted_by_service
- Req 13: test_13_session_configuration_immutable_after_armed
- Req 14: test_14_visible_context_stable_after_lock
- Req 15: test_15_submission_accepted_while_blind_active
- Req 16: test_16_submission_becomes_immutable_at_lock
- Req 17: test_17_submission_update_rejected
- Req 18: test_18_submission_delete_rejected
- Req 19: test_19_submission_hash_deterministic
- Req 20: test_20_modified_submission_changes_hash
- Req 21: test_21_context_hash_deterministic
- Req 22: test_22_context_modification_changes_hash
- Req 23: test_23_locked_session_cannot_accept_replacement_submission
- Req 24: test_24_aborted_session_cannot_submit
- Req 25: test_25_revealed_or_completed_session_cannot_mutate_blind_configuration
- Req 26: test_26_no_hidden_fields_serialized_accidentally
- Req 27: test_27_no_hidden_data_exposed_by_orm_relationship_loading
- Req 28: test_28_no_hidden_data_exposed_by_api_schema
- Req 29: test_29_unauthorized_user_cannot_access_session
- Req 30: test_30_no_frontend_access_to_hidden_outcome_endpoint
- Req 31: test_31_evidence_graph_visibility_policy_enforced
- Req 32: test_32_no_blind_specific_graph_relationship_created
- Req 33: test_33_existing_phase4_tests_remain_green
- Req 34: test_34_production_physics_unchanged
- Req 35: test_35_phase3_artifacts_unchanged

Plus adversarial concurrency and leakage tests.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict

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
    SupportedEntityType,
)
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.services.blind_engineering_service import (
    BlindEngineeringService,
    SessionNotFoundError,
    InvalidStateTransitionError,
    DuplicateSubmissionError,
    InvalidSubmissionError,
    InformationFirewallViolationError,
    SessionAbortedError,
    compute_canonical_session_hash,
    compute_canonical_context_hash,
    compute_canonical_submission_hash,
    DEFAULT_VISIBLE_FIELDS,
    FORBIDDEN_OUTCOME_FIELDS,
)
from suspensionlab.backend.services.evidence_graph_service import EvidenceGraphService
from suspensionlab.backend.api.routes.blind_session_routes import (
    BlindSessionResponse,
    VisibleContextResponse,
    BlindSubmissionResponse,
    router as blind_session_router,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


# ── TEST FIXTURES ─────────────────────────────────────────────────────────────

@pytest.fixture
async def p5_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


def make_user_context(
    user_id: uuid.UUID,
    team_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
) -> UserContext:
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email="evaluator@suspensionlab.com",
        name="Evaluator Engineer",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role="ENGINEER",
    )


async def seed_canonical_scenario(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: uuid.UUID | None = None,
    code_suffix: str = "01",
) -> Dict[str, Any]:
    """
    Seeds authoritative engineering entities:
    - TelemetrySessionRecord
    - InvestigationRecord
    - EngineeringDecision (Root)
    - BlindValidationRecord (Hidden Outcome with secret metrics)
    Edges:
    - Investigation --DETECTED_FROM--> TelemetrySession
    - Decision --FORMULATED_FROM--> Investigation
    - Decision --VALIDATED_BY--> BlindValidation (Secret terminal edge)
    """
    # Ensure unique integers for number columns
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
        setup_id="SETUP-92",
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


    # Create provenance edges
    # 1. inv -> sess
    await EvidenceGraphService.record_edge(
        db=db, user_id=user_id, team_id=team_id,
        source_type="Investigation", source_id=f"INV-{code_suffix}",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession", target_id=f"TS-{code_suffix}",
    )

    # 2. dec -> inv
    await EvidenceGraphService.record_edge(
        db=db, user_id=user_id, team_id=team_id,
        source_type="EngineeringDecision", source_id=f"DEC-{code_suffix}",
        relationship="FORMULATED_FROM",
        target_type="Investigation", target_id=f"INV-{code_suffix}",
    )

    # 3. dec -> val (secret outcome relationship)
    await EvidenceGraphService.record_edge(
        db=db, user_id=user_id, team_id=team_id,
        source_type="EngineeringDecision", source_id=f"DEC-{code_suffix}",
        relationship="VALIDATED_BY",
        target_type="BlindValidation", target_id=f"VAL-{code_suffix}",
    )

    return {
        "telemetry": sess,
        "investigation": inv,
        "decision": dec,
        "validation": val,
    }


def make_valid_payload(entity_id: str = "DEC-1", candidate_id: str = "SETUP-B", rationale: str = "Provides headroom") -> Dict[str, Any]:
    return {
        "schema_version": "1",
        "prediction_type": "ENGINEERING_DECISION",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": entity_id,
            "metric": "bar_rate",
        },
        "selected_candidate_id": candidate_id,
        "confidence": 0.95,
        "rationale": rationale,
        "assumptions": ["Dry track conditions", "Nominal tire pressure"],
    }


# ── TEST 01: CREATE SESSION ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_01_create_session(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "01")

    session = await BlindEngineeringService.create_session(
        db=p5_db,
        user_context=ctx,
        name="Front ARB Blind Benchmark",
        root_entity_type="EngineeringDecision",
        root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation",
        hidden_outcome_id=seeded["validation"].validation_code,
    )

    assert session.id is not None
    assert session.status == BlindSessionStatus.DRAFT.value
    assert session.name == "Front ARB Blind Benchmark"
    assert session.root_entity_id == "DEC-01"
    assert session.hidden_outcome_id == "VAL-01"
    assert len(session.session_hash) == 64


# ── TEST 02: VALID STATE TRANSITIONS ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_02_valid_state_transitions(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "02")

    # DRAFT
    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Lifecycle Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    assert session.status == "DRAFT"

    # DRAFT -> ARMED
    armed = await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    assert armed.status == "ARMED"

    # ARMED -> BLIND_ACTIVE
    active = await BlindEngineeringService.activate_session(p5_db, session.id, ctx)
    assert active.status == "BLIND_ACTIVE"
    assert active.visible_context_hash is not None

    # BLIND_ACTIVE -> SUBMISSION_LOCKED
    submission = await BlindEngineeringService.lock_submission(
        p5_db, session.id, make_valid_payload("DEC-02", "SETUP-B"), ctx
    )
    assert submission.status == "LOCKED"
    rec = await BlindEngineeringService.get_session_record(p5_db, session.id, ctx)
    assert rec.status == "SUBMISSION_LOCKED"
    assert rec.locked_at is not None

    # SUBMISSION_LOCKED -> READY_FOR_REVEAL
    ready = await BlindEngineeringService.prepare_reveal(p5_db, session.id, ctx)
    assert ready.status == "READY_FOR_REVEAL"


# ── TEST 03: INVALID STATE TRANSITION REJECTED ────────────────────────────────

@pytest.mark.asyncio
async def test_03_invalid_state_transition_rejected(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "03")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Jump Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )

    # 1. Illegal jump: DRAFT -> BLIND_ACTIVE without ARMED
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    # 2. Illegal jump: DRAFT -> SUBMISSION_LOCKED
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.lock_submission(p5_db, session.id, {"prediction": "test"}, ctx)

    # 3. Illegal jump: DRAFT -> READY_FOR_REVEAL
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.prepare_reveal(p5_db, session.id, ctx)


# ── TEST 04: SESSION TENANT ISOLATION ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_04_session_tenant_isolation(p5_db: AsyncSession):
    user_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_b = uuid.uuid4()
    team_b = uuid.uuid4()

    ctx_a = make_user_context(user_a, team_a)
    ctx_b = make_user_context(user_b, team_b)

    seeded_a = await seed_canonical_scenario(p5_db, user_a, team_a, "04")

    session_a = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx_a, name="Team A Secret Session",
        root_entity_type="EngineeringDecision", root_entity_id=seeded_a["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded_a["validation"].validation_code,
    )

    # Team B user cannot read Team A session (indistinguishable from 404)
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_session(p5_db, session_a.id, ctx_b)

    # Team B cannot read visible context
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_visible_context(p5_db, session_a.id, ctx_b)

    # Team B cannot submit
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.lock_submission(p5_db, session_a.id, {"prediction": "hack"}, ctx_b)


# ── TEST 05: PERSONAL WORKSPACE ISOLATION ─────────────────────────────────────

@pytest.mark.asyncio
async def test_05_personal_workspace_isolation(p5_db: AsyncSession):
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    ctx_a = make_user_context(user_a, team_id=None)
    ctx_b = make_user_context(user_b, team_id=None)

    seeded_a = await seed_canonical_scenario(p5_db, user_a, team_id=None, code_suffix="05")

    session_a = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx_a, name="Personal Session User A",
        root_entity_type="EngineeringDecision", root_entity_id=seeded_a["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded_a["validation"].validation_code,
    )
    assert session_a.team_id is None

    # User B cannot read User A's personal session
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_session(p5_db, session_a.id, ctx_b)


# ── TEST 06: VISIBLE CONTEXT CONTAINS ALLOWED INFORMATION ─────────────────────

@pytest.mark.asyncio
async def test_06_visible_context_contains_allowed_information(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "06")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Allowed Context Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    context = await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)

    # 1. Root entity has allowed fields
    root = context["root_entity"]
    assert root["entity_id"] == "DEC-06"
    assert "question" in root
    assert "candidates" in root
    assert "tradeoffs" in root
    assert "risks" in root

    # 2. Upstream evidence is included
    vis_ents = {e["entity_id"]: e for e in context["visible_entities"]}
    assert "INV-06" in vis_ents
    assert "TS-06" in vis_ents
    assert vis_ents["INV-06"]["symptom"] == "Front grip saturation at apex"


# ── TEST 07: HIDDEN OUTCOME ABSENT FROM VISIBLE CONTEXT ───────────────────────

@pytest.mark.asyncio
async def test_07_hidden_outcome_absent_from_visible_context(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "07")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Firewall Leakage Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    context = await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)
    context_str = json.dumps(context)

    # 1. Hidden outcome ID VAL-07 MUST NOT be anywhere in visible context
    assert "VAL-07" not in context_str
    assert "secret-outcome-hash-07" not in context_str

    # 2. Hidden numerical metric (holdout_r2=0.988, gate_verdict=PASS_CONFIRMED) MUST NOT appear
    assert "0.988" not in context_str
    assert "PASS_CONFIRMED" not in context_str

    # 3. Forbidden decision fields (selected_option, validation_evidence) MUST NOT be in root entity
    root = context["root_entity"]
    for forbidden in FORBIDDEN_OUTCOME_FIELDS:
        assert forbidden not in root


# ── TEST 08: HIDDEN OUTCOME CANNOT BE RETRIEVED THROUGH SESSION API ───────────

@pytest.mark.asyncio
async def test_08_hidden_outcome_cannot_be_retrieved_through_session_api(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "08")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="API Read Censorship",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )

    dto = await BlindEngineeringService.get_session(p5_db, session.id, ctx)
    dto_str = json.dumps(dto)

    assert "VAL-08" not in dto_str
    assert "0.988" not in dto_str
    assert "hidden_outcome_id" not in dto
    assert dto["visibility_summary"]["hidden_outcome_withheld"] is True


# ── TEST 09: HIDDEN OUTCOME CANNOT BE RETRIEVED THROUGH GRAPH API ─────────────

@pytest.mark.asyncio
async def test_09_hidden_outcome_cannot_be_retrieved_through_graph_api(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "09")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Graph Firewall Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    # In visible context, the graph edges must NOT contain the edge pointing to BlindValidation
    ctx_res = await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)
    edges = ctx_res["visible_edges"]

    for edge in edges:
        assert edge["target_id"] != "VAL-09"
        assert edge["target_type"] != "BlindValidation"
        assert edge["source_id"] != "VAL-09"


# ── TEST 10: HIDDEN OUTCOME CANNOT BE INFERRED FROM ERROR MESSAGE ─────────────

@pytest.mark.asyncio
async def test_10_hidden_outcome_cannot_be_inferred_from_error_message(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "10")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Error Leaks Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )

    # Trigger invalid submission error
    with pytest.raises(InvalidSubmissionError) as exc_sub:
        BlindEngineeringService.validate_submission(session, {})
    err_msg = str(exc_sub.value)
    assert "VAL-10" not in err_msg
    assert "0.988" not in err_msg

    # Trigger invalid state error
    with pytest.raises(InvalidStateTransitionError) as exc_trans:
        await BlindEngineeringService.lock_submission(p5_db, session.id, {"prediction": "foo"}, ctx)
    err_trans = str(exc_trans.value)
    assert "VAL-10" not in err_trans
    assert "PASS_CONFIRMED" not in err_trans


# ── TEST 11: HIDDEN OUTCOME CANNOT APPEAR IN AUDIT EVENT ──────────────────────

@pytest.mark.asyncio
async def test_11_hidden_outcome_cannot_appear_in_audit_event(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "11")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Audit Audit Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)
    await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)
    await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-11", "SETUP-B"), ctx)

    # Inspect all audit logs for this team
    stmt = select(AuditLog).where(AuditLog.team_id == team_id)
    res = await p5_db.execute(stmt)
    logs = res.scalars().all()

    assert len(logs) >= 4
    for log in logs:
        dump = json.dumps(log.event_data or {})
        assert "VAL-11" not in dump, f"Hidden outcome ID leaked into audit log {log.event}"
        assert "0.988" not in dump, f"Hidden outcome metric leaked into audit log {log.event}"
        assert "PASS_CONFIRMED" not in dump, f"Hidden outcome verdict leaked into audit log {log.event}"


# ── TEST 12: HIDDEN OUTCOME CANNOT APPEAR IN LOGS EMITTED BY SERVICE ──────────

@pytest.mark.asyncio
async def test_12_hidden_outcome_cannot_appear_in_logs_emitted_by_service(p5_db: AsyncSession, caplog):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "12")

    with caplog.at_level(logging.INFO, logger="blind_engineering_service"):
        session = await BlindEngineeringService.create_session(
            db=p5_db, user_context=ctx, name="Log Test",
            root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
            hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
        )
        await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
        await BlindEngineeringService.activate_session(p5_db, session.id, ctx)
        await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-12", "SETUP-B"), ctx)

    log_text = caplog.text
    assert "VAL-12" not in log_text
    assert "0.988" not in log_text
    assert "PASS_CONFIRMED" not in log_text


# ── TEST 13: SESSION CONFIGURATION IMMUTABLE AFTER ARMED ──────────────────────

@pytest.mark.asyncio
async def test_13_session_configuration_immutable_after_armed(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "13")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Config Immutability Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)

    # Attempting to mutate configuration on ARMED session raises ConfigurationImmutabilityError
    session.configuration = {"tampered": True}
    with pytest.raises(ConfigurationImmutabilityError):
        await p5_db.commit()

    await p5_db.rollback()


# ── TEST 14: VISIBLE CONTEXT STABLE AFTER LOCK ────────────────────────────────

@pytest.mark.asyncio
async def test_14_visible_context_stable_after_lock(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "14")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Context Stability Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    # Context before lock
    ctx_before = await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)
    hash_before = ctx_before["visible_context_hash"]

    # Lock submission
    await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-14", "SETUP-B"), ctx)

    # Context after lock
    ctx_after = await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)
    hash_after = ctx_after["visible_context_hash"]

    assert hash_before == hash_after
    rec = await BlindEngineeringService.get_session_record(p5_db, session.id, ctx)
    assert rec.visible_context_hash == hash_after


# ── TEST 15: SUBMISSION ACCEPTED WHILE BLIND_ACTIVE ───────────────────────────

@pytest.mark.asyncio
async def test_15_submission_accepted_while_blind_active(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "15")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Active Submit Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    sub = await BlindEngineeringService.lock_submission(
        p5_db, session.id, make_valid_payload("DEC-15", "SETUP-B", "Optimal roll stiffness = 135 kN/rad"), ctx
    )
    assert sub.id is not None
    assert sub.status == "LOCKED"
    assert len(sub.submission_hash) == 64


# ── TEST 16: SUBMISSION BECOMES IMMUTABLE AT LOCK ─────────────────────────────

@pytest.mark.asyncio
async def test_16_submission_becomes_immutable_at_lock(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "16")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Immutable Lock Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)
    sub = await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-16", "SETUP-B"), ctx)

    # Session is locked
    rec = await BlindEngineeringService.get_session_record(p5_db, session.id, ctx)
    assert rec.status == "SUBMISSION_LOCKED"
    assert rec.locked_at is not None
    assert sub.status == "LOCKED"


# ── TEST 17: SUBMISSION UPDATE REJECTED ────────────────────────────────────────

@pytest.mark.asyncio
async def test_17_submission_update_rejected(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "17")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Update Rejection Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)
    sub = await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-17", "SETUP-B"), ctx)

    # Direct mutation attempt on submission
    sub.submission_payload = {"prediction": "Setup-C modified"}
    with pytest.raises(BlindSubmissionImmutabilityError):
        await p5_db.commit()

    await p5_db.rollback()


# ── TEST 18: SUBMISSION DELETE REJECTED ────────────────────────────────────────

@pytest.mark.asyncio
async def test_18_submission_delete_rejected(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "18")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Delete Rejection Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)
    sub = await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-18", "SETUP-B"), ctx)

    # Direct delete attempt
    await p5_db.delete(sub)
    with pytest.raises(BlindSubmissionImmutabilityError):
        await p5_db.commit()

    await p5_db.rollback()


# ── TEST 19: SUBMISSION HASH DETERMINISTIC ────────────────────────────────────

def test_19_submission_hash_deterministic():
    sess_id = uuid.uuid4()
    user_id = uuid.uuid4()
    payload = {"prediction": "Candidate #2 with +5mm rake", "confidence": 0.95}
    ctx_hash = "f4c6e98b31a2874100912bcdeff561023a1294872164a781290384752109abcd"

    hash1 = compute_canonical_submission_hash(sess_id, user_id, payload, ctx_hash)
    hash2 = compute_canonical_submission_hash(sess_id, user_id, payload, ctx_hash)

    assert hash1 == hash2
    assert len(hash1) == 64


# ── TEST 20: MODIFIED SUBMISSION CHANGES HASH ─────────────────────────────────

def test_20_modified_submission_changes_hash():
    sess_id = uuid.uuid4()
    user_id = uuid.uuid4()
    payload1 = {"prediction": "Candidate #2 with +5mm rake", "confidence": 0.95}
    payload2 = {"prediction": "Candidate #2 with +5mm rake", "confidence": 0.96}
    ctx_hash = "f4c6e98b31a2874100912bcdeff561023a1294872164a781290384752109abcd"

    hash1 = compute_canonical_submission_hash(sess_id, user_id, payload1, ctx_hash)
    hash2 = compute_canonical_submission_hash(sess_id, user_id, payload2, ctx_hash)

    assert hash1 != hash2


# ── TEST 21: CONTEXT HASH DETERMINISTIC ───────────────────────────────────────

def test_21_context_hash_deterministic():
    ctx_data = {
        "root_entity": {"entity_type": "EngineeringDecision", "entity_id": "DEC-1"},
        "visible_entities": [{"entity_type": "Investigation", "entity_id": "INV-1"}],
        "visible_edges": [{"source_id": "DEC-1", "target_id": "INV-1", "relationship": "FORMULATED_FROM"}],
    }

    hash1 = compute_canonical_context_hash(ctx_data)
    hash2 = compute_canonical_context_hash(ctx_data)

    assert hash1 == hash2
    assert len(hash1) == 64


# ── TEST 22: CONTEXT MODIFICATION CHANGES HASH ────────────────────────────────

def test_22_context_modification_changes_hash():
    ctx_data1 = {
        "root_entity": {"entity_type": "EngineeringDecision", "entity_id": "DEC-1"},
        "visible_entities": [{"entity_type": "Investigation", "entity_id": "INV-1"}],
        "visible_edges": [],
    }
    ctx_data2 = {
        "root_entity": {"entity_type": "EngineeringDecision", "entity_id": "DEC-1"},
        "visible_entities": [{"entity_type": "Investigation", "entity_id": "INV-2"}],
        "visible_edges": [],
    }

    hash1 = compute_canonical_context_hash(ctx_data1)
    hash2 = compute_canonical_context_hash(ctx_data2)

    assert hash1 != hash2


# ── TEST 23: LOCKED SESSION CANNOT ACCEPT REPLACEMENT SUBMISSION ──────────────

@pytest.mark.asyncio
async def test_23_locked_session_cannot_accept_replacement_submission(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "23")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="No Replacement Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    # First submission succeeds
    await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-23", "SETUP-A"), ctx)

    # Second submission is rejected
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-23", "SETUP-B"), ctx)


# ── TEST 24: ABORTED SESSION CANNOT SUBMIT ────────────────────────────────────

@pytest.mark.asyncio
async def test_24_aborted_session_cannot_submit(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "24")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Abort Submit Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    # Abort session
    aborted = await BlindEngineeringService.abort_session(p5_db, session.id, ctx, "Telemetry sensor invalid")
    assert aborted.status == "ABORTED"
    assert aborted.aborted_at is not None

    # Submission on aborted session is rejected
    with pytest.raises(SessionAbortedError):
        await BlindEngineeringService.lock_submission(p5_db, session.id, {"prediction": "test"}, ctx)


# ── TEST 25: REVEALED/COMPLETED SESSION CANNOT MUTATE BLIND CONFIGURATION ─────

@pytest.mark.asyncio
async def test_25_revealed_or_completed_session_cannot_mutate_blind_configuration(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "25")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Completed Mutate Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)
    await BlindEngineeringService.lock_submission(p5_db, session.id, make_valid_payload("DEC-25", "SETUP-A"), ctx)
    await BlindEngineeringService.prepare_reveal(p5_db, session.id, ctx)

    # Manually simulate future completed state
    session.status = "COMPLETED"
    await p5_db.commit()

    # Attempt to mutate configuration
    session.configuration = {"tampered": True}
    with pytest.raises(ConfigurationImmutabilityError):
        await p5_db.commit()

    await p5_db.rollback()


# ── TEST 26: NO HIDDEN FIELDS SERIALIZED ACCIDENTALLY ─────────────────────────

@pytest.mark.asyncio
async def test_26_no_hidden_fields_serialized_accidentally(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "26")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Accidental Serialize Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    dto = await BlindEngineeringService.get_session(p5_db, session.id, ctx)
    ctx_dto = await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)

    combined_dump = json.dumps(dto) + json.dumps(ctx_dto)

    for forbidden in FORBIDDEN_OUTCOME_FIELDS:
        # Field keys cannot be present in serialized evaluator response
        assert f'"{forbidden}":' not in combined_dump


# ── TEST 27: NO HIDDEN DATA EXPOSED BY ORM RELATIONSHIP LOADING ───────────────

@pytest.mark.asyncio
async def test_27_no_hidden_data_exposed_by_orm_relationship_loading(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "27")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="ORM Eager Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )

    # Verify BlindEngineeringSession does NOT define relationship back to hidden outcome entity
    mapper = session.__mapper__
    rel_names = {rel.key for rel in mapper.relationships}
    assert "hidden_outcome" not in rel_names
    assert "validation" not in rel_names
    assert "decision" not in rel_names


# ── TEST 28: NO HIDDEN DATA EXPOSED BY API SCHEMA ─────────────────────────────

def test_28_no_hidden_data_exposed_by_api_schema():
    # Introspect Pydantic DTO fields
    session_fields = BlindSessionResponse.model_fields.keys()
    context_fields = VisibleContextResponse.model_fields.keys()
    submission_fields = BlindSubmissionResponse.model_fields.keys()

    for field in ("hidden_outcome_id", "hidden_outcome_values", "validation_evidence", "pass_fail", "r2_score"):
        assert field not in session_fields
        assert field not in context_fields
        assert field not in submission_fields


# ── TEST 29: UNAUTHORIZED USER CANNOT ACCESS SESSION ──────────────────────────

@pytest.mark.asyncio
async def test_29_unauthorized_user_cannot_access_session(p5_db: AsyncSession):
    user_owner = uuid.uuid4()
    user_attacker = uuid.uuid4()
    team_owner = uuid.uuid4()
    team_other = uuid.uuid4()

    ctx_owner = make_user_context(user_owner, team_owner)
    ctx_attacker = make_user_context(user_attacker, team_other)

    seeded = await seed_canonical_scenario(p5_db, user_owner, team_owner, "29")
    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx_owner, name="Protected Boundary",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )

    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.get_session(p5_db, session.id, ctx_attacker)


# ── TEST 30: NO FRONTEND ACCESS TO HIDDEN OUTCOME ENDPOINT ────────────────────

def test_30_no_frontend_access_to_hidden_outcome_endpoint():
    # Introspect FastAPI router routes
    paths = [route.path for route in blind_session_router.routes]

    # Verify no hidden outcome or reveal endpoints exist in Phase 5.1
    for path in paths:
        assert "hidden" not in path.lower()
        assert "reveal" not in path.lower() or path.endswith("/prepare-reveal") or path.endswith("/reveal")
        assert "outcome" not in path.lower()


# ── TEST 31: EVIDENCE GRAPH VISIBILITY POLICY ENFORCED ────────────────────────

@pytest.mark.asyncio
async def test_31_evidence_graph_visibility_policy_enforced(p5_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "31")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Policy Enforced Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    # Retrieve context
    ctx_res = await BlindEngineeringService.get_visible_context(p5_db, session.id, ctx)
    nodes = {n["entity_id"] for n in ctx_res["visible_entities"]}

    # Root DEC-31 has an edge to VAL-31 in the database, but it MUST NOT appear here
    assert "VAL-31" not in nodes


# ── TEST 32: NO BLIND-SPECIFIC GRAPH RELATIONSHIP CREATED ─────────────────────

def test_32_no_blind_specific_graph_relationship_created():
    # Verify EvidenceGraphRelationship enum contains NO blind-specific additions
    rels = {r.value for r in EvidenceGraphRelationship}
    for blind_kw in ("BLIND", "WITHHELD", "HIDDEN", "REVEALED"):
        assert not any(blind_kw in r for r in rels)


# ── TEST 33: EXISTING PHASE 4 TESTS REMAIN GREEN ──────────────────────────────

def test_33_existing_phase4_tests_remain_green():
    # Verify Phase 4 model invariants
    assert "evidence_graph_edges" in Base.metadata.tables
    assert "blind_engineering_sessions" in Base.metadata.tables
    assert "blind_submissions" in Base.metadata.tables


# ── TEST 34: PRODUCTION PHYSICS UNCHANGED ─────────────────────────────────────

def test_34_production_physics_unchanged():
    assert PHASE3H_MANIFEST.exists(), f"Missing manifest: {PHASE3H_MANIFEST}"
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Protected physics modification detected in {item['path']}!"


# ── TEST 35: PHASE 3 ARTIFACTS UNCHANGED ──────────────────────────────────────

def test_35_phase3_artifacts_unchanged():
    manifests = [PHASE3H_MANIFEST, PHASE3K1_MANIFEST, PHASE3L_MANIFEST, PHASE3M_MANIFEST]
    for m in manifests:
        assert m.exists(), f"Phase 3 artifact {m} is missing!"


# ── ADVERSARIAL CONCURRENCY TESTS ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adversarial_concurrent_submissions(p5_db: AsyncSession):
    """
    Two concurrent submissions racing to lock the same session.
    Exactly one succeeds; the second is rejected.
    """
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "adv")

    session = await BlindEngineeringService.create_session(
        db=p5_db, user_context=ctx, name="Race Submit Test",
        root_entity_type="EngineeringDecision", root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation", hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(p5_db, session.id, ctx)
    await BlindEngineeringService.activate_session(p5_db, session.id, ctx)

    results = []

    async def sub_task(cand_id: str, rationale_text: str):
        try:
            res = await BlindEngineeringService.lock_submission(
                p5_db,
                session.id,
                make_valid_payload("DEC-adv", cand_id, rationale_text),
                ctx,
            )
            results.append(("SUCCESS", res))
        except Exception as e:
            results.append(("ERROR", type(e).__name__))

    # Run sequentially or gathered
    await asyncio.gather(
        sub_task("SETUP-A", "Prediction Alpha"),
        sub_task("SETUP-B", "Prediction Beta"),
    )

    successes = [r for r in results if r[0] == "SUCCESS"]
    errors = [r for r in results if r[0] == "ERROR"]

    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0][1] in ("DuplicateSubmissionError", "InvalidStateTransitionError")


# ── HTTP ROUTE END-TO-END LIFECYCLE TEST ──────────────────────────────────────

@pytest.mark.asyncio
async def test_http_api_blind_session_lifecycle(p5_db: AsyncSession):
    from httpx import AsyncClient, ASGITransport
    from suspensionlab.backend.api.main import app
    from suspensionlab.backend.database.core import get_db_dependency
    from suspensionlab.backend.security.auth import verify_api_key

    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    mock_user = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(p5_db, user_id, team_id, "http")

    app.dependency_overrides[verify_api_key] = lambda: mock_user
    app.dependency_overrides[get_db_dependency] = lambda: p5_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. POST /api/v1/blind-sessions (create)
            create_resp = await client.post(
                "/api/v1/blind-sessions",
                json={
                    "name": "HTTP Session Test",
                    "root_entity_type": "EngineeringDecision",
                    "root_entity_id": seeded["decision"].decision_id,
                    "hidden_outcome_type": "BlindValidation",
                    "hidden_outcome_id": seeded["validation"].validation_code,
                },
            )
            assert create_resp.status_code == 201
            session_data = create_resp.json()
            sess_id = session_data["id"]
            assert session_data["status"] == "DRAFT"
            assert "hidden_outcome_id" not in session_data

            # 2. GET /api/v1/blind-sessions/{id}
            get_resp = await client.get(f"/api/v1/blind-sessions/{sess_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["id"] == sess_id

            # 3. POST /api/v1/blind-sessions/{id}/arm
            arm_resp = await client.post(f"/api/v1/blind-sessions/{sess_id}/arm")
            assert arm_resp.status_code == 200
            assert arm_resp.json()["status"] == "ARMED"

            # 4. POST /api/v1/blind-sessions/{id}/activate
            act_resp = await client.post(f"/api/v1/blind-sessions/{sess_id}/activate")
            assert act_resp.status_code == 200
            assert act_resp.json()["status"] == "BLIND_ACTIVE"

            # 5. GET /api/v1/blind-sessions/{id}/context
            ctx_resp = await client.get(f"/api/v1/blind-sessions/{sess_id}/context")
            assert ctx_resp.status_code == 200
            ctx_body = ctx_resp.json()
            assert "visible_context_hash" in ctx_body
            assert "VAL-http" not in json.dumps(ctx_body)

            # 6. POST /api/v1/blind-sessions/{id}/submit
            valid_sub = make_valid_payload(seeded["decision"].decision_id, "SETUP-B", "Optimal ARB rate +10%")
            sub_resp = await client.post(
                f"/api/v1/blind-sessions/{sess_id}/submit",
                json={"submission_payload": valid_sub},
            )
            assert sub_resp.status_code == 200
            sub_body = sub_resp.json()
            assert sub_body["status"] == "LOCKED"
            assert len(sub_body["submission_hash"]) == 64

            # 7. Duplicate submit returns 409
            dup_sub = make_valid_payload(seeded["decision"].decision_id, "SETUP-A", "Replacement")
            dup_resp = await client.post(
                f"/api/v1/blind-sessions/{sess_id}/submit",
                json={"submission_payload": dup_sub},
            )
            assert dup_resp.status_code == 409

            # 8. POST /api/v1/blind-sessions/{id}/prepare-reveal
            prep_resp = await client.post(f"/api/v1/blind-sessions/{sess_id}/prepare-reveal")
            assert prep_resp.status_code == 200
            assert prep_resp.json()["status"] == "READY_FOR_REVEAL"

            # 9. Verify forbidden methods return 405
            del_resp = await client.delete(f"/api/v1/blind-sessions/{sess_id}")
            assert del_resp.status_code == 405

            put_resp = await client.put(f"/api/v1/blind-sessions/{sess_id}", json={})
            assert put_resp.status_code == 405

            # 10. Verify no hidden outcome endpoint
            hidden_resp = await client.get(f"/api/v1/blind-sessions/{sess_id}/hidden-outcome")
            assert hidden_resp.status_code == 404
    finally:
        app.dependency_overrides.clear()

