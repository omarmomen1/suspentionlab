from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Optional
import datetime
import os
import uuid
import logging
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.shared.models import SimulateRequest, PlanTier
from suspensionlab.backend.security.auth import require_permission, UserContext, verify_api_key
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.services import report_service
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reporting"])


class CreateReportRequest(BaseModel):
    simulation_run_id: str = "latest"
    baseline_run_id: Optional[str] = None
    title: str = ""
    notes: str = ""


class ApprovalRequest(BaseModel):
    status: str
    comment: str = ""


class DecisionReportVerifyRequest(BaseModel):
    sim_id: str
    user_id: str
    approver_email: str
    approver_role: str
    approval_decision: str
    result_hash: str
    approval_time: str
    signature: str
    organization: Optional[str] = None
    team: Optional[str] = None
    report_id: Optional[str] = None
    report_version: Optional[str] = None
    simulation_run: Optional[str] = None
    setup_version: Optional[str] = None
    vehicle_version: Optional[str] = None
    validation_state: Optional[str] = None
    ed25519_signature: Optional[str] = None
    public_key_hex: Optional[str] = None


@router.post("/iso2631", response_class=Response)
async def generate_iso_report(
    request_data: SimulateRequest,
    user: UserContext = Depends(require_permission(Permission.REPORT_EXPORT)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Generate an HTML report of the ISO 2631-1 Wk-weighted vibration analysis
    with complete cryptographic provenance and version lineage.
    """
    import html
    import jinja2
    import os
    from suspensionlab.backend.security.audit import canonical_hash

    # 1. Run simulation to get Wk weighted acceleration
    params = QuarterCarParams(**request_data.params.model_dump())
    profile = RoadProfile(**request_data.profile.model_dump())
    res = run_quarter_car_analysis(params, profile)
    
    wk_rms = res.rms_body_accel_wk
    comfort_str = res.comfort_rating
    
    # ISO classification color coding
    if wk_rms < 0.315:
        status_color = "#2e7d32" # Green
    elif wk_rms < 0.63:
        status_color = "#f57f17" # Orange
    else:
        status_color = "#c62828" # Red
        
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_email = html.escape(getattr(user, "email", "Enterprise User") if user else "Enterprise User")

    # Cryptographic provenance
    input_hash = canonical_hash(request_data.params.model_dump())
    profile_hash = canonical_hash(request_data.profile.model_dump())
    result_hash = canonical_hash({
        "rms_body_accel_wk": res.rms_body_accel_wk,
        "rms_body_accel": res.rms_body_accel,
        "comfort_rating": res.comfort_rating,
        "rms_susp_travel": res.rms_susp_travel,
        "peak_susp_travel": res.peak_susp_travel,
    })
    software_build = os.getenv("GIT_COMMIT", "BUILD-REL-2026.1")
    solver_version = "rk4-bdf-2.1"
    physics_version = "quarter-car-v2"

    template_str = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>ISO 2631-1 Wk-Weighted Analysis Report</title>
        <style>
            body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 40px; color: #333; }
            .header { border-bottom: 2px solid #000; padding-bottom: 20px; margin-bottom: 30px; }
            .logo { font-size: 24px; font-weight: bold; color: #1a73e8; }
            h1 { font-size: 20px; text-transform: uppercase; }
            .section { margin-bottom: 30px; }
            .metrics-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            .metrics-table th, .metrics-table td { border: 1px solid #ddd; padding: 12px; text-align: left; }
            .metrics-table th { background-color: #f5f5f5; width: 50%; }
            .status-box { padding: 20px; background-color: {{ status_color }}; color: white; text-align: center; font-size: 18px; font-weight: bold; border-radius: 4px; margin-top: 20px; }
            .provenance-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin-top: 20px; font-family: ui-monospace, monospace; font-size: 12px; }
            .hash-block { word-break: break-all; color: #475569; font-size: 11px; margin-top: 2px; }
            .footer { margin-top: 50px; font-size: 12px; color: #777; border-top: 1px solid #ddd; padding-top: 10px; text-align: center; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">SuspensionLab PRO</div>
            <h1>ISO 2631-1 Wk-Weighted Analysis Report</h1>
            <p><strong>Date Generated:</strong> {{ date_str }}</p>
            <p><strong>Generated By:</strong> {{ safe_email }}</p>
        </div>

        <div class="section">
            <h2>1. Vehicle Parameters (Quarter Car)</h2>
            <table class="metrics-table">
                <tr><th>Sprung Mass (m_s)</th><td>{{ params.m_s }} kg</td></tr>
                <tr style="background-color: #fdfdfd;"><th>Unsprung Mass (m_u)</th><td>{{ params.m_u }} kg</td></tr>
                <tr><th>Suspension Stiffness (k_s)</th><td>{{ params.k_s }} N/m</td></tr>
                <tr style="background-color: #fdfdfd;"><th>Suspension Damping (c_s)</th><td>{{ params.c }} N.s/m</td></tr>
                <tr><th>Tire Stiffness (k_t)</th><td>{{ params.k_t }} N/m</td></tr>
            </table>
        </div>

        <div class="section">
            <h2>2. ISO 2631-1 Whole-Body Vibration Assessment</h2>
            <p>The step-response transient was filtered using the principal frequency weighting Wk as specified by ISO 2631-1 for vertical seat vibration.</p>
            <table class="metrics-table">
                <tr><th>Raw RMS Acceleration</th><td>{{ "%.4f"|format(res.rms_body_accel) }} m/s²</td></tr>
                <tr style="background-color: #fdfdfd;"><th>Wk-Weighted RMS Acceleration</th><td><strong>{{ "%.4f"|format(wk_rms) }} m/s²</strong></td></tr>
            </table>
            
            <div class="status-box">
                ISO 2631-1 Comfort Classification (Wk-weighted): {{ comfort_str|upper }}
            </div>
        </div>

        <div class="section">
            <h2>3. Cryptographic Provenance & Configuration Lineage</h2>
            <div class="provenance-card">
                <div><strong>Solver:</strong> {{ solver_version }} &middot; <strong>Physics:</strong> {{ physics_version }} &middot; <strong>Build:</strong> {{ software_build }}</div>
                <div style="margin-top: 8px;"><strong>Input Hash (SHA-256):</strong><div class="hash-block">{{ input_hash }}</div></div>
                <div style="margin-top: 8px;"><strong>Profile Hash (SHA-256):</strong><div class="hash-block">{{ profile_hash }}</div></div>
                <div style="margin-top: 8px;"><strong>Result Hash (SHA-256):</strong><div class="hash-block">{{ result_hash }}</div></div>
            </div>
        </div>

        <div class="footer">
            This document is auto-generated by the SuspensionLab simulation engine.<br>
            It presents an analysis using the ISO 2631-1 Wk weighting method applied to a
            simulated quarter-car model. It is not an ISO certification, and it does not
            constitute regulatory compliance evidence — formal compliance requires
            accredited physical measurement campaigns.
        </div>
    </body>
    </html>
    """
    
    template = jinja2.Template(template_str, autoescape=True)
    html_content = template.render(
        status_color=status_color,
        date_str=date_str,
        safe_email=safe_email,
        params=params,
        res=res,
        wk_rms=wk_rms,
        comfort_str=comfort_str,
        solver_version=solver_version,
        physics_version=physics_version,
        software_build=software_build,
        input_hash=input_hash,
        profile_hash=profile_hash,
        result_hash=result_hash,
    )

    if hasattr(db, "execute"):
        try:
            from suspensionlab.backend.security.audit import record_audit_event
            await record_audit_event(
                db=db,
                event_type="REPORT_GENERATED",
                user_id=getattr(user, "user_id", None),
                team_id=getattr(user, "team_id", None),
                artifact_id=result_hash,
                metadata={
                    "report_type": "ISO2631",
                    "input_hash": input_hash,
                    "result_hash": result_hash,
                    "solver_version": solver_version,
                }
            )
        except Exception:
            pass

    return Response(
        content=html_content,
        media_type="text/html",
        headers={
            "Content-Disposition": "inline; filename=iso2631_report.html",
            "X-Report-Input-Hash": input_hash,
            "X-Report-Result-Hash": result_hash,
            "X-Software-Build": software_build,
        }
    )


@router.post("/decision_report", response_class=Response)
async def generate_engineering_decision_report(
    report_data: dict,
    user: UserContext = Depends(require_permission(Permission.REPORT_EXPORT)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Generate an authentic, traceable Engineering Decision & Compliance Report.
    Enforces server-authenticated Chief Engineer Approval, reject identity spoofing,
    enforces empirical validation requirements before track sign-off, dynamic hashes,
    and cryptographic audit lineage.
    """
    import html
    import jinja2
    import hashlib
    import hmac as _hmac
    import json
    import os
    import uuid as _uuid
    from suspensionlab.backend.security.audit import canonical_hash
    from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY

    run_label = report_data.get("run_label") or report_data.get("simulation_id")
    run = None
    if run_label:
        try:
            run = await report_service.get_simulation_run(
                db, str(run_label), str(user.user_id), getattr(user, "team_id", None)
            )
        except LookupError:
            raise HTTPException(
                status_code=404,
                detail=f"Simulation run '{run_label}' not found or access denied in your organization.",
            )

    if run:
        sim_id = run.label
        vehicle = html.escape(run.vehicle_ref or "NOT SET")
        setup = html.escape(run.setup_ref or "NOT SET")
        track = html.escape(run.track_ref or "NOT SET")
        tire = html.escape(run.tire_ref or "NOT SET")
        aero_ver = html.escape(str(report_data.get("aero_version") or "NOT SET"))
        dataset_ref = html.escape(run.telemetry_ref or "NOT SET")
        vehicle_model_ver = html.escape(run.physics_version or "7-DOF Full Car / 2-DOF Quarter Car Suite")
        tire_model_ver = "Pacejka MF 5.2 / Similarity"
        solver_ver = html.escape(run.solver_version or "RK45 / BDF Adaptive Stiff")
        software_build = html.escape(run.git_build_id or os.getenv("GIT_COMMIT", "BUILD-REL-2026.1"))
        input_hash = run.params_hash
        result_hash = run.result_hash
        mv = run.model_validity if isinstance(run.model_validity, dict) else {}
        val_score = mv.get("score")
        if val_score is None:
            val_score = mv.get("correlation_pct")
        if val_score is not None:
            try:
                val_score_f = float(val_score)
                correlation_pct = round(val_score_f * 100.0 if val_score_f <= 1.0 else val_score_f, 2)
            except (ValueError, TypeError):
                correlation_pct = None
        else:
            correlation_pct = None

        validation_state = mv.get("status") or mv.get("validation_state")
        if not validation_state:
            validation_state = "VALIDATED" if (correlation_pct and correlation_pct >= 85.0) else "UNVALIDATED"
    else:
        # Wave 9 item 2: a decision report without a persisted run is refused.
        # No unbacked fallback path may print invented vehicle, track, tire or
        # telemetry references.
        raise HTTPException(
            status_code=422,
            detail="report requires a persisted simulation run",
        )

    # Chief Engineer Approval verification & Anti-Spoofing
    approval = report_data.get("approval")
    if not isinstance(approval, dict) or not approval:
        approval = {
            "name": report_data.get("approver_name") or report_data.get("name"),
            "email": report_data.get("approver_email") or report_data.get("email"),
            "role": report_data.get("approver_role") or report_data.get("role"),
            "decision": report_data.get("approval_status") or report_data.get("decision"),
            "comment": report_data.get("approval_comment") or report_data.get("comment"),
        }

    decision_raw = str(approval.get("decision") or "").upper()
    wants_approval = decision_raw in ("APPROVED_FOR_TEST_TRACK", "APPROVED", "APPROVED_FOR_TRACK")

    # Server-derived identity
    authenticated_name = getattr(user, "name", None) or (user.email.split("@")[0].replace(".", " ").title() if user.email else "Authenticated Engineer")
    authenticated_email = user.email or "engineer@suspensionlab.pro"
    authenticated_role = str(user.team_role or user.org_role or "ENGINEER").upper()

    if wants_approval:
        if not user.can(Permission.SETUP_APPROVE):
            raise HTTPException(
                status_code=403,
                detail=f"Permission Denied: User '{user.email}' lacks '{Permission.SETUP_APPROVE.value}' required to sign engineering release approvals. Separation of duty requires Chief Engineer, Lead, or Administrator sign-off.",
            )
        # DEF-P2-01: Enforce separation of duty: generic ENGINEER cannot approve track releases
        norm_role = authenticated_role.replace(" ", "_").upper()
        if norm_role not in {"CHIEF_ENGINEER", "CHIEF_RACE_ENGINEER", "LEAD_ENGINEER", "LEAD", "ADMIN", "OWNER", "SUPER_ADMIN", "ORG_ADMIN"} and not ("CHIEF" in norm_role or "LEAD" in norm_role):
            raise HTTPException(
                status_code=403,
                detail=f"Permission Denied: Role '{authenticated_role}' is not authorized to sign release approvals. Separation of duty requires Chief Engineer, Lead, or Administrator sign-off.",
            )

    # Reject client-supplied spoofed identities
    client_name = approval.get("name")
    client_role = approval.get("role")
    client_email = approval.get("email")

    if client_name and client_name.strip() and client_name.strip().lower() != authenticated_name.lower():
        raise HTTPException(
            status_code=403,
            detail=f"Identity spoofing detected: client-supplied approver name '{client_name}' does not match authenticated user '{authenticated_name}'.",
        )
    if client_role and client_role.strip() and client_role.strip().upper() != authenticated_role:
        raise HTTPException(
            status_code=403,
            detail=f"Role spoofing detected: client-supplied approver role '{client_role}' does not match authenticated role '{authenticated_role}'.",
        )
    if client_email and client_email.strip() and client_email.strip().lower() != authenticated_email.lower():
        raise HTTPException(
            status_code=403,
            detail=f"Email spoofing detected: client-supplied approver email '{client_email}' does not match authenticated user '{authenticated_email}'.",
        )

    approver_name = html.escape(authenticated_name)
    approver_role = html.escape(authenticated_role)
    approver_email = html.escape(authenticated_email)
    approval_decision = html.escape(approval.get("decision") or ("APPROVED_FOR_TRACK" if wants_approval else "PROPOSED"))
    # Wave 9 item 1: only a persisted APPROVED decision may print a sign-off.
    _APPROVED_DECISIONS = {"APPROVED_FOR_TRACK", "APPROVED_FOR_TEST_TRACK", "APPROVED"}
    _REJECTED_DECISIONS = {"REJECTED", "REJECTED_FOR_TRACK", "DECLINED", "NOT_APPROVED"}
    if decision_raw in _APPROVED_DECISIONS:
        approval_state = "APPROVED"
    elif decision_raw in _REJECTED_DECISIONS:
        approval_state = "REJECTED"
    else:
        approval_state = "PROPOSED"
    approval_comment = html.escape(approval.get("comment") or "Signed off with server-authenticated cryptographic identity.")
    approval_time = html.escape(datetime.datetime.now(datetime.timezone.utc).isoformat())

    # Invariant: Never approve an unvalidated or failing physics run
    if wants_approval or approval_decision in ("APPROVED_FOR_TEST_TRACK", "APPROVED_FOR_TRACK", "APPROVED"):
        if not run:
            raise HTTPException(
                status_code=400,
                detail="Cannot approve report: report must be backed by a verified database SimulationRun record. Omission of simulation_id/run_label is prohibited for engineering sign-off.",
            )
        if validation_state in ("UNVALIDATED", "DATA_MISSING", "FAILED", "NOT_EVALUATED") or correlation_pct is None or correlation_pct < 85.0:
            corr_str = f"{correlation_pct}%" if correlation_pct is not None else "None"
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve report: physics validation state is '{validation_state}' with correlation {corr_str}. Explicit empirical validation (correlation >= 85.0%) is required before test track sign-off.",
            )

    # Canonical 13-attribute governance payload
    org_id_str = str(getattr(user, "organization_id", None) or "NO_ORG")
    team_id_str = str(getattr(user, "team_id", None) or "NO_TEAM")
    rep_ver = software_build or "v1.0"
    setup_ver = setup or "REV-01"
    veh_ver = vehicle or "VEHICLE-01"

    gov_dict = report_service.build_canonical_governance_dict(
        authenticated_user=str(user.user_id),
        authorized_role=authenticated_role,
        organization=org_id_str,
        team=team_id_str,
        report_id=sim_id,
        report_version=rep_ver,
        simulation_run=sim_id,
        setup_version=setup_ver,
        vehicle_version=veh_ver,
        result_hash=result_hash,
        validation_state=validation_state,
        timestamp=approval_time,
        decision=approval_decision,
    )
    gov_payload = report_service.canonicalize_governance_payload(gov_dict)

    # 1. Asymmetric Ed25519 digital signature (Third-party non-repudiation)
    ed25519_sig = report_service.compute_approval_ed25519(gov_payload)
    authority_pubkey = report_service.get_authority_public_key_hex()

    # 2. Symmetric HMAC-SHA256 signature binding all 13 attributes
    approval_signature = report_service.compute_approval_hmac(
        report_id=sim_id,
        user_id=str(user.user_id),
        user_role=authenticated_role,
        status=approval_decision,
        artifact_hash=result_hash,
        timestamp_iso=approval_time,
        organization=org_id_str,
        team=team_id_str,
        report_version=rep_ver,
        simulation_run=sim_id,
        setup_version=setup_ver,
        vehicle_version=veh_ver,
        result_hash=result_hash,
        validation_state=validation_state,
    )

    # Wave 9 item 1: no approval signature exists unless the decision is APPROVED.
    if approval_state != "APPROVED":
        ed25519_sig = ""
        approval_signature = ""
        authority_pubkey = ""

    # Wave 9 item 3: the auto-computed default-vehicle baseline must be unmistakable.
    _mv = run.model_validity if (run is not None and isinstance(run.model_validity, dict)) else {}
    is_default_vehicle_baseline = bool(_mv.get("is_default_vehicle_baseline"))

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    template_str = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Engineering Decision & Compliance Report — {{ vehicle }}</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 40px; color: #1e293b; background: #fff; }
            .header-banner { border-bottom: 3px solid #2563eb; padding-bottom: 20px; margin-bottom: 24px; }
            .badge-pass { background: #dcfce7; color: #15803d; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 13px; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }
            .card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; background: #f8fafc; }
            .card h3 { margin-top: 0; font-size: 14px; text-transform: uppercase; color: #64748b; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
            .meta-table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .meta-table td { padding: 6px 0; }
            .meta-table td.label { color: #64748b; width: 45%; font-weight: 500; }
            .meta-table td.val { font-family: ui-monospace, SFMono-Regular, monospace; font-weight: 600; color: #0f172a; }
            .approval-box { border: 2px solid #22c55e; border-radius: 6px; padding: 20px; background: #f0fdf4; margin-top: 30px; }
            .approval-title { font-size: 16px; font-weight: bold; color: #166534; display: flex; align-items: center; justify-content: space-between; }
            .hash-block { word-break: break-all; font-family: ui-monospace, monospace; font-size: 11px; color: #475569; background: #f1f5f9; padding: 8px; border-radius: 4px; margin-top: 4px; }
            .signature-block { word-break: break-all; font-family: ui-monospace, monospace; font-size: 11px; color: #166534; background: #dcfce7; padding: 8px; border-radius: 4px; margin-top: 8px; }
        </style>
    </head>
    <body>
        {% if is_default_vehicle_baseline %}
        <div style="border:2px solid #f59e0b; background:#fffbeb; color:#92400e; padding:12px 16px; border-radius:6px; margin-bottom:20px; font-size:13px; font-weight:600;">
            Reference baseline on the default vehicle - not your car. Run a simulation on your own parameters first.
        </div>
        {% endif %}
        <div class="header-banner">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h1 style="margin:0; font-size:22px; color:#0f172a;">Engineering Decision &amp; Compliance Report</h1>
                <span class="badge-pass">{{ validation_state }}</span>
            </div>
            <p style="color:#64748b; margin:6px 0 0 0; font-size:14px;">Sim ID: <strong>{{ sim_id }}</strong> &middot; Vehicle: <strong>{{ vehicle }}</strong> &middot; Setup: <strong>{{ setup }}</strong> &middot; Track: <strong>{{ track }}</strong></p>
        </div>

        <div class="grid">
            <div class="card">
                <h3>1. Physics &amp; Solver Provenance</h3>
                <table class="meta-table">
                    <tr><td class="label">Simulation ID:</td><td class="val">{{ sim_id }}</td></tr>
                    <tr><td class="label">Vehicle Model:</td><td class="val">{{ vehicle_model_ver }}</td></tr>
                    <tr><td class="label">Tire Spec / Model:</td><td class="val">{{ tire }} ({{ tire_model_ver }})</td></tr>
                    <tr><td class="label">Aero Package:</td><td class="val">{{ aero_ver }}</td></tr>
                    <tr><td class="label">Solver / Build:</td><td class="val">{{ solver_ver }} / {{ software_build }}</td></tr>
                </table>
            </div>

            <div class="card">
                <h3>2. Evidence &amp; Telemetry Correlation</h3>
                <table class="meta-table">
                    <tr><td class="label">Dataset Ref:</td><td class="val">{{ dataset_ref }}</td></tr>
                    <tr><td class="label">Hold-out Correlation:</td><td class="val">{% if correlation_pct is not none %}{{ "%.2f"|format(correlation_pct) }}%{% else %}None (Unvalidated){% endif %}</td></tr>
                    <tr><td class="label">Validation State:</td><td class="val">{{ validation_state }}</td></tr>
                    <tr><td class="label">Generated At:</td><td class="val">{{ date_str }}</td></tr>
                </table>
            </div>
        </div>

        <div class="card" style="margin-bottom: 24px;">
            <h3>3. Cryptographic Audit Lineage</h3>
            <div><strong style="font-size:12px; color:#334155;">Input Parameter Hash (SHA-256):</strong><div class="hash-block">{{ input_hash }}</div></div>
            <div style="margin-top:10px;"><strong style="font-size:12px; color:#334155;">Simulation Result Hash (SHA-256):</strong><div class="hash-block">{{ result_hash }}</div></div>
        </div>

        {% if approval_state == 'APPROVED' %}
        <div class="approval-box">
            <div class="approval-title">
                <span>CHIEF ENGINEER DECISION SIGN-OFF</span>
                <span style="font-size:13px; font-weight:bold; color:#15803d;">{{ approval_decision }}</span>
            </div>
            <p style="margin:12px 0 6px 0; font-size:14px; color:#14532d;"><em>"{{ approval_comment }}"</em></p>
            <div style="margin-top:14px; font-size:13px; color:#166534;">
                Approved by <strong>{{ approver_name }}</strong> ({{ approver_role }}) on <strong>{{ approval_time }}</strong>
            </div>
            <div class="signature-block">
                <strong>Cryptographic Approval Signature (HMAC-SHA256):</strong><br>{{ approval_signature }}
            </div>
            <div class="signature-block" style="background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; margin-top:6px;">
                <strong>Asymmetric Non-Repudiation Signature (Ed25519):</strong><br>{{ ed25519_sig }}<br>
                <span style="font-size:10px; color:#64748b;">Authority Public Key: {{ authority_pubkey }}</span>
            </div>
        </div>
        {% elif approval_state == 'REJECTED' %}
        <div class="approval-box" style="border-color:#dc2626; background:#fef2f2;">
            <div class="approval-title" style="color:#991b1b;">
                <span>CHIEF ENGINEER DECISION</span>
                <span style="font-size:13px; font-weight:bold; color:#b91c1c;">{{ approval_decision }}</span>
            </div>
            <p style="margin:12px 0 6px 0; font-size:14px; color:#7f1d1d;"><em>"{{ approval_comment }}"</em></p>
            <div style="margin-top:14px; font-size:13px; color:#991b1b;">
                Rejected by <strong>{{ approver_name }}</strong> ({{ approver_role }}) on <strong>{{ approval_time }}</strong>
            </div>
        </div>
        {% else %}
        <div class="approval-box" style="border-color:#94a3b8; background:#f8fafc;">
            <div class="approval-title" style="color:#334155;">
                <span>CHIEF ENGINEER DECISION SIGN-OFF</span>
                <span style="font-size:13px; font-weight:bold; color:#b45309;">PROPOSED - AWAITING CHIEF ENGINEER DECISION</span>
            </div>
            <p style="margin:12px 0 6px 0; font-size:14px; color:#334155;"><em>"{{ approval_comment }}"</em></p>
            <div style="margin-top:14px; font-size:12px; color:#64748b;">
                No approval has been recorded for this report. Nothing here is signed.
            </div>
        </div>
        {% endif %}
    </body>
    </html>
    """

    template = jinja2.Template(template_str, autoescape=True)
    html_content = template.render(
        sim_id=sim_id,
        vehicle=vehicle,
        setup=setup,
        track=track,
        tire=tire,
        aero_ver=aero_ver,
        dataset_ref=dataset_ref,
        vehicle_model_ver=vehicle_model_ver,
        tire_model_ver=tire_model_ver,
        solver_ver=solver_ver,
        software_build=software_build,
        validation_state=validation_state,
        correlation_pct=correlation_pct,
        approver_name=approver_name,
        approver_role=approver_role,
        approval_decision=approval_decision,
        approval_comment=approval_comment,
        approval_time=approval_time,
        approval_signature=approval_signature,
        approval_state=approval_state,
        is_default_vehicle_baseline=is_default_vehicle_baseline,
        ed25519_sig=ed25519_sig,
        authority_pubkey=authority_pubkey,
        input_hash=input_hash,
        result_hash=result_hash,
        date_str=date_str,
    )

    if hasattr(db, "execute"):
        try:
            from suspensionlab.backend.security.audit import record_audit_event
            await record_audit_event(
                db=db,
                event_type="REPORT_GENERATED",
                user_id=getattr(user, "user_id", None),
                team_id=getattr(user, "team_id", None),
                artifact_id=sim_id,
                metadata={
                    "report_type": "ENGINEERING_DECISION",
                    "simulation_id": sim_id,
                    "input_hash": input_hash,
                    "result_hash": result_hash,
                    "approval_decision": approval_decision,
                    "approval_signature": approval_signature,
                    "ed25519_signature": ed25519_sig,
                    "authority_public_key": authority_pubkey,
                    "governance_13_bound": True,
                }
            )
        except Exception:
            pass

    response_headers = {
        "Content-Disposition": "inline; filename=engineering_decision_report.html",
        "X-Simulation-ID": sim_id,
        "X-Input-Hash": input_hash,
        "X-Result-Hash": result_hash,
        "X-Approval-Time": approval_time,
        "X-Approver-Email": approver_email,
        "X-Approver-Role": approver_role,
        "X-Approval-Decision": approval_decision,
        "X-Approval-State": approval_state,
        "X-Governance-Attributes": "13",
    }
    # Wave 9 item 1: signature headers exist only for an APPROVED decision.
    if approval_state == "APPROVED":
        response_headers["X-Approval-Signature"] = approval_signature
        response_headers["X-Ed25519-Signature"] = ed25519_sig
        response_headers["X-Authority-Public-Key"] = authority_pubkey
    return Response(
        content=html_content,
        media_type="text/html",
        headers=response_headers,
    )


@router.get("/hydrate/{run_id_or_label}")
async def hydrate_report_endpoint(
    run_id_or_label: str,
    baseline_run_id: Optional[str] = None,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Hydrate complete, authentic engineering report from a real SimulationRun artifact.
    Contains zero static values: retrieves real vehicle, setup, tire, track,
    physics, solver, telemetry, optimization, and validation metrics.
    """
    uid = str(user.user_id)
    tid = str(user.team_id) if getattr(user, "team_id", None) else None
    try:
        target_id = run_id_or_label
        if (run_id_or_label or "").strip().lower() == "latest":
            latest_run = await report_service.resolve_latest_or_baseline_run(db, uid, tid)
            target_id = str(latest_run.id)
        data = await report_service.hydrate_engineering_report(
            db, target_id, uid, tid, baseline_run_id=baseline_run_id
        )
        return data
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to hydrate report: %s", e)
        raise HTTPException(status_code=500, detail=f"Hydration error: {e}")


@router.post("/create_from_run")
async def create_from_run_endpoint(
    req: CreateReportRequest,
    user: UserContext = Depends(require_permission(Permission.REPORT_EXPORT)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Persist an authentic engineering report from a completed simulation run.
    Stores complete 13-point configuration lineage, computes canonical artifact hash,
    initializes approval state as PROPOSED, and issues a secure backend share token.
    """
    uid = str(user.user_id)
    uemail = user.email or "engineer@suspensionlab.pro"
    urole = str(user.team_role or user.org_role or "ENGINEER").upper()
    tid = str(user.team_id) if getattr(user, "team_id", None) else None
    oid = str(user.organization_id) if getattr(user, "organization_id", None) else None

    try:
        target_id = req.simulation_run_id
        if (req.simulation_run_id or "").strip().lower() in ("", "latest", "default", "baseline"):
            latest_run = await report_service.resolve_latest_or_baseline_run(db, uid, tid)
            target_id = str(latest_run.id)
        rep = await report_service.create_or_get_persisted_report(
            db=db,
            run_id_or_label=target_id,
            user_id=uid,
            user_email=uemail,
            user_role=urole,
            team_id=tid,
            organization_id=oid,
            title=req.title,
            notes=req.notes,
        )
        hydrated = await report_service.hydrate_engineering_report(
            db, str(rep.simulation_id), uid, tid, baseline_run_id=req.baseline_run_id
        )
        return {
            "id": str(rep.id),
            "token": rep.token,
            "status": rep.status,
            "doc_id": rep.doc_id,
            "artifact_hash": rep.artifact_hash,
            "share_url": f"/report/{rep.token}",
            "hydrated": hydrated,
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error in create_from_run: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/record/{report_id_or_token}")
async def get_report_record_endpoint(
    report_id_or_token: str,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Fetch persistent report record with full provenance, metrics, and signature verification, strictly tenant-scoped."""
    try:
        rep = await report_service.get_report_record(
            db,
            report_id_or_token,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Report '{report_id_or_token}' not found.")

    sig_verification = report_service.verify_report_artifact_signature(rep)
    return {
        "id": str(rep.id),
        "token": rep.token,
        "status": rep.status,
        "doc_id": rep.doc_id,
        "vehicle_ref": rep.vehicle_ref,
        "setup_ref": rep.setup_ref,
        "tire_ref": rep.tire_ref,
        "track_ref": rep.track_ref,
        "telemetry_ref": rep.telemetry_ref,
        "solver_version": rep.solver_version,
        "software_build": rep.software_build,
        "validation_status": rep.validation_status,
        "correlation_pct": rep.correlation_pct,
        "input_hash": rep.input_hash or rep.params_hash,
        "result_hash": rep.result_hash,
        "artifact_hash": rep.artifact_hash,
        "approved_by_email": rep.approved_by_email,
        "approved_by_role": rep.approved_by_role,
        "approved_at": rep.approved_at.isoformat() if rep.approved_at else None,
        "approval_comment": rep.approval_comment,
        "approval_signature": rep.approval_signature,
        "metrics": rep.metrics,
        "plot_data": rep.plot_data,
        "signature_verification": sig_verification,
        "share_url": f"/report/{rep.token}",
    }


@router.post("/{report_id_or_token}/status")
async def update_report_status_endpoint(
    report_id_or_token: str,
    req: ApprovalRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Multi-role approval state transition (PROPOSED -> APPROVED / REJECTED).
    Enforces authorization: requires SETUP_APPROVE capability. Rejects unauthorized (e.g. VIEWER) with 403.
    Computes cryptographic HMAC-SHA256 signature binding the signee and canonical artifact.
    """
    uid = str(user.user_id)
    uemail = user.email or "engineer@suspensionlab.pro"
    urole = str(user.team_role or user.org_role or "ENGINEER").upper()
    tid = str(user.team_id) if getattr(user, "team_id", None) else None

    try:
        result = await report_service.set_report_approval_status(
            db=db,
            report_id_or_token=report_id_or_token,
            status=req.status,
            comment=req.comment,
            user_id=uid,
            user_email=uemail,
            user_role=urole,
            team_id=tid,
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/decision_report/verify")
async def verify_decision_report_signature_endpoint(
    req: DecisionReportVerifyRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Cryptographically verify that an engineering decision report signature matches the artifact, server credentials, and asymmetric Ed25519 authority."""
    from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY
    import hmac as _hmac
    import hashlib

    org = req.organization
    team = req.team
    rep_ver = req.report_version
    setup_ver = req.setup_version
    veh_ver = req.vehicle_version
    val_state = req.validation_state
    sim_run_id = req.simulation_run or req.sim_id

    # If full governance fields were not passed in payload, hydrate from database SimulationRun
    if db and (not org or not team or not rep_ver or not setup_ver or not veh_ver):
        try:
            run = await report_service.get_simulation_run(
                db, req.sim_id, req.user_id, team_id=getattr(user, "team_id", None)
            )
            if run:
                if not org and getattr(user, "organization_id", None):
                    org = str(user.organization_id)
                if not team and run.team_id:
                    team = str(run.team_id)
                elif not team and getattr(user, "team_id", None):
                    team = str(user.team_id)
                if not setup_ver:
                    setup_ver = run.setup_ref or "NOT SET"
                if not veh_ver:
                    veh_ver = run.vehicle_ref or "NOT SET"
                if not rep_ver:
                    rep_ver = run.git_build_id or os.getenv("GIT_COMMIT", "BUILD-REL-2026.1")
                if not val_state and run.model_validity:
                    mv = run.model_validity if isinstance(run.model_validity, dict) else {}
                    val_state = mv.get("status") or mv.get("validation_state")
        except Exception:
            pass

    org = org or "NO_ORG"
    team = team or "NO_TEAM"
    rep_ver = rep_ver or os.getenv("GIT_COMMIT", "BUILD-REL-2026.1")
    setup_ver = setup_ver or "NOT SET"
    veh_ver = veh_ver or "NOT SET"
    val_state = val_state or "VALIDATED"

    # Canonical 13-attribute governance payload
    gov_dict = report_service.build_canonical_governance_dict(
        authenticated_user=req.user_id,
        authorized_role=req.approver_role,
        organization=org,
        team=team,
        report_id=req.report_id or req.sim_id,
        report_version=rep_ver,
        simulation_run=sim_run_id,
        setup_version=setup_ver,
        vehicle_version=veh_ver,
        result_hash=req.result_hash,
        validation_state=val_state,
        timestamp=req.approval_time,
        decision=req.approval_decision,
    )
    gov_payload = report_service.canonicalize_governance_payload(gov_dict)

    # 1. Verify 13-attribute HMAC
    hmac_13 = report_service.compute_approval_hmac(
        report_id=req.report_id or req.sim_id,
        user_id=req.user_id,
        user_role=req.approver_role,
        status=req.approval_decision,
        artifact_hash=req.result_hash,
        timestamp_iso=req.approval_time,
        organization=org,
        team=team,
        report_version=rep_ver,
        simulation_run=sim_run_id,
        setup_version=setup_ver,
        vehicle_version=veh_ver,
        result_hash=req.result_hash,
        validation_state=val_state,
    )
    hmac_valid = _hmac.compare_digest(hmac_13, req.signature)
    if not hmac_valid:
        # Backward compatibility for legacy 7-field HMAC
        jwt_keys = get_jwt_keys()
        active_key = jwt_keys.get(JWT_ACTIVE_KEY)
        if active_key:
            secret_key = active_key.encode("utf-8")
            sig_payload = f"{req.sim_id}:{req.user_id}:{req.approver_email}:{req.approver_role}:{req.approval_decision}:{req.result_hash}:{req.approval_time}".encode("utf-8")
            legacy_expected = _hmac.new(secret_key, sig_payload, hashlib.sha256).hexdigest()
            hmac_valid = _hmac.compare_digest(legacy_expected, req.signature)

    # 2. Verify asymmetric Ed25519 signature if provided
    ed25519_valid = True
    authority_pubkey = report_service.get_authority_public_key_hex()
    if req.ed25519_signature:
        if req.public_key_hex and req.public_key_hex.lower() != authority_pubkey.lower():
            ed25519_valid = False
        else:
            ed25519_valid = report_service.verify_approval_ed25519(gov_payload, req.ed25519_signature, authority_pubkey)

    is_valid = hmac_valid and ed25519_valid
    return {
        "signature_valid": is_valid,
        "hmac_valid": hmac_valid,
        "ed25519_valid": ed25519_valid,
        "tamper_detected": not is_valid,
        "sim_id": req.sim_id,
        "approver_email": req.approver_email,
        "approver_role": req.approver_role,
        "approval_decision": req.approval_decision,
        "governance_13_bound": True,
        "authority_public_key": authority_pubkey,
    }


@router.post("/{report_id_or_token}/verify")
async def verify_report_endpoint(
    report_id_or_token: str,
    db: AsyncSession = Depends(get_db_dependency),
):
    """Cryptographically verify that the report signature matches the canonical artifact hash."""
    try:
        rep = await report_service.get_report_record(db, report_id_or_token)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Report '{report_id_or_token}' not found.")

    return report_service.verify_report_artifact_signature(rep)


@router.post("/{report_id_or_token}/share")
async def share_report_endpoint(
    report_id_or_token: str,
    user: UserContext = Depends(require_permission(Permission.REPORT_SHARE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Generate or retrieve genuine backend share token. Marks status as EXPORTED if APPROVED, strictly tenant-scoped."""
    try:
        rep = await report_service.get_report_record(
            db,
            report_id_or_token,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Report '{report_id_or_token}' not found.")

    rep.is_public = True
    if rep.status == "APPROVED":
        rep.status = "EXPORTED"
    await db.commit()
    await db.refresh(rep)

    return {
        "token": rep.token,
        "url": f"/report/{rep.token}",
        "status": rep.status,
        "provenance": rep.provenance,
        "message": "Report shared with verified backend token.",
    }



