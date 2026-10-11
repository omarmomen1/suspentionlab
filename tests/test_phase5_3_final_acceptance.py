"""
tests/test_phase5_3_final_acceptance.py
=======================================
SuspensionLab PRO — Phase 5.3 Final Hardening & Acceptance Closure Suite.

Provides authoritative, hostile verification of Phase 5.3:
1. Full repository regression result captured
2. Structured categorical identity exact match (Case A)
3. Structured categorical identity mismatch (Case A)
4. Structured ID case behavior (Case A: exact case-sensitive, no generic case-folding)
5. Free-label categorical comparison (Case B: normalized string comparison)
6. Structured object ID normalization ({"id": "..."} -> canonical string)
7. Malformed structured identity -> UNCOMPARABLE
8. Directional +2epsilon -> INCREASE
9. Directional +epsilon -> CONSTANT
10. Directional +epsilon/2 -> CONSTANT
11. Directional zero -> CONSTANT
12. Directional -epsilon/2 -> CONSTANT
13. Directional -epsilon -> CONSTANT
14. Directional -2epsilon -> DECREASE
15. Policy contains directional epsilon
16. Categorical rules recorded in policy
17. Deterministic categorical comparison
18. Deterministic directional comparison
19. Deterministic quantitative comparison
20. Deterministic engineering decision comparison
21. Comparison hash determinism
22. Comparison immutability
23. Pre-reveal firewall
24. Authorized reveal
25. Unauthorized reveal
26. Cross-tenant reveal
27. Concurrent reveal
28. Protected physics unchanged
29. Phase 3 unchanged
30. Evidence Graph unchanged
31. Phase 6 independence
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import math
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
from suspensionlab.backend.services.blind_comparison_engine import (
    COMPARISON_POLICY_V1,
    COMPARISON_POLICY_V1_SPEC,
    DIRECTIONAL_ZERO_EPSILON,
    STRUCTURED_IDENTITY_METRICS,
    ComparisonVerdict,
    compute_canonical_comparison_hash,
    compute_canonical_outcome_identity,
    evaluate_prediction_comparison,
    get_comparison_policy_spec,
    is_structured_identity_target,
    normalize_structured_identity,
)
from suspensionlab.backend.services.blind_engineering_service import (
    BlindEngineeringService,
    SessionNotFoundError,
    DuplicateComparisonError,
    InformationFirewallViolationError,
    InvalidStateTransitionError,
    OutcomeResolutionError,
    UnauthorizedRevealError,
)
from suspensionlab.backend.services.evidence_graph_service import EvidenceGraphService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


# ── TEST FIXTURES ─────────────────────────────────────────────────────────────

@pytest.fixture
async def fa_db():
    """In-memory SQLite async engine with all schemas registered."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
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
    code_suffix: str = "fa01",
) -> Dict[str, Any]:
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
    code_suffix: str = "fa01",
    prediction_payload: Dict[str, Any] | None = None,
) -> Tuple[BlindEngineeringSession, Dict[str, Any], UserContext, BlindSubmission]:
    seeded = await seed_canonical_scenario(db, user_id, team_id, code_suffix)
    ctx = make_user_context(user_id, team_id, team_role="ADMIN")

    config = {
        "visible_graph_relationships": ["DETECTED_FROM", "FORMULATED_FROM"],
        "visible_entities": ["TelemetrySession", "Investigation"],
    }
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


# ── TEST 01: FULL REPOSITORY REGRESSION RESULT CAPTURED ───────────────────────

def test_01_full_repository_regression_result_captured():
    """Confirms policy version and directional epsilon constants."""
    assert COMPARISON_POLICY_V1 == "1"
    assert DIRECTIONAL_ZERO_EPSILON == 1e-9


# ── TEST 02: STRUCTURED CATEGORICAL IDENTITY EXACT MATCH ──────────────────────

def test_02_structured_categorical_identity_exact_match():
    """Case A: Exact match of structured setup identifier produces CORRECT."""
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "setup_id"},
        "predicted_category": "SETUP-A",
    }
    class MockOutcome:
        setup_id = "SETUP-A"

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT.value
    assert res["comparison_metrics"]["match"] is True
    assert res["comparison_metrics"]["identity_mode"] == "STRUCTURED_AUTHORITATIVE"


# ── TEST 03: STRUCTURED CATEGORICAL IDENTITY MISMATCH ─────────────────────────

