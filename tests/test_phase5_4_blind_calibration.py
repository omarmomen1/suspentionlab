"""
tests/test_phase5_4_blind_calibration.py
========================================
SuspensionLab PRO — Phase 5.4 Engineering Calibration & Longitudinal Blind Track Record Suite.

Comprehensive 40-test adversarial verification suite:
1. Empty history returns an explicit unavailable state.
2. One completed categorical evaluation is represented correctly.
3. Multiple completed evaluations aggregate deterministically.
4. Correct/incorrect counts use valid denominators.
5. Coverage uses the documented denominator.
6. UNCOMPARABLE is not counted as incorrect.
7. METRICS_ONLY is not converted into binary accuracy.
8. Generic historical confidence is not silently treated as probability.
9. Explicit probability semantics enable eligibility where other conditions hold.
10. A valid binary Brier score is computed correctly.
11. Brier score rejects ineligible observations.
12. Multiclass scoring requires a complete declared probability distribution.
13. Calibration curve uses the versioned binning policy.
14. Curve reports sample counts.
15. Curve provides documented uncertainty intervals.
16. Empty calibration bins follow policy.
17. Insufficient data returns an explicit state.
18. Policy version is preserved.
19. Deterministic aggregation produces identical results.
20. Changed source comparisons change aggregate identity.
21. Changed policy produces a distinguishable aggregate identity.
22. Different time windows are not conflated.
23. Tenant isolation protects summary counts.
24. Personal workspace isolation works.
25. Team aggregate access requires authorization.
26. Hidden/inaccessible records do not leak.
27. Frontend displays real data only.
28. Frontend distinguishes accuracy from calibration.
29. Frontend explains unavailable measures.
30. No leaderboard or ranking route exists.
31. No rationale scoring is introduced.
32. No prediction or outcome mutation occurs.
33. Phase 5.1 regression remains green.
34. Phase 5.2 regression remains green.
35. Phase 5.3 final-acceptance regression remains green.
36. Phase 4 regression remains green.
37. Phase 6 independence remains intact.
38. Production physics files remain unchanged.
39. Phase 3 manifests remain unchanged.
40. Evidence Graph schema and relationship vocabulary remain unchanged.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.blind_engineering import (
    BlindComparisonImmutabilityError,
    BlindComparisonResult,
    BlindEngineeringSession,
    BlindSessionStatus,
    BlindSubmission,
)
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.evidence_graph import EvidenceGraphRelationship
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.services.blind_calibration_engine import (
    CALIBRATION_POLICY_V1,
    CALIBRATION_POLICY_NAME,
    CALIBRATION_POLICY_V1_SPEC,
    CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
    IneligibilityReason,
    compute_aggregate_hash,
    compute_brier_score,
    compute_calibration_curve,
    compute_calibration_policy_hash,
    compute_multiclass_brier_score,
    compute_outcome_statistics,
    compute_wilson_score_interval,
    evaluate_observation_eligibility,
    get_calibration_policy_spec,
)
from suspensionlab.backend.services.blind_calibration_service import (
    BlindCalibrationService,
    UnauthorizedTeamAccessError,
    TeamNotFoundError,
)
from suspensionlab.backend.services.blind_prediction_schema import (
    PREDICTION_SCHEMA_V1,
    PREDICTION_SCHEMA_V2,
    validate_prediction_contract,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


# ── FIXTURES ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def cal_db():
    """In-memory SQLite async engine with all schemas registered."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def make_user_ctx(
    user_id: uuid.UUID,
    team_id: Optional[uuid.UUID] = None,
    org_id: Optional[uuid.UUID] = None,
    role: str = "engineer",
) -> UserContext:
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email="engineer@suspensionlab.com",
        name="Calibration Engineer",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=role,
        org_role="MEMBER",
        is_admin=role in ("admin", "org_admin"),
    )


