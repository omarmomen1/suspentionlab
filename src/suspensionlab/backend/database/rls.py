"""
backend/database/rls.py
=======================
SuspensionLab PRO — PostgreSQL Row-Level Security (RLS) & Session Tenant Isolation.

Enforces kernel-level tenant isolation in PostgreSQL:
1. Every tenant-owned table has Row-Level Security enabled and forced.
2. Tenant security policies check `app.current_organization_id`, `app.current_tenant_id`, and `app.current_user_id`.
3. Application sessions execute `SET LOCAL` upon acquisition to establish strict isolation boundaries.
4. Application-layer filtering remains active as defense-in-depth.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from suspensionlab.backend.security.tenancy import TenantContext

logger = logging.getLogger(__name__)

# List of all tenant-owned core tables subject to Row-Level Security
TENANT_TABLES = [
    "organizations",
    "teams",
    "users",
    "vehicle_profiles",
    "jobs",
    "sessions",
    "session_comments",
    "simulation_runs",
    "setup_proposals",
    "setup_scores",
    "vehicle_twins",
    "shared_reports",
    "audit_logs",
    "engineering_audit_logs",
    "user_api_keys",
    "user_sessions",
    "webhook_endpoints",
    "scim_groups",
    "evidence_graph_edges",
]


def generate_table_rls_sql(table_name: str) -> List[str]:
    """
    Generate PostgreSQL DDL to enable RLS and define the tenant isolation policy for a table.
    Handles tables with organization_id, team_id, owner_id, or user_id columns.
    """
    statements = [
        f"ALTER TABLE IF EXISTS {table_name} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE IF EXISTS {table_name} FORCE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS {table_name}_tenant_isolation_policy ON {table_name};",
    ]

    # Build appropriate SQL expression for the policy
    if table_name == "organizations":
        policy_expr = (
            "(id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name == "teams":
        policy_expr = (
            "(id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
            "OR owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name == "users":
        policy_expr = (
            "(id = NULLIF(current_setting('app.current_user_id', true), '')::uuid "
            "OR team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid "
            "OR organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name in ("audit_logs", "engineering_audit_logs"):
        policy_expr = (
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR (user_id IS NOT NULL AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name == "evidence_graph_edges":
        policy_expr = (
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id IS NOT NULL AND organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR (created_by_user_id IS NOT NULL AND created_by_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name == "scim_groups":
        policy_expr = (
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name in ("vehicle_profiles", "simulation_runs", "setup_proposals", "vehicle_twins", "job_records", "jobs"):
        policy_expr = (
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (user_id IS NOT NULL AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name in ("sessions", "sim_sessions"):
        policy_expr = (
            "((team_id IS NOT NULL AND team_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "OR (owner_id IS NOT NULL AND owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name == "session_comments":
        policy_expr = (
            "((author_id IS NOT NULL AND author_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name in ("user_api_keys", "user_sessions", "webhook_endpoints"):
        policy_expr = (
            "((user_id IS NOT NULL AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
            "OR current_setting('app.is_super_admin', true) = 'true')"
        )
    elif table_name in ("shared_reports", "setup_scores"):
        policy_expr = "true"
    else:
        policy_expr = "current_setting('app.is_super_admin', true) = 'true'"

    create_policy = (
        f"CREATE POLICY {table_name}_tenant_isolation_policy ON {table_name} "
        f"FOR ALL USING ({policy_expr}) WITH CHECK ({policy_expr});"
    )
    statements.append(create_policy)
    return statements


def get_all_rls_ddl() -> str:
    """Return all PostgreSQL DDL statements for enabling RLS across the entire schema."""
    all_stmts: List[str] = []
    for table in TENANT_TABLES:
        all_stmts.extend(generate_table_rls_sql(table))
    return "\n".join(all_stmts)


async def apply_rls_policies(session: AsyncSession) -> None:
    """Execute RLS DDL on PostgreSQL. Safe no-op on SQLite."""
    bind = session.bind
    dialect_name = bind.dialect.name if bind else ""
    if "postgres" not in dialect_name:
        logger.info("Skipping PostgreSQL RLS DDL on non-Postgres dialect (%s).", dialect_name)
        return

    res = await session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
    existing_tables = {row[0] for row in res}
    for table in TENANT_TABLES:
        if table in existing_tables:
            for stmt in generate_table_rls_sql(table):
                await session.execute(text(stmt))
    await session.commit()
    logger.info("Successfully enabled Row-Level Security on core tables.")


async def set_session_tenant_context(
    session: AsyncSession,
    tenant_context: Optional[TenantContext] = None,
    organization_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
    is_super_admin: bool = False,
) -> None:
    """
    Set PostgreSQL transaction-local session settings for tenant isolation:
      - app.current_organization_id
      - app.current_tenant_id
      - app.current_user_id
      - app.is_super_admin
    """
    org_id = organization_id or (tenant_context.organization_id if tenant_context else "") or ""
    t_id = team_id or (tenant_context.team_id if tenant_context else "") or ""
    u_id = user_id or (tenant_context.user_id if tenant_context else "") or ""
    admin_flag = "true" if (is_super_admin or (tenant_context and tenant_context.role in ("owner", "super_admin", "org_admin"))) else "false"

    bind = session.bind
    dialect_name = bind.dialect.name if bind else ""

    # Safe execution on Postgres; gracefully ignored on SQLite
    if "postgres" in dialect_name:
        await session.execute(text(f"SET LOCAL app.current_organization_id = '{org_id}';"))
        await session.execute(text(f"SET LOCAL app.current_tenant_id = '{t_id}';"))
        await session.execute(text(f"SET LOCAL app.current_user_id = '{u_id}';"))
        await session.execute(text(f"SET LOCAL app.is_super_admin = '{admin_flag}';"))
    else:
        # In non-Postgres (e.g. SQLite test environment), attach to session info dictionary for verification
        session.info["tenant_context"] = {
            "organization_id": org_id,
            "team_id": t_id,
            "user_id": u_id,
            "is_super_admin": admin_flag == "true",
        }
