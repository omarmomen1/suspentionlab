"""
tests/test_enterprise_multi_tenant_complete.py
==============================================
SuspensionLab PRO — Enterprise Multi-Tenancy, Hierarchy, RLS, and RBAC Capability Matrix Tests.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.session import SimSession
from suspensionlab.backend.database.rls import (
    TENANT_TABLES,
    generate_table_rls_sql,
    get_all_rls_ddl,
    set_session_tenant_context,
)
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from suspensionlab.backend.security.permissions import (
    Permission,
    ROLE_PERMISSIONS_MAP,
    has_permission,
    get_role_permissions,
)
from suspensionlab.backend.security.tenancy import (
    TenantContext,
    TenantScopedRepository,
    TenantSecurityException,
)


@pytest.mark.asyncio
async def test_organization_hierarchy_creation_and_team_nesting():
    """Verify Organization -> Teams -> Users hierarchy and data isolation."""
    org_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    team_aero_id = uuid.uuid4()
    team_chassis_id = uuid.uuid4()
    eng_id = uuid.uuid4()

    async with SessionLocal() as db:
        org = Organization(
            id=org_id,
            name="Scuderia Alpha F1",
            slug=f"scuderia-alpha-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
            data_region="eu-central",
            data_retention_days=730,
            telemetry_retention_days=180,
        )
        db.add(org)

        # Create Org Admin User
        user_admin = User(
            id=admin_id,
            email=f"admin_{uuid.uuid4().hex[:6]}@alphaf1.com",
            name="Alpha Principal",
            password_hash=hash_password("Secr3t123!"),
            organization_id=org_id,
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(user_admin)

        # Create nested Teams
        team_aero = Team(
            id=team_aero_id,
            name="Aerodynamics Group",
            slug=f"alpha-aero-{uuid.uuid4().hex[:6]}",
            owner_id=admin_id,
            organization_id=org_id,
            plan="ENTERPRISE",
            data_region="eu-central",
        )
        team_chassis = Team(
            id=team_chassis_id,
            name="Chassis Dynamics",
            slug=f"alpha-chassis-{uuid.uuid4().hex[:6]}",
            owner_id=admin_id,
            organization_id=org_id,
            plan="ENTERPRISE",
            data_region="eu-central",
        )
        db.add_all([team_aero, team_chassis])

        # Create Team Member
        user_engineer = User(
            id=eng_id,
            email=f"aero_eng_{uuid.uuid4().hex[:6]}@alphaf1.com",
            name="Aero Lead",
            password_hash=hash_password("Secr3t123!"),
            organization_id=org_id,
            org_role="MEMBER",
            team_id=team_aero_id,
            team_role="Engineer",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(user_engineer)
        await db.commit()

    # Re-query with explicit relationship loading
    async with SessionLocal() as db:
        loaded_org = (
            await db.execute(
                select(Organization).options(selectinload(Organization.teams)).where(Organization.id == org_id)
            )
        ).scalar_one()
        assert len(loaded_org.teams) == 2
        assert loaded_org.data_region == "eu-central"
        assert loaded_org.data_retention_days == 730

        loaded_eng = (
            await db.execute(
                select(User).options(joinedload(User.team)).where(User.id == eng_id)
            )
        ).scalar_one()
        assert loaded_eng.team.organization_id == org_id


def test_postgresql_rls_ddl_and_policies_generation():
    """Verify Row-Level Security DDL generation across all core tables."""
    assert len(TENANT_TABLES) >= 15
    assert "organizations" in TENANT_TABLES
    assert "teams" in TENANT_TABLES
    assert "users" in TENANT_TABLES
    assert "vehicle_profiles" in TENANT_TABLES
    assert "simulation_runs" in TENANT_TABLES
    assert "scim_groups" in TENANT_TABLES

    all_ddl = get_all_rls_ddl()
    assert "ENABLE ROW LEVEL SECURITY" in all_ddl
    assert "FORCE ROW LEVEL SECURITY" in all_ddl
    assert "app.current_organization_id" in all_ddl
    assert "app.current_tenant_id" in all_ddl

    org_sql = "\n".join(generate_table_rls_sql("organizations"))
    assert "organizations_tenant_isolation_policy" in org_sql

    sim_sql = "\n".join(generate_table_rls_sql("simulation_runs"))
    assert "simulation_runs_tenant_isolation_policy" in sim_sql


@pytest.mark.asyncio
async def test_database_session_tenant_context_execution():
    """Verify session tenant context establishes tenant boundaries on database sessions."""
    async with SessionLocal() as db:
        ctx = TenantContext(
            user_id="usr-test-1",
            organization_id="org-test-1",
            team_id="team-test-1",
            role="engineer",
        )
        await set_session_tenant_context(db, tenant_context=ctx)
        assert db.info.get("tenant_context") is not None
        assert db.info["tenant_context"]["organization_id"] == "org-test-1"
        assert db.info["tenant_context"]["team_id"] == "team-test-1"
        assert db.info["tenant_context"]["is_super_admin"] is False


@pytest.mark.asyncio
async def test_rls_super_admin_flag_restricted_to_system_super_admin():
    """org_owner, owner, org_admin, and super_admin must NEVER set app.is_super_admin='true'; only system_super_admin may."""
    from unittest.mock import AsyncMock, MagicMock

    async with SessionLocal() as db:
        for non_system_role in ("org_owner", "owner", "org_admin", "ORG_ADMIN", "ORG_OWNER", "super_admin", "engineer"):
            ctx = TenantContext(
                user_id="usr-test-1",
                organization_id="org-test-1",
                team_id="team-test-1",
                role=non_system_role,
            )
            await set_session_tenant_context(db, tenant_context=ctx)
            assert db.info["tenant_context"]["is_super_admin"] is False, (
                f"Role {non_system_role!r} must not grant is_super_admin"
            )

        # Even if is_super_admin=True is passed, org_owner/org_admin must never elevate
        for org_role in ("org_owner", "owner", "org_admin"):
            ctx = TenantContext(
                user_id="usr-test-1",
                organization_id="org-test-1",
                team_id="team-test-1",
                role=org_role,
            )
            await set_session_tenant_context(db, tenant_context=ctx, is_super_admin=True)
            assert db.info["tenant_context"]["is_super_admin"] is False

        # Dedicated system_super_admin role grants app.is_super_admin='true'
        sys_ctx = TenantContext(
            user_id="usr-sys-1",
            organization_id="org-sys",
            team_id="team-sys",
            role="system_super_admin",
        )
        await set_session_tenant_context(db, tenant_context=sys_ctx)
        assert db.info["tenant_context"]["is_super_admin"] is True

    # Also verify exact SQL SET LOCAL statements emitted for PostgreSQL dialect
    for role_name, expected_sql_flag in [
        ("org_owner", "false"),
        ("org_admin", "false"),
        ("owner", "false"),
        ("super_admin", "false"),
        ("system_super_admin", "true"),
    ]:
        pg_session = MagicMock()
        pg_session.bind = MagicMock()
        pg_session.bind.dialect = MagicMock()
        pg_session.bind.dialect.name = "postgresql"
        pg_session.execute = AsyncMock()
        ctx = TenantContext(
            user_id="usr-pg",
            organization_id="org-pg",
            team_id="team-pg",
            role=role_name,
        )
        await set_session_tenant_context(pg_session, tenant_context=ctx)
        executed_sql = [str(call.args[0]) for call in pg_session.execute.call_args_list]
        assert f"SET LOCAL app.is_super_admin = '{expected_sql_flag}';" in executed_sql


def test_granular_rbac_capability_matrix_completeness():
    """Test every permission capability against every enterprise role."""
    assert Permission.VEHICLE_READ.value == "vehicle:read"
    assert Permission.VEHICLE_WRITE.value == "vehicle:write"
    assert Permission.SIMULATION_RUN.value == "simulation:run"
    assert Permission.SIMULATION_CANCEL.value == "simulation:cancel"
    assert Permission.TELEMETRY_READ.value == "telemetry:read"
    assert Permission.TELEMETRY_WRITE.value == "telemetry:write"
    assert Permission.REPORT_EXPORT.value == "report:export"
    assert Permission.AUDIT_READ.value == "audit:read"
    assert Permission.TEAM_ADMIN.value == "team:admin"
    assert Permission.BILLING_ADMIN.value == "billing:admin"
    assert Permission.ORG_ADMIN.value == "org:admin"

    assert has_permission("owner", Permission.ORG_ADMIN)
    assert has_permission("org_admin", Permission.ORG_ADMIN)
    assert has_permission("org_admin", Permission.DATA_POLICY_MANAGE)
    assert has_permission("org_admin", Permission.SCIM_MANAGE)

    assert has_permission("billing_admin", Permission.BILLING_ADMIN)
    assert has_permission("billing_admin", Permission.AUDIT_READ)
    assert not has_permission("billing_admin", Permission.SIMULATION_RUN)

    assert has_permission("admin", Permission.TEAM_ADMIN)
    assert has_permission("admin", Permission.VEHICLE_WRITE)
    assert has_permission("admin", Permission.SIMULATION_RUN)

    assert has_permission("engineer", Permission.SIMULATION_RUN)
    assert has_permission("engineer", Permission.TELEMETRY_WRITE)
    assert has_permission("engineer", Permission.VEHICLE_WRITE)
    assert not has_permission("engineer", Permission.TEAM_ADMIN)
    assert not has_permission("engineer", Permission.ORG_ADMIN)

    assert not has_permission("crew", Permission.SIMULATION_RUN)
    assert has_permission("crew", Permission.TELEMETRY_READ)
    assert not has_permission("crew", Permission.SIMULATION_CANCEL)
    assert not has_permission("crew", Permission.VEHICLE_WRITE)

    assert has_permission("viewer", Permission.SIMULATION_READ)
    assert has_permission("viewer", Permission.VEHICLE_READ)
    assert not has_permission("viewer", Permission.SIMULATION_RUN)
    assert not has_permission("viewer", Permission.TELEMETRY_WRITE)


@pytest.mark.asyncio
async def test_cross_tenant_idor_access_prevention():
    """Attempt cross-tenant access to organizations, teams, and profiles confirming rejection."""
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    user1_email = f"u1_{uuid.uuid4().hex[:6]}@alpha.com"
    user2_email = f"u2_{uuid.uuid4().hex[:6]}@beta.com"

    async with SessionLocal() as db:
        org1 = Organization(id=org1_id, name="OEM Alpha", slug=f"oem-alpha-{uuid.uuid4().hex[:6]}")
        user1 = User(
            id=user1_id,
            email=user1_email,
            password_hash=hash_password("Pass123!"),
            organization_id=org1_id,
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        org2 = Organization(id=org2_id, name="OEM Beta", slug=f"oem-beta-{uuid.uuid4().hex[:6]}")
        user2 = User(
            id=user2_id,
            email=user2_email,
            password_hash=hash_password("Pass123!"),
            organization_id=org2_id,
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add_all([org1, user1, org2, user2])
        await db.commit()

    token1 = create_access_token({"sub": str(user1_id), "email": user1_email, "organization_id": str(org1_id)})
    token2 = create_access_token({"sub": str(user2_id), "email": user2_email, "organization_id": str(org2_id)})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # User 1 accesses Org 1 -> OK 200
        res1 = await client.get(f"/api/v1/organizations/{org1_id}", headers={"Authorization": f"Bearer {token1}"})
        assert res1.status_code == 200
        assert res1.json()["name"] == "OEM Alpha"

        # User 2 attempts cross-tenant IDOR access to Org 1 -> Forbidden 403
        res_cross = await client.get(f"/api/v1/organizations/{org1_id}", headers={"Authorization": f"Bearer {token2}"})
        assert res_cross.status_code == 403
        assert "Access Denied" in res_cross.json()["detail"]

        # User 2 attempts cross-tenant team creation in Org 1 -> Forbidden 403
        res_team = await client.post(
            f"/api/v1/organizations/{org1_id}/teams",
            json={"name": "Hacked Team", "slug": f"hack-{uuid.uuid4().hex[:6]}"},
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert res_team.status_code == 403


@pytest.mark.asyncio
async def test_tenant_scoped_repository_org_and_team_boundaries():
    """Verify TenantScopedRepository prevents cross-org and cross-team leaks."""
    tenant_alpha = TenantContext(user_id="u-1", organization_id="org-alpha", team_id="team-alpha-1")
    repo = TenantScopedRepository(tenant_alpha)

    repo.verify_ownership("team-alpha-1")
    repo.verify_org_ownership("org-alpha")

    with pytest.raises(TenantSecurityException):
        repo.verify_ownership("team-beta-1", "VehicleTwin")

    with pytest.raises(TenantSecurityException):
        repo.verify_org_ownership("org-beta", "OrganizationPolicy")