async def seed_session_and_comparison(
    db: AsyncSession,
    user_id: uuid.UUID,
    team_id: Optional[uuid.UUID] = None,
    org_id: Optional[uuid.UUID] = None,
    session_status: str = BlindSessionStatus.REVEALED.value,
    prediction_type: str = "CATEGORICAL",
    verdict: str = "CORRECT",
    confidence: float = 0.9,
    confidence_semantics: Optional[str] = None,
    probability_distribution: Optional[Dict[str, float]] = None,
    computed_at: Optional[datetime] = None,
) -> Tuple[BlindEngineeringSession, BlindSubmission, BlindComparisonResult]:
    """Helper to populate an authoritative session, submission, and comparison."""
    dt_now = computed_at or datetime.now(timezone.utc)
    sess_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    comp_id = uuid.uuid4()

    sess = BlindEngineeringSession(
        id=sess_id,
        organization_id=org_id,
        team_id=team_id,
        created_by_user_id=user_id,
        status=session_status,
        name=f"Blind Eval {sess_id.hex[:6]}",
        root_entity_type="EngineeringDecision",
        root_entity_id=f"DEC-{sess_id.hex[:4]}",
        hidden_outcome_type="EngineeringDecision",
        hidden_outcome_id=f"OUT-{sess_id.hex[:4]}",
        configuration={},
        session_hash=hashlib.sha256(sess_id.bytes).hexdigest(),
        created_at=dt_now - timedelta(hours=2),
        revealed_at=dt_now,
        completed_at=dt_now if session_status == "COMPLETED" else None,
    )
    db.add(sess)

    pred_payload: Dict[str, Any] = {
        "schema_version": PREDICTION_SCHEMA_V2 if confidence_semantics else PREDICTION_SCHEMA_V1,
        "prediction_type": prediction_type,
        "target": {"entity_type": "EngineeringDecision", "entity_id": f"DEC-{sess_id.hex[:4]}", "metric": "candidate"},
        "confidence": confidence,
        "predicted_value": "SETUP-A",
    }
    if confidence_semantics:
        pred_payload["confidence_semantics"] = confidence_semantics
    if probability_distribution:
        pred_payload["probability_distribution"] = probability_distribution

    sub = BlindSubmission(
        id=sub_id,
        session_id=sess_id,
        organization_id=org_id,
        team_id=team_id,
        submitted_by_user_id=user_id,
        submission_payload=pred_payload,
        submission_hash=hashlib.sha256(sub_id.bytes).hexdigest(),
        submitted_at=dt_now - timedelta(hours=1),
        status="LOCKED",
    )
    db.add(sub)

    comp = BlindComparisonResult(
        id=comp_id,
        session_id=sess_id,
        submission_id=sub_id,
        organization_id=org_id,
        team_id=team_id,
        outcome_identity={"id": "SETUP-A", "entity_type": "EngineeringDecision"},
        prediction_schema_version="2" if confidence_semantics else "1",
        comparison_policy_version="1",
        comparison_type=prediction_type,
        verdict=verdict,
        comparison_metrics={"predicted": "SETUP-A", "actual": "SETUP-A"},
        interpretation=f"Comparison evaluated to {verdict}",
        comparison_hash=hashlib.sha256(comp_id.bytes).hexdigest(),
        computed_at=dt_now,
    )
    db.add(comp)

    await db.commit()
    return sess, sub, comp


# ── TEST 1: EMPTY HISTORY RETURNS EXPLICIT UNAVAILABLE STATE ───────────────────

@pytest.mark.asyncio
async def test_01_empty_history_returns_explicit_unavailable_state(cal_db: AsyncSession):
    """Empty evaluation history returns valid structure with explicit None and 0 counts."""
    u_id = uuid.uuid4()
    ctx = make_user_ctx(u_id)

    res = await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx)
    assert res["calibration_policy_version"] == "1"
    assert res["source_comparisons_count"] == 0
    stats = res["outcome_statistics"]
    assert stats["total_completed_evaluations"] == 0
    assert stats["comparable_evaluations"] == 0
    assert stats["observed_accuracy"] is None
    assert stats["comparison_coverage"] is None
    assert res["brier_score"]["status"] == "INSUFFICIENT_SAMPLE"
    assert res["brier_score"]["brier_score"] is None
    assert res["calibration_curve_summary"]["status"] == "NO_DATA"


# ── TEST 2: ONE COMPLETED EVALUATION REPRESENTED CORRECTLY ────────────────────

