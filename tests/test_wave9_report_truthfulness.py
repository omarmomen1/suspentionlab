"""
tests/test_wave9_report_truthfulness.py
=======================================
Wave 9 — Reports: no proposed report may look approved.

Pins:
1. A PROPOSED decision report never prints "Approved by" and never carries a signature.
2. A decision report without a persisted simulation run is refused with 422.
3. Missing vehicle/setup/track/tire/telemetry references render "NOT SET", never an invented string.
4. The auto-computed default-vehicle baseline is labeled on screen (hydrate) and in the PDF.
"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password


@pytest.fixture
async def report_env():
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()
    tag = uuid.uuid4().hex[:6].upper()
    email = f"wave9_chief_{tag.lower()}@f1team.com"

    async with SessionLocal() as db:
        org = Organization(id=org_id, name="Wave9 Racing", slug=f"wave9-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        team = Team(
            id=team_id,
            name="Vehicle Dynamics",
            slug=f"wave9-vd-{uuid.uuid4().hex[:6]}",
            organization_id=org_id,
            owner_id=user_id,
            plan="ENTERPRISE",
        )
        user = User(
            id=user_id,
            email=email,
            name="Pat Fry",
            password_hash=hash_password("ChiefPass123!"),
            organization_id=org_id,
            team_id=team_id,
            team_role="Admin",
            org_role="MEMBER",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        # Run with every reference filled in.
        full_id = uuid.uuid4()
        full_run = SimulationRun(
            id=full_id,
            seq=int(uuid.uuid4().int % 1000000) + 900000,
            label=f"RUN-W9FULL-{tag}",
            user_id=user_id,
            team_id=team_id,
            simulation_type="quarter_car",
            vehicle_ref="FW46-01",
            setup_ref="SETUP-A",
            track_ref="SILVERSTONE-GP",
            tire_ref="TIRE-SOFT-C3",
            telemetry_ref="TELEM-SILVERSTONE-Q3",
            params={"m_s": 250.0, "k_s": 30000.0},
            result={"rms_body_accel_wk": 0.35},
            model_validity={"status": "VALIDATED", "score": 0.925},
            software_version="2.0.0",
            physics_version="2.0.0",
            solver_version="scipy-1.11.0",
            params_hash="w9_params_full",
            result_hash="w9_result_full",
            created_at=datetime.now(timezone.utc),
        )

        # Run with no references at all: every missing value must render NOT SET.
        bare_id = uuid.uuid4()
        bare_run = SimulationRun(
            id=bare_id,
            seq=int(uuid.uuid4().int % 1000000) + 800000,
            label=f"RUN-W9BARE-{tag}",
            user_id=user_id,
            team_id=team_id,
            simulation_type="quarter_car",
            params={"m_s": 250.0, "k_s": 30000.0},
            result={"rms_body_accel_wk": 0.35},
            model_validity={"status": "VALIDATED", "score": 0.925},
            software_version="2.0.0",
            physics_version="2.0.0",
            solver_version="scipy-1.11.0",
            params_hash="w9_params_bare",
            result_hash="w9_result_bare",
            created_at=datetime.now(timezone.utc),
        )

        # The auto-computed default-vehicle baseline.
        baseline_id = uuid.uuid4()
        baseline_run = SimulationRun(
            id=baseline_id,
            seq=int(uuid.uuid4().int % 1000000) + 700000,
            label=f"RUN-W9BASE-{tag}",
            user_id=user_id,
            team_id=team_id,
            simulation_type="quarter_car",
            title="Baseline Quarter-Car Reference Run",
            vehicle_ref="VEH-DEFAULT",
            setup_ref="BASELINE-QC",
            tire_ref="TIRE-DEFAULT",
            track_ref="ISO8608-B",
            telemetry_ref="NONE",
            params={"m_s": 320.0, "k_s": 35000.0},
            result={"rms_body_accel_wk": 0.4},
            model_validity={"status": "UNVALIDATED", "score": None, "is_default_vehicle_baseline": True},
            software_version="2.0.0",
            physics_version="2.0.0",
            solver_version="scipy-1.11.0",
            params_hash="w9_params_base",
            result_hash="w9_result_base",
            created_at=datetime.now(timezone.utc),
        )

        db.add_all([org, team, user, full_run, bare_run, baseline_run])
        await db.commit()

    token = create_access_token(
        {
            "sub": str(user_id),
            "email": email,
            "organization_id": str(org_id),
            "team_id": str(team_id),
            "team_role": "Admin",
            "plan": "ENTERPRISE",
        }
    )
    return {
        "token": token,
        "user_id": str(user_id),
        "full_label": f"RUN-W9FULL-{tag}",
        "bare_label": f"RUN-W9BARE-{tag}",
        "baseline_id": str(baseline_id),
    }


def _headers(env):
    return {"Authorization": f"Bearer {env['token']}"}


@pytest.mark.asyncio
async def test_decision_report_without_run_is_422(report_env):
    """No persisted run means no decision report: 422, never an invented one."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/reports/decision_report",
            json={
                "approval": {
                    "decision": "APPROVED_FOR_TEST_TRACK",
                    "comment": "Trying to sign nothing.",
                }
            },
            headers=_headers(report_env),
        )
    assert resp.status_code == 422, resp.text
    assert "report requires a persisted simulation run" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_proposed_pdf_has_no_approved_by_and_no_signatures(report_env):
    """A PROPOSED report cannot be mistaken for a signed approval."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/reports/decision_report",
            json={
                "simulation_id": report_env["full_label"],
                "approval": {"decision": "PROPOSED", "comment": "Draft for review."},
            },
            headers=_headers(report_env),
        )
    assert resp.status_code == 200, resp.text
    html = resp.text
    assert "PROPOSED - AWAITING CHIEF ENGINEER DECISION" in html
    assert "Approved by" not in html
    assert "Cryptographic Approval Signature" not in html
    assert "Asymmetric Non-Repudiation Signature" not in html
    assert "X-Approval-Signature" not in resp.headers
    assert "X-Ed25519-Signature" not in resp.headers
    assert resp.headers.get("X-Approval-State") == "PROPOSED"


@pytest.mark.asyncio
async def test_missing_refs_render_not_set(report_env):
    """Every missing reference renders NOT SET. No invented vehicle, track or tire string."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/reports/decision_report",
            json={
                "simulation_id": report_env["bare_label"],
                "approval": {"decision": "PROPOSED", "comment": "Bare run."},
            },
            headers=_headers(report_env),
        )
    assert resp.status_code == 200, resp.text
    html = resp.text
    assert "NOT SET" in html
    for invented in (
        "CAR-07",
        "REV-48",
        "SPA-FRANCORCHAMPS 2026",
        "TIRE-MF52-COMPOUND-SOFT",
        "TELEMETRY-SYNC-SPA-Q2",
        "AERO-POLAR-v2.3",
    ):
        assert invented not in html, f"invented reference {invented} leaked into the report"


@pytest.mark.asyncio
async def test_baseline_report_shows_default_vehicle_banner(report_env):
    """The auto-computed default-vehicle baseline is labeled in the PDF and in the hydrated payload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pdf = await client.post(
            "/reports/decision_report",
            json={
                "simulation_id": report_env["baseline_id"],
                "approval": {"decision": "PROPOSED", "comment": "Baseline."},
            },
            headers=_headers(report_env),
        )
        assert pdf.status_code == 200, pdf.text
        assert "Reference baseline on the default vehicle - not your car." in pdf.text

        hydrated = await client.get(
            f"/reports/hydrate/{report_env['baseline_id']}",
            headers=_headers(report_env),
        )
        assert hydrated.status_code == 200, hydrated.text
        assert hydrated.json().get("is_default_vehicle_baseline") is True

        normal = await client.get(
            f"/reports/hydrate/{report_env['full_label']}",
            headers=_headers(report_env),
        )
        assert normal.status_code == 200, normal.text
        assert normal.json().get("is_default_vehicle_baseline") is False