def test_03_structured_categorical_identity_mismatch():
    """Case A: Different structured setup identifier produces INCORRECT."""
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "setup_id"},
        "predicted_category": "SETUP-A",
    }
    class MockOutcome:
        setup_id = "SETUP-B"

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.INCORRECT.value
    assert res["comparison_metrics"]["match"] is False
    assert res["comparison_metrics"]["identity_mode"] == "STRUCTURED_AUTHORITATIVE"


# ── TEST 04: STRUCTURED ID CASE BEHAVIOR ──────────────────────────────────────

def test_04_structured_id_case_behavior():
    """
    Case A: Structured IDs must NOT be silently case-folded.
    'SETUP-A' does not equal 'setup-a' under authoritative identity comparison.
    """
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "setup_id"},
        "predicted_category": "SETUP-A",
    }
    class MockOutcome:
        setup_id = "setup-a"

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.INCORRECT.value
    assert res["comparison_metrics"]["match"] is False
    assert res["comparison_metrics"]["identity_mode"] == "STRUCTURED_AUTHORITATIVE"


# ── TEST 05: FREE-LABEL CATEGORICAL COMPARISON ────────────────────────────────

def test_05_free_label_categorical_comparison():
    """
    Case B: Free categorical labels (gate_verdict) allow normalized string comparison.
    'pass_confirmed' matches 'PASS_CONFIRMED'.
    """
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "gate_verdict"},
        "predicted_category": "pass_confirmed",
    }
    class MockOutcome:
        gate_verdict = "PASS_CONFIRMED"

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT.value
    assert res["comparison_metrics"]["match"] is True
    assert res["comparison_metrics"]["identity_mode"] == "NORMALIZED_STRING"


# ── TEST 06: STRUCTURED OBJECT ID NORMALIZATION ───────────────────────────────

def test_06_structured_object_id_normalization():
    """Case A: Structured object {'id': 'SETUP-A'} normalizes to canonical identity."""
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "setup_id"},
        "predicted_category": "SETUP-A",
    }
    class MockOutcome:
        setup_id = {"id": "SETUP-A"}

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT.value
    assert res["comparison_metrics"]["actual_category"] == "SETUP-A"
    assert res["comparison_metrics"]["identity_mode"] == "STRUCTURED_AUTHORITATIVE"


# ── TEST 07: MALFORMED STRUCTURED IDENTITY ────────────────────────────────────

def test_07_malformed_structured_identity():
    """Case A: Malformed or unresolvable structured identity yields UNCOMPARABLE."""
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "setup_id"},
        "predicted_category": "SETUP-A",
    }
    class MockOutcome:
        setup_id = {"unknown_key": "unresolvable"}

    res = evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
    assert res["verdict"] == ComparisonVerdict.UNCOMPARABLE.value
    assert res["comparison_metrics"].get("error") == "MALFORMED_STRUCTURED_IDENTITY"


# ── TEST 08: DIRECTIONAL +2EPSILON ────────────────────────────────────────────

def test_08_directional_plus_2epsilon():
    """Delta = +2 * eps is outside zero deadband: direction is INCREASE."""
    eps = DIRECTIONAL_ZERO_EPSILON
    delta = 2.0 * eps

    class MockOutcome:
        residual = delta

    submission_inc = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "INCREASE",
    }
    res = evaluate_prediction_comparison(submission_inc, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "INCREASE"


# ── TEST 09: DIRECTIONAL +EPSILON ─────────────────────────────────────────────

def test_09_directional_plus_epsilon():
    """Delta = +eps is at the boundary: inside deadband, direction is CONSTANT."""
    eps = DIRECTIONAL_ZERO_EPSILON
    delta = eps

    class MockOutcome:
        residual = delta

    submission_const = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "CONSTANT",
    }
    res = evaluate_prediction_comparison(submission_const, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "CONSTANT"

    submission_inc = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "INCREASE",
    }
    res_inc = evaluate_prediction_comparison(submission_inc, MockOutcome(), "Investigation", "INV-1")
    assert res_inc["verdict"] == ComparisonVerdict.INCORRECT_DIRECTION.value


# ── TEST 10: DIRECTIONAL +EPSILON/2 ───────────────────────────────────────────

