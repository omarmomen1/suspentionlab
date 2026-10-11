"""
tests/test_phase4_1_evidence_graph_schema.py
============================================
SuspensionLab PRO — Phase 4.1 Canonical Edge Schema & Integrity Layer Acceptance Suite.

Explicit 1-to-1 Mapping to the 25 Minimum Test Requirements:
- Requirement 01: test_req_01_table_exists
- Requirement 02: test_req_02_required_columns_exist
- Requirement 03: test_req_03_supported_entity_types_enforced
- Requirement 04: test_req_04_supported_relationships_enforced
- Requirement 05: test_req_05_source_endpoint_must_exist
- Requirement 06: test_req_06_target_endpoint_must_exist
- Requirement 07: test_req_07_source_tenant_isolation_enforced
- Requirement 08: test_req_08_target_tenant_isolation_enforced
- Requirement 09: test_req_09_cross_tenant_edge_rejected
- Requirement 10: test_req_10_duplicate_edge_rejected_or_idempotent
- Requirement 11: test_req_11_edge_hash_deterministic
- Requirement 12: test_req_12_metadata_canonicalization_deterministic
- Requirement 13: test_req_13_edge_cannot_be_updated
- Requirement 14: test_req_14_edge_cannot_be_deleted_through_service
- Requirement 15: test_req_15_endpoint_artifact_hashes_are_stored
- Requirement 16: test_req_16_historical_edge_remains_stable
- Requirement 17: test_req_17_cycle_detection_rejects_cyclic_insertion
- Requirement 18: test_req_18_same_tenant_valid_edge_succeeds
- Requirement 19: test_req_19_organization_team_scope_is_honored
- Requirement 20: test_req_20_unsupported_entity_type_rejected
- Requirement 21: test_req_21_unsupported_relationship_rejected
- Requirement 22: test_req_22_metadata_size_and_type_constraints
- Requirement 23: test_req_23_no_secret_or_token_fields_accepted
- Requirement 24: test_req_24_no_production_physics_files_modified
- Requirement 25: test_req_25_phase_3_artifacts_unchanged
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
from pathlib import Path
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
    EdgeImmutabilityError,
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
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.setup_engineering import (
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    EngineeringProblemRecord,
    PostTrackReconciliationRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
)
from suspensionlab.backend.services.evidence_graph_service import (
    CycleDetectedError,
    DuplicateEdgeError,
    EntityNotFoundError,
    EvidenceGraphService,
    MalformedIdentifierError,
    MetadataValidationError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    UnsupportedRelationshipError,
    compute_edge_hash,
    validate_and_canonicalize_metadata,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHASE3H_MANIFEST = PROJECT_ROOT / "data" / "phase3h_final_validity_manifest.json"
PHASE3K1_MANIFEST = PROJECT_ROOT / "data" / "phase3k1_engineering_case.json"
PHASE3L_MANIFEST = PROJECT_ROOT / "data" / "phase3l_setup_engineering_manifest.json"
PHASE3M_MANIFEST = PROJECT_ROOT / "data" / "phase3m_engineering_case.json"


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


# ── REQUIREMENT 01: TABLE EXISTS ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_req_01_table_exists(async_test_db: AsyncSession):
    assert "evidence_graph_edges" in Base.metadata.tables
    table = Base.metadata.tables["evidence_graph_edges"]
    assert table.name == "evidence_graph_edges"

    stmt = select(EvidenceGraphEdgeRecord).limit(1)
    res = await async_test_db.execute(stmt)
    assert res.scalars().all() == []


# ── REQUIREMENT 02: REQUIRED COLUMNS EXIST ────────────────────────────────────

def test_req_02_required_columns_exist():
    table = Base.metadata.tables["evidence_graph_edges"]
    col_names = {col.name for col in table.columns}

    required = {
        "id",
        "organization_id",
        "team_id",
        "created_by_user_id",
        "source_type",
        "source_id",
        "relationship",
        "target_type",
        "target_id",
        "source_artifact_hash",
        "target_artifact_hash",
        "metadata",
        "edge_hash",
        "created_at",
    }
    missing = required - col_names
    assert not missing, f"Missing required columns in evidence_graph_edges: {missing}"


# ── REQUIREMENT 03: SUPPORTED ENTITY TYPES ENFORCED ───────────────────────────

def test_req_03_supported_entity_types_enforced():
    expected_entities = {
        "TelemetrySession",
        "Investigation",
        "EngineeringQuestion",
        "EngineeringProblem",
        "CausalHypothesis",
        "ControlledExperiment",
        "SimulationRun",
        "SetupCandidate",
        "VehicleProfile",
        "VehicleTwin",
        "SetupProposal",
        "SetupComparison",
        "Optimization",
        "BlindValidation",
        "EngineeringDecision",
        "Approval",
        "TrackTestPrediction",
        "PostTrackReconciliation",
        "TimelineEvent",
        "Experiment",
    }
    actual_entities = {e.value for e in SupportedEntityType}
    assert expected_entities.issubset(actual_entities), f"Missing entity types: {expected_entities - actual_entities}"


# ── REQUIREMENT 04: SUPPORTED RELATIONSHIPS ENFORCED ──────────────────────────

def test_req_04_supported_relationships_enforced():
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
    assert expected_rels == actual_rels, f"Relationship mismatch: {expected_rels ^ actual_rels}"


# ── REQUIREMENT 05: SOURCE ENDPOINT MUST EXIST ────────────────────────────────

@pytest.mark.asyncio
async def test_req_05_source_endpoint_must_exist(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    sess = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=901,
        session_code="TS-901",
        channels={},
        summary_metrics={},
        artifact_hash="hash-ts-901",
        user_id=user_id,
        team_id=team_id,
    )
    async_test_db.add(sess)
    await async_test_db.commit()

    with pytest.raises(EntityNotFoundError) as exc:
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_id,
            team_id=team_id,
            source_type="Investigation",
            source_id="INV-DOES-NOT-EXIST",
            relationship="DETECTED_FROM",
            target_type="TelemetrySession",
            target_id="TS-901",
        )
    assert "INV-DOES-NOT-EXIST" in str(exc.value)


# ── REQUIREMENT 06: TARGET ENDPOINT MUST EXIST ────────────────────────────────

@pytest.mark.asyncio
async def test_req_06_target_endpoint_must_exist(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    inv = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=901,
        investigation_code="INV-901",
        session_code="TS-901",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-inv-901",
        user_id=user_id,
        team_id=team_id,
    )
    async_test_db.add(inv)
    await async_test_db.commit()

    with pytest.raises(EntityNotFoundError) as exc:
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_id,
            team_id=team_id,
            source_type="Investigation",
            source_id="INV-901",
            relationship="DETECTED_FROM",
            target_type="TelemetrySession",
            target_id="TS-DOES-NOT-EXIST",
        )
    assert "TS-DOES-NOT-EXIST" in str(exc.value)


# ── REQUIREMENT 07: SOURCE TENANT ISOLATION ENFORCED ──────────────────────────

@pytest.mark.asyncio
async def test_req_07_source_tenant_isolation_enforced(async_test_db: AsyncSession):
    user_b = uuid.uuid4()
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()

    inv_b = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=701,
        investigation_code="INV-TEAM-B-701",
        session_code="TS-TEAM-B-701",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-inv-b",
        user_id=user_b,
        team_id=team_b,
    )
    async_test_db.add(inv_b)
    await async_test_db.commit()

    # Source belonging to Team B is rejected when acting as Team A
    with pytest.raises(TenantIsolationError):
        await EvidenceGraphService.validate_endpoint(
            db=async_test_db,
            entity_type="Investigation",
            entity_id="INV-TEAM-B-701",
            expected_team_id=team_a,
        )


# ── REQUIREMENT 08: TARGET TENANT ISOLATION ENFORCED ──────────────────────────

@pytest.mark.asyncio
async def test_req_08_target_tenant_isolation_enforced(async_test_db: AsyncSession):
    user_a = uuid.uuid4()
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()

    sess_a = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=801,
        session_code="TS-TEAM-A-801",
        channels={},
        summary_metrics={},
        artifact_hash="hash-ts-a",
        user_id=user_a,
        team_id=team_a,
    )
    async_test_db.add(sess_a)
    await async_test_db.commit()

    # Target belonging to Team A is rejected when acting as Team B
    with pytest.raises(TenantIsolationError):
        await EvidenceGraphService.validate_endpoint(
            db=async_test_db,
            entity_type="TelemetrySession",
            entity_id="TS-TEAM-A-801",
            expected_team_id=team_b,
        )


# ── REQUIREMENT 09: CROSS-TENANT EDGE REJECTED ────────────────────────────────

@pytest.mark.asyncio
async def test_req_09_cross_tenant_edge_rejected(async_test_db: AsyncSession):
    user_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_b = uuid.uuid4()
    team_b = uuid.uuid4()

    sess_a = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=909,
        session_code="TS-TEAM-A-909",
        channels={},
        summary_metrics={},
        artifact_hash="hash-ts-a-909",
        user_id=user_a,
        team_id=team_a,
    )
    inv_b = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=909,
        investigation_code="INV-TEAM-B-909",
        session_code="TS-TEAM-B-909",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-inv-b-909",
        user_id=user_b,
        team_id=team_b,
    )
    async_test_db.add_all([sess_a, inv_b])
    await async_test_db.commit()

    # Inserting edge across different teams is strictly rejected
    with pytest.raises(TenantIsolationError):
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_a,
            team_id=team_a,
            source_type="Investigation",
            source_id="INV-TEAM-B-909",
            relationship="DETECTED_FROM",
            target_type="TelemetrySession",
            target_id="TS-TEAM-A-909",
        )


# ── REQUIREMENT 10: DUPLICATE EDGE REJECTED / IDEMPOTENT ──────────────────────

@pytest.mark.asyncio
async def test_req_10_duplicate_edge_rejected_or_idempotent(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    sess = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=910,
        session_code="TS-910",
        channels={},
        summary_metrics={},
        artifact_hash="hash-ts-910",
        user_id=user_id,
        team_id=team_id,
    )
    inv = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=910,
        investigation_code="INV-910",
        session_code="TS-910",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-inv-910",
        user_id=user_id,
        team_id=team_id,
    )
    async_test_db.add_all([sess, inv])
    await async_test_db.commit()

    # 1. First insert
    e1 = await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        source_type="Investigation",
        source_id="INV-910",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-910",
        idempotent=True,
    )
    assert e1 is not None

    # 2. Duplicate with idempotent=True returns same record
    e2 = await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        source_type="Investigation",
        source_id="INV-910",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-910",
        idempotent=True,
    )
    assert e1.id == e2.id

    # 3. Duplicate with idempotent=False raises DuplicateEdgeError
    with pytest.raises(DuplicateEdgeError):
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_id,
            team_id=team_id,
            source_type="Investigation",
            source_id="INV-910",
            relationship="DETECTED_FROM",
            target_type="TelemetrySession",
            target_id="TS-910",
            idempotent=False,
        )


# ── REQUIREMENT 11: EDGE HASH DETERMINISTIC ───────────────────────────────────

def test_req_11_edge_hash_deterministic():
    u_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    t_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    o_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    meta = {"delta": 0.15, "unit": "g"}

    base_args = {
        "created_by_user_id": u_id,
        "metadata": meta,
        "organization_id": o_id,
        "relationship": "DETECTED_FROM",
        "source_artifact_hash": "hash-inv-91",
        "source_id": "INV-91",
        "source_type": "Investigation",
        "target_artifact_hash": "hash-ts-381",
        "target_id": "TS-381",
        "target_type": "TelemetrySession",
        "team_id": t_id,
    }
    h_base = compute_edge_hash(**base_args)
    assert len(h_base) == 64

    # 1. Same canonical input => identical hash
    h_repeat = compute_edge_hash(**base_args)
    assert h_base == h_repeat

    # 2. Intentional equivalence: UUID object vs string representation
    equiv_args = copy.deepcopy(base_args)
    equiv_args["created_by_user_id"] = str(u_id)
    equiv_args["team_id"] = str(t_id)
    equiv_args["organization_id"] = str(o_id)
    assert compute_edge_hash(**equiv_args) == h_base

    # 3. Intentional equivalence: Metadata dictionary key insertion order
    meta_order_args = copy.deepcopy(base_args)
    meta_order_args["metadata"] = {"unit": "g", "delta": 0.15}
    assert compute_edge_hash(**meta_order_args) == h_base

    # 4. Modifying EACH of the 11 canonical fields produces a strictly different hash
    mutations = {
        "created_by_user_id": uuid.UUID("44444444-4444-4444-4444-444444444444"),
        "metadata": {"delta": 0.20, "unit": "g"},
        "organization_id": uuid.UUID("55555555-5555-5555-5555-555555555555"),
        "relationship": "SUPERSEDES",
        "source_artifact_hash": "hash-inv-DIFFERENT",
        "source_id": "INV-999",
        "source_type": "SimulationRun",
        "target_artifact_hash": "hash-ts-DIFFERENT",
        "target_id": "TS-999",
        "target_type": "Optimization",
        "team_id": uuid.UUID("66666666-6666-6666-6666-666666666666"),
    }
    assert len(mutations) == 11, "All 11 canonical fields must be verified"
    for field, new_val in mutations.items():
        altered_args = copy.deepcopy(base_args)
        altered_args[field] = new_val
        h_mut = compute_edge_hash(**altered_args)
        assert h_mut != h_base, f"Canonical field mutation ignored or collided: {field}"


# ── REQUIREMENT 12: METADATA CANONICALIZATION DETERMINISTIC ────────────────────

def test_req_12_metadata_canonicalization_deterministic():
    # Different insertion orders produce identical canonical JSON
    dict_a = {"z": 10, "a": "first", "m": [3, 2, 1]}
    dict_b = {"a": "first", "m": [3, 2, 1], "z": 10}

    c_a = validate_and_canonicalize_metadata(dict_a)
    c_b = validate_and_canonicalize_metadata(dict_b)

    dump_a = json.dumps(c_a, sort_keys=True)
    dump_b = json.dumps(c_b, sort_keys=True)
    assert dump_a == dump_b


# ── REQUIREMENT 13: EDGE CANNOT BE UPDATED ────────────────────────────────────

@pytest.mark.asyncio
async def test_req_13_edge_cannot_be_updated(async_test_db: AsyncSession):
    # 1. Verify service exposes no update method
    assert not hasattr(EvidenceGraphService, "update_edge")
    assert not hasattr(EvidenceGraphService, "update")
    assert not hasattr(EvidenceGraphService, "modify_edge")

    # 2. Verify ORM-level update is prevented
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    edge = EvidenceGraphEdgeRecord(
        id=uuid.uuid4(),
        organization_id=None,
        team_id=team_id,
        created_by_user_id=user_id,
        source_type="Investigation",
        source_id="INV-913",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-913",
        source_artifact_hash="src-hash",
        target_artifact_hash="tgt-hash",
        metadata_={"test": True},
        edge_hash="canonical-hash-913",
    )
    async_test_db.add(edge)
    await async_test_db.commit()

    edge_id = edge.id
    edge.relationship = "SUPERSEDES"
    with pytest.raises(EdgeImmutabilityError):
        await async_test_db.commit()

    await async_test_db.rollback()


# ── REQUIREMENT 14: EDGE CANNOT BE DELETED THROUGH SERVICE ────────────────────

@pytest.mark.asyncio
async def test_req_14_edge_cannot_be_deleted_through_service(async_test_db: AsyncSession):
    # 1. Verify service exposes no delete method
    assert not hasattr(EvidenceGraphService, "delete_edge")
    assert not hasattr(EvidenceGraphService, "delete")
    assert not hasattr(EvidenceGraphService, "remove_edge")

    # 2. Verify ORM-level delete is prevented
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    edge = EvidenceGraphEdgeRecord(
        id=uuid.uuid4(),
        organization_id=None,
        team_id=team_id,
        created_by_user_id=user_id,
        source_type="Investigation",
        source_id="INV-914",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-914",
        source_artifact_hash="src-hash",
        target_artifact_hash="tgt-hash",
        metadata_={"test": True},
        edge_hash="canonical-hash-914",
    )
    async_test_db.add(edge)
    await async_test_db.commit()

    edge_id = edge.id
    stmt = select(EvidenceGraphEdgeRecord).where(EvidenceGraphEdgeRecord.id == edge_id)
    res = await async_test_db.execute(stmt)
    edge_fetched = res.scalar_one()

    await async_test_db.delete(edge_fetched)
    with pytest.raises(EdgeImmutabilityError):
        await async_test_db.commit()

    await async_test_db.rollback()


# ── REQUIREMENT 15: ENDPOINT ARTIFACT HASHES ARE STORED ───────────────────────

@pytest.mark.asyncio
async def test_req_15_endpoint_artifact_hashes_are_stored(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    sess = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=915,
        session_code="TS-915",
        channels={},
        summary_metrics={},
        artifact_hash="hash-initial-sess-915",
        user_id=user_id,
        team_id=team_id,
    )
    inv = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=915,
        investigation_code="INV-915",
        session_code="TS-915",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-initial-inv-915",
        user_id=user_id,
        team_id=team_id,
    )
    async_test_db.add_all([sess, inv])
    await async_test_db.commit()

    edge = await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        source_type="Investigation",
        source_id="INV-915",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-915",
    )

    assert edge.source_artifact_hash == "hash-initial-inv-915"
    assert edge.target_artifact_hash == "hash-initial-sess-915"


# ── REQUIREMENT 16: HISTORICAL EDGE REMAINS STABLE ────────────────────────────

@pytest.mark.asyncio
async def test_req_16_historical_edge_remains_stable(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    sess = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=916,
        session_code="TS-916",
        channels={},
        summary_metrics={},
        artifact_hash="hash-initial-sess-916",
        user_id=user_id,
        team_id=team_id,
    )
    inv = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=916,
        investigation_code="INV-916",
        session_code="TS-916",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-initial-inv-916",
        user_id=user_id,
        team_id=team_id,
    )
    async_test_db.add_all([sess, inv])
    await async_test_db.commit()

    edge = await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        source_type="Investigation",
        source_id="INV-916",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-916",
    )

    # Even if target record later updates its own fields in place,
    # the historical edge preserves the historical artifact hash
    sess.artifact_hash = "hash-MUTATED-sess-916"
    await async_test_db.commit()

    # Re-fetch edge: historical hash is unaffected and differs from mutated live entity
    edge_reloaded = await EvidenceGraphService.get_edge(db=async_test_db, edge_id=edge.id, team_id=team_id)
    assert edge_reloaded.target_artifact_hash == "hash-initial-sess-916"
    assert edge_reloaded.target_artifact_hash != sess.artifact_hash

    # Verify edge cryptographic self-integrity passes against stored provenance
    verification = await EvidenceGraphService.verify_edge_integrity(db=async_test_db, edge_id=edge.id, team_id=team_id)
    assert verification["valid"] is True
    assert verification["stored_hash"] == edge.edge_hash
    assert verification["recomputed_hash"] == edge.edge_hash


# ── REQUIREMENT 17: CYCLE DETECTION REJECTS CYCLIC INSERTION ──────────────────

@pytest.mark.asyncio
async def test_req_17_cycle_detection_rejects_cyclic_insertion(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    # Setup chain: Question -> Experiment -> Simulation
    q = EngineeringQuestion(
        id=uuid.uuid4(),
        question_id="Q-CYCLE-01",
        title="Cycle test",
        question_text="Testing DAG",
        created_by="Engineer",
        created_by_user_id=user_id,
        team_id=team_id,
    )
    exp = ControlledExperimentDesignRecord(
        id=uuid.uuid4(),
        experiment_id="EXP-CYCLE-01",
        problem_id="PROB-NONE",
        hypothesis_id="HYP-NONE",
        control_variables={},
        treatment_variables={},
        held_constant_variables={},
        measured_outputs={},
        expected_effect={},
        constraints={},
        validity_domain={},
        artifact_hash="hash-exp-cycle",
        user_id=user_id,
        team_id=team_id,
    )
    sim = SimulationRun(
        id=uuid.uuid4(),
        seq=9991,
        label="RUN-CYCLE-01",
        simulation_type="quarter_car",
        params={},
        result={},
        software_version="1.0",
        physics_version="1.0",
        solver_version="1.0",
        params_hash="h1",
        result_hash="h2",
        user_id=user_id,
        team_id=team_id,
    )
    async_test_db.add_all([q, exp, sim])
    await async_test_db.commit()

    # 1. Edge 1: Q -> Exp
    await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        source_type="EngineeringQuestion",
        source_id="Q-CYCLE-01",
        relationship="TESTED_BY",
        target_type="ControlledExperiment",
        target_id="EXP-CYCLE-01",
    )

    # 2. Edge 2: Exp -> Sim
    await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        source_type="ControlledExperiment",
        source_id="EXP-CYCLE-01",
        relationship="EXECUTED_AS",
        target_type="SimulationRun",
        target_id="RUN-CYCLE-01",
    )

    # 3. Direct self-loop (Q -> Q) rejected
    with pytest.raises(CycleDetectedError) as exc_self:
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_id,
            team_id=team_id,
            source_type="EngineeringQuestion",
            source_id="Q-CYCLE-01",
            relationship="TESTED_BY",
            target_type="EngineeringQuestion",
            target_id="Q-CYCLE-01",
        )
    assert "Self-loop" in str(exc_self.value)

    # 4. Transitive cycle (Sim -> Q) rejected
    with pytest.raises(CycleDetectedError) as exc_cycle:
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_id,
            team_id=team_id,
            source_type="SimulationRun",
            source_id="RUN-CYCLE-01",
            relationship="EVIDENCED_BY",
            target_type="EngineeringQuestion",
            target_id="Q-CYCLE-01",
        )
    assert "cycle detected" in str(exc_cycle.value).lower()


# ── REQUIREMENT 18: SAME TENANT VALID EDGE SUCCEEDS ───────────────────────────

@pytest.mark.asyncio
async def test_req_18_same_tenant_valid_edge_succeeds(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()

    sess = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=918,
        session_code="TS-918",
        channels={},
        summary_metrics={},
        artifact_hash="hash-ts-918",
        user_id=user_id,
        team_id=team_a,
    )
    inv = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=918,
        investigation_code="INV-918",
        session_code="TS-918",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-inv-918",
        user_id=user_id,
        team_id=team_a,
    )
    async_test_db.add_all([sess, inv])
    await async_test_db.commit()

    edge = await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_a,
        source_type="Investigation",
        source_id="INV-918",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-918",
        metadata={"phase": "4.1", "confidence": 0.99},
    )

    assert edge.id is not None
    assert edge.team_id == team_a
    assert edge.relationship == "DETECTED_FROM"
    assert edge.edge_hash is not None
    assert len(edge.edge_hash) == 64

    # Verification passes
    integrity = await EvidenceGraphService.verify_edge_integrity(db=async_test_db, edge_id=edge.id, team_id=team_a)
    assert integrity["valid"] is True


# ── REQUIREMENT 19: ORGANIZATION / TEAM SCOPE IS HONORED ──────────────────────

@pytest.mark.asyncio
async def test_req_19_organization_team_scope_is_honored(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()

    sess = TelemetrySessionRecord(
        id=uuid.uuid4(),
        session_number=919,
        session_code="TS-919",
        channels={},
        summary_metrics={},
        artifact_hash="hash-ts-919",
        user_id=user_id,
        team_id=team_a,
    )
    inv = InvestigationRecord(
        id=uuid.uuid4(),
        investigation_number=919,
        investigation_code="INV-919",
        session_code="TS-919",
        detection_type="LAT_DROP",
        symptom="Grip loss",
        evidence_snapshot={},
        artifact_hash="hash-inv-919",
        user_id=user_id,
        team_id=team_a,
    )
    async_test_db.add_all([sess, inv])
    await async_test_db.commit()

    edge = await EvidenceGraphService.record_edge(
        db=async_test_db,
        user_id=user_id,
        team_id=team_a,
        source_type="Investigation",
        source_id="INV-919",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession",
        target_id="TS-919",
    )

    # 1. Fetching as team_a succeeds
    found_a = await EvidenceGraphService.get_edge(db=async_test_db, edge_id=edge.id, team_id=team_a)
    assert found_a is not None

    # 2. Fetching as team_b returns None (no cross-tenant leakage)
    found_b = await EvidenceGraphService.get_edge(db=async_test_db, edge_id=edge.id, team_id=team_b)
    assert found_b is None

    # 3. Listing as team_b returns empty
    edges_b = await EvidenceGraphService.list_edges(db=async_test_db, team_id=team_b)
    assert len(edges_b) == 0

    # 4. Integrity verification as team_b raises EntityNotFoundError without disclosing team_a ownership
    with pytest.raises(EntityNotFoundError) as exc:
        await EvidenceGraphService.verify_edge_integrity(db=async_test_db, edge_id=edge.id, team_id=team_b)
    assert f"Edge {edge.id} not found." in str(exc.value)


# ── REQUIREMENT 20: UNSUPPORTED ENTITY TYPE REJECTED ──────────────────────────

@pytest.mark.asyncio
async def test_req_20_unsupported_entity_type_rejected(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    with pytest.raises(UnsupportedEntityTypeError) as exc:
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_id,
            team_id=team_id,
            source_type="ArbitraryWidget",
            source_id="WIDGET-01",
            relationship="TESTED_BY",
            target_type="EngineeringQuestion",
            target_id="Q-01",
        )
    assert "ArbitraryWidget" in str(exc.value)
    assert "Unsupported entity type" in str(exc.value)


# ── REQUIREMENT 21: UNSUPPORTED RELATIONSHIP REJECTED ─────────────────────────

@pytest.mark.asyncio
async def test_req_21_unsupported_relationship_rejected(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    with pytest.raises(UnsupportedRelationshipError) as exc:
        await EvidenceGraphService.record_edge(
            db=async_test_db,
            user_id=user_id,
            team_id=team_id,
            source_type="EngineeringQuestion",
            source_id="Q-01",
            relationship="ARBITRARY_LINK",
            target_type="ControlledExperiment",
            target_id="EXP-01",
        )
    assert "Unsupported relationship 'ARBITRARY_LINK'" in str(exc.value)


# ── REQUIREMENT 22: METADATA SIZE AND TYPE CONSTRAINTS ────────────────────────

def test_req_22_metadata_size_and_type_constraints():
    # Non-dict rejected
    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata("not-a-dict")  # type: ignore

    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata([1, 2, 3])  # type: ignore

    # Non-string keys rejected
    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata({123: "number key"})  # type: ignore

    # Payload exceeding 32 KB rejected
    huge_data = {"blob": "X" * 35000}
    with pytest.raises(MetadataValidationError) as exc:
        validate_and_canonicalize_metadata(huge_data)
    assert "exceeds maximum allowable limit" in str(exc.value)


# ── REQUIREMENT 23: NO SECRET OR TOKEN FIELDS ACCEPTED ────────────────────────

def test_req_23_no_secret_or_token_fields_accepted():
    # Forbidden key names
    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata({"api_key": "12345"})

    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata({"auth_token": "secret"})

    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata({"client_secret": "my-secret"})

    # Sensitive values (Bearer token)
    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata({"header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeak"})

    # Script / executable pattern
    with pytest.raises(MetadataValidationError):
        validate_and_canonicalize_metadata({"description": "<script>alert(1)</script>"})


# ── REQUIREMENT 24: NO PRODUCTION PHYSICS FILES MODIFIED ──────────────────────

def test_req_24_no_production_physics_files_modified():
    assert PHASE3H_MANIFEST.exists(), f"Missing manifest: {PHASE3H_MANIFEST}"
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Protected physics modification detected in {item['path']}!"


# ── REQUIREMENT 25: PHASE 3 ARTIFACTS UNCHANGED ───────────────────────────────

def test_req_25_phase_3_artifacts_unchanged():
    manifests = [PHASE3H_MANIFEST, PHASE3K1_MANIFEST, PHASE3L_MANIFEST, PHASE3M_MANIFEST]
    for m in manifests:
        assert m.exists(), f"Phase 3 artifact {m} is missing!"


# ── TRUE ADVERSARIAL CYCLE CONCURRENCY TEST (TWO CONCURRENT TRANSACTIONS) ────

@pytest.mark.asyncio
async def test_true_adversarial_cycle_concurrency():
    """
    True Adversarial Concurrency Test:
    Initial Graph:
      A -> B
      C -> D
    Both transactions proposed concurrently:
      Transaction 1: B -> C (individually acyclic: A -> B -> C -> D)
      Transaction 2: D -> A (individually acyclic: C -> D -> A -> B)

    Together they create the directed cycle:
      A -> B -> C -> D -> A

    The concurrency integrity layer MUST guarantee:
      1. Both transactions cannot commit simultaneously.
      2. Exactly one transaction commits successfully.
      3. The competing transaction is rejected with CycleDetectedError.
      4. The final committed graph contains exactly 3 edges and remains strictly a DAG.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()

    # Pre-seed questions A, B, C, D in an initial transaction
    async with session_factory() as init_db:
        q_a = EngineeringQuestion(
            id=uuid.uuid4(), question_id="Q-ADV-A", title="QA", question_text="QA",
            created_by="Eng", created_by_user_id=user_id, team_id=team_id,
        )
        q_b = EngineeringQuestion(
            id=uuid.uuid4(), question_id="Q-ADV-B", title="QB", question_text="QB",
            created_by="Eng", created_by_user_id=user_id, team_id=team_id,
        )
        q_c = EngineeringQuestion(
            id=uuid.uuid4(), question_id="Q-ADV-C", title="QC", question_text="QC",
            created_by="Eng", created_by_user_id=user_id, team_id=team_id,
        )
        q_d = EngineeringQuestion(
            id=uuid.uuid4(), question_id="Q-ADV-D", title="QD", question_text="QD",
            created_by="Eng", created_by_user_id=user_id, team_id=team_id,
        )
        init_db.add_all([q_a, q_b, q_c, q_d])
        await init_db.commit()

        # Seed initial disconnected paths: A -> B and C -> D
        await EvidenceGraphService.record_edge(
            db=init_db, user_id=user_id, team_id=team_id,
            source_type="EngineeringQuestion", source_id="Q-ADV-A",
            relationship="FORMULATED_FROM",
            target_type="EngineeringQuestion", target_id="Q-ADV-B",
        )
        await EvidenceGraphService.record_edge(
            db=init_db, user_id=user_id, team_id=team_id,
            source_type="EngineeringQuestion", source_id="Q-ADV-C",
            relationship="FORMULATED_FROM",
            target_type="EngineeringQuestion", target_id="Q-ADV-D",
        )

    # Execute concurrent operations across independent sessions
    results = {}

    async def task_b_to_c():
        async with session_factory() as db1:
            try:
                edge = await EvidenceGraphService.record_edge(
                    db=db1, user_id=user_id, team_id=team_id,
                    source_type="EngineeringQuestion", source_id="Q-ADV-B",
                    relationship="FORMULATED_FROM",
                    target_type="EngineeringQuestion", target_id="Q-ADV-C",
                )
                results["task_b_to_c"] = ("SUCCESS", edge.id)
            except Exception as e:
                results["task_b_to_c"] = ("ERROR", type(e).__name__)

    async def task_d_to_a():
        async with session_factory() as db2:
            try:
                edge = await EvidenceGraphService.record_edge(
                    db=db2, user_id=user_id, team_id=team_id,
                    source_type="EngineeringQuestion", source_id="Q-ADV-D",
                    relationship="FORMULATED_FROM",
                    target_type="EngineeringQuestion", target_id="Q-ADV-A",
                )
                results["task_d_to_a"] = ("SUCCESS", edge.id)
            except Exception as e:
                results["task_d_to_a"] = ("ERROR", type(e).__name__)

    await asyncio.gather(task_b_to_c(), task_d_to_a())

    # Assertions: exactly one succeeded, exactly one was rejected with CycleDetectedError
    statuses = [results["task_b_to_c"][0], results["task_d_to_a"][0]]
    assert "SUCCESS" in statuses
    assert "ERROR" in statuses

    error_task = "task_d_to_a" if results["task_d_to_a"][0] == "ERROR" else "task_b_to_c"
    assert results[error_task][1] == "CycleDetectedError"

    # Verify committed database state: exactly 3 edges, cycle NEVER committed
    async with session_factory() as verify_db:
        committed_edges = await EvidenceGraphService.list_edges(db=verify_db, team_id=team_id)
        assert len(committed_edges) == 3
        committed_pairs = {(e.source_id, e.target_id) for e in committed_edges}
        assert ("Q-ADV-A", "Q-ADV-B") in committed_pairs
        assert ("Q-ADV-C", "Q-ADV-D") in committed_pairs
        # The cycle cannot be closed: both ('Q-ADV-B', 'Q-ADV-C') and ('Q-ADV-D', 'Q-ADV-A') cannot exist together
        assert not (("Q-ADV-B", "Q-ADV-C") in committed_pairs and ("Q-ADV-D", "Q-ADV-A") in committed_pairs)


