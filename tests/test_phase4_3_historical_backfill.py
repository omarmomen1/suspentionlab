"""
Phase 4.3 Test Suite — Historical Backfill & Deterministic Case Reconstruction
==============================================================================
Validates the complete 28 explicit test requirements for Phase 4.3:
1. generic relationship extractor
2. no hardcoded IDs in production backfill code
3. no textual case matching (.contains() or string heuristics)
4. valid persisted relationship becomes graph edge
5. invalid endpoint rejected (fails closed)
6. cross-tenant relationship rejected (fails closed)
7. duplicate relationship idempotent
8. artifact hashes captured at backfill time
9. metadata is provenance-safe (bounded, no secrets)
10. first backfill creates expected edges
11. second backfill creates zero duplicates
12. Phase 3K1 case reconstructible backward
13. Phase 3K1 case reconstructible forward
14. Phase 3L setup engineering case reconstructible
15. Phase 3M independent engineering case reconstructible
16. Stanford VW Golf Thunderhill dataset provenance reconstructible
17. generic reconstruction succeeds on completely synthetic IDs
18. no case name branching in reconstruction
19. reconstruct_complete_lineage preserves caller contract
20. no legacy textual heuristics remain in active reconstruction
21. tenant isolation strictly enforced
22. personal workspace isolation strictly enforced
23. no cycle introduced by backfill
24. deterministic edge set
25. deterministic traversal result
26. graph edge count stable across repeated backfill
27. protected Phase 3 artifacts unchanged
28. production physics unchanged
"""
from __future__ import annotations

import glob
import hashlib
import inspect
import json
import os
import uuid
from typing import Any, Dict, List

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.decision_loop import (
    ApprovalRecord,
    BlindValidationRecord,
    InvestigationRecord,
    OptimizationRecord,
    SetupComparisonRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.database.models.experiment import ExperimentRecord
from suspensionlab.backend.database.models.setup_engineering import (
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    EngineeringProblemRecord,
    PostTrackReconciliationRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
)
from suspensionlab.backend.database.models.simulation_run import SimulationRun

from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    CycleDetectedError,
    TenantIsolationError,
    EntityNotFoundError,
    compute_edge_hash,
)
from suspensionlab.backend.services.evidence_graph_backfill_service import (
    EvidenceGraphBackfillService,
    RELATIONSHIP_EXTRACTORS,
)
from suspensionlab.backend.services.engineering_decision_loop_service import (
    EngineeringDecisionLoopService,
)
from suspensionlab.backend.services.phase3k1_case_service import Phase3K1CaseService
from suspensionlab.backend.services.phase3l_setup_engineering_service import (
    Phase3LSetupEngineeringService,
)
from suspensionlab.backend.services.phase3m_case_service import Phase3MCaseService


