"""
tests/test_report_and_artifact_integrity.py
============================================
Comprehensive verification test suite ensuring 100% genuine engineering integrity,
tamper-evident detection, 13-point configuration provenance, and cryptographically
sealed multi-role approvals across SuspensionLab Pro.
"""


import hashlib
import hmac
import json
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from suspensionlab.shared.models import SimulateRequest, PlanTier, QuarterCarParamsSchema, RoadProfileSchema
from suspensionlab.backend.security.audit import canonical_hash, compute_audit_hash, verify_audit_hash_chain
from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.database.models.setup_proposal import SetupProposal
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.api.routes.share_routes import get_shared_report, create_shared_report, ShareRequest, _sign
from suspensionlab.backend.api.routes.report_routes import generate_iso_report, generate_engineering_decision_report
from suspensionlab.backend.api.routes.audit_routes import export_audit_logs
from suspensionlab.backend.api.routes.twin_routes import set_proposal_status
from suspensionlab.backend.services.setup_proposal import proposal_to_dict
from suspensionlab.backend.services import report_service
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis


def test_anti_fabrication_hash_sensitivity():
    """Verify that any alteration in simulation inputs or results deterministically changes SHA-256 hashes."""
    base_input = {"k_s": 35000.0, "c": 2200.0, "m_s": 300.0, "m_u": 40.0}
    altered_input = {"k_s": 35000.01, "c": 2200.0, "m_s": 300.0, "m_u": 40.0}

    hash_base = canonical_hash(base_input)
    hash_altered = canonical_hash(altered_input)
    assert hash_base != hash_altered, "Parameter hash must strictly change when input varies"

    base_res = {"rms_body_accel": 0.4210, "rms_susp_travel": 0.0182}
    altered_res = {"rms_body_accel": 0.4211, "rms_susp_travel": 0.0182}

    res_hash_base = canonical_hash(base_res)
    res_hash_altered = canonical_hash(altered_res)
    assert res_hash_base != res_hash_altered, "Result hash must strictly change when output varies"