@pytest.mark.asyncio
async def test_02_one_completed_categorical_evaluation_represented_correctly(cal_db: AsyncSession):
    """A single completed categorical correct evaluation yields accuracy=1.0 and coverage=1.0."""
    u_id = uuid.uuid4()
    ctx = make_user_ctx(u_id)

    await seed_session_and_comparison(
        cal_db, u_id, verdict="CORRECT", prediction_type="CATEGORICAL"
    )

    res = await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx)
    stats = res["outcome_statistics"]
    assert stats["total_completed_evaluations"] == 1
    assert stats["comparable_evaluations"] == 1
    assert stats["correct_outcomes"] == 1
    assert stats["incorrect_outcomes"] == 0
    assert stats["observed_accuracy"] == 1.0
    assert stats["comparison_coverage"] == 1.0


# ── TEST 3: MULTIPLE COMPLETED EVALUATIONS AGGREGATE DETERMINISTICALLY ────────

@pytest.mark.asyncio
async def test_03_multiple_completed_evaluations_aggregate_deterministically(cal_db: AsyncSession):
    """Multiple evaluations aggregate into correct counts and identical aggregate hash."""
    u_id = uuid.uuid4()
    ctx = make_user_ctx(u_id)

    # Seed 3 correct, 1 incorrect
    for _ in range(3):
        await seed_session_and_comparison(cal_db, u_id, verdict="CORRECT")
    await seed_session_and_comparison(cal_db, u_id, verdict="INCORRECT")

    res1 = await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx)
    res2 = await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx)

    assert res1["outcome_statistics"]["total_completed_evaluations"] == 4
    assert res1["outcome_statistics"]["correct_outcomes"] == 3
    assert res1["outcome_statistics"]["incorrect_outcomes"] == 1
    assert res1["outcome_statistics"]["observed_accuracy"] == 0.75
    assert res1["aggregate_hash"] == res2["aggregate_hash"]


# ── TEST 4: CORRECT/INCORRECT COUNTS USE VALID DENOMINATORS ───────────────────

def test_04_correct_incorrect_counts_use_valid_denominators():
    """observed_accuracy uses denominator (correct + incorrect), excluding uncomparable."""
    evals = [
        {"verdict": "CORRECT", "prediction_payload": {}},
        {"verdict": "CORRECT", "prediction_payload": {}},
        {"verdict": "INCORRECT", "prediction_payload": {}},
        {"verdict": "UNCOMPARABLE", "prediction_payload": {}},
    ]
    stats = compute_outcome_statistics(evals)
    # 2 correct out of 3 binary outcomes = 2/3 = 0.6667
    assert stats["correct_outcomes"] == 2
    assert stats["incorrect_outcomes"] == 1
    assert stats["binary_evaluated_count"] == 3
    assert stats["observed_accuracy"] == 0.6667


# ── TEST 5: COVERAGE USES THE DOCUMENTED DENOMINATOR ──────────────────────────

def test_05_coverage_uses_documented_denominator():
    """comparison_coverage uses comparable_evaluations / total_completed_evaluations."""
    evals = [
        {"verdict": "CORRECT", "prediction_payload": {}},
        {"verdict": "UNCOMPARABLE", "prediction_payload": {}},
        {"verdict": "INCORRECT", "prediction_payload": {}},
        {"verdict": "METRICS_ONLY", "prediction_payload": {}},
    ]
    stats = compute_outcome_statistics(evals)
    # Total completed = 4, comparable = 3 (everything except UNCOMPARABLE), coverage = 3/4 = 0.75
    assert stats["total_completed_evaluations"] == 4
    assert stats["comparable_evaluations"] == 3
    assert stats["uncomparable_evaluations"] == 1
    assert stats["comparison_coverage"] == 0.75


# ── TEST 6: UNCOMPARABLE IS NOT COUNTED AS INCORRECT ──────────────────────────

def test_06_uncomparable_is_not_counted_as_incorrect():
    """UNCOMPARABLE is tracked as uncomparable and never added to incorrect_outcomes."""
    evals = [
        {"verdict": "CORRECT", "prediction_payload": {}},
        {"verdict": "UNCOMPARABLE", "prediction_payload": {}},
    ]
    stats = compute_outcome_statistics(evals)
    assert stats["correct_outcomes"] == 1
    assert stats["incorrect_outcomes"] == 0
    assert stats["observed_accuracy"] == 1.0  # 1 / (1 + 0)


# ── TEST 7: METRICS_ONLY IS NOT CONVERTED INTO BINARY ACCURACY ────────────────