@pytest.fixture
async def p43_db():
    """In-memory SQLite async database with complete schema for Phase 4.3 testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _make_telemetry_session(
    number: int,
    code: str,
    h: str,
    team_id: Any = None,
    user_id: Any = None,
) -> TelemetrySessionRecord:
    return TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=number,
        session_code=code,
        track_name="Silverstone GP",
        vehicle_id="CAR-2026-07",
        setup_id="SETUP-91",
        channels={"time": [0.0, 1.0], "speed": [50.0, 52.0]},
        summary_metrics={"peak_lat_g": 2.1, "mean_speed": 51.0},
        sample_count=2,
        duration_s=1.0,
        artifact_hash=h,
        team_id=team_id,
        user_id=user_id or uuid.uuid4(),
    )


def _make_inv(
    number: int,
    code: str,
    sess_code: str,
    h: str,
    team_id: Any = None,
    user_id: Any = None,
) -> InvestigationRecord:
    return InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=number,
        investigation_code=code,
        session_code=sess_code,
        detection_type="EXCESSIVE_CHASSIS_ROLL_COMPLIANCE",
        symptom="Excessive chassis roll detected under transient excitation.",
        affected_regime="High-Speed Lateral Cornering",
        severity="CRITICAL",
        status="OPEN",
        evidence_snapshot={"channel": "roll_angle", "observed": 3.8, "expected": 2.1, "unit": "deg"},
        artifact_hash=h,
        team_id=team_id,
        user_id=user_id or uuid.uuid4(),
    )


# ── REQUIREMENT 1: GENERIC RELATIONSHIP EXTRACTOR ─────────────────────────────

def test_01_generic_relationship_extractor():
    """Requirement 1: Generic relationship extractor mapping exists and covers supported entity types."""
    extractors = EvidenceGraphBackfillService.get_registered_extractors()
    assert len(extractors) >= 12
    assert SupportedEntityType.INVESTIGATION.value in extractors
    assert SupportedEntityType.ENGINEERING_PROBLEM.value in extractors
    assert SupportedEntityType.ENGINEERING_QUESTION.value in extractors
    assert SupportedEntityType.CAUSAL_HYPOTHESIS.value in extractors
    assert SupportedEntityType.CONTROLLED_EXPERIMENT.value in extractors
    assert SupportedEntityType.SIMULATION_RUN.value in extractors
    assert SupportedEntityType.SETUP_CANDIDATE.value in extractors
    assert SupportedEntityType.SETUP_COMPARISON.value in extractors
    assert SupportedEntityType.OPTIMIZATION.value in extractors
    assert SupportedEntityType.BLIND_VALIDATION.value in extractors
    assert SupportedEntityType.ENGINEERING_DECISION.value in extractors
    assert SupportedEntityType.APPROVAL.value in extractors
    assert SupportedEntityType.TRACK_TEST_PREDICTION.value in extractors
    assert SupportedEntityType.POST_TRACK_RECONCILIATION.value in extractors


# ── REQUIREMENT 2: NO HARDCODED IDS IN PRODUCTION BACKFILL CODE ───────────────

def test_02_no_hardcoded_ids_in_production_backfill_code():
    """Requirement 2: No historical hardcoded case IDs exist in production backfill service."""
    service_path = "src/suspensionlab/backend/services/evidence_graph_backfill_service.py"
    with open(service_path, "r", encoding="utf-8") as f:
        content = f.read()

    prohibited_ids = [
        "SETUP-92", "RUN-1844", "INV-91", "TS-381", "Q-17", "DEC-12",
        "APPR-8", "COMP-31", "OPT-18", "VAL-31", "DEC-P3K1-01", "DEC-P3M-01",
        "TS-STANFORD-01", "INV-P3K1-01", "SETUP-GTI-OPT", "SETUP-P3L-GOV",
    ]
    for pid in prohibited_ids:
        assert pid not in content, f"Hardcoded ID '{pid}' detected in production backfill code!"


# ── REQUIREMENT 3: NO TEXTUAL CASE MATCHING & NO DESCRIPTIVE TEXT INFERENCE ─

def test_03_no_textual_case_matching():
    """Requirement 3: No string contains(), title, objective, or fuzzy text heuristics used for relationship derivation."""
    src_backfill = inspect.getsource(EvidenceGraphBackfillService)
    src_lineage = inspect.getsource(EngineeringDecisionLoopService.reconstruct_complete_lineage)

    for src in (src_backfill, src_lineage):
        assert ".contains(" not in src, "text contains() method call found in active code!"
        assert "front roll stiffness" not in src, "'front roll stiffness' heuristic found in active code!"
        assert "Front Axle" not in src, "'Front Axle' heuristic found in active code!"
        assert "Phase3K1" not in src, "'Phase3K1' case branching found in active code!"
        assert "Phase3L" not in src, "'Phase3L' case branching found in active code!"
        assert "Phase3M" not in src, "'Phase3M' case branching found in active code!"
        assert "difflib" not in src, "text similarity library found in active code!"
        assert "fuzzy" not in src, "fuzzy matching found in active code!"
        assert "rec.title" not in src, "rec.title matching found in active code!"
        assert "rec.objective" not in src, "rec.objective matching found in active code!"
        assert "rec.question_text" not in src, "rec.question_text matching found in active code!"


@pytest.mark.asyncio
async def test_03b_canonical_relationship_directions(p43_db: AsyncSession):
    """
    Requirement 3b: Explicitly proves unambiguous canonical direction semantics for representative relationships:
    1. Question -> TESTED_BY -> Experiment
    2. Experiment -> EXECUTED_AS -> Simulation
    3. Simulation -> USES_SETUP -> Setup
    4. Comparison -> EVALUATED_IN -> Validation
    5. Decision -> JUSTIFIED_BY -> Validation
    6. Approval -> APPROVED_UNDER -> Decision
    """
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    q = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-DIR-01", title="Q", question_text="Q",
        created_by="Engineer", team_id=team_id, created_by_user_id=user_id,
        linked_experiments=[],
    )
    exp = ExperimentRecord(
        id=uuid.uuid4(), question="Q-DIR-01",
        hypothesis="H", author="Eng", simulation_id="RUN-DIR-01",
        parent_setup={}, candidate_setup={}, parameter_changes=[],
        baseline_metrics={}, candidate_metrics={}, improvements=[],
        regressions=[], causal_chain={}, recommendation="Rec",
        result_hash="h-exp",
        team_id=team_id, user_id=user_id,
    )
    sim = SimulationRun(
        id=uuid.uuid4(), label="RUN-DIR-01", seq=7701, setup_ref="SETUP-DIR-01",
        simulation_type="quarter_car", params={"k": 1}, result={"d": 1},
        software_version="1.0", physics_version="1.0", solver_version="RK45",
        params_hash="h-sim", result_hash="h-res", team_id=team_id, user_id=user_id,
    )
    setup = SetupCandidateRecord(
        id=uuid.uuid4(), setup_id="SETUP-DIR-01", parent_setup_id="SETUP-BASE",
        changed_parameters={}, unchanged_parameters={}, parameter_provenance={},
        model_version="1.0", validity_domain={}, creation_reason="test",
        artifact_hash="h-set", team_id=team_id, user_id=user_id,
    )
    comp = SetupComparisonRecord(
        id=uuid.uuid4(), comparison_number=7701, comparison_code="COMP-DIR-01",
        baseline_setup_id="SETUP-BASE", candidate_setup_id="SETUP-DIR-01",
        simulation_run_id="RUN-DIR-01", baseline_metrics={}, candidate_metrics={},
        measured_metrics={}, deltas={}, uncertainty={},
        validity={"validation_code": "VAL-DIR-01", "model_validity_status": "VALIDATED"},
        artifact_hash="h-comp", team_id=team_id, user_id=user_id,
    )
    val = BlindValidationRecord(
        id=uuid.uuid4(), validation_number=7701, validation_code="VAL-DIR-01",
        setup_id="SETUP-DIR-01", decision_id="DEC-DIR-01",
        fit_dataset_ref="TS-FIT", holdout_dataset_ref="TS-HOLD",
        fit_r2=0.9, holdout_r2=0.9, holdout_rmse=0.01,
        artifact_hash="h-val", team_id=team_id, user_id=user_id,
    )
    dec = EngineeringDecision(
        id=uuid.uuid4(), decision_id="DEC-DIR-01", question="Q",
        context={}, candidates=[], selected_option={"setup_id": "SETUP-DIR-01"},
        reason="R", tradeoffs={}, risks=[], simulation_evidence={}, telemetry_evidence={},
        validation_evidence={"validation_code": "VAL-DIR-01"}, author="Eng",
        artifact_hashes={"decision_hash": "h-dec"}, team_id=team_id, user_id=user_id,
    )
    app = ApprovalRecord(
        id=uuid.uuid4(), approval_number=7701, approval_code="APP-DIR-01",
        decision_id="DEC-DIR-01", approver_name="Chief", approver_role="Chief",
        approval_signature="sig", status="APPROVED",
        artifact_hash="h-app", team_id=team_id, user_id=user_id,
    )

    p43_db.add_all([q, exp, sim, setup, comp, val, dec, app])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)

    edges = await EvidenceGraphService.list_edges(p43_db, team_id=team_id)
    edge_tuples = {(e.source_type, e.relationship, e.target_type) for e in edges}

    assert ("EngineeringQuestion", "TESTED_BY", "Experiment") in edge_tuples
    assert ("Experiment", "EXECUTED_AS", "SimulationRun") in edge_tuples
    assert ("SimulationRun", "USES_SETUP", "SetupCandidate") in edge_tuples
    assert ("SetupComparison", "EVALUATED_IN", "BlindValidation") in edge_tuples
    assert ("EngineeringDecision", "JUSTIFIED_BY", "BlindValidation") in edge_tuples
    assert ("Approval", "APPROVED_UNDER", "EngineeringDecision") in edge_tuples


@pytest.mark.asyncio
async def test_03c_no_descriptive_text_inference(p43_db: AsyncSession):
    """
    Requirement 3c: Proves that identical titles, objectives, or descriptions NEVER generate
    inferred relationships without real, explicit persisted foreign keys.
    """
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    q1 = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-TEXT-01", title="Identical Transient Roll Problem",
        question_text="How to reduce body roll in Turn 8 apex?",
        created_by="Engineer", team_id=team_id, created_by_user_id=user_id,
        linked_experiments=["EXP-TEXT-01"],
    )
    exp1 = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-TEXT-01", problem_id="PROB-TEXT-01", hypothesis_id="HYP-TEXT-01",
        control_variables={}, treatment_variables={}, held_constant_variables={},
        measured_outputs=[], expected_effect={}, constraints={}, validity_domain={},
        artifact_hash="h-exp-text", team_id=team_id, user_id=user_id,
    )
    q2 = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-TEXT-02", title="Identical Transient Roll Problem",
        question_text="How to reduce body roll in Turn 8 apex?",
        created_by="Engineer", team_id=team_id, created_by_user_id=user_id,
        linked_experiments=[],
    )
    p43_db.add_all([q1, exp1, q2])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)

    exists_q1 = await EvidenceGraphService.edge_exists(
        p43_db, team_id, "EngineeringQuestion", "Q-TEXT-01", "TESTED_BY", "ControlledExperiment", "EXP-TEXT-01"
    )
    assert exists_q1 is True

    exists_q2 = await EvidenceGraphService.edge_exists(
        p43_db, team_id, "EngineeringQuestion", "Q-TEXT-02", "TESTED_BY", "ControlledExperiment", "EXP-TEXT-01"
    )
    assert exists_q2 is False


# ── REQUIREMENT 4: VALID PERSISTED RELATIONSHIP BECOMES GRAPH EDGE ─────────────

@pytest.mark.asyncio
async def test_04_valid_persisted_relationship_becomes_graph_edge(p43_db: AsyncSession):
    """Requirement 4: Valid persisted foreign relationship correctly becomes canonical graph edge."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(100, "TS-REQ4", "hash-ts-req4", team_id=team_id, user_id=user_id)
    inv = _make_inv(100, "INV-REQ4", "TS-REQ4", "hash-inv-req4", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    res = await EvidenceGraphBackfillService.backfill_entity(
        db=p43_db,
        entity_type="Investigation",
        entity_id="INV-REQ4",
        team_id=team_id,
        user_id=user_id,
    )
    assert res["edges_created"] == 1
    assert len(res["rejected"]) == 0

    stmt = select(EvidenceGraphEdgeRecord).where(
        EvidenceGraphEdgeRecord.source_id == "INV-REQ4",
        EvidenceGraphEdgeRecord.target_id == "TS-REQ4",
    )
    edge = (await p43_db.execute(stmt)).scalar_one_or_none()
    assert edge is not None
    assert edge.relationship == "DETECTED_FROM"


# ── REQUIREMENT 5: INVALID ENDPOINT REJECTED ──────────────────────────────────

@pytest.mark.asyncio
async def test_05_invalid_endpoint_rejected(p43_db: AsyncSession):
    """Requirement 5: Invalid or missing endpoint relationship fails closed with structured rejection."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    inv = _make_inv(105, "INV-REQ5", "TS-NONEXISTENT", "hash-inv-req5", team_id, user_id)
    p43_db.add(inv)
    await p43_db.commit()

    res = await EvidenceGraphBackfillService.backfill_entity(
        db=p43_db,
        entity_type="Investigation",
        entity_id="INV-REQ5",
        team_id=team_id,
        user_id=user_id,
    )
    assert res["edges_created"] == 0
    assert len(res["rejected"]) == 1
    rej = res["rejected"][0]
    assert rej["source_id"] == "INV-REQ5"
    assert rej["target_id"] == "TS-NONEXISTENT"
    assert rej["reason_code"] == "EntityNotFoundError"


# ── REQUIREMENT 6: CROSS-TENANT RELATIONSHIP REJECTED ─────────────────────────

@pytest.mark.asyncio
async def test_06_cross_tenant_relationship_rejected(p43_db: AsyncSession):
    """Requirement 6: Cross-tenant relationship is rejected with TenantIsolationError."""
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()
    user_id = uuid.uuid4()

    sess_b = _make_telemetry_session(106, "TS-TEAM-B", "hash-ts-b", team_id=team_b, user_id=user_id)
    inv_a = _make_inv(106, "INV-TEAM-A", "TS-TEAM-B", "hash-inv-a", team_a, user_id)
    p43_db.add_all([sess_b, inv_a])
    await p43_db.commit()

    res = await EvidenceGraphBackfillService.backfill_entity(
        db=p43_db,
        entity_type="Investigation",
        entity_id="INV-TEAM-A",
        team_id=team_a,
        user_id=user_id,
    )
    assert res["edges_created"] == 0
    assert len(res["rejected"]) == 1
    assert res["rejected"][0]["reason_code"] == "TenantIsolationError"


# ── REQUIREMENT 7: DUPLICATE RELATIONSHIP IDEMPOTENT ──────────────────────────

@pytest.mark.asyncio
async def test_07_duplicate_relationship_idempotent(p43_db: AsyncSession):
    """Requirement 7: Duplicate relationships execute idempotently without edge duplication."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(107, "TS-REQ7", "hash-ts-req7", team_id=team_id, user_id=user_id)
    inv = _make_inv(107, "INV-REQ7", "TS-REQ7", "hash-inv-req7", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    run1 = await EvidenceGraphBackfillService.backfill_entity(p43_db, "Investigation", "INV-REQ7", team_id, user_id=user_id)
    run2 = await EvidenceGraphBackfillService.backfill_entity(p43_db, "Investigation", "INV-REQ7", team_id, user_id=user_id)

    assert run1["edges_created"] == 1
    assert run2["edges_created"] == 0
    assert run2["already_existing"] == 1

    stmt = select(EvidenceGraphEdgeRecord).where(EvidenceGraphEdgeRecord.source_id == "INV-REQ7")
    edges = (await p43_db.execute(stmt)).scalars().all()
    assert len(edges) == 1


# ── REQUIREMENT 8: ARTIFACT HASHES CAPTURED ───────────────────────────────────

@pytest.mark.asyncio
async def test_08_artifact_hashes_captured(p43_db: AsyncSession):
    """Requirement 8: Endpoint artifact hashes are captured at backfill time."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(
        108, "TS-REQ8",
        "a1b2c3d4e5f60000000000000000000000000000000000000000000000000001",
        team_id=team_id, user_id=user_id,
    )
    inv = _make_inv(108, "INV-REQ8", "TS-REQ8", "f6e5d4c3b2a10000000000000000000000000000000000000000000000000002", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_entity(p43_db, "Investigation", "INV-REQ8", team_id, user_id=user_id)

    stmt = select(EvidenceGraphEdgeRecord).where(EvidenceGraphEdgeRecord.source_id == "INV-REQ8")
    edge = (await p43_db.execute(stmt)).scalar_one()
    assert edge.source_artifact_hash == "f6e5d4c3b2a10000000000000000000000000000000000000000000000000002"
    assert edge.target_artifact_hash == "a1b2c3d4e5f60000000000000000000000000000000000000000000000000001"


# ── REQUIREMENT 9: METADATA IS PROVENANCE-SAFE ────────────────────────────────

@pytest.mark.asyncio
async def test_09_metadata_is_provenance_safe(p43_db: AsyncSession):
    """Requirement 9: Edge metadata is bounded, safe, and provenance-focused."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(109, "TS-REQ9", "hash-ts-req9", team_id=team_id, user_id=user_id)
    inv = _make_inv(109, "INV-REQ9", "TS-REQ9", "hash-inv-req9", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_entity(p43_db, "Investigation", "INV-REQ9", team_id, user_id=user_id)

    stmt = select(EvidenceGraphEdgeRecord).where(EvidenceGraphEdgeRecord.source_id == "INV-REQ9")
    edge = (await p43_db.execute(stmt)).scalar_one()
    meta = edge.metadata_
    assert meta["backfill_source"] == "persisted_relationship_field"
    assert meta["source_field"] == "session_code"
    raw_str = json.dumps(meta)
    assert len(raw_str) < 512
    assert "token" not in raw_str and "password" not in raw_str


# ── REQUIREMENTS 10 & 11: SCOPE BACKFILL & ZERO DUPLICATES ────────────────────

@pytest.mark.asyncio
async def test_10_first_backfill_creates_expected_edges(p43_db: AsyncSession):
    """Requirement 10: Initial backfill of scope creates all discovered candidate edges."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(110, "TS-110", "h-ts", team_id=team_id, user_id=user_id)
    inv = _make_inv(110, "INV-110", "TS-110", "h-inv", team_id, user_id)
    prob = EngineeringProblemRecord(
        id=uuid.uuid4(), problem_id="PROB-110", telemetry_session_id="TS-110",
        investigation_id="INV-110", engineering_question_id="Q-110",
        observable="Front axle roll", baseline_metric={"roll": 3.2}, target_metric={"roll": 2.0},
        operating_condition={"speed": 100}, track_context={"track": "Silverstone"},
        session_context={"surface": "dry"}, model_version="v1",
        epistemic_classification={"observed_fact": ["roll"]},
        artifact_hash="h-prob", team_id=team_id, user_id=user_id,
    )
    p43_db.add_all([sess, inv, prob])
    await p43_db.commit()

    rep1 = await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    assert rep1.edges_created >= 2
    assert rep1.already_existing == 0


@pytest.mark.asyncio
async def test_11_second_backfill_creates_zero_duplicates(p43_db: AsyncSession):
    """Requirement 11: Subsequent repeated backfill creates zero duplicates."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(111, "TS-111", "h-ts", team_id=team_id, user_id=user_id)
    inv = _make_inv(111, "INV-111", "TS-111", "h-inv", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    rep1 = await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    rep2 = await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)

    assert rep1.edges_created == 1
    assert rep2.edges_created == 0
    assert rep2.already_existing == 1


# ── REQUIREMENTS 12 & 13: PHASE 3K1 RECONSTRUCTION ────────────────────────────

@pytest.mark.asyncio
async def test_12_phase3k1_backward_reconstruction(p43_db: AsyncSession):
    """Requirement 12: Backward traversal from Phase 3K1 decision discovers full upstream lineage."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    await Phase3K1CaseService.execute_end_to_end_case(p43_db, user_id=user_id, team_id=team_id)

    report = await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    assert report.edges_created >= 4

    case_lineage = await EvidenceGraphBackfillService.rebuild_case_lineage(
        db=p43_db,
        root_type="EngineeringDecision",
        root_id="DEC-P3K1-01",
        team_id=team_id,
        user_id=user_id,
    )
    node_types = {n["entity_type"] for n in case_lineage["nodes"]}
    assert "EngineeringDecision" in node_types
    assert "Approval" in node_types
    assert "BlindValidation" in node_types
    assert "TelemetrySession" in node_types


@pytest.mark.asyncio
async def test_13_phase3k1_forward_reconstruction(p43_db: AsyncSession):
    """Requirement 13: Forward traversal from Phase 3K1 question discovers downstream engineering entities."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    await Phase3K1CaseService.execute_end_to_end_case(p43_db, user_id=user_id, team_id=team_id)
    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)

    fwd = await EvidenceGraphService.traverse_forward(
        db=p43_db,
        root_type="EngineeringQuestion",
        root_id="Q-P3K1-01",
        team_id=team_id,
        user_id=user_id,
        max_depth=5,
    )
    fwd_types = {n["entity_type"] for n in fwd["nodes"]}
    assert "EngineeringQuestion" in fwd_types
    assert len(fwd_types) >= 2


# ── REQUIREMENTS 14 & 15: PHASE 3L & PHASE 3M RECONSTRUCTION ──────────────────

@pytest.mark.asyncio
async def test_14_phase3l_reconstruction(p43_db: AsyncSession):
    """Requirement 14: Phase 3L setup engineering case is reconstructed generically."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    bundle = await Phase3LSetupEngineeringService.execute_full_workflow(p43_db, user_id=user_id, team_id=team_id)
    assert bundle["decision"]["decision_id"] == "DEC-P3L-01"

    report = await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    assert report.edges_created >= 4

    case_data = await EvidenceGraphBackfillService.rebuild_case_lineage(
        db=p43_db,
        root_type="EngineeringDecision",
        root_id="DEC-P3L-01",
        team_id=team_id,
        user_id=user_id,
    )
    node_types = {n["entity_type"] for n in case_data["nodes"]}
    assert "EngineeringDecision" in node_types
    assert "Approval" in node_types
    assert "TrackTestPrediction" in node_types or "SetupCandidate" in node_types


@pytest.mark.asyncio
async def test_15_phase3m_reconstruction(p43_db: AsyncSession):
    """Requirement 15: Phase 3M independent engineering case is reconstructed generically."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    prob, hyp = await Phase3MCaseService.create_problem_and_hypothesis(p43_db, user_id=user_id, team_id=team_id)
    cand_info = await Phase3MCaseService.design_experiment_and_candidates(p43_db, user_id=user_id, hypothesis_id=hyp.hypothesis_id, team_id=team_id)
    sims = Phase3MCaseService.execute_candidate_simulations_fit_window()
    opt = Phase3MCaseService.evaluate_tradeoffs_and_optimization(sims)
    val = await Phase3MCaseService.execute_sealed_blind_validation(p43_db, user_id=user_id, candidate_setup_id=opt["selected_setup_id"], team_id=team_id)
    dec = await Phase3MCaseService.formulate_engineering_decision(p43_db, user_id=user_id, decision_code="DEC-P3M-01", selected_setup_id=opt["selected_setup_id"], blind_validation_results=val, team_id=team_id)
    app = await Phase3MCaseService.execute_human_approval(p43_db, user_id=user_id, decision_code="DEC-P3M-01", team_id=team_id)

    report = await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    assert report.edges_created >= 4

    lineage = await EvidenceGraphBackfillService.rebuild_case_lineage(
        db=p43_db,
        root_type="EngineeringDecision",
        root_id="DEC-P3M-01",
        team_id=team_id,
        user_id=user_id,
    )
    discovered_ids = {n["entity_id"] for n in lineage["nodes"]}
    assert "DEC-P3M-01" in discovered_ids
    assert app["approval_code"] in discovered_ids
    assert val["validation_code"] in discovered_ids


# ── REQUIREMENT 16: DATASET PROVENANCE RECONSTRUCTION ─────────────────────────

@pytest.mark.asyncio
async def test_16_dataset_provenance_reconstruction(p43_db: AsyncSession):
    """Requirement 16: Stanford VW Golf Thunderhill dataset provenance hash is recovered from graph."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    await Phase3K1CaseService.execute_end_to_end_case(p43_db, user_id=user_id, team_id=team_id)
    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)

    case_data = await EvidenceGraphBackfillService.rebuild_case_lineage(
        db=p43_db,
        root_type="EngineeringQuestion",
        root_id="Q-P3K1-01",
        team_id=team_id,
        user_id=user_id,
    )
    ts_node = next((n for n in case_data["nodes"] if n["entity_type"] == "TelemetrySession"), None)
    assert ts_node is not None
    sess_rec = ts_node["record"]
    assert sess_rec is not None
    assert sess_rec.summary_metrics.get("dataset_id") == "stanford_vw_golf_thunderhill_2023_11"
    assert sess_rec.summary_metrics.get("provenance_hash") == "489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3"


# ── REQUIREMENTS 17 & 18: SYNTHETIC GENERALIZATION TEST ───────────────────────

@pytest.mark.asyncio
async def test_17_generic_reconstruction_with_synthetic_ids(p43_db: AsyncSession):
    """Requirement 17 & 18: Synthetic engineering case with completely non-Phase 3 IDs reconstructs generically."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    q = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-901", title="Synthetic question", question_text="How to optimize heave?",
        created_by="Engineer", team_id=team_id, created_by_user_id=user_id, linked_experiments=["EXP-901"],
    )
    exp = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-901", problem_id="PROB-901", hypothesis_id="HYP-901",
        control_variables={"mass": 300}, treatment_variables={"c": 2200}, held_constant_variables={"k": 30000},
        measured_outputs=["lat_accel"], expected_effect={"gain": 0.1}, constraints={"max_roll": 3.0},
        validity_domain={"speed": [50, 150]},
        artifact_hash="h-exp-901", team_id=team_id, user_id=user_id,
    )
    sim = SimulationRun(
        id=uuid.uuid4(), label="RUN-901", seq=901, setup_ref="SETUP-901", simulation_type="quarter_car",
        params={"k_s": 35000.0}, result={"damping_ratio": 0.3},
        software_version="1.0.0", physics_version="1.0.0", solver_version="RK45",
        params_hash="h-sim-901", result_hash="h-sim-res-901", team_id=team_id, user_id=user_id,
    )
    setup = SetupCandidateRecord(
        id=uuid.uuid4(), setup_id="SETUP-901", parent_setup_id="SETUP-BASE",
        changed_parameters={"c": {"baseline": 2000, "candidate": 2200, "delta_pct": 10}},
        unchanged_parameters={"m": 300}, parameter_provenance={"c": "sim"},
        model_version="1.0.0", validity_domain={"envelope": "normal"},
        creation_reason="Optimization", simulation_run_id="RUN-901",
        artifact_hash="h-setup-901", team_id=team_id, user_id=user_id,
    )
    val = BlindValidationRecord(
        id=uuid.uuid4(), validation_number=901, validation_code="VAL-901", setup_id="SETUP-901", decision_id="DEC-901",
        fit_dataset_ref="TS-FIT", holdout_dataset_ref="TS-HOLD", fit_r2=0.92, holdout_r2=0.88, holdout_rmse=0.04,
        artifact_hash="h-val-901", team_id=team_id, user_id=user_id,
    )
    dec = EngineeringDecision(
        id=uuid.uuid4(), decision_id="DEC-901", question="How to optimize heave?",
        context={"vehicle": "car"}, candidates=["SETUP-901"],
        selected_option={"setup_id": "SETUP-901"}, reason="better damping",
        tradeoffs={"comfort": "lower"}, risks=["stiffness"],
        simulation_evidence={"status": "ok"}, telemetry_evidence={"session": "s1"},
        validation_evidence={"validation_code": "VAL-901"}, author="Chief Engineer",
        artifact_hashes={"decision_hash": "h-dec-901"}, team_id=team_id, user_id=user_id,
    )
    app = ApprovalRecord(
        id=uuid.uuid4(), approval_number=901, approval_code="APP-901", decision_id="DEC-901",
        approver_name="Chief Engineer", approver_role="Chief", approval_signature="sig-901",
        artifact_hash="h-app-901", team_id=team_id, user_id=user_id,
    )

    p43_db.add_all([q, exp, sim, setup, val, dec, app])
    await p43_db.commit()

    rep = await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    assert rep.edges_created >= 4

    reconstructed = await EngineeringDecisionLoopService.reconstruct_complete_lineage(p43_db, "DEC-901")
    assert reconstructed["provenance_verified"] is True
    steps = {s["stage"]: s["id"] for s in reconstructed["lineage"]}
    assert steps["ENGINEERING_DECISION"] == "DEC-901"
    assert steps["APPROVAL"] == "APP-901"
    assert steps["BLIND_VALIDATION"] == "VAL-901"
    assert steps["SETUP"] == "SETUP-901"