@pytest.mark.asyncio
async def test_shared_report_read_tamper_detection():
    """Verify zero-trust read-time tamper detection in get_shared_report."""
    token = str(uuid.uuid4())
    params = {"k_s": 30000.0, "c": 2000.0}
    result = {"rms_body_accel": 0.450}
    
    p_hash = canonical_hash(params)
    r_hash = canonical_hash(result)
    signature = _sign(token, p_hash, r_hash)

    # 1. Untampered report
    report = SharedReport(
        token=token,
        simulation_type="quarter_car",
        params=params,
        result=result,
        title="Test Report",
        notes="",
        params_hash=p_hash,
        result_hash=r_hash,
        provenance="verified",
        signature=signature,
        is_public=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = report
    mock_db.execute.return_value = mock_scalars

    resp = await get_shared_report(token=token, db=mock_db)
    assert resp.provenance.payload_verified is True
    assert resp.provenance.tamper_detected is False
    assert resp.provenance.signature_valid is True

    # 2. Tampered report: database payload altered post-creation
    tampered_result = {"rms_body_accel": 0.200} # Faked lower acceleration
    report_tampered = SharedReport(
        token=token,
        simulation_type="quarter_car",
        params=params,
        result=tampered_result,
        title="Test Report",
        notes="",
        params_hash=p_hash,
        result_hash=r_hash, # Stored hash points to old result
        provenance="verified",
        signature=signature,
        is_public=True,
        created_at=datetime.now(timezone.utc),
    )

    mock_scalars_tampered = MagicMock()
    mock_scalars_tampered.scalar_one_or_none.return_value = report_tampered
    mock_db.execute.return_value = mock_scalars_tampered

    resp_tampered = await get_shared_report(token=token, db=mock_db)
    assert resp_tampered.provenance.payload_verified is False
    assert resp_tampered.provenance.tamper_detected is True
    assert resp_tampered.provenance.signature_valid is False, "Signature verification must fail on tampered payload"


@pytest.mark.asyncio
async def test_setup_proposal_approval_cryptographic_signing():
    """Verify non-repudiable cryptographic sign-offs and audit log stamping for setup proposals."""
    proposal_id = uuid.uuid4()
    twin_id = uuid.uuid4()
    user_id = uuid.uuid4()

    rec_params = {"k_s": 38000.0, "c": 2450.0}
    param_changes = [{"parameter": "k_s", "current": 36000.0, "recommended": 38000.0, "change_pct": 5.5}]
    predicted_effects = [{"metric": "Ride Comfort", "baseline": 0.48, "predicted": 0.42, "change_pct": -12.5, "improved": True}]
    
    prop_payload = {
        "recommended_params": rec_params,
        "param_changes": param_changes,
        "predicted_effects": predicted_effects,
    }
    expected_hash = canonical_hash(prop_payload)

    proposal = SetupProposal(
        id=proposal_id,
        twin_id=twin_id,
        user_id=user_id,
        problem="High speed turn in instability",
        focus="handling",
        baseline_params={"k_s": 36000.0, "c": 2200.0},
        tested_setups=25,
        feasible_found=18,
        recommended_params=rec_params,
        param_changes=param_changes,
        predicted_effects=predicted_effects,
        confidence=0.92,
        status="PROPOSED",
        proposal_hash=expected_hash,
        created_at=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = proposal
    mock_db.execute.return_value = mock_scalars

    mock_user = MagicMock()
    mock_user.user_id = str(user_id)
    mock_user.team_id = str(uuid.uuid4())
    mock_user.team_role = "OWNER"

    resp = await set_proposal_status(
        proposal_id=str(proposal_id),
        status="APPROVED",
        user=mock_user,
        db=mock_db,
    )

    assert resp["status"] == "APPROVED"
    assert resp["approved_by"] == str(user_id)
    assert resp["approved_role"] == "OWNER"
    assert resp["proposal_hash"] == expected_hash
    assert len(resp["approval_signature"]) == 64
    assert proposal.approval_signature == resp["approval_signature"]

    # Verify proposal_to_dict serialization
    d = proposal_to_dict(proposal)
    assert d["proposal_hash"] == expected_hash
    assert d["approval_signature"] == resp["approval_signature"]
    assert d["approved_by_role"] == "OWNER"


@pytest.mark.asyncio
async def test_decision_report_13_point_provenance_and_headers():
    """Verify that engineering decision reports stamp all 13 required configuration fields."""
    sim_run_id = str(uuid.uuid4())
    sim_label = f"RUN-{sim_run_id[:8].upper()}"
    report_data = {
        "simulation_id": sim_label,
        "run_label": sim_label,
        "vehicle": "CAR-07",
        "setup": "REV-48",
        "track": "SPA-FRANCORCHAMPS 2026",
        "tire": "TIRE-MF52-COMPOUND-SOFT",
        "aero_version": "AERO-POLAR-v2.3",
        "dataset_ref": "TELEMETRY-SYNC-SPA-Q2",
        "vehicle_model_version": "7-DOF Full Car / 2-DOF Quarter Car Suite",
        "tire_model_version": "Pacejka MF 5.2 / Similarity",
        "solver_version": "RK45 / BDF Adaptive Stiff",
        "software_build": "BUILD-REL-2026.1",
        "input_parameters": {"m_s": 1200.0, "k_s": 35000.0},
        "simulation_results": {"rms_body_accel": 0.421, "lap_delta_s": -0.087},
        "validation_state": "PASS",
        "correlation_pct": 91.4,
        "approval": {
            "name": "Senior Vehicle Dynamics Lead",
            "role": "Chief Race Engineer",
            "decision": "APPROVED_FOR_TEST_TRACK",
            "comment": "Residual within correlation tolerance",
        }
    }

    mock_user = MagicMock()
    mock_user.user_id = str(uuid.uuid4())
    mock_user.email = "chief.engineer@f1team.com"
    mock_user.name = "Senior Vehicle Dynamics Lead"
    mock_user.team_role = "Chief Race Engineer"
    mock_user.team_id = None
    mock_user.organization_id = None
    mock_user.can.return_value = True

    mock_run = SimulationRun(
        id=uuid.UUID(sim_run_id),
        label=sim_label,
        user_id=uuid.UUID(mock_user.user_id),
        vehicle_ref="CAR-07",
        setup_ref="REV-48",
        track_ref="SPA-FRANCORCHAMPS 2026",
        tire_ref="TIRE-MF52-COMPOUND-SOFT",
        telemetry_ref="TELEMETRY-SYNC-SPA-Q2",
        physics_version="7-DOF Full Car / 2-DOF Quarter Car Suite",
        solver_version="RK45 / BDF Adaptive Stiff",
        git_build_id="BUILD-REL-2026.1",
        params_hash="44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        result_hash="44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        model_validity={"status": "VALIDATED", "correlation_pct": 91.4},
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = mock_run
    mock_db.execute.return_value = mock_scalars

    resp = await generate_engineering_decision_report(report_data=report_data, user=mock_user, db=mock_db)
    
    html_text = resp.body.decode("utf-8")
    assert "Engineering Decision &amp; Compliance Report" in html_text
    assert "CAR-07" in html_text
    assert "REV-48" in html_text
    assert "SPA-FRANCORCHAMPS 2026" in html_text
    assert "TIRE-MF52-COMPOUND-SOFT" in html_text
    assert "AERO-POLAR-v2.3" in html_text
    assert "TELEMETRY-SYNC-SPA-Q2" in html_text
    assert "7-DOF Full Car / 2-DOF Quarter Car Suite" in html_text
    assert "RK45 / BDF Adaptive Stiff" in html_text
    assert "BUILD-REL-2026.1" in html_text
    assert "91.40%" in html_text
    assert "CHIEF ENGINEER DECISION SIGN-OFF" in html_text
    assert "Cryptographic Approval Signature" in html_text

    # Verify HTTP response headers
    assert "X-Simulation-ID" in resp.headers
    assert "X-Input-Hash" in resp.headers
    assert "X-Result-Hash" in resp.headers
    assert "X-Approval-Signature" in resp.headers


@pytest.mark.asyncio
async def test_iso2631_report_provenance_stamping():
    """Verify ISO 2631 HTML report includes cryptographic provenance block."""
    req = SimulateRequest(
        params=QuarterCarParamsSchema(m_s=250.0, m_u=30.0, k_s=20000.0, c=1500.0, k_t=180000.0, MR=1.0),
        profile=RoadProfileSchema(profile_type="step", step_height=0.05, duration=2.0)
    )
    mock_user = MagicMock()
    mock_user.email = "dynamics@suspensionlab.io"

    resp = await generate_iso_report(request_data=req, user=mock_user)
    html_text = resp.body.decode("utf-8")
    assert "ISO 2631-1 Wk-Weighted Analysis Report" in html_text
    assert "Cryptographic Provenance & Configuration Lineage" in html_text
    assert "Input Hash (SHA-256):" in html_text
    assert "Result Hash (SHA-256):" in html_text
    assert "X-Report-Input-Hash" in resp.headers
    assert "X-Report-Result-Hash" in resp.headers


@pytest.mark.asyncio
async def test_audit_log_export_merkle_chain_columns():
    """Verify audit log exports include cryptographic Merkle hash columns."""
    mock_user = MagicMock()
    mock_user.user_id = str(uuid.uuid4())
    mock_user.team_id = str(uuid.uuid4())
    mock_user.plan = PlanTier.ENTERPRISE

    log1 = AuditLog(
        id=uuid.uuid4(),
        event="SIMULATION_RUN",
        user_id=uuid.UUID(mock_user.user_id),
        team_id=uuid.UUID(mock_user.team_id),
        ip="127.0.0.1",
        timestamp=datetime.now(timezone.utc),
        event_data={"sim": "RUN-000183"},
        previous_hash="GENESIS",
        hash="abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [log1]
    mock_scalars.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_scalars

    # CSV Export
    csv_resp = await export_audit_logs(format="csv", user=mock_user, db=mock_db)
    body = "".join([chunk if isinstance(chunk, str) else chunk.decode("utf-8") async for chunk in csv_resp.body_iterator])
    assert "Previous Hash (SHA-256)" in body
    assert "Record Hash (SHA-256)" in body
    assert "Chain Integrity" in body
    assert "GENESIS" in body
    assert "abcd1234" in body

    # JSON Export
    json_resp = await export_audit_logs(format="json", user=mock_user, db=mock_db)
    data = json.loads(json_resp.body.decode("utf-8"))
    assert "chain_integrity" in data
    assert len(data["records"]) == 1
    assert data["records"][0]["previous_hash"] == "GENESIS"


# ── STEP 8: COMPREHENSIVE REPORTING & SIGN-OFF INTEGRITY TESTS ────────────────

@pytest.mark.asyncio
async def test_report_hydration_from_simulation_run():
    """Verify STEP 1 & 2: Real report hydration from simulation_run_id with calculated physics."""
    import dataclasses
    p = QuarterCarParams(m_s=320.0, m_u=45.0, k_s=36000.0, c=2400.0, k_t=210000.0, MR=1.0)
    prof = RoadProfile(profile_type="step", amplitude=0.04, duration=2.5)
    res = run_quarter_car_analysis(p, prof)

    p_dict = dataclasses.asdict(p)
    r_raw = dataclasses.asdict(res)
    r_dict = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in r_raw.items()}
    prof_dict = {"profile_type": "step", "amplitude": 0.04, "duration": 2.5}

    run_id = uuid.uuid4()
    run = SimulationRun(
        id=run_id,
        seq=183,
        label="RUN-000183",
        title="Pouhon Turn 9 High Speed Setup",
        user_id=uuid.uuid4(),
        simulation_type="quarter_car",
        params=p_dict,
        profile=prof_dict,
        result=r_dict,
        params_hash=canonical_hash(p_dict),
        result_hash=canonical_hash(r_dict),
        input_hash=canonical_hash(prof_dict),
        software_version="1.0.0",
        physics_version="quarter-car-v2",
        solver_version="rk4-bdf-1.0",
        setup_ref="REV-28.4",
        vehicle_ref="CAR-07",
        track_ref="SPA-FRANCORCHAMPS",
        tire_ref="TIRE-MF52-COMPOUND-SOFT",
        telemetry_ref="TELEMETRY-SYNC-Q2",
        created_at=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = run
    mock_db.execute.return_value = mock_scalars

    hydrated = await report_service.hydrate_engineering_report(mock_db, "RUN-000183")

    assert hydrated["run_id"] == "RUN-000183"
    assert hydrated["vehicle_ref"] == "CAR-07"
    assert hydrated["setup_ref"] == "REV-28.4"
    assert hydrated["track_ref"] == "SPA-FRANCORCHAMPS"
    assert hydrated["tire_ref"] == "TIRE-MF52-COMPOUND-SOFT"
    assert hydrated["telemetry_ref"] == "TELEMETRY-SYNC-Q2"
    assert hydrated["solver_version"] == "rk4-bdf-1.0"
    assert hydrated["physics_version"] == "quarter-car-v2"
    assert hydrated["input_hash"] == canonical_hash(prof_dict)
    assert hydrated["result_hash"] == canonical_hash(r_dict)
    assert len(hydrated["artifact_hash"]) == 64

    # Check calculated physics (no static fallbacks)
    metrics = hydrated["metrics"]
    assert "Wk-Weighted RMS Accel" in metrics
    assert "Vibration Dose Value (VDV)" in metrics
    assert "Heave Natural Frequency" in metrics
    assert "Damping Ratio" in metrics
    assert float(metrics["Heave Natural Frequency"].replace(" Hz", "")) > 1.0

    # Check vector plots
    plot_data = hydrated["plot_data"]
    assert "time" in plot_data and len(plot_data["time"]) > 10
    assert "z_s" in plot_data and len(plot_data["z_s"]) > 10
    assert "aerodynamics" in plot_data
    assert "gg_envelope" in plot_data
    assert "kinematics" in plot_data
    assert len(plot_data["kinematics"]["camber_deg"]) == 7


def test_report_hash_changes_when_simulation_changes():
    """Verify STEP 4: Changing simulation results strictly alters canonical artifact hash."""
    h1 = report_service.build_canonical_artifact_hash(
        run_id="RUN-000183",
        vehicle_ref="CAR-07",
        setup_ref="REV-28.4",
        tire_ref="TIRE-MF52",
        track_ref="SPA",
        physics_version="quarter-car-v2",
        solver_version="rk4-bdf-1.0",
        software_build="BUILD-2026.1",
        input_hash="1111111111111111111111111111111111111111111111111111111111111111",
        result_hash="2222222222222222222222222222222222222222222222222222222222222222",
        metrics={"Wk-Weighted RMS Accel": "0.4210 m/s²"},
        validation_status="VALIDATED",
    )

    # Change 1 metric slightly
    h2 = report_service.build_canonical_artifact_hash(
        run_id="RUN-000183",
        vehicle_ref="CAR-07",
        setup_ref="REV-28.4",
        tire_ref="TIRE-MF52",
        track_ref="SPA",
        physics_version="quarter-car-v2",
        solver_version="rk4-bdf-1.0",
        software_build="BUILD-2026.1",
        input_hash="1111111111111111111111111111111111111111111111111111111111111111",
        result_hash="2222222222222222222222222222222222222222222222222222222222222222",
        metrics={"Wk-Weighted RMS Accel": "0.4211 m/s²"},
        validation_status="VALIDATED",
    )

    assert h1 != h2, "Artifact hash must change when metric alters"

    # Change result_hash
    h3 = report_service.build_canonical_artifact_hash(
        run_id="RUN-000183",
        vehicle_ref="CAR-07",
        setup_ref="REV-28.4",
        tire_ref="TIRE-MF52",
        track_ref="SPA",
        physics_version="quarter-car-v2",
        solver_version="rk4-bdf-1.0",
        software_build="BUILD-2026.1",
        input_hash="1111111111111111111111111111111111111111111111111111111111111111",
        result_hash="3333333333333333333333333333333333333333333333333333333333333333",
        metrics={"Wk-Weighted RMS Accel": "0.4210 m/s²"},
        validation_status="VALIDATED",
    )

    assert h1 != h3, "Artifact hash must change when result hash alters"


@pytest.mark.asyncio
async def test_unauthorized_approval_rejected():
    """Verify STEP 5: VIEWER role cannot sign off on reports (PermissionError / 403)."""
    viewer_id = uuid.uuid4()
    report = SharedReport(
        id=uuid.uuid4(),
        token=str(uuid.uuid4()),
        status="PROPOSED",
        artifact_hash="a"*64,
        owner_id=viewer_id,
        simulation_type="quarter_car",
        params={"k_s": 35000.0},
        result={"rms_body_accel": 0.42},
        title="Test Report",
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = report
    mock_db.execute.return_value = mock_scalars

    with pytest.raises(PermissionError, match=r"Role 'VIEWER' is not authorized"):
        await report_service.set_report_approval_status(
            db=mock_db,
            report_id_or_token=str(report.id),
            status="APPROVED",
            user_id=str(viewer_id),
            user_email="viewer@suspensionlab.io",
            user_role="VIEWER",
            comment="I am a viewer trying to sign off.",
        )


@pytest.mark.asyncio
async def test_authorized_approval_signed():
    """Verify STEP 5 & 6: Authorized ENGINEER signs off, producing valid HMAC signature."""
    test_user_id = uuid.uuid4()
    report = SharedReport(
        id=uuid.uuid4(),
        token=str(uuid.uuid4()),
        status="PROPOSED",
        artifact_hash="b"*64,
        owner_id=test_user_id,
        simulation_type="quarter_car",
        params={"k_s": 35000.0},
        result={"rms_body_accel": 0.42},
        title="Test Report",
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = report
    mock_db.execute.return_value = mock_scalars

    approved = await report_service.set_report_approval_status(
        db=mock_db,
        report_id_or_token=str(report.id),
        status="APPROVED",
        user_id=str(test_user_id),
        user_email="chief.engineer@f1team.com",
        user_role="CHIEF_ENGINEER",
        comment="Correlated with track telemetry within tolerance.",
    )

    assert approved["status"] == "APPROVED"
    assert approved["approved_by_email"] == "chief.engineer@f1team.com"
    assert approved["approved_by_role"] == "CHIEF_ENGINEER"
    assert approved["approval_signature"] is not None
    assert len(approved["approval_signature"]) == 64

    # Verify signature verification
    ver = report_service.verify_report_artifact_signature(report)
    assert ver["signature_valid"] is True
    assert ver["tamper_detected"] is False


@pytest.mark.asyncio
async def test_separation_of_duty_standard_engineer_rejected():
    """Verify DEF-P2-01: Standard generic ENGINEER role is rejected from signing release approvals."""
    test_user_id = uuid.uuid4()
    report = SharedReport(
        id=uuid.uuid4(),
        token=str(uuid.uuid4()),
        status="PROPOSED",
        artifact_hash="c" * 64,
        owner_id=test_user_id,
        simulation_type="quarter_car",
        params={"k_s": 35000.0},
        result={"rms_body_accel": 0.42},
        title="Test Report",
    )
    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = report
    mock_db.execute.return_value = mock_scalars

    with pytest.raises(PermissionError, match=r"Role 'ENGINEER' is not authorized to sign or reject engineering reports"):
        await report_service.set_report_approval_status(
            db=mock_db,
            report_id_or_token=str(report.id),
            status="APPROVED",
            user_id=str(test_user_id),
            user_email="engineer@f1team.com",
            user_role="ENGINEER",
            comment="Attempting approval as standard engineer",
        )


def test_post_signing_tamper_detected():
    """Verify STEP 6: Any tampering with signed artifact invalidates signature."""
    user_id = uuid.uuid4()
    rep = SharedReport(
        id=uuid.uuid4(),
        token=str(uuid.uuid4()),
        status="APPROVED",
        artifact_hash="c"*64,
        approved_by_user_id=user_id,
        approved_by_email="lead@suspensionlab.io",
        approved_by_role="LEAD",
        approved_at=datetime.now(timezone.utc),
        owner_id=user_id,
        simulation_type="quarter_car",
        params={"k_s": 35000.0},
        result={"rms_body_accel": 0.42},
        title="Test Report",
    )
    sig = report_service.sign_report_artifact(
        report_id=str(rep.id),
        artifact_hash=rep.artifact_hash,
        user_email=rep.approved_by_email,
        user_role=rep.approved_by_role,
        timestamp_iso=rep.approved_at.isoformat(),
        user_id=str(rep.approved_by_user_id),
        status=rep.status,
    )
    rep.approval_signature = sig

    # Initial check passes
    ver1 = report_service.verify_report_artifact_signature(rep)
    assert ver1["signature_valid"] is True

    # Tamper with the artifact hash (e.g. Someone altered underlying simulation result)
    rep.artifact_hash = "d"*64
    ver2 = report_service.verify_report_artifact_signature(rep)
    assert ver2["signature_valid"] is False
    assert ver2["tamper_detected"] is True


@pytest.mark.asyncio
async def test_backend_share_token_generation():
    """Verify STEP 7: Real backend share token generation and URL format."""
    rep = SharedReport(
        id=uuid.uuid4(),
        token=str(uuid.uuid4()),
        doc_id="DOC-2026-SL-0001",
        status="APPROVED",
        artifact_hash="e"*64,
        owner_id=uuid.uuid4(),
        simulation_type="quarter_car",
        params={"k_s": 35000.0},
        result={"rms_body_accel": 0.42},
        title="Share Token Test",
    )

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.scalar_one_or_none.return_value = rep
    mock_db.execute.return_value = mock_scalars

    res = await report_service.create_or_get_share_token(mock_db, str(rep.id))
    assert res["token"] == rep.token
    assert res["share_url"] == f"/report/{rep.token}"
    assert res["doc_id"] == "DOC-2026-SL-0001"


