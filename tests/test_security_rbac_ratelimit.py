"""
tests/test_security_rbac_ratelimit.py
======================================
SuspensionLab PRO — Enterprise Security, RBAC, Multi-Tenant Boundaries, and Rate Limiting Suite.

Verifies:
1. Auth rate limiting differentiation: strict limit on /login (15/min) vs high capacity on /me (300/min).
2. /auth/me returns complete role/permission profile including permissions list.
3. Least privilege: MEMBER and VIEWER lack 'setup:approve' and are rejected with HTTP 403.
4. Authorized engineering approval: ORG_ADMIN / ADMIN / OWNER generates HMAC signature and persists APPROVED.
5. Multi-tenant boundary isolation: Cross-tenant approval attempts are rejected with HTTP 403.
6. Idempotency: Re-approving an already APPROVED proposal or decision is safe and returns the existing signature.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.database.models.setup_proposal import SetupProposal
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from suspensionlab.backend.security.permissions import Permission


@pytest.fixture
async def enterprise_security_env():
    # Tenant A
    org_a_id = uuid.uuid4()
    team_a_id = uuid.uuid4()
    admin_a_id = uuid.uuid4()
    member_a_id = uuid.uuid4()
    viewer_a_id = uuid.uuid4()

    # Tenant B
    org_b_id = uuid.uuid4()
    team_b_id = uuid.uuid4()
    admin_b_id = uuid.uuid4()

    suffix = uuid.uuid4().hex[:6]
    admin_a_email = f"admin_a_{suffix}@williams.com"
    member_a_email = f"member_a_{suffix}@williams.com"
    viewer_a_email = f"viewer_a_{suffix}@williams.com"
    admin_b_email = f"admin_b_{suffix}@redbull.com"

    async with SessionLocal() as db:
        # Create Org A and Team A
        org_a = Organization(id=org_a_id, name="Williams F1", slug=f"williams-{suffix}", plan="ENTERPRISE")
        team_a = Team(id=team_a_id, name="Dynamics A", slug=f"dyn-a-{suffix}", organization_id=org_a_id, owner_id=admin_a_id, plan="ENTERPRISE")

        # Create Org B and Team B
        org_b = Organization(id=org_b_id, name="Red Bull Racing", slug=f"redbull-{suffix}", plan="ENTERPRISE")
        team_b = Team(id=team_b_id, name="Dynamics B", slug=f"dyn-b-{suffix}", organization_id=org_b_id, owner_id=admin_b_id, plan="ENTERPRISE")

        # Admin A (Authorized approver)
        user_admin_a = User(
            id=admin_a_id,
            email=admin_a_email,
            name="James Vowles",
            password_hash=hash_password("Pass123!"),
            organization_id=org_a_id,
            team_id=team_a_id,
            team_role="OWNER",
            org_role="ORG_ADMIN",
            is_admin=True,
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        # Member A (Standard engineer - NO setup:approve)
        user_member_a = User(
            id=member_a_id,
            email=member_a_email,
            name="Junior Dynamicist",
            password_hash=hash_password("Pass123!"),
            organization_id=org_a_id,
            team_id=team_a_id,
            team_role="Engineer",
            org_role="MEMBER",
            is_admin=False,
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        # Viewer A (Read-only - NO setup:approve)
        user_viewer_a = User(
            id=viewer_a_id,
            email=viewer_a_email,
            name="Guest Observer",
            password_hash=hash_password("Pass123!"),
            organization_id=org_a_id,
            team_id=team_a_id,
            team_role="Viewer",
            org_role="VIEWER",
            is_admin=False,
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        # Admin B (Admin of Tenant B)
        user_admin_b = User(
            id=admin_b_id,
            email=admin_b_email,
            name="Christian Horner",
            password_hash=hash_password("Pass123!"),
            organization_id=org_b_id,
            team_id=team_b_id,
            team_role="OWNER",
            org_role="ORG_ADMIN",
            is_admin=True,
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        # Vehicle Twin for Tenant A
        twin_a_id = uuid.uuid4()
        twin_a = VehicleTwin(
            id=twin_a_id,
            car_ref="FW46-01",
            setup_ref="SETUP-BASE",
            track_ref="Silverstone",
            user_id=member_a_id,
            team_id=team_a_id,
            base_params={"k_s": 35000.0, "c": 2200.0, "k_t": 220000.0, "m_s": 320.0},
        )

        # Setup Proposal in Tenant A
        proposal_a_id = uuid.uuid4()
        proposal_a = SetupProposal(
            id=proposal_a_id,
            twin_id=twin_a_id,
            user_id=member_a_id,
            team_id=team_a_id,
            problem="Excessive mid-corner body roll in Turn 9 Copse",
            focus="handling",
            baseline_params={"k_s": 35000.0, "c": 2200.0},
            tested_setups=24,
            feasible_found=8,
            recommended_params={"k_s": 38500.0, "c": 2450.0},
            param_changes=[{"parameter": "k_s", "current": 35000.0, "recommended": 38500.0, "change_pct": 10.0}],
            predicted_effects=[{"metric": "roll_angle_deg", "baseline": 2.8, "predicted": 2.1, "change_pct": -25.0, "improved": True}],
            confidence=94.5,
            status="PROPOSED",
        )

        # Engineering Decision in Tenant A
        decision_a_code = f"DEC-TEST-{suffix}"
        decision_a = EngineeringDecision(
            id=uuid.uuid4(),
            decision_id=decision_a_code,
            user_id=member_a_id,
            team_id=team_a_id,
            question="How to eliminate roll in Copse?",
            context={"vehicle": "FW46-01", "setup": "SETUP-BASE"},
            candidates=[{"name": "Setup A"}],
            selected_option={"name": "Setup A", "parameter_changes": []},
            status="RECOMMENDED",
            reason="Reduces roll without tyre overheating",
            tradeoffs=[{"benefit": "roll", "penalty": "kerb ride"}],
            risks=["Sub-optimal kerb compliance at Turn 15"],
            simulation_evidence={"run_id": "RUN-001"},
            telemetry_evidence={"session_id": "FP2"},
            validation_evidence={"rig": "PASS"},
            artifact_hashes={"decision_hash": f"hash_{suffix}"},
            author="Junior Dynamicist",
        )

        db.add_all([org_a, team_a, org_b, team_b, user_admin_a, user_member_a, user_viewer_a, user_admin_b, twin_a, proposal_a, decision_a])
        await db.commit()

    token_admin_a = create_access_token({
        "sub": str(admin_a_id), "email": admin_a_email,
        "organization_id": str(org_a_id), "team_id": str(team_a_id),
        "team_role": "OWNER", "plan": "ENTERPRISE",
    })
    token_member_a = create_access_token({
        "sub": str(member_a_id), "email": member_a_email,
        "organization_id": str(org_a_id), "team_id": str(team_a_id),
        "team_role": "Engineer", "plan": "ENTERPRISE",
    })
    token_viewer_a = create_access_token({
        "sub": str(viewer_a_id), "email": viewer_a_email,
        "organization_id": str(org_a_id), "team_id": str(team_a_id),
        "team_role": "Viewer", "plan": "ENTERPRISE",
    })
    token_admin_b = create_access_token({
        "sub": str(admin_b_id), "email": admin_b_email,
        "organization_id": str(org_b_id), "team_id": str(team_b_id),
        "team_role": "OWNER", "plan": "ENTERPRISE",
    })

    return {
        "org_a_id": str(org_a_id), "team_a_id": str(team_a_id),
        "admin_a_id": str(admin_a_id), "admin_a_email": admin_a_email, "token_admin_a": token_admin_a,
        "member_a_id": str(member_a_id), "member_a_email": member_a_email, "token_member_a": token_member_a,
        "viewer_a_id": str(viewer_a_id), "viewer_a_email": viewer_a_email, "token_viewer_a": token_viewer_a,
        "org_b_id": str(org_b_id), "team_b_id": str(team_b_id),
        "admin_b_id": str(admin_b_id), "admin_b_email": admin_b_email, "token_admin_b": token_admin_b,
        "twin_a_id": str(twin_a_id), "proposal_a_id": str(proposal_a_id),
        "decision_a_code": decision_a_code,
    }


@pytest.mark.asyncio
async def test_auth_me_returns_complete_rbac_profile(enterprise_security_env):
    """Verify /auth/me returns team_role, org_role, organization_id, is_admin, and permissions list."""
    ctx = enterprise_security_env
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Admin A profile
        res_admin = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ctx['token_admin_a']}"})
        assert res_admin.status_code == 200
        data_admin = res_admin.json()
        assert data_admin["email"] == ctx["admin_a_email"]
        assert data_admin["is_admin"] is True
        assert data_admin["org_role"] == "ORG_ADMIN"
        assert data_admin["team_role"] == "OWNER"
        assert data_admin["organization_id"] == ctx["org_a_id"]
        assert "permissions" in data_admin
        assert "setup:approve" in data_admin["permissions"]

        # 2. Member A profile (least privilege)
        res_member = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ctx['token_member_a']}"})
        assert res_member.status_code == 200
        data_member = res_member.json()
        assert data_member["email"] == ctx["member_a_email"]
        assert data_member["is_admin"] is False
        assert data_member["org_role"] == "MEMBER"
        assert "permissions" in data_member
        assert "setup:approve" not in data_member["permissions"]
        assert "vehicle:read" in data_member["permissions"]

        # 3. Viewer A profile
        res_viewer = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ctx['token_viewer_a']}"})
        assert res_viewer.status_code == 200
        data_viewer = res_viewer.json()
        assert "setup:approve" not in data_viewer["permissions"]


@pytest.mark.asyncio
async def test_session_rate_limit_allows_high_concurrency(enterprise_security_env):
    """Verify authenticated /auth/me and /auth/status easily sustain 25+ requests without 429."""
    ctx = enterprise_security_env
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {ctx['token_admin_a']}"}
        # Rapid session checks
        for _ in range(25):
            res = await client.get("/api/v1/auth/me", headers=headers)
            assert res.status_code == 200, f"Unexpected status {res.status_code}"

        # Rapid session status checks
        for _ in range(10):
            res = await client.get("/api/v1/auth/status", headers=headers)
            assert res.status_code == 200


@pytest.mark.asyncio
async def test_proposal_approval_rbac_least_privilege(enterprise_security_env):
    """
    Verify:
    1. Member user without 'setup:approve' gets HTTP 403 Forbidden.
    2. Viewer user without 'setup:approve' gets HTTP 403 Forbidden.
    3. Admin user with 'setup:approve' gets HTTP 200 with cryptographic signature.
    """
    ctx = enterprise_security_env
    transport = ASGITransport(app=app)
    proposal_url = f"/api/v1/twin/proposals/{ctx['proposal_a_id']}/status?status=APPROVED"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Member attempts to approve -> 403
        res_member = await client.put(proposal_url, headers={"Authorization": f"Bearer {ctx['token_member_a']}"})
        assert res_member.status_code == 403
        assert "permission" in res_member.text.lower() or "forbidden" in res_member.text.lower()

        # 2. Viewer attempts to approve -> 403
        res_viewer = await client.put(proposal_url, headers={"Authorization": f"Bearer {ctx['token_viewer_a']}"})
        assert res_viewer.status_code == 403

        # 3. Admin approves -> 200
        res_admin = await client.put(proposal_url, headers={"Authorization": f"Bearer {ctx['token_admin_a']}"})
        assert res_admin.status_code == 200
        data = res_admin.json()
        assert data["status"] == "APPROVED"
        assert data["approval_signature"] is not None
        assert len(data["approval_signature"]) == 64  # HMAC-SHA256 hex string
        assert data["proposal_hash"] is not None
        assert data["approved_by"] == ctx["admin_a_id"]


@pytest.mark.asyncio
async def test_proposal_approval_cross_tenant_isolation(enterprise_security_env):
    """Verify Admin of Tenant B cannot approve a proposal belonging to Tenant A (HTTP 403)."""
    ctx = enterprise_security_env
    transport = ASGITransport(app=app)
    proposal_url = f"/api/v1/twin/proposals/{ctx['proposal_a_id']}/status?status=APPROVED"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Admin B has 'setup:approve' in Org B, but is cross-tenant for Proposal A
        res_cross = await client.put(proposal_url, headers={"Authorization": f"Bearer {ctx['token_admin_b']}"})
        assert res_cross.status_code == 403
        assert "cross-tenant" in res_cross.json()["detail"].lower()


@pytest.mark.asyncio
async def test_proposal_approval_idempotency(enterprise_security_env):
    """Verify re-approving an already APPROVED proposal returns HTTP 200 and existing signature."""
    ctx = enterprise_security_env
    transport = ASGITransport(app=app)
    proposal_url = f"/api/v1/twin/proposals/{ctx['proposal_a_id']}/status?status=APPROVED"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First approval
        res1 = await client.put(proposal_url, headers={"Authorization": f"Bearer {ctx['token_admin_a']}"})
        assert res1.status_code == 200
        sig1 = res1.json()["approval_signature"]

        # Second approval (idempotent replay)
        res2 = await client.put(proposal_url, headers={"Authorization": f"Bearer {ctx['token_admin_a']}"})
        assert res2.status_code == 200
        assert res2.json()["status"] == "APPROVED"
        assert res2.json()["approval_signature"] == sig1
        assert res2.json().get("idempotent") is True


@pytest.mark.asyncio
async def test_decision_approval_rbac_cross_tenant_and_idempotency(enterprise_security_env):
    """
    Verify /decisions/{id}/approve:
    1. Member A rejected with 403.
    2. Tenant B Admin rejected with 403 (cross-tenant).
    3. Admin A approves successfully (200, signed).
    4. Admin A re-approves idempotently (200, same signature).
    """
    ctx = enterprise_security_env
    transport = ASGITransport(app=app)
    approve_url = f"/api/v1/decisions/{ctx['decision_a_code']}/approve"
    payload = {
        "approver_name": "James Vowles",
        "approver_role": "Chief Race Engineer",
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Member A rejected (no setup:approve)
        res_member = await client.post(approve_url, json=payload, headers={"Authorization": f"Bearer {ctx['token_member_a']}"})
        assert res_member.status_code == 403

        # 2. Admin B rejected (cross-tenant)
        res_cross = await client.post(approve_url, json=payload, headers={"Authorization": f"Bearer {ctx['token_admin_b']}"})
        assert res_cross.status_code == 403
        assert "cross-tenant" in res_cross.json()["detail"].lower()

        # 3. Admin A approves
        res_admin = await client.post(approve_url, json=payload, headers={"Authorization": f"Bearer {ctx['token_admin_a']}"})
        assert res_admin.status_code == 200
        dec_data = res_admin.json()
        assert dec_data["status"] == "APPROVED"
        sig = dec_data["approval_signature"]
        assert sig is not None

        # 4. Admin A re-approves idempotently
        res_reapprove = await client.post(approve_url, json=payload, headers={"Authorization": f"Bearer {ctx['token_admin_a']}"})
        assert res_reapprove.status_code == 200
        assert res_reapprove.json()["status"] == "APPROVED"
        assert res_reapprove.json()["approval_signature"] == sig


@pytest.mark.asyncio
async def test_login_rate_limiting_enforcement():
    """Verify strict 15/minute rate limiting on /auth/login."""
    from suspensionlab.backend.security.rate_limit import _fallback_store
    _fallback_store.clear()

    transport = ASGITransport(app=app)
    bad_login_payload = {
        "email": f"brute_force_{uuid.uuid4().hex[:6]}@domain.com",
        "password": "WrongPassword123!",
    }

    # Use a distinct client IP header to isolate test run from other tests
    headers = {"X-Forwarded-For": f"198.51.100.{uuid.uuid4().int % 250 + 1}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First 15 attempts should be evaluated (returning 401 Unauthorized)
        for i in range(15):
            res = await client.post("/api/v1/auth/login", json=bad_login_payload, headers=headers)
            assert res.status_code == 401, f"Attempt {i+1} expected 401, got {res.status_code}"

        # 16th attempt should be blocked by RateLimiter with 429
        res_blocked = await client.post("/api/v1/auth/login", json=bad_login_payload, headers=headers)
        assert res_blocked.status_code == 429, f"Expected 429 on 16th attempt, got {res_blocked.status_code}"
        assert "rate limit exceeded" in res_blocked.text.lower()

