"""
tests/test_phase7_2_solver_exchange_operational.py
==================================================
SuspensionLab PRO — Phase 7.2 Operational Solver Interoperability Test Suite.

Verifies:
1. Adapter Capabilities and Format Restrictions (Work Package A).
2. Persistent Exchange Lifecycle & Finite State Machine (Work Package B).
3. Hardened Artifact Ingestion & Security Defenses (Work Package C).
4. Production API Registration, Authentication & Multi-Tenancy (Work Package D).
5. Engineering Semantics, Round Trips & Lossy Mapping Audits (Work Package E).
6. Adversarial Attack Verification, Invariants & Regression Proof (Work Package G).
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import pathlib
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.solver_exchange import (
    ArtifactDirection,
    ExchangeOperationState,
    ExchangeOperationType,
    ImmutableOperationError,
    InvalidStateTransitionError,
    SolverExchangeArtifact,
    SolverExchangeOperation,
)
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.jwt_utils import create_access_token
from suspensionlab.backend.services.solver_exchange_service import SolverExchangeService
from suspensionlab.interop.adapter import SupportLevel
from suspensionlab.interop.manifest import (
    CanonicalExchangeManifest,
    ParameterValue,
    ResultProvenanceOrigin,
    validate_canonical_manifest,
)
from suspensionlab.interop.registry import get_adapter_registry
from suspensionlab.interop.security import (
    ContentMismatchSecurityError,
    ExecutableContentSecurityError,
    HashMismatchSecurityError,
    PathTraversalSecurityError,
    ResourceExhaustionSecurityError,
    TenantIsolationError,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
async def seeded_users():
    """Seeds two isolated users for cross-tenant verification."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    team_a_id = uuid.uuid4()
    team_b_id = uuid.uuid4()

    async with SessionLocal() as db:
        user_a = User(
            id=user_a_id,
            email=f"engineer_a_{user_a_id.hex[:6]}@oem.com",
            name="Engineer A",
            plan="PRO",
            password_hash="test-hash",
        )
        user_b = User(
            id=user_b_id,
            email=f"engineer_b_{user_b_id.hex[:6]}@competitor.com",
            name="Engineer B",
            plan="PRO",
            password_hash="test-hash",
        )
        db.add_all([user_a, user_b])
        await db.commit()

    token_a = create_access_token({
        "sub": str(user_a_id),
        "user_id": str(user_a_id),
        "email": user_a.email,
        "team_id": str(team_a_id),
        "plan": "PRO",
    })
    token_b = create_access_token({
        "sub": str(user_b_id),
        "user_id": str(user_b_id),
        "email": user_b.email,
        "team_id": str(team_b_id),
        "plan": "PRO",
    })

    return {
        "user_a_id": user_a_id,
        "team_a_id": team_a_id,
        "token_a": token_a,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "user_b_id": user_b_id,
        "team_b_id": team_b_id,
        "token_b": token_b,
        "headers_b": {"Authorization": f"Bearer {token_b}"},
    }