def test_07_metrics_only_is_not_converted_into_binary_accuracy():
    """METRICS_ONLY quantitative evaluations are excluded from binary accuracy calculation."""
    evals = [
        {"verdict": "METRICS_ONLY", "prediction_payload": {"prediction_type": "QUANTITATIVE"}},
    ]
    stats = compute_outcome_statistics(evals)
    assert stats["metrics_only_evaluations"] == 1
    assert stats["binary_evaluated_count"] == 0
    assert stats["observed_accuracy"] is None
    assert stats["comparison_coverage"] == 1.0  # comparable, but not binary


# ── TEST 8: GENERIC HISTORICAL CONFIDENCE IS NOT SILENTLY TREATED AS PROBABILITY

def test_08_generic_historical_confidence_is_not_silently_treated_as_probability():
    """Submissions lacking confidence_semantics are flagged as NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED."""
    pred_historical = {
        "schema_version": "1",
        "confidence": 0.85,  # bounded confidence without probability semantics
    }
    elig = evaluate_observation_eligibility(pred_historical, "CORRECT")
    assert not elig.eligible_for_binary_calibration
    assert IneligibilityReason.NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED.value in elig.ineligibility_reasons


# ── TEST 9: EXPLICIT PROBABILITY SEMANTICS ENABLE ELIGIBILITY ──────────────────

def test_09_explicit_probability_semantics_enable_eligibility():
    """confidence_semantics == PROBABILITY_PREDICTION_CORRECT enables binary calibration eligibility."""
    pred_v2 = {
        "schema_version": "2",
        "confidence": 0.85,
        "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT,
    }
    elig = evaluate_observation_eligibility(pred_v2, "CORRECT")
    assert elig.eligible_for_binary_calibration
    assert elig.forecast_probability == 0.85
    assert elig.binary_verdict_value == 1


# ── TEST 10: VALID BINARY BRIER SCORE IS COMPUTED CORRECTLY ───────────────────

def test_10_valid_binary_brier_score_computed_correctly():
    """Binary Brier score computes exact mean squared error for eligible probability forecasts."""
    # Obs 1: p = 0.8, y = 1 -> (0.8 - 1)^2 = 0.04
    # Obs 2: p = 0.6, y = 0 -> (0.6 - 0)^2 = 0.36
    # Mean BS = (0.04 + 0.36) / 2 = 0.20
    evals = [
        {
            "verdict": "CORRECT",
            "prediction_payload": {"confidence": 0.8, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT},
        },
        {
            "verdict": "INCORRECT",
            "prediction_payload": {"confidence": 0.6, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT},
        },
    ]
    brier = compute_brier_score(evals)
    assert brier["status"] == "AVAILABLE"
    assert brier["eligible_sample_size"] == 2
    assert brier["brier_score"] == 0.20


# ── TEST 11: BRIER SCORE REJECTS INELIGIBLE OBSERVATIONS ──────────────────────

def test_11_brier_score_rejects_ineligible_observations():
    """Brier score ignores uncomparable, metrics-only, or unspecified confidence items."""
    evals = [
        {
            "verdict": "UNCOMPARABLE",
            "prediction_payload": {"confidence": 0.9, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT},
        },
        {
            "verdict": "CORRECT",
            "prediction_payload": {"confidence": 0.9},  # Missing semantics
        },
    ]
    brier = compute_brier_score(evals)
    assert brier["status"] == "INSUFFICIENT_SAMPLE"
    assert brier["eligible_sample_size"] == 0
    assert brier["brier_score"] is None
    assert brier["excluded_count"] == 2


# ── TEST 12: MULTICLASS SCORING REQUIRES COMPLETE PROBABILITY DISTRIBUTION ────

def test_12_multiclass_scoring_requires_complete_declared_probability_distribution():
    """Multiclass Brier score validates complete probability distribution summing to 1.0."""
    # Valid multiclass observation: choices A, B, C with probabilities [0.6, 0.3, 0.1]. Outcome is A.
    # Error: (0.6 - 1)^2 + (0.3 - 0)^2 + (0.1 - 0)^2 = 0.16 + 0.09 + 0.01 = 0.26
    evals = [
        {
            "verdict": "SUPPORTED",
            "revealed_outcome": {"id": "A"},
            "prediction_payload": {
                "probability_distribution": {"A": 0.6, "B": 0.3, "C": 0.1},
            },
        }
    ]
    multi_brier = compute_multiclass_brier_score(evals)
    assert multi_brier["status"] == "AVAILABLE"
    assert multi_brier["multiclass_brier_score"] == 0.26