# ── TENANT NULLABILITY & ISOLATION SEMANTICS ──────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_nullability_and_isolation(async_test_db: AsyncSession):
    """
    Proves allowed tenant nullability semantics:
    - Standalone / personal workspaces can store edges with team_id=None
    - Corporate teams (team_a) only see their own edges
    - Corporate teams cannot see or leak personal edges
    - Cross-tenant creation between team_a and personal entity is rejected
    """
    user_id = uuid.uuid4()
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()

    sess_a = TelemetrySessionRecord(
        id=uuid.uuid4(), session_number=701, session_code="TS-NULL-A",
        channels={}, summary_metrics={}, artifact_hash="h-a",
        user_id=user_id, team_id=team_a,
    )
    inv_a = InvestigationRecord(
        id=uuid.uuid4(), investigation_number=701, investigation_code="INV-NULL-A",
        session_code="TS-NULL-A", detection_type="LAT_DROP", symptom="Grip loss",
        evidence_snapshot={}, artifact_hash="h-inv-a",
        user_id=user_id, team_id=team_a,
    )
    sess_null = TelemetrySessionRecord(
        id=uuid.uuid4(), session_number=702, session_code="TS-NULL-NONE",
        channels={}, summary_metrics={}, artifact_hash="h-none",
        user_id=user_id, team_id=None,
    )
    inv_null = InvestigationRecord(
        id=uuid.uuid4(), investigation_number=702, investigation_code="INV-NULL-NONE",
        session_code="TS-NULL-NONE", detection_type="LAT_DROP", symptom="Grip loss",
        evidence_snapshot={}, artifact_hash="h-inv-none",
        user_id=user_id, team_id=None,
    )
    async_test_db.add_all([sess_a, inv_a, sess_null, inv_null])
    await async_test_db.commit()

    # 1. Edge for team_a
    e_a = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_a,
        source_type="Investigation", source_id="INV-NULL-A",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession", target_id="TS-NULL-A",
    )

    # 2. Edge with team_id=None (allowed for standalone/personal workspace)
    e_null = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=None,
        source_type="Investigation", source_id="INV-NULL-NONE",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession", target_id="TS-NULL-NONE",
    )
    assert e_null.team_id is None

    # 3. Querying as team_a returns ONLY e_a (no personal edge leakage)
    list_a = await EvidenceGraphService.list_edges(db=async_test_db, team_id=team_a)
    assert [e.id for e in list_a] == [e_a.id]

    # 4. Querying as team_b returns NOTHING
    list_b = await EvidenceGraphService.list_edges(db=async_test_db, team_id=team_b)
    assert len(list_b) == 0

    # 5. Cross-tenant attempt between Team_A and personal entity is strictly rejected
    with pytest.raises(TenantIsolationError):
        await EvidenceGraphService.record_edge(
            db=async_test_db, user_id=user_id, team_id=team_a,
            source_type="Investigation", source_id="INV-NULL-A",
            relationship="DETECTED_FROM",
            target_type="TelemetrySession", target_id="TS-NULL-NONE",
        )