@pytest.fixture
def sample_canonical_manifest_dict():
    """Standard valid canonical exchange manifest for testing."""
    return {
        "schema_version": "1.0.0",
        "source_application": "SuspensionLab PRO",
        "source_solver": "SuspensionLab",
        "engineering_model_id": "MDL-TEST-001",
        "parameters": {
            "m_s": {"name": "m_s", "value": 300.0, "unit": "kg", "dimension": "MASS"},
            "m_u": {"name": "m_u", "value": 35.0, "unit": "kg", "dimension": "MASS"},
            "k_s": {"name": "k_s", "value": 25000.0, "unit": "N/m", "dimension": "TRANSLATIONAL_STIFFNESS"},
            "c": {"name": "c", "value": 2050.0, "unit": "Ns/m", "dimension": "TRANSLATIONAL_DAMPING"},
            "k_t": {"name": "k_t", "value": 200000.0, "unit": "N/m", "dimension": "TRANSLATIONAL_STIFFNESS"},
            "MR": {"name": "MR", "value": 0.85, "unit": "-", "dimension": "DIMENSIONLESS"},
        },
        "coordinate_frame": {
            "name": "ISO_8855",
            "x_axis": "FORWARD",
            "y_axis": "LEFT",
            "z_axis": "UP",
            "handedness": "RIGHT_HANDED",
        },
        "operating_conditions": {"temperature_c": 22.5},
        "warnings": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# WORK PACKAGE A: CAPABILITY MATRIX & TRUTHFULNESS
# ══════════════════════════════════════════════════════════════════════════════

def test_wpa_01_canonical_json_capability():
    reg = get_adapter_registry()
    ad = reg.get_adapter("adapter-canonical-json-v1")
    assert ad is not None
    caps = ad.get_capabilities()
    assert caps.solver_name == "CANONICAL_JSON"
    assert caps.import_capability == SupportLevel.SUPPORTED
    assert caps.export_capability == SupportLevel.SUPPORTED
    assert ".json" in caps.supported_import_formats
    assert ".json" in caps.supported_export_formats


def test_wpa_02_adams_capability_and_export_only_scripts():
    reg = get_adapter_registry()
    ad = reg.get_adapter("adapter-msc-adams-v1")
    assert ad is not None
    caps = ad.get_capabilities()
    assert caps.solver_name == "MSC_ADAMS"
    assert caps.import_capability == SupportLevel.PARTIALLY_SUPPORTED
    assert caps.export_capability == SupportLevel.SUPPORTED
    assert caps.supported_import_formats == [".adm"]
    assert sorted(caps.supported_export_formats) == sorted([".adm", ".cmd", ".py"])
    # Runtime execution dependency must report is_available=False unless host Adams installed
    dep = caps.required_dependencies[0]
    assert dep.name == "msc-adams-solver"


def test_wpa_03_matlab_simulink_export_only_capability():
    reg = get_adapter_registry()
    ad = reg.get_adapter("adapter-matlab-simulink-v1")
    assert ad is not None
    caps = ad.get_capabilities()
    assert caps.solver_name == "MATLAB_SIMULINK"
    assert caps.import_capability == SupportLevel.UNSUPPORTED
    assert caps.export_capability == SupportLevel.SUPPORTED
    assert caps.supported_import_formats == []
    assert ".m" in caps.supported_export_formats


def test_wpa_04_fmi_metadata_only_boundary():
    reg = get_adapter_registry()
    ad = reg.get_adapter("adapter-fmi-cosim-v1")
    assert ad is not None
    caps = ad.get_capabilities()
    assert caps.solver_name == "FMI_COSIMULATION"
    assert caps.import_capability == SupportLevel.PARTIALLY_SUPPORTED
    assert caps.export_capability == SupportLevel.SUPPORTED
    assert caps.supported_import_formats == [".xml"]
    assert caps.supported_export_formats == [".xml"]
    dep = caps.required_dependencies[0]
    assert dep.is_available is False


def test_wpa_05_pac2002_tir_bidirectional():
    reg = get_adapter_registry()
    ad = reg.get_adapter("adapter-pac2002-tir-v1")
    assert ad is not None
    caps = ad.get_capabilities()
    assert caps.solver_name == "PAC2002_MAGIC_FORMULA"
    assert caps.import_capability == SupportLevel.SUPPORTED
    assert caps.export_capability == SupportLevel.SUPPORTED
    assert ".tir" in caps.supported_import_formats
    assert ".tir" in caps.supported_export_formats


# ══════════════════════════════════════════════════════════════════════════════
# WORK PACKAGE B: PERSISTENT EXCHANGE LIFECYCLE & STATE MACHINE
# ══════════════════════════════════════════════════════════════════════════════

def test_wpb_01_state_machine_valid_transitions():
    op = SolverExchangeOperation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        operation_type=ExchangeOperationType.IMPORT.value,
        adapter_id="adapter-canonical-json-v1",
        adapter_version="1.0.0",
        solver_name="CANONICAL_JSON",
        state=ExchangeOperationState.PENDING.value,
    )
    assert op.state == ExchangeOperationState.PENDING.value
    op.transition_to(ExchangeOperationState.VALIDATING)
    assert op.state == ExchangeOperationState.VALIDATING.value
    op.transition_to(ExchangeOperationState.TRANSFORMING)
    assert op.state == ExchangeOperationState.TRANSFORMING.value
    op.transition_to(ExchangeOperationState.COMPLETED)
    assert op.state == ExchangeOperationState.COMPLETED.value
    assert op.completed_at is not None


def test_wpb_02_terminal_state_immutability():
    op = SolverExchangeOperation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        operation_type=ExchangeOperationType.EXPORT.value,
        adapter_id="adapter-canonical-json-v1",
        adapter_version="1.0.0",
        solver_name="CANONICAL_JSON",
        state=ExchangeOperationState.COMPLETED.value,
    )
    with pytest.raises(ImmutableOperationError):
        op.transition_to(ExchangeOperationState.VALIDATING)
    with pytest.raises(ImmutableOperationError):
        op.transition_to(ExchangeOperationState.FAILED)
    with pytest.raises(ImmutableOperationError):
        op.assert_mutable()