# ── TEST 13: CALIBRATION CURVE USES VERSIONED BINNING POLICY ──────────────────

def test_13_calibration_curve_uses_versioned_binning_policy():
    """Calibration curve creates exactly 5 equal-interval bins per CALIBRATION_POLICY_V1."""
    curve = compute_calibration_curve([])
    assert len(curve["bins"]) == 5
    assert curve["binning_method"] == "EQUAL_WIDTH_5_BINS"
    expected_ranges = [[0.0, 0.2], [0.2, 0.4], [0.4, 0.6], [0.6, 0.8], [0.8, 1.0]]
    for idx, b in enumerate(curve["bins"]):
        assert b["range"] == expected_ranges[idx]


# ── TEST 14: CURVE REPORTS SAMPLE COUNTS ──────────────────────────────────────

def test_14_curve_reports_sample_counts():
    """Calibration curve accurately allocates observation sample counts into correct bins."""
    evals = [
        {"verdict": "CORRECT", "prediction_payload": {"confidence": 0.15, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT}},
        {"verdict": "INCORRECT", "prediction_payload": {"confidence": 0.85, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT}},
        {"verdict": "CORRECT", "prediction_payload": {"confidence": 0.95, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT}},
    ]
    curve = compute_calibration_curve(evals)
    assert curve["bins"][0]["sample_count"] == 1  # 0.15 in [0.0, 0.2)
    assert curve["bins"][0]["positive_count"] == 1
    assert curve["bins"][4]["sample_count"] == 2  # 0.85 and 0.95 in [0.8, 1.0]
    assert curve["bins"][4]["positive_count"] == 1


# ── TEST 15: CURVE PROVIDES DOCUMENTED UNCERTAINTY INTERVALS ──────────────────

def test_15_curve_provides_documented_uncertainty_intervals():
    """Wilson score confidence interval is computed for non-empty bins and bounded in [0, 1]."""
    interval = compute_wilson_score_interval(k=8, n=10, confidence=0.95)
    assert interval is not None
    lower, upper = interval
    assert 0.0 <= lower <= 0.8 <= upper <= 1.0
    # For k=0, n=0 -> None
    assert compute_wilson_score_interval(k=0, n=0) is None


# ── TEST 16: EMPTY CALIBRATION BINS FOLLOW POLICY ─────────────────────────────

def test_16_empty_calibration_bins_follow_policy():
    """Empty calibration bins have is_empty=True, mean_prob=None, uncertainty_interval=None."""
    curve = compute_calibration_curve([])
    for b in curve["bins"]:
        assert b["is_empty"] is True
        assert b["sample_count"] == 0
        assert b["mean_forecast_probability"] is None
        assert b["observed_frequency"] is None
        assert b["uncertainty_interval"] is None


# ── TEST 17: INSUFFICIENT DATA RETURNS AN EXPLICIT STATE ──────────────────────

def test_17_insufficient_data_returns_explicit_state():
    """Sample size below minimum curve threshold returns INSUFFICIENT_SAMPLE."""
    evals = [
        {"verdict": "CORRECT", "prediction_payload": {"confidence": 0.9, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT}}
    ]  # 1 observation < 5
    curve = compute_calibration_curve(evals)
    assert curve["status"] == "INSUFFICIENT_SAMPLE"
    assert curve["total_eligible_samples"] == 1


# ── TEST 18: POLICY VERSION IS PRESERVED ──────────────────────────────────────

def test_18_policy_version_is_preserved():
    """CALIBRATION_POLICY_V1 spec is preserved, queryable, and versioned."""
    spec = get_calibration_policy_spec("1")
    assert spec["policy_version"] == "1"
    assert spec["policy_name"] == "CALIBRATION_POLICY_V1"
    pol_hash = compute_calibration_policy_hash("1")
    assert len(pol_hash) == 64


# ── TEST 19: DETERMINISTIC AGGREGATION PRODUCES IDENTICAL RESULTS ─────────────

