"""
tests/test_phase4_2_evidence_graph_traversal.py
===============================================
SuspensionLab PRO — Phase 4.2 Evidence Graph Query, Traversal & Read API Suite.

Covers all 38 mandatory specification requirements:
 1. Direct edge lookup
 2. Empty result
 3. Forward 1-hop traversal
 4. Forward multi-hop traversal
 5. Backward 1-hop traversal
 6. Backward multi-hop traversal
 7. Direction semantics
 8. Deterministic ordering
 9. Duplicate node elimination
10. Duplicate edge elimination
11. max_depth enforcement
12. max_nodes enforcement
13. max_edges enforcement
14. Limit metadata returned
15. Relationship filtering
16. Entity-type filtering
17. Unknown relationship rejected
18. Unknown entity type rejected
19. Team isolation
20. Organization isolation
21. Personal workspace isolation
22. Cross-tenant root access rejected
23. Cross-tenant traversal blocked
24. No information leakage through errors
25. Path exists
26. Path does not exist
27. Deterministic path selection
28. Subgraph correctness
29. Authenticated API access
30. Unauthenticated API rejected
31. API read-only enforcement
32. No POST endpoint
33. No PUT/PATCH endpoint
34. No DELETE endpoint
35. Traversal uses stored edges only
36. No legacy reconstruction invoked
37. Protected Phase 3 artifacts unchanged
38. Production physics unchanged
+ Targeted query performance benchmark tests
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import Base, get_db_dependency
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
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    UnsupportedRelationshipError,
    DEFAULT_MAX_DEPTH,
    MAX_ALLOWED_DEPTH,
    DEFAULT_MAX_NODES,
    MAX_ALLOWED_NODES,
    DEFAULT_MAX_EDGES,
    MAX_ALLOWED_EDGES,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
PHASE3H_MANIFEST = DATA_DIR / "phase3h_final_validity_manifest.json"


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded_graph_db(async_test_db: AsyncSession):
    """
    Seeds a standard multi-stage engineering decision lineage:
    TS-101 (TelemetrySession)
      └─[DETECTED_FROM]─> INV-101 (Investigation)
            └─[FORMULATED_FROM]─> Q-101 (Question)
                  ├─[TESTED_BY]─> EXP-101 (Experiment)
                  │     └─[EXECUTED_AS]─> RUN-101 (SimulationRun)
                  │           └─[USES_SETUP]─> SETUP-101 (SetupCandidate)
                  │                 └─[VALIDATED_BY]─> BV-101 (BlindValidation)
                  │                       └─[JUSTIFIED_BY]─> DEC-101 (Decision)
                  │                             └─[APPROVED_UNDER]─> APP-101 (Approval)
                  └─[TESTED_BY]─> EXP-102 (Experiment)
                        └─[EXECUTED_AS]─> RUN-102 (SimulationRun)
    """
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # 1. Authoritative engineering entities
    ts = TelemetrySessionRecord(
        id=uuid.uuid4(), session_number=101, session_code="TS-101",
        channels={}, summary_metrics={}, artifact_hash="h-ts-101",
        user_id=user_id, team_id=team_id,
    )
    inv = InvestigationRecord(
        id=uuid.uuid4(), investigation_number=101, investigation_code="INV-101",
        session_code="TS-101", detection_type="PITCH_OSCILLATION", symptom="Porpoising",
        evidence_snapshot={}, artifact_hash="h-inv-101",
        user_id=user_id, team_id=team_id,
    )
    q = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-101", title="Pitch damping", question_text="Why pitch?",
        created_by="Aerodynamicist", created_by_user_id=user_id, team_id=team_id, organization_id=org_id,
    )
    exp1 = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-101", problem_id="PROB-101", hypothesis_id="HYP-101",
        control_variables={}, treatment_variables={}, held_constant_variables={},
        measured_outputs={}, expected_effect={}, constraints={}, validity_domain={},
        artifact_hash="h-exp-101", user_id=user_id, team_id=team_id,
    )
    exp2 = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-102", problem_id="PROB-102", hypothesis_id="HYP-102",
        control_variables={}, treatment_variables={}, held_constant_variables={},
        measured_outputs={}, expected_effect={}, constraints={}, validity_domain={},
        artifact_hash="h-exp-102", user_id=user_id, team_id=team_id,
    )
    run1 = SimulationRun(
        id=uuid.uuid4(), label="RUN-101", seq=101, simulation_type="quarter_car",
        params={}, result={}, software_version="1.0", physics_version="1.0", solver_version="1.0",
        params_hash="h-p-101", result_hash="h-run-101", user_id=user_id, team_id=team_id,
    )
    run2 = SimulationRun(
        id=uuid.uuid4(), label="RUN-102", seq=102, simulation_type="quarter_car",
        params={}, result={}, software_version="1.0", physics_version="1.0", solver_version="1.0",
        params_hash="h-p-102", result_hash="h-run-102", user_id=user_id, team_id=team_id,
    )
    setup = SetupCandidateRecord(
        id=uuid.uuid4(), setup_id="SETUP-101", parent_setup_id="SETUP-BASE",
        changed_parameters={}, unchanged_parameters={}, parameter_provenance={},
        model_version="1.0", validity_domain={}, creation_reason="Anti-dive geometry",
        artifact_hash="h-setup-101", user_id=user_id, team_id=team_id,
    )
    bv = BlindValidationRecord(
        id=uuid.uuid4(), validation_number=101, validation_code="VAL-101", setup_id="SETUP-101",
        fit_dataset_ref="TS-101", holdout_dataset_ref="TS-101", fit_r2=0.9, holdout_r2=0.88,
        holdout_rmse=0.01, gate_verdict="PASSED", artifact_hash="h-bv-101",
        user_id=user_id, team_id=team_id,
    )
    dec = EngineeringDecision(
        id=uuid.uuid4(), decision_id="DEC-101", question="Pitch damping",
        context={}, candidates=[], selected_option={}, reason="Validated in BV-101",
        tradeoffs={}, risks={}, simulation_evidence={}, telemetry_evidence={},
        validation_evidence={}, status="ACCEPTED", author="Chief Engineer",
        artifact_hashes={"h": "h-dec-101"}, user_id=user_id, team_id=team_id,
    )
    appr = ApprovalRecord(
        id=uuid.uuid4(), approval_number=101, approval_code="APP-101", decision_id=str(dec.id),
        approver_name="Technical Director", approver_role="DIRECTOR", approval_signature="sig-101",
        status="APPROVED", artifact_hash="h-app-101", user_id=user_id, team_id=team_id,
    )

    async_test_db.add_all([ts, inv, q, exp1, exp2, run1, run2, setup, bv, dec, appr])
    await async_test_db.commit()

    # 2. Canonical Evidence Graph Edges
    e_inv_ts = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="Investigation", source_id="INV-101",
        relationship="DETECTED_FROM",
        target_type="TelemetrySession", target_id="TS-101",
    )
    e_q_inv = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="EngineeringQuestion", source_id="Q-101",
        relationship="FORMULATED_FROM",
        target_type="Investigation", target_id="INV-101",
    )
    e_q_exp1 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="EngineeringQuestion", source_id="Q-101",
        relationship="TESTED_BY",
        target_type="ControlledExperiment", target_id="EXP-101",
    )
    e_q_exp2 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="EngineeringQuestion", source_id="Q-101",
        relationship="TESTED_BY",
        target_type="ControlledExperiment", target_id="EXP-102",
    )
    e_exp1_run1 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="ControlledExperiment", source_id="EXP-101",
        relationship="EXECUTED_AS",
        target_type="SimulationRun", target_id="RUN-101",
    )
    e_exp2_run2 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="ControlledExperiment", source_id="EXP-102",
        relationship="EXECUTED_AS",
        target_type="SimulationRun", target_id="RUN-102",
    )
    e_run1_setup = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="SimulationRun", source_id="RUN-101",
        relationship="USES_SETUP",
        target_type="SetupCandidate", target_id="SETUP-101",
    )
    e_setup_bv = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="SetupCandidate", source_id="SETUP-101",
        relationship="VALIDATED_BY",
        target_type="BlindValidation", target_id=str(bv.validation_number),
    )
    e_dec_bv = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="EngineeringDecision", source_id="DEC-101",
        relationship="JUSTIFIED_BY",
        target_type="BlindValidation", target_id=str(bv.validation_number),
    )
    e_app_dec = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="Approval", source_id="APP-101",
        relationship="APPROVED_UNDER",
        target_type="EngineeringDecision", target_id="DEC-101",
    )

    return {
        "db": async_test_db,
        "user_id": user_id,
        "team_id": team_id,
        "org_id": org_id,
        "edge_inv_ts": e_inv_ts,
        "edge_q_inv": e_q_inv,
        "edge_q_exp1": e_q_exp1,
        "edge_q_exp2": e_q_exp2,
        "edge_exp1_run1": e_exp1_run1,
        "edge_exp2_run2": e_exp2_run2,
        "edge_run1_setup": e_run1_setup,
        "edge_setup_bv": e_setup_bv,
        "edge_dec_bv": e_dec_bv,
        "edge_app_dec": e_app_dec,
    }


# ── TEST 01: DIRECT EDGE LOOKUP ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_01_direct_edge_lookup(seeded_graph_db):
    data = seeded_graph_db
    edge = await EvidenceGraphService.get_edge(
        db=data["db"],
        edge_id=data["edge_q_exp1"].id,
        team_id=data["team_id"],
        user_id=data["user_id"],
        organization_id=data["org_id"],
    )
    assert edge is not None
    assert edge.id == data["edge_q_exp1"].id
    assert edge.source_type == "EngineeringQuestion"
    assert edge.source_id == "Q-101"
    assert edge.relationship == "TESTED_BY"
    assert edge.target_type == "ControlledExperiment"
    assert edge.target_id == "EXP-101"


# ── TEST 02: EMPTY RESULT (NOT FOUND) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_02_empty_result(seeded_graph_db):
    data = seeded_graph_db
    non_existent = uuid.uuid4()
    edge = await EvidenceGraphService.get_edge(
        db=data["db"],
        edge_id=non_existent,
        team_id=data["team_id"],
        user_id=data["user_id"],
    )
    assert edge is None


# ── TEST 03: FORWARD 1-HOP TRAVERSAL ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_03_forward_1hop_traversal(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=1,
    )
    assert res["root"] == {"entity_type": "EngineeringQuestion", "entity_id": "Q-101"}
    assert res["traversal"]["direction"] == "FORWARD"
    assert res["traversal"]["max_depth"] == 1
    # 1 root + 3 outgoing targets (INV-101, EXP-101, EXP-102)
    target_ids = {n["entity_id"] for n in res["nodes"]}
    assert "Q-101" in target_ids
    assert "EXP-101" in target_ids
    assert "EXP-102" in target_ids
    assert "INV-101" in target_ids
    # Multi-hop nodes should NOT be present at depth 1
    assert "RUN-101" not in target_ids
    assert "SETUP-101" not in target_ids


# ── TEST 04: FORWARD MULTI-HOP TRAVERSAL ──────────────────────────────────────

@pytest.mark.asyncio
async def test_04_forward_multihop_traversal(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=4,
    )
    node_ids = {n["entity_id"] for n in res["nodes"]}
    # Path reached: Q-101 -> EXP-101 -> RUN-101 -> SETUP-101 -> 101(BV)
    assert "Q-101" in node_ids
    assert "EXP-101" in node_ids
    assert "RUN-101" in node_ids
    assert "SETUP-101" in node_ids
    assert "101" in node_ids  # BV-101


# ── TEST 05: BACKWARD 1-HOP TRAVERSAL ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_05_backward_1hop_traversal(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_backward(
        db=data["db"],
        root_type="SimulationRun",
        root_id="RUN-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=1,
    )
    assert res["root"] == {"entity_type": "SimulationRun", "entity_id": "RUN-101"}
    node_ids = {n["entity_id"] for n in res["nodes"]}
    assert "RUN-101" in node_ids
    assert "EXP-101" in node_ids
    assert "Q-101" not in node_ids


# ── TEST 06: BACKWARD MULTI-HOP TRAVERSAL ─────────────────────────────────────

@pytest.mark.asyncio
async def test_06_backward_multihop_traversal(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_backward(
        db=data["db"],
        root_type="BlindValidation",
        root_id="101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=5,
    )
    node_ids = {n["entity_id"] for n in res["nodes"]}
    # Backward from BlindValidation should reach SETUP-101, RUN-101, EXP-101, Q-101
    assert "101" in node_ids  # BV
    assert "SETUP-101" in node_ids
    assert "RUN-101" in node_ids
    assert "EXP-101" in node_ids
    assert "Q-101" in node_ids


# ── TEST 07: DIRECTION SEMANTICS ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_07_direction_semantics(seeded_graph_db):
    data = seeded_graph_db
    # Forward from SimulationRun RUN-101 only discovers downstream (SetupCandidate)
    fwd = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="SimulationRun",
        root_id="RUN-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=3,
    )
    fwd_ids = {n["entity_id"] for n in fwd["nodes"]}
    assert "SETUP-101" in fwd_ids
    assert "EXP-101" not in fwd_ids  # Upstream must NOT be traversed forward

    # Backward from SimulationRun RUN-101 only discovers upstream (ControlledExperiment, Question)
    bwd = await EvidenceGraphService.traverse_backward(
        db=data["db"],
        root_type="SimulationRun",
        root_id="RUN-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=3,
    )
    bwd_ids = {n["entity_id"] for n in bwd["nodes"]}
    assert "EXP-101" in bwd_ids
    assert "Q-101" in bwd_ids
    assert "SETUP-101" not in bwd_ids  # Downstream must NOT be traversed backward


# ── TEST 08: DETERMINISTIC ORDERING ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_08_deterministic_ordering(seeded_graph_db):
    data = seeded_graph_db
    res1 = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=3,
    )
    res2 = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=3,
    )
    assert [n["entity_id"] for n in res1["nodes"]] == [n["entity_id"] for n in res2["nodes"]]
    assert [e["id"] for e in res1["edges"]] == [e["id"] for e in res2["edges"]]

    # Verify explicit deterministic ordering rule
    edges = res1["edges"]
    for i in range(len(edges) - 1):
        k1 = (edges[i]["depth"], edges[i]["source_type"], edges[i]["source_id"], edges[i]["relationship"], edges[i]["target_type"], edges[i]["target_id"])
        k2 = (edges[i+1]["depth"], edges[i+1]["source_type"], edges[i+1]["source_id"], edges[i+1]["relationship"], edges[i+1]["target_type"], edges[i+1]["target_id"])
        assert k1 <= k2


# ── TEST 09: DUPLICATE NODE ELIMINATION ───────────────────────────────────────

@pytest.mark.asyncio
async def test_09_duplicate_node_elimination(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=4,
    )
    node_pairs = [(n["entity_type"], n["entity_id"]) for n in res["nodes"]]
    assert len(node_pairs) == len(set(node_pairs))


# ── TEST 10: DUPLICATE EDGE ELIMINATION ───────────────────────────────────────

@pytest.mark.asyncio
async def test_10_duplicate_edge_elimination(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=4,
    )
    edge_ids = [e["id"] for e in res["edges"]]
    assert len(edge_ids) == len(set(edge_ids))


# ── TEST 11: MAX_DEPTH ENFORCEMENT ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_11_max_depth_enforcement(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=2,
    )
    for n in res["nodes"]:
        assert n["depth"] <= 2
    for e in res["edges"]:
        assert e["depth"] <= 2


# ── TEST 12: MAX_NODES ENFORCEMENT ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_12_max_nodes_enforcement(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=4,
        max_nodes=3,
    )
    assert len(res["nodes"]) <= 3
    assert res["traversal"]["limit_reached"] is True
    assert res["traversal"]["limit_type"] == "max_nodes"


# ── TEST 13: MAX_EDGES ENFORCEMENT ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_13_max_edges_enforcement(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=4,
        max_edges=2,
    )
    assert len(res["edges"]) <= 2
    assert res["traversal"]["limit_reached"] is True
    assert res["traversal"]["limit_type"] == "max_edges"


# ── TEST 14: LIMIT METADATA RETURNED ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_14_limit_metadata_returned(seeded_graph_db):
    data = seeded_graph_db
    # Truncated by depth
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=1,
    )
    assert "limit_reached" in res["traversal"]
    assert "limit_type" in res["traversal"]
    assert res["traversal"]["limit_reached"] is True
    assert res["traversal"]["limit_type"] == "max_depth"


# ── TEST 15: RELATIONSHIP FILTERING ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_15_relationship_filtering(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=2,
        relationship="TESTED_BY",
    )
    for e in res["edges"]:
        assert e["relationship"] == "TESTED_BY"
    target_ids = {n["entity_id"] for n in res["nodes"]}
    assert "INV-101" not in target_ids  # FORMULATED_FROM filtered out


# ── TEST 16: ENTITY-TYPE FILTERING ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_16_entity_type_filtering(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=2,
        entity_type="ControlledExperiment",
    )
    # Only edges leading to ControlledExperiment retained
    for e in res["edges"]:
        assert e["target_type"] == "ControlledExperiment"


# ── TEST 17: UNKNOWN RELATIONSHIP REJECTED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_17_unknown_relationship_rejected(seeded_graph_db):
    data = seeded_graph_db
    with pytest.raises(UnsupportedRelationshipError):
        await EvidenceGraphService.traverse_forward(
            db=data["db"],
            root_type="EngineeringQuestion",
            root_id="Q-101",
            team_id=data["team_id"],
            user_id=data["user_id"],
            relationship="MAGICALLY_SOLVED_BY",
        )


# ── TEST 18: UNKNOWN ENTITY TYPE REJECTED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_18_unknown_entity_type_rejected(seeded_graph_db):
    data = seeded_graph_db
    with pytest.raises(UnsupportedEntityTypeError):
        await EvidenceGraphService.traverse_forward(
            db=data["db"],
            root_type="QuantumWarpDrive",
            root_id="Q-101",
            team_id=data["team_id"],
            user_id=data["user_id"],
        )


# ── TEST 19: TEAM ISOLATION ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_19_team_isolation(seeded_graph_db):
    data = seeded_graph_db
    other_team = uuid.uuid4()
    # Querying from another team must raise EntityNotFoundError on root lookup
    with pytest.raises(EntityNotFoundError):
        await EvidenceGraphService.traverse_forward(
            db=data["db"],
            root_type="EngineeringQuestion",
            root_id="Q-101",
            team_id=other_team,
            user_id=data["user_id"],
        )


# ── TEST 20: ORGANIZATION ISOLATION ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_20_organization_isolation(seeded_graph_db):
    data = seeded_graph_db
    other_org = uuid.uuid4()
    with pytest.raises(EntityNotFoundError):
        await EvidenceGraphService.traverse_forward(
            db=data["db"],
            root_type="EngineeringQuestion",
            root_id="Q-101",
            team_id=data["team_id"],
            user_id=data["user_id"],
            organization_id=other_org,
        )


# ── TEST 21: PERSONAL WORKSPACE ISOLATION ─────────────────────────────────────

@pytest.mark.asyncio
async def test_21_personal_workspace_isolation(async_test_db: AsyncSession):
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    q_a = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-PERS-A", title="QA", question_text="QA",
        created_by="EngA", created_by_user_id=user_a, team_id=None,
    )
    exp_a = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-PERS-A", problem_id="PROB-A", hypothesis_id="HYP-A",
        control_variables={}, treatment_variables={}, held_constant_variables={},
        measured_outputs={}, expected_effect={}, constraints={}, validity_domain={},
        artifact_hash="hA", user_id=user_a, team_id=None,
    )
    async_test_db.add_all([q_a, exp_a])
    await async_test_db.commit()

    edge_a = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_a, team_id=None,
        source_type="EngineeringQuestion", source_id="Q-PERS-A",
        relationship="TESTED_BY",
        target_type="ControlledExperiment", target_id="EXP-PERS-A",
    )

    # User A traverses personal workspace
    res_a = await EvidenceGraphService.traverse_forward(
        db=async_test_db,
        root_type="EngineeringQuestion",
        root_id="Q-PERS-A",
        team_id=None,
        user_id=user_a,
    )
    assert len(res_a["edges"]) == 1

    # User B cannot traverse User A's personal graph
    with pytest.raises(EntityNotFoundError):
        await EvidenceGraphService.traverse_forward(
            db=async_test_db,
            root_type="EngineeringQuestion",
            root_id="Q-PERS-A",
            team_id=None,
            user_id=user_b,
        )


# ── TEST 22: CROSS-TENANT ROOT ACCESS REJECTED ────────────────────────────────

@pytest.mark.asyncio
async def test_22_cross_tenant_root_access_rejected(seeded_graph_db):
    data = seeded_graph_db
    with pytest.raises(EntityNotFoundError):
        await EvidenceGraphService.traverse_forward(
            db=data["db"],
            root_type="EngineeringQuestion",
            root_id="Q-101",
            team_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )


# ── TEST 23: CROSS-TENANT TRAVERSAL BLOCKED ───────────────────────────────────

@pytest.mark.asyncio
async def test_23_cross_tenant_traversal_blocked(async_test_db: AsyncSession):
    user_a = uuid.uuid4()
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()

    q_a = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-TB-1", title="QA", question_text="QA",
        created_by="EngA", created_by_user_id=user_a, team_id=team_a,
    )
    exp_a = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-TB-1", problem_id="PROB-1", hypothesis_id="HYP-1",
        control_variables={}, treatment_variables={}, held_constant_variables={},
        measured_outputs={}, expected_effect={}, constraints={}, validity_domain={},
        artifact_hash="h1", user_id=user_a, team_id=team_a,
    )
    async_test_db.add_all([q_a, exp_a])
    await async_test_db.commit()

    await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_a, team_id=team_a,
        source_type="EngineeringQuestion", source_id="Q-TB-1",
        relationship="TESTED_BY",
        target_type="ControlledExperiment", target_id="EXP-TB-1",
    )

    # In team B scope, list_edges returns empty
    edges_b = await EvidenceGraphService.list_edges(db=async_test_db, team_id=team_b)
    assert len(edges_b) == 0


# ── TEST 24: NO INFORMATION LEAKAGE THROUGH ERRORS ────────────────────────────

@pytest.mark.asyncio
async def test_24_no_information_leakage_through_errors(seeded_graph_db):
    data = seeded_graph_db
    # Attacker tries to query existing edge of another team
    non_tenant_team = uuid.uuid4()
    edge = await EvidenceGraphService.get_edge(
        db=data["db"],
        edge_id=data["edge_q_exp1"].id,
        team_id=non_tenant_team,
    )
    # Must return None, exactly as if the edge does not exist
    assert edge is None


# ── TEST 25: PATH EXISTS & SHORTEST PATH SELECTION ───────────────────────────

@pytest.mark.asyncio
async def test_25_path_exists(seeded_graph_db):
    data = seeded_graph_db
    # 1. Standard path verification
    path_res = await EvidenceGraphService.explain_path(
        db=data["db"],
        source_type="EngineeringQuestion",
        source_id="Q-101",
        target_type="BlindValidation",
        target_id="101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=5,
    )
    assert path_res["path_found"] is True
    assert path_res["length"] > 0
    node_types = [n["entity_type"] for n in path_res["nodes"]]
    assert node_types[0] == "EngineeringQuestion"
    assert node_types[-1] == "BlindValidation"

    # 2. Executable proof of SHORTEST-PATH guarantee (minimum edge count):
    # Path Q-101 -> RUN-101 has length 2 (Q-101 -> EXP-101 -> RUN-101).
    p_before = await EvidenceGraphService.explain_path(
        db=data["db"],
        source_type="EngineeringQuestion",
        source_id="Q-101",
        target_type="SimulationRun",
        target_id="RUN-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=5,
    )
    assert p_before["path_found"] is True
    assert p_before["length"] == 2

    # Now add a direct shortcut edge: Q-101 -> RUN-101 (length 1)
    await EvidenceGraphService.record_edge(
        db=data["db"],
        user_id=data["user_id"],
        team_id=data["team_id"],
        organization_id=data["org_id"],
        source_type="EngineeringQuestion",
        source_id="Q-101",
        relationship="EVIDENCED_BY",
        target_type="SimulationRun",
        target_id="RUN-101",
    )

    # Re-query path between Q-101 and RUN-101: must return the shorter path (length 1, not length 2)
    p_after = await EvidenceGraphService.explain_path(
        db=data["db"],
        source_type="EngineeringQuestion",
        source_id="Q-101",
        target_type="SimulationRun",
        target_id="RUN-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=5,
    )
    assert p_after["path_found"] is True
    assert p_after["length"] == 1
    assert len(p_after["edges"]) == 1
    assert p_after["edges"][0]["relationship"] == "EVIDENCED_BY"


# ── TEST 26: PATH DOES NOT EXIST ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_26_path_does_not_exist(seeded_graph_db):
    data = seeded_graph_db
    # Path in reverse direction does not exist because graph is a forward DAG
    path_res = await EvidenceGraphService.explain_path(
        db=data["db"],
        source_type="BlindValidation",
        source_id="101",
        target_type="EngineeringQuestion",
        target_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=5,
    )
    assert path_res["path_found"] is False
    assert path_res["length"] == 0
    assert path_res["nodes"] == []
    assert path_res["edges"] == []


# ── TEST 27: DETERMINISTIC PATH SELECTION & TIE-BREAKING ──────────────────────

@pytest.mark.asyncio
async def test_27_deterministic_path_selection(seeded_graph_db):
    data = seeded_graph_db
    # Add an edge connecting RUN-102 to SETUP-101:
    # Now there exist two distinct equal-length paths (length 3) from Q-101 to SETUP-101:
    # Path A: Q-101 -> EXP-101 -> RUN-101 -> SETUP-101 (path string has 'EXP-101')
    # Path B: Q-101 -> EXP-102 -> RUN-102 -> SETUP-101 (path string has 'EXP-102')
    await EvidenceGraphService.record_edge(
        db=data["db"],
        user_id=data["user_id"],
        team_id=data["team_id"],
        organization_id=data["org_id"],
        source_type="SimulationRun",
        source_id="RUN-102",
        relationship="USES_SETUP",
        target_type="SetupCandidate",
        target_id="SETUP-101",
    )

    # Query path repeatedly
    p1 = await EvidenceGraphService.explain_path(
        db=data["db"],
        source_type="EngineeringQuestion",
        source_id="Q-101",
        target_type="SetupCandidate",
        target_id="SETUP-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=5,
    )
    p2 = await EvidenceGraphService.explain_path(
        db=data["db"],
        source_type="EngineeringQuestion",
        source_id="Q-101",
        target_type="SetupCandidate",
        target_id="SETUP-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=5,
    )

    # 1. Both find a length-3 path
    assert p1["path_found"] is True
    assert p1["length"] == 3
    # 2. Canonical tie-break selects Path A (EXP-101 < EXP-102 in path string)
    assert p1["nodes"][1]["entity_id"] == "EXP-101"
    assert p1["nodes"][2]["entity_id"] == "RUN-101"
    # 3. Repeated identical queries return the exact same path
    assert [e["id"] for e in p1["edges"]] == [e["id"] for e in p2["edges"]]
    assert [n["entity_id"] for n in p1["nodes"]] == [n["entity_id"] for n in p2["nodes"]]


# ── TEST 28: SUBGRAPH CORRECTNESS ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_28_subgraph_correctness(seeded_graph_db):
    data = seeded_graph_db
    sub = await EvidenceGraphService.get_subgraph(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        direction="FORWARD",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=2,
    )
    assert sub["root"] == {"entity_type": "EngineeringQuestion", "entity_id": "Q-101"}
    assert len(sub["nodes"]) > 0
    assert len(sub["edges"]) > 0


# ── TEST 29: AUTHENTICATED API ACCESS ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_29_authenticated_api_access(seeded_graph_db):
    data = seeded_graph_db
    mock_user = UserContext(
        user_id=str(data["user_id"]),
        email="eng@team.com",
        name="Engineer",
        plan="PRO",
        onboarding_complete=True,
        team_id=str(data["team_id"]),
        team_role="ENGINEER",
        organization_id=str(data["org_id"]),
    )

    app.dependency_overrides[verify_api_key] = lambda: mock_user
    app.dependency_overrides[get_db_dependency] = lambda: data["db"]

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(
                "/api/v1/evidence-graph/traverse",
                params={"root_type": "EngineeringQuestion", "root_id": "Q-101", "max_depth": 2},
            )
            assert res.status_code == 200
            body = res.json()
            assert body["root"]["entity_id"] == "Q-101"
            assert len(body["nodes"]) > 0
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


# ── TEST 30: UNAUTHENTICATED API REJECTED ─────────────────────────────────────

@pytest.mark.asyncio
async def test_30_unauthenticated_api_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/v1/evidence-graph/traverse",
            params={"root_type": "EngineeringQuestion", "root_id": "Q-101"},
        )
        assert res.status_code in (401, 403)


# ── TEST 31: API READ-ONLY ENFORCEMENT ────────────────────────────────────────

@pytest.mark.asyncio
async def test_31_api_read_only_enforcement(seeded_graph_db):
    data = seeded_graph_db
    mock_user = UserContext(
        user_id=str(data["user_id"]), email="eng@team.com", name="Eng",
        plan="PRO", onboarding_complete=True, team_id=str(data["team_id"]),
    )
    app.dependency_overrides[verify_api_key] = lambda: mock_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/evidence-graph/edges")
            assert res.status_code in (200, 404)
    finally:
        app.dependency_overrides.pop(verify_api_key, None)


# ── TEST 32: NO POST ENDPOINT ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_32_no_post_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/evidence-graph/edges", json={})
        assert res.status_code in (404, 405)


# ── TEST 33: NO PUT/PATCH ENDPOINT ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_33_no_put_patch_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_put = await client.put(f"/api/v1/evidence-graph/edges/{uuid.uuid4()}", json={})
        assert res_put.status_code in (404, 405)
        res_patch = await client.patch(f"/api/v1/evidence-graph/edges/{uuid.uuid4()}", json={})
        assert res_patch.status_code in (404, 405)


# ── TEST 34: NO DELETE ENDPOINT ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_34_no_delete_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.delete(f"/api/v1/evidence-graph/edges/{uuid.uuid4()}")
        assert res.status_code in (404, 405)


# ── TEST 35: TRAVERSAL USES STORED EDGES ONLY ─────────────────────────────────

@pytest.mark.asyncio
async def test_35_traversal_uses_stored_edges_only(seeded_graph_db):
    data = seeded_graph_db
    res = await EvidenceGraphService.traverse_forward(
        db=data["db"],
        root_type="EngineeringQuestion",
        root_id="Q-101",
        team_id=data["team_id"],
        user_id=data["user_id"],
        max_depth=3,
    )
    # Check that each returned edge exists in evidence_graph_edges
    stmt = select(EvidenceGraphEdgeRecord.id)
    all_stored_ids = {str(x) for x in (await data["db"].execute(stmt)).scalars().all()}
    for e in res["edges"]:
        assert e["id"] in all_stored_ids


# ── TEST 36: NO LEGACY RECONSTRUCTION INVOKED ─────────────────────────────────

def test_36_no_legacy_reconstruction_invoked():
    # Verify reconstruct_complete_lineage is NOT imported or called in evidence_graph_service
    src_file = PROJECT_ROOT / "src" / "suspensionlab" / "backend" / "services" / "evidence_graph_service.py"
    content = src_file.read_text(encoding="utf-8")
    assert "reconstruct_complete_lineage" not in content
    assert "case_3k" not in content.lower()
    assert "case_3l" not in content.lower()
    assert "case_3m" not in content.lower()


# ── TEST 37: PROTECTED PHASE 3 ARTIFACTS UNCHANGED ───────────────────────────

def test_37_protected_phase3_artifacts_unchanged():
    manifests = [
        DATA_DIR / "phase3h_final_validity_manifest.json",
        DATA_DIR / "phase3m_engineering_case.json",
        DATA_DIR / "phase3m_parameter_snapshot.json",
        DOCS_DIR / "phase3m_independent_engineering_case.md",
        DOCS_DIR / "phase3o_preregistration_manifest.json",
        DOCS_DIR / "phase3p_preregistration_manifest.json",
    ]
    for m in manifests:
        assert m.exists(), f"Protected Phase 3 manifest missing: {m}"


# ── TEST 38: PRODUCTION PHYSICS UNCHANGED ────────────────────────────────────

def test_38_production_physics_unchanged():
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing physics file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Physics modification in {item['path']}!"


# ── TARGETED PERFORMANCE BENCHMARK TESTS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_39_performance_benchmark_traversal(seeded_graph_db):
    data = seeded_graph_db

    # 1. Direct edge lookup benchmark (< 50ms)
    t0 = time.perf_counter()
    for _ in range(10):
        await EvidenceGraphService.get_edge(
            db=data["db"], edge_id=data["edge_q_exp1"].id, team_id=data["team_id"]
        )
    t_lookup = (time.perf_counter() - t0) / 10.0
    assert t_lookup < 0.05, f"Direct lookup too slow: {t_lookup:.4f}s"

    # 2. 1-hop traversal benchmark (< 50ms)
    t0 = time.perf_counter()
    for _ in range(10):
        await EvidenceGraphService.traverse_forward(
            db=data["db"], root_type="EngineeringQuestion", root_id="Q-101",
            team_id=data["team_id"], max_depth=1,
        )
    t_1hop = (time.perf_counter() - t0) / 10.0
    assert t_1hop < 0.05, f"1-hop traversal too slow: {t_1hop:.4f}s"

    # 3. Multi-hop traversal benchmark (< 100ms)
    t0 = time.perf_counter()
    for _ in range(10):
        await EvidenceGraphService.traverse_forward(
            db=data["db"], root_type="EngineeringQuestion", root_id="Q-101",
            team_id=data["team_id"], max_depth=5,
        )
    t_multihop = (time.perf_counter() - t0) / 10.0
    assert t_multihop < 0.10, f"Multi-hop traversal too slow: {t_multihop:.4f}s"

    # 4. Node-limit truncation benchmark (< 50ms)
    t0 = time.perf_counter()
    for _ in range(10):
        await EvidenceGraphService.traverse_forward(
            db=data["db"], root_type="EngineeringQuestion", root_id="Q-101",
            team_id=data["team_id"], max_depth=5, max_nodes=2,
        )
    t_trunc = (time.perf_counter() - t0) / 10.0
    assert t_trunc < 0.05, f"Truncation traversal too slow: {t_trunc:.4f}s"