def test_18_no_case_name_branching_in_reconstruction():
    """Requirement 18: No case-name branching ('3K', '3L', '3M', 'Stanford') in backfill or lineage code."""
    b_src = inspect.getsource(EvidenceGraphBackfillService)
    l_src = inspect.getsource(EngineeringDecisionLoopService.reconstruct_complete_lineage)

    for src in (b_src, l_src):
        for term in ("Phase3K", "Phase3L", "Phase3M", "Thunderhill", "Stanford"):
            assert term not in src, f"Disallowed case-specific token '{term}' detected in production service code!"


# ── REQUIREMENT 19: LEGACY RECONSTRUCT_COMPLETE_LINEAGE PRESERVED ─────────────

@pytest.mark.asyncio
async def test_19_legacy_reconstruct_complete_lineage_preserved(p43_db: AsyncSession):
    """Requirement 19: reconstruct_complete_lineage preserves caller contract and succeeds for multiple query IDs."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    await EngineeringDecisionLoopService.create_track_session(
        db=p43_db, user_id=user_id, team_id=team_id, session_number=381, session_code="TS-381"
    )
    await EngineeringDecisionLoopService.detect_anomaly(
        db=p43_db, user_id=user_id, team_id=team_id, session_id_or_code="TS-381", investigation_number=91
    )
    await EngineeringDecisionLoopService.create_engineering_question(
        db=p43_db, user_id=user_id, team_id=team_id, investigation_code="INV-91", question_number=17, question_text="Why did front axle roll increase?"
    )
    await EngineeringDecisionLoopService.create_experiment(
        db=p43_db, user_id=user_id, team_id=team_id, question_id="Q-17", experiment_number=52
    )
    await EngineeringDecisionLoopService.execute_simulation(
        db=p43_db, user_id=user_id, team_id=team_id, experiment_code="EXP-52", simulation_number=1844
    )
    await EngineeringDecisionLoopService.compare_setups(
        db=p43_db, user_id=user_id, team_id=team_id, comparison_number=31, candidate_setup_id="SETUP-92", simulation_run_id="RUN-001844", measured_session_code="TS-381"
    )
    await EngineeringDecisionLoopService.run_optimization(
        db=p43_db, user_id=user_id, team_id=team_id, experiment_code="EXP-52", optimization_number=18
    )
    await EngineeringDecisionLoopService.execute_blind_validation(
        db=p43_db, user_id=user_id, team_id=team_id, setup_id="SETUP-92", validation_number=31, telemetry_session_code="TS-381"
    )
    await EngineeringDecisionLoopService.create_engineering_decision(
        db=p43_db, user_id=user_id, team_id=team_id, decision_number=12, selected_setup_id="SETUP-92"
    )
    await EngineeringDecisionLoopService.approve_decision(
        db=p43_db, user_id=user_id, team_id=team_id, decision_code="DEC-12", approval_number=8
    )

    for q_id in ("DEC-12", "SETUP-92", "12"):
        res = await EngineeringDecisionLoopService.reconstruct_complete_lineage(p43_db, q_id)
        assert res["provenance_verified"] is True
        assert len(res["lineage"]) == 11
        steps = res["lineage"]
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


# ── REQUIREMENT 20: NO LEGACY TEXTUAL HEURISTICS IN ACTIVE RECONSTRUCTION ─────

def test_20_no_legacy_textual_heuristics_remain_in_active_reconstruction():
    """Requirement 20: Verified absence of legacy textual string matching in reconstruction."""
    source = inspect.getsource(EngineeringDecisionLoopService.reconstruct_complete_lineage)
    assert ".contains(" not in source
    assert "front roll stiffness" not in source
    assert "Front Axle" not in source


# ── REQUIREMENTS 21 & 22: TENANT & PERSONAL WORKSPACE ISOLATION ───────────────

@pytest.mark.asyncio
async def test_21_tenant_isolation(p43_db: AsyncSession):
    """Requirement 21: Cross-tenant data isolation strictly enforced during backfill and traversal."""
    team_1 = uuid.uuid4()
    team_2 = uuid.uuid4()
    user_id = uuid.uuid4()

    s1 = _make_telemetry_session(1, "TS-T1", "h1", team_id=team_1, user_id=user_id)
    i1 = _make_inv(1, "INV-T1", "TS-T1", "h1", team_1, user_id)
    s2 = _make_telemetry_session(2, "TS-T2", "h2", team_id=team_2, user_id=user_id)
    i2 = _make_inv(2, "INV-T2", "TS-T2", "h2", team_2, user_id)

    p43_db.add_all([s1, i1, s2, i2])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_1, user_id=user_id)
    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_2, user_id=user_id)

    t1_case = await EvidenceGraphBackfillService.rebuild_case_lineage(p43_db, "Investigation", "INV-T1", team_id=team_1)
    discovered_ids = {n["entity_id"] for n in t1_case["nodes"]}
    assert "INV-T1" in discovered_ids
    assert "TS-T1" in discovered_ids
    assert "INV-T2" not in discovered_ids
    assert "TS-T2" not in discovered_ids


@pytest.mark.asyncio
async def test_22_personal_workspace_isolation(p43_db: AsyncSession):
    """Requirement 22: Personal workspace isolation enforced when team_id is None."""
    user_1 = uuid.uuid4()
    user_2 = uuid.uuid4()

    s1 = _make_telemetry_session(1, "TS-U1", "h1", team_id=None, user_id=user_1)
    i1 = _make_inv(1, "INV-U1", "TS-U1", "h1", None, user_1)
    s2 = _make_telemetry_session(2, "TS-U2", "h2", team_id=None, user_id=user_2)
    i2 = _make_inv(2, "INV-U2", "TS-U2", "h2", None, user_2)

    p43_db.add_all([s1, i1, s2, i2])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=None, user_id=user_1)
    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=None, user_id=user_2)

    u1_case = await EvidenceGraphBackfillService.rebuild_case_lineage(p43_db, "Investigation", "INV-U1", team_id=None, user_id=user_1)
    discovered_ids = {n["entity_id"] for n in u1_case["nodes"]}
    assert "INV-U1" in discovered_ids
    assert "TS-U1" in discovered_ids
    assert "INV-U2" not in discovered_ids
    assert "TS-U2" not in discovered_ids


# ── REQUIREMENT 23: NO CYCLE INTRODUCED ───────────────────────────────────────

@pytest.mark.asyncio
async def test_23_no_cycle_introduced(p43_db: AsyncSession):
    """Requirement 23: Adversarial cycle attempt fails closed and is rejected with CycleDetectedError."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    q = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-CYC", title="q", question_text="q",
        created_by="Engineer", team_id=team_id, created_by_user_id=user_id,
    )
    exp = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-CYC", problem_id="P", hypothesis_id="H",
        control_variables={}, treatment_variables={}, held_constant_variables={},
        measured_outputs=[], expected_effect={}, constraints={}, validity_domain={},
        artifact_hash="h-exp-cyc", team_id=team_id, user_id=user_id,
    )
    p43_db.add_all([q, exp])
    await p43_db.commit()

    await EvidenceGraphService.record_edge(
        db=p43_db, user_id=user_id, team_id=team_id,
        source_type="EngineeringQuestion", source_id="Q-CYC",
        relationship="TESTED_BY",
        target_type="ControlledExperiment", target_id="EXP-CYC",
    )

    with pytest.raises(CycleDetectedError):
        await EvidenceGraphService.record_edge(
            db=p43_db, user_id=user_id, team_id=team_id,
            source_type="ControlledExperiment", source_id="EXP-CYC",
            relationship="HYPOTHESIZED_FROM",
            target_type="EngineeringQuestion", target_id="Q-CYC",
        )