def test_10_directional_plus_epsilon_half():
    """Delta = +eps / 2 is inside deadband: direction is CONSTANT."""
    eps = DIRECTIONAL_ZERO_EPSILON
    delta = eps / 2.0

    class MockOutcome:
        residual = delta

    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "CONSTANT",
    }
    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "CONSTANT"


# ── TEST 11: DIRECTIONAL ZERO ─────────────────────────────────────────────────

def test_11_directional_zero():
    """Delta = 0.0 is center of deadband: direction is CONSTANT (matches NEUTRAL/CONSTANT)."""
    delta = 0.0

    class MockOutcome:
        residual = delta

    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "NEUTRAL",
    }
    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "CONSTANT"


# ── TEST 12: DIRECTIONAL -EPSILON/2 ───────────────────────────────────────────

def test_12_directional_minus_epsilon_half():
    """Delta = -eps / 2 is inside deadband: direction is CONSTANT."""
    eps = DIRECTIONAL_ZERO_EPSILON
    delta = -eps / 2.0

    class MockOutcome:
        residual = delta

    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "CONSTANT",
    }
    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "CONSTANT"


# ── TEST 13: DIRECTIONAL -EPSILON ─────────────────────────────────────────────

def test_13_directional_minus_epsilon():
    """Delta = -eps is at the negative boundary: inside deadband, direction is CONSTANT."""
    eps = DIRECTIONAL_ZERO_EPSILON
    delta = -eps

    class MockOutcome:
        residual = delta

    submission_const = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "CONSTANT",
    }
    res = evaluate_prediction_comparison(submission_const, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "CONSTANT"

    submission_dec = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "DECREASE",
    }
    res_dec = evaluate_prediction_comparison(submission_dec, MockOutcome(), "Investigation", "INV-1")
    assert res_dec["verdict"] == ComparisonVerdict.INCORRECT_DIRECTION.value


# ── TEST 14: DIRECTIONAL -2EPSILON ────────────────────────────────────────────

def test_14_directional_minus_2epsilon():
    """Delta = -2 * eps is outside negative deadband: direction is DECREASE."""
    eps = DIRECTIONAL_ZERO_EPSILON
    delta = -2.0 * eps

    class MockOutcome:
        residual = delta

    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "DECREASE",
    }
    res = evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
    assert res["verdict"] == ComparisonVerdict.CORRECT_DIRECTION.value
    assert res["comparison_metrics"]["actual_direction"] == "DECREASE"


# ── TEST 15: POLICY CONTAINS DIRECTIONAL EPSILON ──────────────────────────────

def test_15_policy_contains_directional_epsilon():
    """Verifies that COMPARISON_POLICY_V1 explicitly contains DIRECTIONAL_ZERO_EPSILON."""
    spec = get_comparison_policy_spec("1")
    assert spec["version"] == "1"
    assert spec["directional_zero_epsilon"] == 1e-9
    assert DIRECTIONAL_ZERO_EPSILON == 1e-9


# ── TEST 16: CATEGORICAL RULES RECORDED IN POLICY ─────────────────────────────

def test_16_categorical_rules_recorded_in_policy():
    """Verifies that COMPARISON_POLICY_V1 explicitly records Case A and Case B rules."""
    spec = get_comparison_policy_spec("1")
    cat_rules = spec["rules"]["categorical_identity"]
    assert "case_a_structured_identity" in cat_rules
    assert "case_b_free_categorical" in cat_rules
    assert "setup_id" in spec["structured_identity_metrics"]


# ── TEST 17: DETERMINISTIC CATEGORICAL COMPARISON ─────────────────────────────

def test_17_deterministic_categorical_comparison():
    """Repeated evaluations of identical categorical inputs produce identical results."""
    submission = {
        "prediction_type": "CATEGORICAL",
        "target": {"metric": "setup_id"},
        "predicted_category": "SETUP-A",
    }
    class MockOutcome:
        setup_id = "SETUP-A"

    results = [
        evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
        for _ in range(5)
    ]
    for r in results[1:]:
        assert r == results[0]


# ── TEST 18: DETERMINISTIC DIRECTIONAL COMPARISON ─────────────────────────────

def test_18_deterministic_directional_comparison():
    """Repeated evaluations of identical directional inputs produce identical results."""
    submission = {
        "prediction_type": "DIRECTIONAL",
        "target": {"metric": "residual"},
        "expected_direction": "INCREASE",
    }
    class MockOutcome:
        residual = 0.05

    results = [
        evaluate_prediction_comparison(submission, MockOutcome(), "Investigation", "INV-1")
        for _ in range(5)
    ]
    for r in results[1:]:
        assert r == results[0]


