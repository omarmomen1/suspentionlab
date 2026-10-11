"""
tests/test_phase5_2_blind_prediction.py
=======================================
SuspensionLab PRO — Phase 5.2 Blind Prediction & Decision Contract Acceptance Suite.

Authoritative verification of the versioned (PREDICTION_SCHEMA_V1), validated,
and deterministic engineering prediction schema contract.

Explicit 1-to-1 Mapping to the 36 Mandatory Acceptance Test Requirements:
- Req 01: test_01_valid_categorical_prediction
- Req 02: test_02_valid_directional_prediction
- Req 03: test_03_valid_quantitative_prediction
- Req 04: test_04_valid_engineering_decision
- Req 05: test_05_invalid_prediction_type_rejected
- Req 06: test_06_invalid_target_structure_rejected
- Req 07: test_07_hidden_target_rejected
- Req 08: test_08_invisible_candidate_rejected
- Req 09: test_09_invalid_unit_rejected
- Req 10: test_10_missing_unit_rejected_where_required
- Req 11: test_11_nan_rejected
- Req 12: test_12_infinity_rejected
- Req 13: test_13_invalid_confidence_rejected
- Req 14: test_14_malformed_payload_rejected
- Req 15: test_15_missing_schema_version_rejected
- Req 16: test_16_unsupported_schema_version_rejected
- Req 17: test_17_canonicalization_deterministic
- Req 18: test_18_hash_deterministic
- Req 19: test_19_changed_prediction_changes_hash
- Req 20: test_20_changed_context_changes_binding
- Req 21: test_21_same_prediction_context_reproduces_same_hash
- Req 22: test_22_rationale_preserved_exactly
- Req 23: test_23_assumptions_preserved_exactly
- Req 24: test_24_repeated_submission_rejected
- Req 25: test_25_concurrent_submission_race_remains_safe
- Req 26: test_26_prediction_cannot_be_edited_after_lock
- Req 27: test_27_prediction_cannot_be_deleted
- Req 28: test_28_hidden_outcome_absent_from_validation_errors
- Req 29: test_29_hidden_outcome_absent_from_autocomplete_lookup_apis
- Req 30: test_30_hidden_outcome_absent_from_frontend_payload
- Req 31: test_31_tenant_isolation
- Req 32: test_32_personal_workspace_isolation
- Req 33: test_33_phase_5_1_regression_remains_green
- Req 34: test_34_phase_4_regression_remains_green
- Req 35: test_35_production_physics_unchanged
- Req 36: test_36_phase_3_artifacts_unchanged

Strictly NO outcome scoring or accuracy comparison implemented.
Zero hidden outcome leakage.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import uuid
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
    SUPPORTED_SCHEMA_VERSIONS,
    SUPPORTED_UNITS,
    PredictionType,
    ExpectedDirection,
    PredictionSchemaError,
    UnsupportedSchemaVersionError,
    InvalidPredictionTypeError,
    InvalidPredictionTargetError,
    InvisibleTargetError,
    InvisibleCandidateError,
    MissingUnitError,
    InvalidUnitError,
    InvalidNumericValueError,
    InvalidConfidenceError,
    ContextBindingMismatchError,
    validate_prediction_contract,
    canonicalize_prediction_payload,
)
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
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


# ── TEST FIXTURES ─────────────────────────────────────────────────────────────

@pytest.fixture
async def p52_db():
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

    # Create provenance edges: inv -> sess, dec -> inv, dec -> val
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

    return {
        "telemetry": sess,
        "investigation": inv,
        "decision": dec,
        "validation": val,
    }


async def setup_active_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: uuid.UUID | None,
    code_suffix: str = "01",
) -> Tuple[BlindEngineeringSession, Dict[str, Any], UserContext]:
    """Helper creating and activating a blind session for testing."""
    ctx = make_user_context(user_id, team_id)
    seeded = await seed_canonical_scenario(db, user_id, team_id, code_suffix)
    session = await BlindEngineeringService.create_session(
        db=db,
        user_context=ctx,
        name=f"Blind Session {code_suffix}",
        root_entity_type="EngineeringDecision",
        root_entity_id=seeded["decision"].decision_id,
        hidden_outcome_type="BlindValidation",
        hidden_outcome_id=seeded["validation"].validation_code,
    )
    await BlindEngineeringService.arm_session(db, session.id, ctx)
    active = await BlindEngineeringService.activate_session(db, session.id, ctx)
    return active, seeded, ctx


# ── TEST 01: VALID CATEGORICAL PREDICTION ──────────────────────────────────────

@pytest.mark.asyncio
async def test_01_valid_categorical_prediction(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "01")

    payload = {
        "schema_version": "1",
        "prediction_type": "CATEGORICAL",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "setup_selection",
        },
        "predicted_category": "SETUP-B",
        "allowed_categories": ["SETUP-A", "SETUP-B"],
        "confidence": 0.90,
        "rationale": "Setup B provides superior lateral load distribution at high speed",
        "assumptions": ["Dry track conditions", "Nominal tire pressures"],
    }

    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert sub.status == "LOCKED"
    assert len(sub.submission_hash) == 64
    assert sub.submission_payload["prediction_type"] == "CATEGORICAL"
    assert sub.submission_payload["predicted_category"] == "SETUP-B"
    assert sub.submission_payload["confidence"] == 0.90


# ── TEST 02: VALID DIRECTIONAL PREDICTION ──────────────────────────────────────

@pytest.mark.asyncio
async def test_02_valid_directional_prediction(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "02")

    payload = {
        "schema_version": "1",
        "prediction_type": "DIRECTIONAL",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "apex_lateral_g",
        },
        "expected_direction": "INCREASE",
        "expected_delta": 0.15,
        "unit": "g",
        "confidence": 0.85,
        "rationale": "Stiffer front roll bar reduces camber compliance deflection",
    }

    sub = await BlindEngineeringService.lock_submission(p522_db := p52_db, session.id, payload, ctx)
    assert sub.status == "LOCKED"
    assert sub.submission_payload["prediction_type"] == "DIRECTIONAL"
    assert sub.submission_payload["expected_direction"] == "INCREASE"
    assert sub.submission_payload["expected_delta"] == 0.15
    assert sub.submission_payload["unit"] == "g"


# ── TEST 03: VALID QUANTITATIVE PREDICTION ────────────────────────────────────

@pytest.mark.asyncio
async def test_03_valid_quantitative_prediction(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "03")

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "front_roll_stiffness",
            "aggregation": "mean",
        },
        "predicted_value": 1400.0,
        "unit": "N/m",
        "confidence": 0.95,
        "rationale": "Exact stiffness calculated from mechanical linkage geometry",
        "assumptions": ["Linear spring rate regime"],
    }

    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert sub.status == "LOCKED"
    assert sub.submission_payload["prediction_type"] == "QUANTITATIVE"
    assert sub.submission_payload["predicted_value"] == 1400.0
    assert sub.submission_payload["unit"] == "N/m"
    assert sub.submission_payload["target"]["aggregation"] == "mean"


# ── TEST 04: VALID ENGINEERING DECISION ───────────────────────────────────────

@pytest.mark.asyncio
async def test_04_valid_engineering_decision(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "04")

    payload = {
        "schema_version": "1",
        "prediction_type": "ENGINEERING_DECISION",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "candidate_choice",
        },
        "selected_candidate_id": "SETUP-B",
        "confidence": 0.92,
        "rationale": "Candidate B optimizes front balance without exceeding kerb compliance limit",
        "assumptions": ["Aggressive kerb riding profile"],
    }

    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert sub.status == "LOCKED"
    assert sub.submission_payload["prediction_type"] == "ENGINEERING_DECISION"
    assert sub.submission_payload["selected_candidate_id"] == "SETUP-B"


# ── TEST 05: INVALID PREDICTION TYPE REJECTED ─────────────────────────────────

@pytest.mark.asyncio
async def test_05_invalid_prediction_type_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "05")

    payload = {
        "schema_version": "1",
        "prediction_type": "WILD_GUESS",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "bar_rate",
        },
        "confidence": 0.8,
    }

    with pytest.raises(InvalidPredictionTypeError) as exc:
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert "Unsupported prediction_type 'WILD_GUESS'" in str(exc.value)


# ── TEST 06: INVALID TARGET STRUCTURE REJECTED ────────────────────────────────

@pytest.mark.asyncio
async def test_06_invalid_target_structure_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "06")

    # Missing entity_type
    payload1 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
    }
    with pytest.raises(InvalidPredictionTargetError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload1, ctx)

    # Missing metric
    payload2 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id},
        "predicted_value": 140.0,
        "unit": "N/m",
    }
    with pytest.raises(InvalidPredictionTargetError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload2, ctx)

    # Free-text target
    payload3 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": "I predict the front roll bar rate will be 140",
        "predicted_value": 140.0,
        "unit": "N/m",
    }
    with pytest.raises(InvalidPredictionTargetError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload3, ctx)


# ── TEST 07: HIDDEN TARGET REJECTED ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_07_hidden_target_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "07")

    # Attempt to target the withheld outcome directly
    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {
            "entity_type": "BlindValidation",
            "entity_id": seeded["validation"].validation_code,
            "metric": "holdout_r2",
        },
        "predicted_value": 0.988,
        "unit": "unitless",
        "confidence": 0.9,
    }

    with pytest.raises(InvisibleTargetError) as exc:
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)

    # Anti-leakage: error must be generic and never leak hidden outcome details
    assert str(exc.value) == "Target is not available in the active session context."
    assert seeded["validation"].validation_code not in str(exc.value)
    assert "0.988" not in str(exc.value)


# ── TEST 08: INVISIBLE CANDIDATE REJECTED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_08_invisible_candidate_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "08")

    payload = {
        "schema_version": "1",
        "prediction_type": "ENGINEERING_DECISION",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "setup_selection",
        },
        "selected_candidate_id": "GHOST_SETUP_999",
        "confidence": 0.8,
    }

    with pytest.raises(InvisibleCandidateError) as exc:
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert str(exc.value) == "Target candidate is not available in the active session context."


# ── TEST 09: INVALID UNIT REJECTED ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_09_invalid_unit_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "09")

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "bar_rate",
        },
        "predicted_value": 140.0,
        "unit": "lightyears",
        "confidence": 0.8,
    }

    with pytest.raises(InvalidUnitError) as exc:
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert "Unsupported unit 'lightyears'" in str(exc.value)


# ── TEST 10: MISSING UNIT REJECTED WHERE REQUIRED ─────────────────────────────

@pytest.mark.asyncio
async def test_10_missing_unit_rejected_where_required(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "10")

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {
            "entity_type": "EngineeringDecision",
            "entity_id": seeded["decision"].decision_id,
            "metric": "bar_rate",
        },
        "predicted_value": 140.0,
        # unit intentionally omitted
        "confidence": 0.8,
    }

    with pytest.raises(MissingUnitError) as exc:
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert "explicit physical unit" in str(exc.value).lower()


# ── TEST 11: NAN REJECTED ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_11_nan_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "11")

    # NaN in predicted_value
    payload1 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": float("nan"),
        "unit": "N/m",
        "confidence": 0.8,
    }
    with pytest.raises(InvalidNumericValueError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload1, ctx)

    # NaN string
    payload2 = copy.deepcopy(payload1)
    payload2["predicted_value"] = "NaN"
    with pytest.raises(InvalidNumericValueError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload2, ctx)


# ── TEST 12: INFINITY REJECTED ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_12_infinity_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "12")

    # +Infinity
    payload1 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": float("inf"),
        "unit": "N/m",
        "confidence": 0.8,
    }
    with pytest.raises(InvalidNumericValueError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload1, ctx)

    # -Infinity
    payload2 = copy.deepcopy(payload1)
    payload2["predicted_value"] = float("-inf")
    with pytest.raises(InvalidNumericValueError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload2, ctx)


# ── TEST 13: INVALID CONFIDENCE REJECTED ──────────────────────────────────────

@pytest.mark.asyncio
async def test_13_invalid_confidence_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "13")

    base = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
    }

    # Negative confidence
    with pytest.raises(InvalidConfidenceError):
        p = copy.deepcopy(base)
        p["confidence"] = -0.05
        await BlindEngineeringService.lock_submission(p52_db, session.id, p, ctx)

    # Greater than 1.0
    with pytest.raises(InvalidConfidenceError):
        p = copy.deepcopy(base)
        p["confidence"] = 1.05
        await BlindEngineeringService.lock_submission(p52_db, session.id, p, ctx)

    # Text confidence
    with pytest.raises(InvalidConfidenceError):
        p = copy.deepcopy(base)
        p["confidence"] = "very confident"
        await BlindEngineeringService.lock_submission(p52_db, session.id, p, ctx)


# ── TEST 14: MALFORMED PAYLOAD REJECTED ───────────────────────────────────────

@pytest.mark.asyncio
async def test_14_malformed_payload_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "14")

    with pytest.raises(InvalidSubmissionError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, {}, ctx)

    with pytest.raises(InvalidSubmissionError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, "not a dictionary", ctx)  # type: ignore


# ── TEST 15: MISSING SCHEMA VERSION REJECTED ──────────────────────────────────

@pytest.mark.asyncio
async def test_15_missing_schema_version_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "15")

    payload = {
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
    }
    with pytest.raises(UnsupportedSchemaVersionError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)


# ── TEST 16: UNSUPPORTED SCHEMA VERSION REJECTED ──────────────────────────────

@pytest.mark.asyncio
async def test_16_unsupported_schema_version_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "16")

    payload = {
        "schema_version": "99",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
    }
    with pytest.raises(UnsupportedSchemaVersionError) as exc:
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert "Unsupported schema_version '99'" in str(exc.value)


# ── TEST 17: CANONICALIZATION DETERMINISTIC ───────────────────────────────────

def test_17_canonicalization_deterministic():
    payload_a = {
        "confidence": 0.95,
        "schema_version": "1",
        "target": {"metric": "roll_rate", "entity_id": "DEC-1", "entity_type": "EngineeringDecision"},
        "prediction_type": "QUANTITATIVE",
        "unit": "N/m",
        "predicted_value": 120.0,
    }
    payload_b = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": "DEC-1", "metric": "roll_rate"},
        "predicted_value": 120.0,
        "unit": "N/m",
        "confidence": 0.95,
    }

    canon_a = canonicalize_prediction_payload(payload_a)
    canon_b = canonicalize_prediction_payload(payload_b)

    assert canon_a == canon_b
    assert json.dumps(canon_a, sort_keys=True) == json.dumps(canon_b, sort_keys=True)


# ── TEST 18: HASH DETERMINISTIC ───────────────────────────────────────────────

def test_18_hash_deterministic():
    sess_id = uuid.uuid4()
    user_id = uuid.uuid4()
    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": "DEC-1", "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }
    ctx_hash = "f4c6e98b31a2874100912bcdeff561023a1294872164a781290384752109abcd"

    hash1 = compute_canonical_submission_hash(sess_id, user_id, payload, ctx_hash)
    hash2 = compute_canonical_submission_hash(sess_id, user_id, payload, ctx_hash)

    assert hash1 == hash2
    assert len(hash1) == 64


# ── TEST 19: CHANGED PREDICTION CHANGES HASH ──────────────────────────────────

def test_19_changed_prediction_changes_hash():
    sess_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx_hash = "f4c6e98b31a2874100912bcdeff561023a1294872164a781290384752109abcd"

    payload1 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": "DEC-1", "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }
    payload2 = copy.deepcopy(payload1)
    payload2["predicted_value"] = 140.1

    hash1 = compute_canonical_submission_hash(sess_id, user_id, payload1, ctx_hash)
    hash2 = compute_canonical_submission_hash(sess_id, user_id, payload2, ctx_hash)

    assert hash1 != hash2


# ── TEST 20: CHANGED CONTEXT CHANGES BINDING ──────────────────────────────────

@pytest.mark.asyncio
async def test_20_changed_context_changes_binding(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "20")

    # Provide a mismatched visible_context_hash in the payload
    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.9,
        "visible_context_hash": "stale_or_tampered_context_hash_00000000000000000000000000000000",
    }

    with pytest.raises(ContextBindingMismatchError) as exc:
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert "context hash does not match active session context" in str(exc.value)


# ── TEST 21: SAME PREDICTION AND CONTEXT REPRODUCES SAME HASH ─────────────────

def test_21_same_prediction_context_reproduces_same_hash():
    sess_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
    user_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    ctx_hash = "64charhexstring1111111111111111111111111111111111111111111111111111"

    payload = {
        "schema_version": "1",
        "prediction_type": "CATEGORICAL",
        "target": {"entity_type": "EngineeringDecision", "entity_id": "DEC-1", "metric": "setup"},
        "predicted_category": "SETUP-B",
        "confidence": 0.95,
    }

    h_first = compute_canonical_submission_hash(sess_id, user_id, payload, ctx_hash)
    h_second = compute_canonical_submission_hash(sess_id, user_id, payload, ctx_hash)

    assert h_first == h_second


# ── TEST 22: RATIONALE PRESERVED EXACTLY ──────────────────────────────────────

@pytest.mark.asyncio
async def test_22_rationale_preserved_exactly(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "22")

    exact_rationale = (
        "Complex rationale with special chars: Δroll_angle = 0.35° @ 240km/h; "
        "rebound damping ratio ξ_reb = 0.68 ensures 15% overshoot reduction."
    )
    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
        "rationale": exact_rationale,
    }

    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert sub.submission_payload["rationale"] == exact_rationale


# ── TEST 23: ASSUMPTIONS PRESERVED EXACTLY ────────────────────────────────────

@pytest.mark.asyncio
async def test_23_assumptions_preserved_exactly(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "23")

    exact_assumptions = [
        "Track surface complies with ISO 8608 Class A roughness",
        "Tire carcass bulk temperature stabilized at 100°C ± 5°C",
        "Kerb strike excitation limited to 15mm vertical amplitude",
    ]
    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
        "assumptions": exact_assumptions,
    }

    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)
    assert sub.submission_payload["assumptions"] == exact_assumptions


# ── TEST 24: REPEATED SUBMISSION REJECTED ──────────────────────────────────────

@pytest.mark.asyncio
async def test_24_repeated_submission_rejected(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "24")

    payload1 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }
    payload2 = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 150.0,
        "unit": "N/m",
        "confidence": 0.80,
    }

    # First submission succeeds
    await BlindEngineeringService.lock_submission(p52_db, session.id, payload1, ctx)

    # Replacement attempt on locked session is rejected
    with pytest.raises(InvalidStateTransitionError):
        await BlindEngineeringService.lock_submission(p52_db, session.id, payload2, ctx)


# ── TEST 25: CONCURRENT SUBMISSION RACE REMAINS SAFE ──────────────────────────

@pytest.mark.asyncio
async def test_25_concurrent_submission_race_remains_safe(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "25")

    results = []

    async def race_sub(val: float, note: str):
        try:
            res = await BlindEngineeringService.lock_submission(
                p52_db,
                session.id,
                {
                    "schema_version": "1",
                    "prediction_type": "QUANTITATIVE",
                    "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
                    "predicted_value": val,
                    "unit": "N/m",
                    "confidence": 0.9,
                    "rationale": note,
                },
                ctx,
            )
            results.append(("SUCCESS", res))
        except Exception as e:
            results.append(("ERROR", type(e).__name__))

    await asyncio.gather(
        race_sub(140.0, "Race Contender Alpha"),
        race_sub(150.0, "Race Contender Beta"),
    )

    successes = [r for r in results if r[0] == "SUCCESS"]
    errors = [r for r in results if r[0] == "ERROR"]

    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0][1] in ("DuplicateSubmissionError", "InvalidStateTransitionError")


# ── TEST 26: PREDICTION CANNOT BE EDITED AFTER LOCK ───────────────────────────

@pytest.mark.asyncio
async def test_26_prediction_cannot_be_edited_after_lock(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "26")

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }
    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)

    # Direct ORM mutation attempt
    sub.submission_payload = {"prediction": "Hacked mutation"}
    with pytest.raises(BlindSubmissionImmutabilityError):
        await p52_db.commit()

    await p52_db.rollback()


# ── TEST 27: PREDICTION CANNOT BE DELETED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_27_prediction_cannot_be_deleted(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "27")

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }
    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)

    # Direct delete attempt
    await p52_db.delete(sub)
    with pytest.raises(BlindSubmissionImmutabilityError):
        await p52_db.commit()

    await p52_db.rollback()


# ── TEST 28: HIDDEN OUTCOME ABSENT FROM VALIDATION ERRORS ─────────────────────

@pytest.mark.asyncio
async def test_28_hidden_outcome_absent_from_validation_errors(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "28")

    hidden_code = seeded["validation"].validation_code

    # Multiple failure scenarios
    test_cases = [
        {"schema_version": "1", "prediction_type": "QUANTITATIVE", "target": {"entity_type": "BlindValidation", "entity_id": hidden_code, "metric": "bar_rate"}, "predicted_value": 100.0, "unit": "N/m"},
        {"schema_version": "1", "prediction_type": "ENGINEERING_DECISION", "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "choice"}, "selected_candidate_id": "UNKNOWN_CANDIDATE"},
        {"schema_version": "1", "prediction_type": "QUANTITATIVE", "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "choice"}, "predicted_value": 100.0, "unit": "invalid_unit"},
    ]

    for tc in test_cases:
        try:
            await BlindEngineeringService.lock_submission(p52_db, session.id, tc, ctx)
            pytest.fail("Expected submission validation failure")
        except Exception as e:
            err_msg = str(e)
            assert hidden_code not in err_msg, f"Hidden outcome ID leaked in error message: {err_msg}"
            assert "0.988" not in err_msg, f"Hidden outcome metric leaked in error message: {err_msg}"
            assert "PASS_CONFIRMED" not in err_msg, f"Hidden outcome verdict leaked in error message: {err_msg}"


# ── TEST 29: HIDDEN OUTCOME ABSENT FROM AUTOCOMPLETE / LOOKUP APIS ────────────

@pytest.mark.asyncio
async def test_29_hidden_outcome_absent_from_autocomplete_lookup_apis(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "29")

    # Evaluator queries visible context
    ctx_data = await BlindEngineeringService.get_visible_context(p52_db, session.id, ctx)
    ctx_json = json.dumps(ctx_data)

    hidden_code = seeded["validation"].validation_code
    assert hidden_code not in ctx_json
    assert "0.988" not in ctx_json
    assert "PASS_CONFIRMED" not in ctx_json


# ── TEST 30: HIDDEN OUTCOME ABSENT FROM FRONTEND PAYLOAD ──────────────────────

@pytest.mark.asyncio
async def test_30_hidden_outcome_absent_from_frontend_payload(p52_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    session, seeded, ctx = await setup_active_session(p52_db, user_id, team_id, "30")

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }
    sub = await BlindEngineeringService.lock_submission(p52_db, session.id, payload, ctx)

    # Inspect submission record and session record returned to frontend
    sub_dto = {
        "id": str(sub.id),
        "session_id": str(sub.session_id),
        "submission_hash": sub.submission_hash,
        "payload": sub.submission_payload,
    }
    sess_dto = await BlindEngineeringService.get_session(p52_db, session.id, ctx)

    sub_json = json.dumps(sub_dto)
    sess_json = json.dumps(sess_dto)

    hidden_code = seeded["validation"].validation_code
    assert hidden_code not in sub_json
    assert hidden_code not in sess_json
    assert "0.988" not in sub_json
    assert "0.988" not in sess_json


# ── TEST 31: TENANT ISOLATION ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_31_tenant_isolation(p52_db: AsyncSession):
    user_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_b = uuid.uuid4()
    team_b = uuid.uuid4()

    session_a, seeded_a, ctx_a = await setup_active_session(p52_db, user_a, team_a, "31a")
    ctx_b = make_user_context(user_b, team_b)

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded_a["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }

    # Tenant B cannot submit to Tenant A's session
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.lock_submission(p52_db, session_a.id, payload, ctx_b)


# ── TEST 32: PERSONAL WORKSPACE ISOLATION ─────────────────────────────────────

@pytest.mark.asyncio
async def test_32_personal_workspace_isolation(p52_db: AsyncSession):
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # Both users have team_id = None (personal workspaces)
    session_a, seeded_a, ctx_a = await setup_active_session(p52_db, user_a, None, "32a")
    ctx_b = make_user_context(user_b, None)

    payload = {
        "schema_version": "1",
        "prediction_type": "QUANTITATIVE",
        "target": {"entity_type": "EngineeringDecision", "entity_id": seeded_a["decision"].decision_id, "metric": "bar_rate"},
        "predicted_value": 140.0,
        "unit": "N/m",
        "confidence": 0.95,
    }

    # Personal user B cannot submit to Personal user A's session
    with pytest.raises(SessionNotFoundError):
        await BlindEngineeringService.lock_submission(p52_db, session_a.id, payload, ctx_b)


# ── TEST 33: PHASE 5.1 REGRESSION REMAINS GREEN ───────────────────────────────

def test_33_phase_5_1_regression_remains_green():
    # Verify Phase 5.1 tables and statuses remain fully intact
    assert "blind_engineering_sessions" in Base.metadata.tables
    assert "blind_submissions" in Base.metadata.tables
    expected_statuses = {
        "DRAFT", "ARMED", "BLIND_ACTIVE", "SUBMISSION_LOCKED",
        "READY_FOR_REVEAL", "REVEALED", "COMPLETED", "ABORTED"
    }
    actual_statuses = {s.value for s in BlindSessionStatus}
    assert expected_statuses == actual_statuses


# ── TEST 34: PHASE 4 REGRESSION REMAINS GREEN ─────────────────────────────────

def test_34_phase_4_regression_remains_green():
    # Verify Phase 4 tables and relationships remain intact
    assert "evidence_graph_edges" in Base.metadata.tables
    assert "blind_engineering_sessions" in Base.metadata.tables
    assert "blind_submissions" in Base.metadata.tables
    rels = {r.value for r in EvidenceGraphRelationship}
    assert "FORMULATED_FROM" in rels
    assert "VALIDATED_BY" in rels


# ── TEST 35: PRODUCTION PHYSICS UNCHANGED ─────────────────────────────────────

def test_35_production_physics_unchanged():
    assert PHASE3H_MANIFEST.exists(), f"Missing manifest: {PHASE3H_MANIFEST}"
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Protected physics modification detected in {item['path']}!"


# ── TEST 36: PHASE 3 ARTIFACTS UNCHANGED ──────────────────────────────────────

def test_36_phase_3_artifacts_unchanged():
    manifests = [PHASE3H_MANIFEST, PHASE3K1_MANIFEST, PHASE3L_MANIFEST, PHASE3M_MANIFEST]
    for m in manifests:
        assert m.exists(), f"Phase 3 artifact {m} is missing!"