# ── REQUIREMENTS 24, 25, 26: DETERMINISM & STABILITY ──────────────────────────

@pytest.mark.asyncio
async def test_24_deterministic_edge_set(p43_db: AsyncSession):
    """Requirement 24: Deterministic edge set across repeated scope backfills."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(124, "TS-124", "h-ts", team_id=team_id, user_id=user_id)
    inv = _make_inv(124, "INV-124", "TS-124", "h-inv", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    edges1 = await EvidenceGraphService.list_edges(p43_db, team_id=team_id)

    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
    edges2 = await EvidenceGraphService.list_edges(p43_db, team_id=team_id)

    assert len(edges1) == len(edges2)
    assert [e.edge_hash for e in edges1] == [e.edge_hash for e in edges2]


@pytest.mark.asyncio
async def test_25_deterministic_traversal_result(p43_db: AsyncSession):
    """Requirement 25: Traversal results are deterministic across repeated queries."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(125, "TS-125", "h-ts", team_id=team_id, user_id=user_id)
    inv = _make_inv(125, "INV-125", "TS-125", "h-inv", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)

    res1 = await EvidenceGraphService.traverse_backward(p43_db, "TelemetrySession", "TS-125", team_id=team_id)
    res2 = await EvidenceGraphService.traverse_backward(p43_db, "TelemetrySession", "TS-125", team_id=team_id)

    assert [n["entity_id"] for n in res1["nodes"]] == [n["entity_id"] for n in res2["nodes"]]
    assert [e["id"] for e in res1["edges"]] == [e["id"] for e in res2["edges"]]


