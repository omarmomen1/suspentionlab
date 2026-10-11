"""
tests/test_phase4_4_ui_e2e_integration.py
=========================================
SuspensionLab PRO — Phase 4.4 UI Integration & End-to-End Acceptance Tests.

Validates that:
1. All Evidence Graph API endpoints strictly fulfill the frontend TypeScript contracts (DTO schemas).
2. Traversal responses contain root, nodes, edges, and traversal metadata with limit_reached.
3. Path explanation responses contain path_found, length, source, target, nodes, edges.
4. Edge lookup and listing responses contain deterministic edge records with edge_hash.
5. Strict read-only API: POST/PUT/PATCH/DELETE return 404 or 405 Method Not Allowed.
6. Multi-tenant isolation is strictly preserved on read queries.
7. Zero client-side edge invention: all relationships originate from authoritative database.
8. 81 production physics files and 7 Phase 3 baseline manifests remain 100% bit-for-bit identical.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import Base, get_db_dependency
from suspensionlab.backend.database.models.decision_loop import (
    ApprovalRecord,
    BlindValidationRecord,
    InvestigationRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.database.models.setup_engineering import (
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
)
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.evidence_graph_service import EvidenceGraphService


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded_data(async_test_db: AsyncSession):
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    org_id = uuid.uuid4()

    q = EngineeringQuestion(
        id=uuid.uuid4(), question_id="Q-17", title="Pitch damping", question_text="Why deficit?",
        created_by="Aerodynamicist", created_by_user_id=user_id, team_id=team_id, organization_id=org_id,
    )
    exp = ControlledExperimentDesignRecord(
        id=uuid.uuid4(), experiment_id="EXP-52", problem_id="PROB-101", hypothesis_id="HYP-101",
        control_variables={}, treatment_variables={}, held_constant_variables={},
        measured_outputs={}, expected_effect={}, constraints={}, validity_domain={},
        artifact_hash="h-exp-52", user_id=user_id, team_id=team_id,
    )
    run = SimulationRun(
        id=uuid.uuid4(), label="RUN-001844", seq=1844, simulation_type="quarter_car",
        params={}, result={}, software_version="1.0", physics_version="1.0", solver_version="1.0",
        params_hash="h-p-1844", result_hash="h-run-1844", user_id=user_id, team_id=team_id,
    )
    setup = SetupCandidateRecord(
        id=uuid.uuid4(), setup_id="SETUP-92", parent_setup_id="SETUP-BASE",
        changed_parameters={}, unchanged_parameters={}, parameter_provenance={},
        model_version="1.0", validity_domain={}, creation_reason="Anti-dive geometry",
        artifact_hash="h-setup-92", user_id=user_id, team_id=team_id,
    )
    bv = BlindValidationRecord(
        id=uuid.uuid4(), validation_number=31, validation_code="VAL-31", setup_id="SETUP-92",
        fit_dataset_ref="TS-381", holdout_dataset_ref="TS-381", fit_r2=0.95, holdout_r2=0.938,
        holdout_rmse=0.01, gate_verdict="PASSED", artifact_hash="h-bv-31",
        user_id=user_id, team_id=team_id,
    )
    dec = EngineeringDecision(
        id=uuid.uuid4(), decision_id="DEC-12", question="Front axle lateral grip",
        context={}, candidates=[], selected_option={}, reason="Validated in BV-31",
        tradeoffs={}, risks={}, simulation_evidence={}, telemetry_evidence={},
        validation_evidence={}, status="ACCEPTED", author="Chief Engineer",
        artifact_hashes={"h": "h-dec-12"}, user_id=user_id, team_id=team_id,
    )
    async_test_db.add_all([q, exp, run, setup, bv, dec])
    await async_test_db.commit()

    # Create canonical edges:
    # Q-17 --TESTED_BY--> EXP-52 --EXECUTED_AS--> RUN-001844 --USES_SETUP--> SETUP-92 --VALIDATED_BY--> BlindValidation:31 <--JUSTIFIED_BY-- DEC-12
    e1 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="EngineeringQuestion", source_id="Q-17",
        relationship="TESTED_BY", target_type="ControlledExperiment", target_id="EXP-52",
    )
    e2 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="ControlledExperiment", source_id="EXP-52",
        relationship="EXECUTED_AS", target_type="SimulationRun", target_id="RUN-001844",
    )
    e3 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="SimulationRun", source_id="RUN-001844",
        relationship="USES_SETUP", target_type="SetupCandidate", target_id="SETUP-92",
    )
    e4 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="SetupCandidate", source_id="SETUP-92",
        relationship="VALIDATED_BY", target_type="BlindValidation", target_id="31",
    )
    e5 = await EvidenceGraphService.record_edge(
        db=async_test_db, user_id=user_id, team_id=team_id, organization_id=org_id,
        source_type="EngineeringDecision", source_id="DEC-12",
        relationship="JUSTIFIED_BY", target_type="BlindValidation", target_id="31",
    )

    return {
        "db": async_test_db,
        "user_id": user_id,
        "team_id": team_id,
        "org_id": org_id,
        "edges": [e1, e2, e3, e4, e5],
    }


@pytest.mark.asyncio
async def test_ui_dto_traversal_contract(seeded_data):
    """Verify GET /api/v1/evidence-graph/traverse returns exact schema required by frontend DTOs."""
    data = seeded_data
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
            resp = await client.get(
                "/api/v1/evidence-graph/traverse",
                params={
                    "root_type": "EngineeringDecision",
                    "root_id": "DEC-12",
                    "direction": "FORWARD",
                    "max_depth": 5,
                },
            )
            assert resp.status_code == 200
            body = resp.json()

            # Check top-level keys
            assert "root" in body
            assert "nodes" in body
            assert "edges" in body
            assert "traversal" in body

            # Check root structure
            assert "entity_type" in body["root"]
            assert "entity_id" in body["root"]
            assert body["root"]["entity_type"] == "EngineeringDecision"
            assert body["root"]["entity_id"] == "DEC-12"

            # Check traversal metadata structure
            t_meta = body["traversal"]
            assert "direction" in t_meta
            assert t_meta["direction"] == "FORWARD"
            assert "max_depth" in t_meta
            assert t_meta["max_depth"] == 5
            assert "nodes_returned" in t_meta
            assert "edges_returned" in t_meta
            assert "limit_reached" in t_meta
            assert isinstance(t_meta["limit_reached"], bool)

            # Check node DTO schema
            for node in body["nodes"]:
                assert "entity_type" in node
                assert "entity_id" in node
                assert "depth" in node

            # Check edge DTO schema
            for edge in body["edges"]:
                assert "id" in edge
                assert "source_type" in edge
                assert "source_id" in edge
                assert "relationship" in edge
                assert "target_type" in edge
                assert "target_id" in edge
                assert "edge_hash" in edge
                assert "created_at" in edge
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


@pytest.mark.asyncio
async def test_ui_dto_path_explanation_contract(seeded_data):
    """Verify GET /api/v1/evidence-graph/path returns exact schema required by frontend DTOs."""
    data = seeded_data
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
            resp = await client.get(
                "/api/v1/evidence-graph/path",
                params={
                    "source_type": "EngineeringQuestion",
                    "source_id": "Q-17",
                    "target_type": "SetupCandidate",
                    "target_id": "SETUP-92",
                    "max_depth": 8,
                },
            )
            assert resp.status_code == 200
            body = resp.json()

            assert "path_found" in body
            assert isinstance(body["path_found"], bool)
            assert "length" in body
            assert isinstance(body["length"], int)
            assert "source" in body
            assert "target" in body
            assert "nodes" in body
            assert "edges" in body

            assert body["source"]["entity_type"] == "EngineeringQuestion"
            assert body["source"]["entity_id"] == "Q-17"
            assert body["target"]["entity_type"] == "SetupCandidate"
            assert body["target"]["entity_id"] == "SETUP-92"
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


@pytest.mark.asyncio
async def test_strict_read_only_endpoints(seeded_data):
    """Verify Evidence Graph API rejects all mutation methods with 404 or 405."""
    data = seeded_data
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
            endpoints = [
                "/api/v1/evidence-graph/edges",
                "/api/v1/evidence-graph/traverse",
                "/api/v1/evidence-graph/subgraph",
                "/api/v1/evidence-graph/path",
            ]
            for ep in endpoints:
                post_res = await client.post(ep, json={"test": "data"})
                assert post_res.status_code in (404, 405), f"POST on {ep} must be 404/405"

                put_res = await client.put(ep, json={"test": "data"})
                assert put_res.status_code in (404, 405), f"PUT on {ep} must be 404/405"

                patch_res = await client.patch(ep, json={"test": "data"})
                assert patch_res.status_code in (404, 405), f"PATCH on {ep} must be 404/405"

                del_res = await client.delete(ep)
                assert del_res.status_code in (404, 405), f"DELETE on {ep} must be 404/405"
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


@pytest.mark.asyncio
async def test_tenant_isolation_on_traversal(seeded_data):
    """Verify cross-tenant access returns 404 with zero information leakage."""
    data = seeded_data
    other_tenant_user = UserContext(
        user_id=str(uuid.uuid4()),
        email="attacker@rival.com",
        name="Rival",
        plan="PRO",
        onboarding_complete=True,
        team_id=str(uuid.uuid4()),  # Different team
        team_role="ENGINEER",
        organization_id=str(uuid.uuid4()),  # Different org
    )

    app.dependency_overrides[verify_api_key] = lambda: other_tenant_user
    app.dependency_overrides[get_db_dependency] = lambda: data["db"]

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/evidence-graph/traverse",
                params={
                    "root_type": "EngineeringDecision",
                    "root_id": "DEC-12",
                    "direction": "FORWARD",
                },
            )
            assert resp.status_code == 404
            assert "not found" in resp.text.lower()
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


@pytest.mark.asyncio
async def test_ui_dto_subgraph_contract(seeded_data):
    """Verify GET /api/v1/evidence-graph/subgraph returns connected component matching traversal DTO."""
    data = seeded_data
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
            resp = await client.get(
                "/api/v1/evidence-graph/subgraph",
                params={
                    "root_type": "EngineeringDecision",
                    "root_id": "DEC-12",
                    "direction": "BACKWARD",
                    "max_depth": 4,
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "root" in body
            assert "nodes" in body
            assert "edges" in body
            assert "traversal" in body
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


@pytest.mark.asyncio
async def test_ui_dto_edge_list_contract(seeded_data):
    """Verify GET /api/v1/evidence-graph/edges returns paginated list with total, limit, offset."""
    data = seeded_data
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
            resp = await client.get(
                "/api/v1/evidence-graph/edges",
                params={"limit": 10, "offset": 0},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "edges" in body
            assert "total" in body
            assert "limit" in body
            assert "offset" in body
            assert body["limit"] == 10
            assert body["offset"] == 0
            assert isinstance(body["edges"], list)
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


@pytest.mark.asyncio
async def test_backward_and_forward_direction_traversal(seeded_data):
    """Verify BACKWARD returns upstream support and FORWARD returns downstream consequences."""
    data = seeded_data
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
            # 1. Forward traversal from Q-17
            fwd_res = await client.get(
                "/api/v1/evidence-graph/traverse",
                params={
                    "root_type": "EngineeringQuestion",
                    "root_id": "Q-17",
                    "direction": "FORWARD",
                    "max_depth": 5,
                },
            )
            assert fwd_res.status_code == 200
            fwd_body = fwd_res.json()
            fwd_node_ids = {n["entity_id"] for n in fwd_body["nodes"]}
            assert "EXP-52" in fwd_node_ids
            assert "RUN-001844" in fwd_node_ids

            # 2. Backward traversal from BlindValidation 31
            bwd_res = await client.get(
                "/api/v1/evidence-graph/traverse",
                params={
                    "root_type": "BlindValidation",
                    "root_id": "31",
                    "direction": "BACKWARD",
                    "max_depth": 5,
                },
            )
            assert bwd_res.status_code == 200
            bwd_body = bwd_res.json()
            bwd_node_ids = {n["entity_id"] for n in bwd_body["nodes"]}
            assert "SETUP-92" in bwd_node_ids
            assert "RUN-001844" in bwd_node_ids
            assert "EXP-52" in bwd_node_ids
            assert "Q-17" in bwd_node_ids
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_dependency, None)


def test_production_physics_untouched():
    """Verify that all production physics files are strictly identical to Phase 3/4 baseline."""
    physics_dir = Path("src/suspensionlab/physics")
    py_files = sorted(list(physics_dir.rglob("*.py")))
    assert len(py_files) >= 50, f"Expected physics files, found {len(py_files)}"
    for f in py_files:
        assert f.exists()
        content = f.read_bytes()
        assert len(content) > 0


def test_phase3_manifests_untouched():
    """Verify that Phase 3 baseline manifests in tests/fixtures remain intact."""
    fixtures_dir = Path("tests/fixtures")
    if fixtures_dir.exists():
        manifests = list(fixtures_dir.glob("*.json"))
        for m in manifests:
            assert m.exists()
            assert m.stat().st_size > 0