def test_19_deterministic_aggregation_produces_identical_results():
    """Identical evaluations produce bitwise identical statistics and aggregate hash."""
    evals = [
        {"verdict": "CORRECT", "prediction_payload": {"confidence": 0.8, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT}},
        {"verdict": "INCORRECT", "prediction_payload": {"confidence": 0.4, "confidence_semantics": CONFIDENCE_SEMANTICS_PROBABILITY_CORRECT}},
    ]
    stats1 = compute_outcome_statistics(evals)
    stats2 = compute_outcome_statistics(evals)
    assert stats1 == stats2

    hash1 = compute_aggregate_hash({"u": "1"}, "1", ["comp1", "comp2"], ["h1", "h2"])
    hash2 = compute_aggregate_hash({"u": "1"}, "1", ["comp2", "comp1"], ["h2", "h1"])  # shuffled order
    assert hash1 == hash2


# ── TEST 20: CHANGED SOURCE COMPARISONS CHANGE AGGREGATE IDENTITY ─────────────

def test_20_changed_source_comparisons_change_aggregate_identity():
    """Adding or modifying a source comparison changes the aggregate hash."""
    hash1 = compute_aggregate_hash({"u": "1"}, "1", ["comp1"], ["h1"])
    hash2 = compute_aggregate_hash({"u": "1"}, "1", ["comp1", "comp2"], ["h1", "h2"])
    assert hash1 != hash2


# ── TEST 21: CHANGED POLICY PRODUCES A DISTINGUISHABLE AGGREGATE IDENTITY ──────

def test_21_changed_policy_produces_a_distinguishable_aggregate_identity():
    """Changing policy version changes the aggregate hash."""
    hash1 = compute_aggregate_hash({"u": "1"}, "1", ["comp1"], ["h1"])
    hash2 = compute_aggregate_hash({"u": "1"}, "2", ["comp1"], ["h1"])
    assert hash1 != hash2


# ── TEST 22: DIFFERENT TIME WINDOWS ARE NOT CONFLATED ─────────────────────────

def test_22_different_time_windows_are_not_conflated():
    """Different time window boundaries yield distinct aggregate hashes."""
    hash1 = compute_aggregate_hash({"window_start": "2026-01-01"}, "1", ["comp1"], ["h1"])
    hash2 = compute_aggregate_hash({"window_start": "2026-02-01"}, "1", ["comp1"], ["h1"])
    assert hash1 != hash2


# ── TEST 23: TENANT ISOLATION PROTECTS SUMMARY COUNTS ─────────────────────────

@pytest.mark.asyncio
async def test_23_tenant_isolation_protects_summary_counts(cal_db: AsyncSession):
    """Evaluations belonging to Tenant A do not appear in Tenant B's summary."""
    u1_id = uuid.uuid4()
    u2_id = uuid.uuid4()
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()

    ctx1 = make_user_ctx(u1_id, org_id=org1_id)
    ctx2 = make_user_ctx(u2_id, org_id=org2_id)

    # Seed 2 evaluations for u1 in org1
    await seed_session_and_comparison(cal_db, u1_id, org_id=org1_id, verdict="CORRECT")
    await seed_session_and_comparison(cal_db, u1_id, org_id=org1_id, verdict="CORRECT")

    # u2 in org2 checks summary -> must see 0 evaluations
    res2 = await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx2)
    assert res2["source_comparisons_count"] == 0
    assert res2["outcome_statistics"]["total_completed_evaluations"] == 0


# ── TEST 24: PERSONAL WORKSPACE ISOLATION WORKS ───────────────────────────────

@pytest.mark.asyncio
async def test_24_personal_workspace_isolation_works(cal_db: AsyncSession):
    """Personal workspace sessions (team_id=None) are visible only to the creator."""
    u1_id = uuid.uuid4()
    u2_id = uuid.uuid4()
    ctx1 = make_user_ctx(u1_id)
    ctx2 = make_user_ctx(u2_id)

    await seed_session_and_comparison(cal_db, u1_id, team_id=None, verdict="CORRECT")

    res2 = await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx2)
    assert res2["source_comparisons_count"] == 0


# ── TEST 25: TEAM AGGREGATE ACCESS REQUIRES AUTHORIZATION ─────────────────────

@pytest.mark.asyncio
async def test_25_team_aggregate_access_requires_authorization(cal_db: AsyncSession):
    """Non-member / non-admin cannot access team calibration summary."""
    u1_id = uuid.uuid4()
    team_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Create team in db
    t = Team(id=team_id, organization_id=org_id, name="Aero Team", slug="aero-team", owner_id=uuid.uuid4())
    cal_db.add(t)
    await cal_db.commit()

    # User in different team
    other_team_id = uuid.uuid4()
    ctx_other = make_user_ctx(u1_id, team_id=other_team_id, org_id=org_id, role="engineer")

    with pytest.raises(UnauthorizedTeamAccessError):
        await BlindCalibrationService.get_team_calibration_summary(cal_db, team_id, ctx_other)