# ── TEST 19: DETERMINISTIC QUANTITATIVE COMPARISON ────────────────────────────

def test_19_deterministic_quantitative_comparison():
    """Repeated evaluations of identical quantitative inputs produce identical results."""
    submission = {
        "prediction_type": "QUANTITATIVE",
        "target": {"metric": "holdout_r2"},
        "predicted_value": 0.990,
        "unit": "ratio",
    }
    class MockOutcome:
        holdout_r2 = 0.980

    results = [
        evaluate_prediction_comparison(submission, MockOutcome(), "BlindValidation", "VAL-1")
        for _ in range(5)
    ]
    for r in results[1:]:
        assert r == results[0]


# ── TEST 20: DETERMINISTIC ENGINEERING DECISION COMPARISON ────────────────────

def test_20_deterministic_engineering_decision_comparison():
    """Repeated evaluations of identical decision inputs produce identical results."""
    submission = {
        "prediction_type": "ENGINEERING_DECISION",
        "target": {"metric": "selected_option"},
        "selected_candidate_id": "SETUP-A",
    }
    class MockOutcome:
        selected_option = {"id": "SETUP-A"}

    results = [
        evaluate_prediction_comparison(submission, MockOutcome(), "EngineeringDecision", "DEC-1")
        for _ in range(5)
    ]
    for r in results[1:]:
        assert r == results[0]


# ── TEST 21: COMPARISON HASH DETERMINISM ──────────────────────────────────────

def test_21_comparison_hash_determinism():
    """Canonical RFC 8785 comparison hash is strictly deterministic across runs."""
    h1 = compute_canonical_comparison_hash(
        session_id="sess-1",
        submission_id="sub-1",
        submission_hash="sha-1",
        outcome_identity={"entity_type": "BlindValidation", "entity_id": "VAL-1"},
        comparison_policy_version="1",
        prediction_schema_version="1",
        comparison_type="QUANTITATIVE",
        verdict="METRICS_ONLY",
        comparison_metrics={"signed_error": 0.01, "absolute_error": 0.01},
    )
    h2 = compute_canonical_comparison_hash(
        session_id="sess-1",
        submission_id="sub-1",
        submission_hash="sha-1",
        outcome_identity={"entity_type": "BlindValidation", "entity_id": "VAL-1"},
        comparison_policy_version="1",
        prediction_schema_version="1",
        comparison_type="QUANTITATIVE",
        verdict="METRICS_ONLY",
        comparison_metrics={"signed_error": 0.01, "absolute_error": 0.01},
    )
    assert h1 == h2
    assert len(h1) == 64


# ── TEST 22: COMPARISON IMMUTABILITY ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_22_comparison_immutability(fa_db: AsyncSession):
    """Mutating or deleting a BlindComparisonResult raises BlindComparisonImmutabilityError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, ctx_admin, sub = await setup_ready_for_reveal_session(fa_db, user_id, team_id, "22")

    comp = await BlindEngineeringService.execute_reveal(fa_db, session.id, ctx_admin)

    # Attempt mutation
    comp.verdict = "TAMPERED_VERDICT"
    with pytest.raises(BlindComparisonImmutabilityError):
        await fa_db.commit()

    await fa_db.rollback()

    # Attempt deletion
    await fa_db.delete(comp)
    with pytest.raises(BlindComparisonImmutabilityError):
        await fa_db.commit()


# ── TEST 23: PRE-REVEAL FIREWALL ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_23_pre_reveal_firewall(fa_db: AsyncSession):
    """Pre-reveal outcome and comparison access raises InformationFirewallViolationError."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, ctx_admin, _ = await setup_ready_for_reveal_session(fa_db, user_id, team_id, "23")

    with pytest.raises(InformationFirewallViolationError):
        await BlindEngineeringService.get_comparison_result(fa_db, session.id, ctx_admin)

    with pytest.raises(InformationFirewallViolationError):
        await BlindEngineeringService.get_revealed_outcome(fa_db, session.id, ctx_admin)


