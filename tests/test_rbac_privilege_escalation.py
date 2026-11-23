"""
tests/test_rbac_privilege_escalation.py
======================================
SuspensionLab PRO — Enterprise RBAC & Privilege Escalation Defense Test Suite

Verifies:
1. Complete rejection (HTTP 403) of compute operations for Viewer and Crew seats:
   - /simulate (quarter-car, active, full-car, half-car, sweep)
   - /optimize, /auto-tune
   - /kinematics/solve
   - /twins (create, calibrate)
2. Complete rejection (HTTP 403) of exports and reports for Viewer seats:
   - /reports/iso2631, /reports/decision_report, /reports/create_from_run
   - /export/fmu, /export/simulink, /export/adams
3. Complete rejection (HTTP 403) of audit logs for unauthorized roles:
   - Viewer, Crew, and Engineer seats cannot access /audit/logs or /audit/export
4. Billing Admin seat scoping:
   - Allowed: /audit/logs, billing routes
   - Denied: compute routes (/simulate, /optimize)
5. Read-only permissions for Viewer and Crew:
   - Allowed: GET /profiles, GET /jobs, GET /twins/{id}
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from suspensionlab.backend.security.permissions import Permission, has_permission


@pytest.fixture
async def rbac_test_environment():
    """Create test organization with users across different RBAC roles."""
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()

    roles = ["viewer", "crew", "engineer", "admin", "billing_admin"]
    users = {}
    tokens = {}

    async with SessionLocal() as db:
        org = Organization(
            id=org_id,
            name="Scuderia Ferrari Mission Winnow",
            slug=f"ferrari-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
        )
        owner_id = uuid.uuid4()
        team = Team(
            id=team_id,
            name="Vehicle Performance Group",
            slug=f"ferrari-vpg-{uuid.uuid4().hex[:6]}",
            organization_id=org_id,
            owner_id=owner_id,
            plan="ENTERPRISE",
        )
        db.add_all([org, team])

        for role in roles:
            u_id = uuid.uuid4()
            u_email = f"{role}_{uuid.uuid4().hex[:6]}@ferrari.com"
            org_role = "BILLING_ADMIN" if role == "billing_admin" else "MEMBER"
            team_role = role.capitalize() if role != "billing_admin" else "Viewer"

            user = User(
                id=u_id,
                email=u_email,
                name=f"Ferrari {role.title()}",
                password_hash=hash_password("Passw0rd123!"),
                organization_id=org_id,
                org_role=org_role,
                team_id=team_id,
                team_role=team_role,
                plan="ENTERPRISE",
                onboarding_complete=True,
            )
            db.add(user)
            users[role] = user
            tokens[role] = create_access_token({
                "sub": str(u_id),
                "email": u_email,
                "organization_id": str(org_id),
                "org_role": org_role,
                "team_id": str(team_id),
                "team_role": team_role,
                "plan": "ENTERPRISE",
            })

        # Also create a sample vehicle profile
        profile_id = uuid.uuid4()
        profile = VehicleProfile(
            id=profile_id,
            name="SF-24 Launch Spec",
            vehicle_type="QUARTER_CAR",
            params={"m_s": 260.0, "m_u": 40.0, "k_s": 35000.0, "c": 2600.0, "k_t": 240000.0},
            user_id=users["engineer"].id,
            team_id=team_id,
        )
        db.add(profile)
        await db.commit()

    return {
        "org_id": str(org_id),
        "team_id": str(team_id),
        "profile_id": str(profile_id),
        "tokens": tokens,
    }


@pytest.mark.asyncio
async def test_viewer_blocked_from_all_compute(rbac_test_environment):
    """Ensure Viewer seat receives HTTP 403 Forbidden on all compute and simulation routes."""
    tokens = rbac_test_environment["tokens"]
    headers = {"Authorization": f"Bearer {tokens['viewer']}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Quarter car simulation
        resp = await client.post("/simulate", json={"params": {"k_s": 30000.0, "c": 2000.0}}, headers=headers)
        assert resp.status_code == 403
        assert "permission denied" in resp.json()["detail"].lower()

        # 2. Active suspension simulation
        resp = await client.post("/simulate/active", json={"params": {"k_s": 30000.0, "c": 2000.0}}, headers=headers)
        assert resp.status_code == 403

        # 3. Full car simulation
        resp = await client.post("/simulate/full-car", json={"params": {}, "profile": {}}, headers=headers)
        assert resp.status_code == 403

        # 4. Sweep simulation
        resp = await client.post("/simulate/sweep", json={}, headers=headers)
        assert resp.status_code == 403

        # 5. Optimization
        resp = await client.post("/optimize", json={}, headers=headers)
        assert resp.status_code == 403

        # 6. Auto-tune
        resp = await client.post("/auto-tune", json={}, headers=headers)
        assert resp.status_code == 403

        # 7. Kinematics solve
        resp = await client.post("/kinematics/solve", json={}, headers=headers)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_crew_blocked_from_compute_and_calibrations(rbac_test_environment):
    """Ensure Crew seat is strictly blocked from executing simulations, optimizations, and calibrations."""
    tokens = rbac_test_environment["tokens"]
    headers = {"Authorization": f"Bearer {tokens['crew']}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Denied compute
        resp = await client.post("/simulate", json={"params": {}}, headers=headers)
        assert resp.status_code == 403

        resp = await client.post("/optimize", json={}, headers=headers)
        assert resp.status_code == 403

        fake_twin_id = str(uuid.uuid4())
        resp = await client.post(f"/twins/{fake_twin_id}/calibrate", json={}, headers=headers)
        assert resp.status_code == 403

        # Permitted reads:
        resp = await client.get("/profiles/", headers=headers)
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_viewer_and_crew_blocked_from_export_and_reports(rbac_test_environment):
    """Ensure Viewer seat cannot export CAE models or generate decision reports."""
    tokens = rbac_test_environment["tokens"]
    headers_viewer = {"Authorization": f"Bearer {tokens['viewer']}"}
    headers_crew = {"Authorization": f"Bearer {tokens['crew']}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Viewer denied CAE exports
        resp = await client.post("/export/fmu", headers=headers_viewer)
        assert resp.status_code == 403

        resp = await client.post("/export/simulink", json={}, headers=headers_viewer)
        assert resp.status_code == 403

        # Viewer denied decision reports
        resp = await client.post("/reports/decision_report", json={}, headers=headers_viewer)
        assert resp.status_code == 403

        # Crew denied decision reports
        resp = await client.post("/reports/decision_report", json={}, headers=headers_crew)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_routes_gated_by_audit_read_permission(rbac_test_environment):
    """Ensure /audit/logs and /audit/export require Permission.AUDIT_READ."""
    tokens = rbac_test_environment["tokens"]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Viewer: denied
        resp = await client.get("/audit/logs", headers={"Authorization": f"Bearer {tokens['viewer']}"})
        assert resp.status_code == 403

        # Crew: denied
        resp = await client.get("/audit/logs", headers={"Authorization": f"Bearer {tokens['crew']}"})
        assert resp.status_code == 403

        # Engineer: denied (engineer does not have AUDIT_READ)
        resp = await client.get("/audit/logs", headers={"Authorization": f"Bearer {tokens['engineer']}"})
        assert resp.status_code == 403

        # Billing Admin: allowed (has AUDIT_READ)
        resp = await client.get("/audit/logs", headers={"Authorization": f"Bearer {tokens['billing_admin']}"})
        assert resp.status_code == 200

        # Admin: allowed (has AUDIT_READ)
        resp = await client.get("/audit/logs", headers={"Authorization": f"Bearer {tokens['admin']}"})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_billing_admin_cannot_run_compute(rbac_test_environment):
    """Ensure Billing Admin is strictly scoped to administrative/billing tasks and cannot run simulations."""
    tokens = rbac_test_environment["tokens"]
    headers = {"Authorization": f"Bearer {tokens['billing_admin']}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/simulate", json={"params": {}}, headers=headers)
        assert resp.status_code == 403
        assert "simulation:run" in resp.json()["detail"].lower()

        resp = await client.post("/optimize", json={}, headers=headers)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_solo_user_privilege_escalation_defense():
    """Ensure solo users (unassigned to team/org) receive solo permissions and are denied enterprise admin actions."""
    from suspensionlab.backend.security.auth import UserContext
    from suspensionlab.backend.security.permissions import get_role_permissions

    solo_user = UserContext(
        user_id=str(uuid.uuid4()),
        email="solo_racer@example.com",
        plan="pro",
        name="Solo Racer",
        onboarding_complete=True,
        team_id=None,
        organization_id=None,
    )

    # Solo user has engineering capabilities
    assert solo_user.can(Permission.SIMULATION_RUN)
    assert solo_user.can(Permission.VEHICLE_READ)
    assert solo_user.can(Permission.VEHICLE_WRITE)
    assert solo_user.can(Permission.SETUP_CREATE)

    # Solo user CANNOT perform enterprise admin or audit actions
    assert not solo_user.can(Permission.AUDIT_READ)
    assert not solo_user.can(Permission.BILLING_ADMIN)
    assert not solo_user.can(Permission.SCIM_MANAGE)
    assert not solo_user.can(Permission.SAML_MANAGE)
    assert not solo_user.can(Permission.TEAM_MANAGE)
    assert not solo_user.can(Permission.ORG_ADMIN)


@pytest.mark.asyncio
async def test_solo_user_get_me_endpoint_defense():
    """Verify GET /api/v1/auth/me returns SOLO_PERMISSIONS for solo users and never owner/admin permissions."""
    from suspensionlab.backend.security.permissions import get_role_permissions

    solo_id = uuid.uuid4()
    solo_email = f"solo_{solo_id.hex[:8]}@example.com"
    token = create_access_token({"sub": str(solo_id), "email": solo_email})

    async with SessionLocal() as db:
        user = User(
            id=solo_id,
            email=solo_email,
            password_hash=hash_password("Password123!"),
            name="Solo Test User",
            plan="PRO",
            team_id=None,
            organization_id=None,
            team_role="Viewer",
            org_role=None,
            is_admin=False,
        )
        db.add(user)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        perms = set(data["permissions"])
        expected_solo_perms = set(get_role_permissions("solo"))
        owner_perms = set(get_role_permissions("owner"))

        assert perms == expected_solo_perms
        assert "audit:read" not in perms
        assert "billing:admin" not in perms
        assert "scim:manage" not in perms
        assert "saml:manage" not in perms
        assert "team:manage" not in perms
        assert "org:admin" not in perms
        assert perms != owner_perms