def test_wpb_03_illegal_state_transition():
    op = SolverExchangeOperation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        operation_type=ExchangeOperationType.IMPORT.value,
        adapter_id="adapter-canonical-json-v1",
        adapter_version="1.0.0",
        solver_name="CANONICAL_JSON",
        state=ExchangeOperationState.PENDING.value,
    )
    # Skipping VALIDATING straight to TRANSFORMING or COMPLETED is illegal
    with pytest.raises(InvalidStateTransitionError):
        op.transition_to(ExchangeOperationState.TRANSFORMING)
    with pytest.raises(InvalidStateTransitionError):
        op.transition_to(ExchangeOperationState.COMPLETED)


# ══════════════════════════════════════════════════════════════════════════════
# WORK PACKAGE C: SECURE ARTIFACT INGESTION & DEFENSES
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wpc_01_reject_executable_script_ingestion(seeded_users):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Attempt .py script ingestion
        r_py = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-msc-adams-v1",
                "filename": "malicious_script.py",
                "content": "import os; os.system('calc.exe')",
            },
        )
        assert r_py.status_code == 400
        assert "executable" in r_py.text.lower() or "prohibited" in r_py.text.lower()

        # 2. Attempt .cmd command file ingestion
        r_cmd = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-msc-adams-v1",
                "filename": "run_adams.cmd",
                "content": "model create model_name=bad",
            },
        )
        assert r_cmd.status_code == 400


@pytest.mark.asyncio
async def test_wpc_02_path_traversal_rejection(seeded_users):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-canonical-json-v1",
                "filename": "../../etc/passwd.json",
                "content": json.dumps({"schema_version": "1.0.0"}),
            },
        )
        assert r.status_code == 400
        assert "traversal" in r.text.lower()


@pytest.mark.asyncio
async def test_wpc_03_content_extension_mismatch(seeded_users):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Claims to be .adm, but content is HTML without solver tokens
        r = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-msc-adams-v1",
                "filename": "test.adm",
                "content": "<html><body>Arbitrary HTML document without any solver tokens</body></html>",
            },
        )
        assert r.status_code == 400
        assert "mismatch" in r.text.lower() or "directives" in r.text.lower()


@pytest.mark.asyncio
async def test_wpc_04_tampered_content_hash_rejection(seeded_users):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        content = json.dumps({"schema_version": "1.0.0"})
        r = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-canonical-json-v1",
                "filename": "manifest.json",
                "content": content,
                "expected_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            },
        )
        assert r.status_code == 400
        assert "hash mismatch" in r.text.lower()