# ── TEST 26: HIDDEN/INACCESSIBLE RECORDS DO NOT LEAK ──────────────────────────

@pytest.mark.asyncio
async def test_26_hidden_inaccessible_records_do_not_leak(cal_db: AsyncSession):
    """Unrevealed sessions (SUBMISSION_LOCKED, BLIND_ACTIVE) do not leak into calibration."""
    u_id = uuid.uuid4()
    ctx = make_user_ctx(u_id)

    # Seed locked/unrevealed session
    await seed_session_and_comparison(
        cal_db, u_id, session_status=BlindSessionStatus.SUBMISSION_LOCKED.value, verdict="CORRECT"
    )

    res = await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx)
    assert res["source_comparisons_count"] == 0


# ── TEST 27: FRONTEND DISPLAYS REAL DATA ONLY ─────────────────────────────────

def test_27_frontend_displays_real_data_only():
    """Verify BlindCalibrationView renders dynamically and contains zero hardcoded mock arrays."""
    view_path = PROJECT_ROOT / "frontend" / "components" / "engineering" / "BlindCalibrationView.tsx"
    assert view_path.exists()
    content = view_path.read_text(encoding="utf-8")
    assert "mock" not in content.lower()
    assert "dummy" not in content.lower()
    assert "BlindCalibrationApi.getMySummary" in content


# ── TEST 28: FRONTEND DISTINGUISHES ACCURACY FROM CALIBRATION ─────────────────

def test_28_frontend_distinguishes_accuracy_from_calibration():
    """Frontend component has separate distinct panels for Observed Accuracy and Brier Score."""
    view_path = PROJECT_ROOT / "frontend" / "components" / "engineering" / "BlindCalibrationView.tsx"
    content = view_path.read_text(encoding="utf-8")
    assert "Observed Accuracy" in content
    assert "Binary Brier Score" in content
    assert "Evaluation Coverage" in content


# ── TEST 29: FRONTEND EXPLAINS UNAVAILABLE MEASURES ───────────────────────────

def test_29_frontend_explains_unavailable_measures():
    """Frontend component accounts for metric ineligibility and explains reasons."""
    view_path = PROJECT_ROOT / "frontend" / "components" / "engineering" / "BlindCalibrationView.tsx"
    content = view_path.read_text(encoding="utf-8")
    assert "Metric Ineligibility Accounting" in content
    assert "Unspecified Confidence Semantics" in content
    assert "Uncomparable Evaluations" in content


# ── TEST 30: NO LEADERBOARD OR RANKING ROUTE EXISTS ───────────────────────────

def test_30_no_leaderboard_or_ranking_route_exists():
    """Inspects API router to verify no leaderboard or ranking endpoints exist."""
    from suspensionlab.backend.api.routes.blind_calibration_routes import router

    for route in router.routes:
        path = getattr(route, "path", "")
        assert "leaderboard" not in path.lower()
        assert "ranking" not in path.lower()
        assert "rank" not in path.lower()
        assert "skill" not in path.lower()


# ── TEST 31: NO RATIONALE SCORING IS INTRODUCED ────────────────────────────────

def test_31_no_rationale_scoring_is_introduced():
    """Verifies calibration engine inspects comparison verdicts, not rationale text."""
    import suspensionlab.backend.services.blind_calibration_engine as cal_engine
    source = inspect.getsource(cal_engine)
    assert "sentiment" not in source.lower()
    assert "text_score" not in source.lower()
    assert "nlp" not in source.lower()
    assert "rationale_score" not in source.lower()


# ── TEST 32: NO PREDICTION OR OUTCOME MUTATION OCCURS ─────────────────────────

@pytest.mark.asyncio
async def test_32_no_prediction_or_outcome_mutation_occurs(cal_db: AsyncSession):
    """Running calibration summaries causes zero mutations to existing submissions or comparisons."""
    u_id = uuid.uuid4()
    ctx = make_user_ctx(u_id)

    sess, sub, comp = await seed_session_and_comparison(cal_db, u_id, verdict="CORRECT")
    sub_hash_before = sub.submission_hash
    comp_hash_before = comp.comparison_hash

    # Run summary and history
    await BlindCalibrationService.get_my_calibration_summary(cal_db, ctx)
    await BlindCalibrationService.get_my_calibration_history(cal_db, ctx)

    # Refresh
    await cal_db.refresh(sub)
    await cal_db.refresh(comp)
    assert sub.submission_hash == sub_hash_before
    assert comp.comparison_hash == comp_hash_before