@pytest.mark.asyncio
async def test_26_graph_edge_count_stable_across_repeated_backfill(p43_db: AsyncSession):
    """Requirement 26: Graph edge count remains completely stable across 5 repeated backfills."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    sess = _make_telemetry_session(126, "TS-126", "h-ts", team_id=team_id, user_id=user_id)
    inv = _make_inv(126, "INV-126", "TS-126", "h-inv", team_id, user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    counts = []
    for _ in range(5):
        await EvidenceGraphBackfillService.backfill_scope(p43_db, team_id=team_id, user_id=user_id)
        edges = await EvidenceGraphService.list_edges(p43_db, team_id=team_id)
        counts.append(len(edges))

    assert len(set(counts)) == 1
    assert counts[0] == 1


# ── REQUIREMENTS 27 & 28: IMMUTABLE SCIENTIFIC ASSETS ─────────────────────────

def test_27_protected_phase3_artifacts_unchanged():
    """Requirement 27: Verify frozen Phase 3 baseline manifests remain bit-for-bit identical."""
    with open("pre_phase4_3_hashes.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    manifest_hashes = data.get("manifests", {})
    assert len(manifest_hashes) == 7

    for rel_path, expected_hash in manifest_hashes.items():
        assert os.path.exists(rel_path), f"Manifest file missing: {rel_path}"
        with open(rel_path, "rb") as mf:
            current_hash = hashlib.sha256(mf.read()).hexdigest()
        assert current_hash == expected_hash, f"Protected manifest {rel_path} was modified!"


def test_28_production_physics_unchanged():
    """Requirement 28: Verify all 81 production physics source files remain 100% untouched."""
    with open("pre_phase4_3_hashes.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    physics_hashes = data.get("physics", {})
    assert len(physics_hashes) == 81, f"Expected 81 physics files, found {len(physics_hashes)}"

    for rel_path, expected_hash in physics_hashes.items():
        assert os.path.exists(rel_path), f"Physics file missing: {rel_path}"
        with open(rel_path, "rb") as f:
            curr_hash = hashlib.sha256(f.read()).hexdigest()
        assert curr_hash == expected_hash, f"CRITICAL: Production physics file {rel_path} was modified!"


# ── REQUIREMENT 29: CANONICAL PHASE 4.1 EDGE HASH CONTRACT ───────────────────

@pytest.mark.asyncio
async def test_29_canonical_phase4_1_edge_hash_contract(p43_db: AsyncSession):
    """
    Requirement 29: Proves Phase 4.1 canonical edge_hash contract is 100% preserved.
    Verifies that:
    1. Direct Phase 4.1 edge created before backfill uses the 11-field canonical edge_hash.
    2. Historical backfill over the same logical relationship yields the exact same canonical edge_hash.
    3. Endpoint artifact hashes and metadata remain integral parts of the canonical edge identity.
    """
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()
    source_artifact_hash = "f6e5d4c3b2a10000000000000000000000000000000000000000000000000002"
    target_artifact_hash = "a1b2c3d4e5f60000000000000000000000000000000000000000000000000001"

    sess = _make_telemetry_session(290, "TS-HASH-29", target_artifact_hash, team_id=team_id, user_id=user_id)
    inv = _make_inv(290, "INV-HASH-29", "TS-HASH-29", source_artifact_hash, team_id=team_id, user_id=user_id)
    p43_db.add_all([sess, inv])
    await p43_db.commit()

    expected_metadata = {"backfill_source": "persisted_relationship_field", "source_field": "session_code"}

    # 1. Direct Phase 4.1 edge creation before backfill
    p41_edge = await EvidenceGraphService.record_edge(
        db=p43_db,
        team_id=team_id,
        user_id=user_id,
        source_type="Investigation",
        source_id="INV-HASH-29",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-HASH-29",
        metadata=expected_metadata,
        idempotent=False,
    )
    p41_hash = p41_edge.edge_hash

    # Verify edge has 11-field canonical hash matching compute_edge_hash
    computed_hash = compute_edge_hash(
        organization_id=None,
        team_id=team_id,
        source_type="Investigation",
        source_id="INV-HASH-29",
        source_artifact_hash=source_artifact_hash,
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-HASH-29",
        target_artifact_hash=target_artifact_hash,
        metadata=expected_metadata,
        created_by_user_id=user_id,
    )
    assert p41_hash == computed_hash
    assert p41_edge.source_artifact_hash == source_artifact_hash
    assert p41_edge.target_artifact_hash == target_artifact_hash

    # 2. Historical backfill executes over the same scope
    backfill_report = await EvidenceGraphBackfillService.backfill_scope(
        db=p43_db,
        team_id=team_id,
        user_id=user_id,
    )
    assert backfill_report.already_existing == 1
    assert backfill_report.edges_created == 0

    # 3. Retrieve edge from DB and verify exact hash preservation
    persisted_edge = await EvidenceGraphService.get_edge(p43_db, p41_edge.id, team_id=team_id)
    assert persisted_edge is not None
    assert persisted_edge.edge_hash == p41_hash
    assert persisted_edge.edge_hash == computed_hash
    assert persisted_edge.source_artifact_hash == source_artifact_hash
    assert persisted_edge.target_artifact_hash == target_artifact_hash
    assert persisted_edge.metadata_ == expected_metadata