# ══════════════════════════════════════════════════════════════════════════════
# WORK PACKAGE D: PRODUCTION API INTEGRATION & MULTI-TENANCY
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wpd_01_unauthenticated_requests_fail_closed():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/interop/adapters")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_wpd_02_cross_tenant_operation_access_denied(seeded_users, sample_canonical_manifest_dict):
    headers_a = seeded_users["headers_a"]
    headers_b = seeded_users["headers_b"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User A creates export operation
        r_create = await client.post(
            "/api/v1/interop/export",
            headers=headers_a,
            json={
                "adapter_id": "adapter-canonical-json-v1",
                "target_format": ".json",
                "manifest": sample_canonical_manifest_dict,
            },
        )
        assert r_create.status_code == 200
        op_id = r_create.json()["id"]

        # User A can inspect operation
        r_get_a = await client.get(f"/api/v1/interop/operations/{op_id}", headers=headers_a)
        assert r_get_a.status_code == 200

        # User B attempts to access User A's operation (IDOR attack)
        r_get_b = await client.get(f"/api/v1/interop/operations/{op_id}", headers=headers_b)
        assert r_get_b.status_code in (403, 404)

        # User B attempts to download User A's artifact
        r_dl_b = await client.get(f"/api/v1/interop/operations/{op_id}/artifact", headers=headers_b)
        assert r_dl_b.status_code in (403, 404)


@pytest.mark.asyncio
async def test_wpd_03_idempotent_operation_execution(seeded_users, sample_canonical_manifest_dict):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        idemp_key = f"idemp-{uuid.uuid4().hex}"
        payload = {
            "adapter_id": "adapter-canonical-json-v1",
            "target_format": ".json",
            "manifest": sample_canonical_manifest_dict,
            "idempotency_key": idemp_key,
        }

        # First request
        r1 = await client.post("/api/v1/interop/export", headers=headers, json=payload)
        assert r1.status_code == 200
        op1 = r1.json()

        # Second request with identical idempotency key
        r2 = await client.post("/api/v1/interop/export", headers=headers, json=payload)
        assert r2.status_code == 200
        op2 = r2.json()

        assert op1["id"] == op2["id"]


# ══════════════════════════════════════════════════════════════════════════════
# WORK PACKAGE E: ENGINEERING SEMANTICS & REAL ARTIFACT ROUND TRIPS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wpe_01_canonical_json_round_trip(seeded_users, sample_canonical_manifest_dict):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Export
        r_exp = await client.post(
            "/api/v1/interop/export",
            headers=headers,
            json={
                "adapter_id": "adapter-canonical-json-v1",
                "target_format": ".json",
                "manifest": sample_canonical_manifest_dict,
            },
        )
        assert r_exp.status_code == 200
        exp_data = r_exp.json()
        assert exp_data["state"] == "COMPLETED"
        assert exp_data["is_executed"] is False
        assert exp_data["is_physically_validated"] is False

        # 2. Download artifact
        r_dl = await client.get(f"/api/v1/interop/operations/{exp_data['id']}/artifact", headers=headers)
        assert r_dl.status_code == 200
        exported_bytes = r_dl.content

        # 3. Import back
        r_imp = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-canonical-json-v1",
                "filename": "roundtrip.json",
                "content": exported_bytes.decode("utf-8"),
            },
        )
        assert r_imp.status_code == 200
        imp_data = r_imp.json()
        assert imp_data["state"] == "COMPLETED"
        assert imp_data["is_executed"] is False
        assert imp_data["is_physically_validated"] is False
        assert set(imp_data["units_summary"].keys()) == set(exp_data["units_summary"].keys())
        assert imp_data["units_summary"] == exp_data["units_summary"]


@pytest.mark.asyncio
async def test_wpe_02_adams_adm_export_and_inert_import(seeded_users, sample_canonical_manifest_dict):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Export .adm
        r_exp = await client.post(
            "/api/v1/interop/export",
            headers=headers,
            json={
                "adapter_id": "adapter-msc-adams-v1",
                "target_format": ".adm",
                "manifest": sample_canonical_manifest_dict,
            },
        )
        assert r_exp.status_code == 200
        op_exp = r_exp.json()
        assert op_exp["state"] == "COMPLETED"

        # 2. Download .adm artifact
        r_dl = await client.get(f"/api/v1/interop/operations/{op_exp['id']}/artifact", headers=headers)
        assert r_dl.status_code == 200
        adm_text = r_dl.text
        assert "PART/1" in adm_text or "PART/101" in adm_text or "PART/" in adm_text

        # 3. Inert import of .adm dataset
        r_imp = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-msc-adams-v1",
                "filename": "qcar.adm",
                "content": adm_text,
            },
        )
        assert r_imp.status_code == 200
        op_imp = r_imp.json()
        assert op_imp["state"] == "COMPLETED"
        assert op_imp["is_executed"] is False
        assert op_imp["is_physically_validated"] is False


@pytest.mark.asyncio
async def test_wpe_03_matlab_export_generates_script_and_rejects_import(seeded_users, sample_canonical_manifest_dict):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Export .m
        r_exp = await client.post(
            "/api/v1/interop/export",
            headers=headers,
            json={
                "adapter_id": "adapter-matlab-simulink-v1",
                "target_format": ".m",
                "manifest": sample_canonical_manifest_dict,
            },
        )
        assert r_exp.status_code == 200
        op_exp = r_exp.json()
        assert op_exp["state"] == "COMPLETED"

        # Download .m
        r_dl = await client.get(f"/api/v1/interop/operations/{op_exp['id']}/artifact", headers=headers)
        assert r_dl.status_code == 200
        m_code = r_dl.text
        assert "A = [" in m_code
        assert "B = [" in m_code
        assert "sys = ss(A, B, C, D);" in m_code

        # Attempting import of .m MUST be rejected immediately
        r_imp = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-matlab-simulink-v1",
                "filename": "model.m",
                "content": m_code,
            },
        )
        assert r_imp.status_code == 400
        assert "unsupported" in r_imp.text.lower() or "prohibited" in r_imp.text.lower()