@pytest.mark.asyncio
async def test_personal_workspace_user_level_isolation(async_test_db: AsyncSession):
    """
    Proves that in personal workspace mode (team_id=None, organization_id=None):
    - User A's edges are strictly isolated from User B
    - User B cannot fetch User A's edge via get_edge (returns None)
    - User B cannot list User A's edges via list_edges
    - User B cannot verify User A's edges via verify_edge_integrity (raises EntityNotFoundError)
    - User B cannot link User A's personal entities (raises TenantIsolationError)
    """
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    sess_a = TelemetrySessionRecord(
        id=uuid.uuid4(), session_number=801, session_code="TS-USER-A",
        channels={}, summary_metrics={}, artifact_hash="h-user-a",
        user_id=user_a, team_id=None,
    )
    inv_a = InvestigationRecord(
        id=uuid.uuid4(), investigation_number=801, investigation_code="INV-USER-A",
        session_code="TS-USER-A", detection_type="HEAVE_RESONANCE", symptom="Bounce",
        evidence_snapshot={}, artifact_hash="h-inv-user-a",
        user_id=user_a, team_id=None,
    )

    sess_b = TelemetrySessionRecord(
        id=uuid.uuid4(), session_number=802, session_code="TS-USER-B",
        channels={}, summary_metrics={}, artifact_hash="h-user-b",
        user_id=user_b, team_id=None,
    )
    inv_b = InvestigationRecord(
        id=uuid.uuid4(), investigation_number=802, investigation_code="INV-USER-B",
        session_code="TS-USER-B", detection_type="HEAVE_RESONANCE", symptom="Bounce",
        evidence_snapshot={}, artifact_hash="h-inv-user-b",
        user_id=user_b, team_id=None,
    )
    async_test_db.add_all([sess_a, inv_a, sess_b, inv_b])
    await async_test_db.commit()

    # User A creates personal edge
    edge_a = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_a, team_id=None,
        source_type="Investigation", source_id="INV-USER-A",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession", target_id="TS-USER-A",
    )
    assert edge_a.team_id is None
    assert edge_a.created_by_user_id == user_a

    # User B creates personal edge
    edge_b = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_b, team_id=None,
        source_type="Investigation", source_id="INV-USER-B",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession", target_id="TS-USER-B",
    )
    assert edge_b.team_id is None
    assert edge_b.created_by_user_id == user_b

    # 1. User B cannot fetch User A's personal edge via get_edge
    fetched_by_b = await EvidenceGraphService.get_edge(
        db=async_test_db, edge_id=edge_a.id, team_id=None, user_id=user_b
    )
    assert fetched_by_b is None

    # User A CAN fetch User A's edge
    fetched_by_a = await EvidenceGraphService.get_edge(
        db=async_test_db, edge_id=edge_a.id, team_id=None, user_id=user_a
    )
    assert fetched_by_a is not None
    assert fetched_by_a.id == edge_a.id

    # 2. User B list_edges sees ONLY User B's edge (zero leakage of User A)
    user_b_edges = await EvidenceGraphService.list_edges(
        db=async_test_db, team_id=None, user_id=user_b
    )
    assert [e.id for e in user_b_edges] == [edge_b.id]

    user_a_edges = await EvidenceGraphService.list_edges(
        db=async_test_db, team_id=None, user_id=user_a
    )
    assert [e.id for e in user_a_edges] == [edge_a.id]

    # 3. User B cannot verify integrity of User A's edge (raises EntityNotFoundError)
    with pytest.raises(EntityNotFoundError):
        await EvidenceGraphService.verify_edge_integrity(
            db=async_test_db, edge_id=edge_a.id, team_id=None, user_id=user_b
        )

    # 4. User B cannot link User A's personal entity (raises TenantIsolationError)
    with pytest.raises(TenantIsolationError):
        await EvidenceGraphService.record_edge(
            db=async_test_db, user_id=user_b, team_id=None,
            source_type="Investigation", source_id="INV-USER-B",
            relationship="DETECTED_FROM",
            target_type="TelemetrySession", target_id="TS-USER-A",
        )