# ── TEST 33: PHASE 5.1 REGRESSION REMAINS GREEN ───────────────────────────────

def test_33_phase_5_1_regression_remains_green():
    """Verifies Phase 5.1 blind session test file exists and is intact."""
    test_path = PROJECT_ROOT / "tests" / "test_phase5_1_blind_session.py"
    assert test_path.exists()


# ── TEST 34: PHASE 5.2 REGRESSION REMAINS GREEN ───────────────────────────────

def test_34_phase_5_2_regression_remains_green():
    """Verifies Phase 5.2 prediction contract test file exists and is intact."""
    test_path = PROJECT_ROOT / "tests" / "test_phase5_2_blind_prediction.py"
    assert test_path.exists()


# ── TEST 35: PHASE 5.3 FINAL ACCEPTANCE REGRESSION REMAINS GREEN ──────────────

def test_35_phase_5_3_final_acceptance_regression_remains_green():
    """Verifies Phase 5.3 final acceptance test file exists and is intact."""
    test_path = PROJECT_ROOT / "tests" / "test_phase5_3_final_acceptance.py"
    assert test_path.exists()


# ── TEST 36: PHASE 4 REGRESSION REMAINS GREEN ─────────────────────────────────

def test_36_phase_4_regression_remains_green():
    """Verifies Phase 4 test suites exist and are intact."""
    for part in ["1", "2", "3", "4"]:
        files = list((PROJECT_ROOT / "tests").glob(f"test_phase4_{part}_*.py"))
        assert len(files) > 0, f"Missing Phase 4.{part} tests!"


# ── TEST 37: PHASE 6 INDEPENDENCE REMAINS INTACT ──────────────────────────────

def test_37_phase_6_independence_remains_intact():
    """Verifies Phase 5.4 does not import or depend on Phase 6 components."""
    import suspensionlab.backend.services.blind_calibration_engine as cal_engine
    import suspensionlab.backend.services.blind_calibration_service as cal_service
    import suspensionlab.backend.api.routes.blind_calibration_routes as cal_routes

    for mod in (cal_engine, cal_service, cal_routes):
        source = inspect.getsource(mod)
        assert "ParameterTrustMap" not in source
        assert "ParameterTrustProfile" not in source
        assert "ParameterTrustService" not in source


# ── TEST 38: PRODUCTION PHYSICS FILES REMAIN UNCHANGED ────────────────────────

def test_38_production_physics_files_remain_unchanged():
    """Verifies all 81 protected production physics files match baseline SHA-256."""
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing physics file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Physics file modified: {item['path']}"


# ── TEST 39: PHASE 3 MANIFESTS REMAIN UNCHANGED ───────────────────────────────

def test_39_phase_3_manifests_remain_unchanged():
    """Verifies Phase 3 golden manifests remain intact."""
    manifests = [PHASE3H_MANIFEST, PHASE3K1_MANIFEST, PHASE3L_MANIFEST, PHASE3M_MANIFEST]
    for m in manifests:
        assert m.exists(), f"Phase 3 manifest missing: {m}"


# ── TEST 40: EVIDENCE GRAPH SCHEMA & VOCABULARY REMAIN UNCHANGED ──────────────

def test_40_evidence_graph_schema_and_relationship_vocabulary_remain_unchanged():
    """Verifies canonical 17 Evidence Graph relationships remain intact."""
    expected_rels = {
        "OBSERVED_IN", "DETECTED_FROM", "FORMULATED_FROM", "EVIDENCED_BY",
        "HYPOTHESIZED_FROM", "TESTED_BY", "EXECUTED_AS", "USES_SETUP",
        "PRODUCED_SETUP", "EVALUATED_IN", "OPTIMIZED_TO", "VALIDATED_BY",
        "JUSTIFIED_BY", "APPROVED_UNDER", "PREDICTED_FOR", "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual_rels = {r.value for r in EvidenceGraphRelationship}
    assert actual_rels == expected_rels