@pytest.mark.asyncio
async def test_wpe_04_fmi_model_description_round_trip(seeded_users, sample_canonical_manifest_dict):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Export FMI modelDescription.xml
        r_exp = await client.post(
            "/api/v1/interop/export",
            headers=headers,
            json={
                "adapter_id": "adapter-fmi-cosim-v1",
                "target_format": ".xml",
                "manifest": sample_canonical_manifest_dict,
            },
        )
        assert r_exp.status_code == 200
        op_exp = r_exp.json()

        # Download XML
        r_dl = await client.get(f"/api/v1/interop/operations/{op_exp['id']}/artifact", headers=headers)
        assert r_dl.status_code == 200
        xml_text = r_dl.text
        assert "fmiModelDescription" in xml_text

        # Ingest FMI XML
        r_imp = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-fmi-cosim-v1",
                "filename": "modelDescription.xml",
                "content": xml_text,
            },
        )
        assert r_imp.status_code == 200
        op_imp = r_imp.json()
        assert op_imp["state"] == "COMPLETED"
        assert op_imp["is_executed"] is False
        assert op_imp["is_physically_validated"] is False


@pytest.mark.asyncio
async def test_wpe_05_pac2002_tir_property_exchange(seeded_users):
    headers = seeded_users["headers_a"]
    transport = ASGITransport(app=app)
    tir_sample = """[MDI_HEADER]
FILE_TYPE = 'tir'
FILE_VERSION = 3.0
FILE_FORMAT = 'ASCII'
! Pacejka MF5.2
[DIMENSION]
UNLOADED_RADIUS = 0.315
WIDTH = 0.205
[VERTICAL]
FNOMIN = 4000.0
NOMPRES = 200000.0
[LATERAL_COEFFICIENTS]
PCY1 = 1.3
PDY1 = 1.0
PEY1 = -0.8
PKY1 = -15.0
[LONGITUDINAL_COEFFICIENTS]
PKX1 = 21.0
"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Import .tir
        r_imp = await client.post(
            "/api/v1/interop/import",
            headers=headers,
            json={
                "adapter_id": "adapter-pac2002-tir-v1",
                "filename": "tire.tir",
                "content": tir_sample,
            },
        )
        assert r_imp.status_code == 200
        op_imp = r_imp.json()
        assert op_imp["state"] == "COMPLETED"

        # Get diagnostics
        r_diag = await client.get(f"/api/v1/interop/operations/{op_imp['id']}/diagnostics", headers=headers)
        assert r_diag.status_code == 200
        diag = r_diag.json()
        assert "Fz0" in diag["mapping_diagnostics"]["parameter_names"]
        assert "pCy1" in diag["mapping_diagnostics"]["parameter_names"]
        assert "pKx1" in diag["mapping_diagnostics"]["parameter_names"]


# ══════════════════════════════════════════════════════════════════════════════
# WORK PACKAGE G: PROTECTED SYSTEM BOUNDARIES & INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════

def test_wpg_01_all_81_protected_physics_files_remain_unchanged():
    """All 81 production physics source files match authoritative pre-Phase 4 baseline SHA-256."""
    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    assert hash_file.exists(), "pre_phase4_3_hashes.json missing!"

    with open(hash_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    physics_hashes = data.get("physics", {})
    assert len(physics_hashes) == 81, f"Expected 81 physics files, found {len(physics_hashes)}"

    for rel_path, expected_hash in physics_hashes.items():
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Protected physics file {rel_path} does not exist!"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Protected physics file {rel_path} was modified!"


def test_wpg_02_phase3_manifests_remain_unchanged():
    """Phase 3 freeze manifests remain bit-for-bit unchanged."""
    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    assert hash_file.exists(), "pre_phase4_3_hashes.json missing!"

    with open(hash_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    manifest_hashes = data.get("manifests", {})
    assert len(manifest_hashes) == 7, f"Expected 7 manifest files, found {len(manifest_hashes)}"

    for rel_path, expected_hash in manifest_hashes.items():
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Phase 3 manifest file {rel_path} does not exist!"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Phase 3 manifest file {rel_path} was modified!"


def test_wpg_03_alembic_single_head():
    """Alembic maintains exactly one unified head."""
    import alembic.config
    import alembic.script

    cfg = alembic.config.Config(str(PROJECT_ROOT / "alembic.ini"))
    script_dir = alembic.script.ScriptDirectory.from_config(cfg)
    heads = script_dir.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 Alembic head, got {heads}"
    assert heads[0] in ("s9t0u1v2w3x4", "r8s9t0u1v2w3", "t0u1v2w3x4y5")