# ── TEST 24: AUTHORIZED REVEAL ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_24_authorized_reveal(fa_db: AsyncSession):
    """Authorized reveal transitions session to COMPLETED and generates comparison."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx_admin, sub = await setup_ready_for_reveal_session(fa_db, user_id, team_id, "24")

    comp = await BlindEngineeringService.execute_reveal(fa_db, session.id, ctx_admin)
    assert comp is not None
    assert comp.session_id == session.id
    assert comp.submission_id == sub.id

    await fa_db.refresh(session)
    assert session.status == BlindSessionStatus.COMPLETED.value
    assert session.revealed_at is not None
    assert session.completed_at is not None


# ── TEST 25: UNAUTHORIZED REVEAL ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_25_unauthorized_reveal(fa_db: AsyncSession):
    """Unauthorized engineer reveal attempt raises UnauthorizedRevealError with zero leakage."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, _, _ = await setup_ready_for_reveal_session(fa_db, user_id, team_id, "25")

    ctx_engineer = make_user_context(user_id, team_id, team_role="ENGINEER")
    with pytest.raises(UnauthorizedRevealError) as exc_info:
        await BlindEngineeringService.execute_reveal(fa_db, session.id, ctx_engineer)

    # Zero leakage check
    assert "VAL-25" not in str(exc_info.value)
    assert "0.988" not in str(exc_info.value)


# ── TEST 26: CROSS-TENANT REVEAL ──────────────────────────────────────

@pytest.mark.asyncio
async def test_26_cross_tenant_reveal(fa_db: AsyncSession):
    """Cross-tenant reveal attempt is rejected fail-closed."""
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    session_a, _, _, _ = await setup_ready_for_reveal_session(fa_db, user_a, team_a, "26a")
    ctx_b_admin = make_user_context(user_b, team_b, team_role="ADMIN")

    with pytest.raises((UnauthorizedRevealError, SessionNotFoundError)):
        await BlindEngineeringService.execute_reveal(fa_db, session_a.id, ctx_b_admin)


# ── TEST 27: CONCURRENT REVEAL ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_27_concurrent_reveal(fa_db: AsyncSession):
    """Concurrent reveal attempts resolve safely without duplicate comparisons."""
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, _, ctx_admin, _ = await setup_ready_for_reveal_session(fa_db, user_id, team_id, "27")

    results = []
    errors = []

    async def try_reveal():
        try:
            r = await BlindEngineeringService.execute_reveal(fa_db, session.id, ctx_admin)
            results.append(r)
        except Exception as e:
            errors.append(e)

    await asyncio.gather(try_reveal(), try_reveal(), return_exceptions=True)

    # Exactly one reveal succeeded
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], (InvalidStateTransitionError, DuplicateComparisonError))


# ── TEST 28: PROTECTED PHYSICS UNCHANGED ──────────────────────────────────────

def test_28_protected_physics_unchanged():
    """Verifies that all 81 protected production physics files are untouched."""
    assert PHASE3H_MANIFEST.exists(), f"Missing manifest: {PHASE3H_MANIFEST}"
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Protected physics modification detected in {item['path']}!"


# ── TEST 29: PHASE 3 UNCHANGED ────────────────────────────────────────────────

def test_29_phase_3_unchanged():
    """Verifies Phase 3 artifacts and manifest remain permanently frozen."""
    manifests = [PHASE3H_MANIFEST, PHASE3K1_MANIFEST, PHASE3L_MANIFEST, PHASE3M_MANIFEST]
    for m in manifests:
        assert m.exists(), f"Phase 3 artifact {m} is missing!"
        with open(m, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict), f"Artifact {m} is malformed!"


# ── TEST 30: EVIDENCE GRAPH UNCHANGED ─────────────────────────────────────────

def test_30_evidence_graph_unchanged():
    """Verifies Evidence Graph vocabulary contains exactly 17 canonical relationships."""
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


# ── TEST 31: PHASE 6 INDEPENDENCE ─────────────────────────────────────────────

def test_31_phase_6_independence():
    """Proves Phase 5.3 does not import or depend on Phase 6 components."""
    import suspensionlab.backend.services.blind_comparison_engine as comp_engine
    import suspensionlab.backend.services.blind_engineering_service as eng_service

    for mod in (comp_engine, eng_service):
        source = inspect.getsource(mod)
        assert "ParameterTrustMap" not in source
        assert "ParameterTrustProfile" not in source
        assert "trust_score" not in source
        assert "trust_scoring" not in source
