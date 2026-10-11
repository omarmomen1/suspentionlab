"""
backend/security/tenancy.py
===========================
SuspensionLab PRO — Enterprise Multi-Tenancy Architecture & IDOR Prevention

Establishes TenantContext as an architectural invariant across all database and service operations.
Eliminates Insecure Direct Object Reference (IDOR) vulnerabilities by automatically scoping
queries to the authenticated tenant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from suspensionlab.backend.security.permissions import (
    Permission,
    ROLE_PERMISSIONS_MAP,
    has_permission,
)


@dataclass(frozen=True)
class TenantContext:
    """Architectural tenant context passed through request lifecycles and repositories."""
    user_id: str
    organization_id: str
    team_id: str
    role: str = "engineer"
    permissions: Set[Permission] = field(default_factory=set)

    def __post_init__(self):
        if not self.permissions:
            role_key = (self.role or "viewer").lower().strip()
            granted = ROLE_PERMISSIONS_MAP.get(role_key, ROLE_PERMISSIONS_MAP["viewer"])
            object.__setattr__(self, "permissions", granted)

    def can(self, permission: Permission) -> bool:
        """Verify whether this tenant context has the required permission."""
        return permission in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "team_id": self.team_id,
            "role": self.role,
            "permissions": [p.value for p in self.permissions],
        }


class TenantSecurityException(PermissionError):
    """Raised when an operation attempts to cross tenant boundaries or lacks permissions."""
    pass


class TenantScopedRepository:
    """Base repository enforcing tenant-scoped filtering on all entity operations."""

    def __init__(self, tenant_context: TenantContext):
        if not tenant_context or not tenant_context.team_id:
            raise TenantSecurityException("Cannot initialize repository without a valid TenantContext.")
        self.tenant = tenant_context

    def filter_scope(self, items: List[Dict[str, Any]], team_id_key: str = "team_id") -> List[Dict[str, Any]]:
        """Filter an in-memory collection strictly to the tenant's team ID."""
        return [item for item in items if str(item.get(team_id_key)) == str(self.tenant.team_id)]

    def verify_ownership(self, entity_team_id: str, entity_name: str = "Resource") -> None:
        """Verify that an accessed entity belongs to the current tenant's team."""
        if str(entity_team_id) != str(self.tenant.team_id):
            raise TenantSecurityException(
                f"Access Denied: {entity_name} belongs to team '{entity_team_id}', but request was made from team '{self.tenant.team_id}'."
            )

    def verify_org_ownership(self, entity_org_id: str, entity_name: str = "Resource") -> None:
        """Verify that an accessed entity belongs to the current tenant's organization."""
        if str(entity_org_id) != str(self.tenant.organization_id):
            raise TenantSecurityException(
                f"Access Denied: {entity_name} belongs to organization '{entity_org_id}', but request was made from organization '{self.tenant.organization_id}'."
            )


class TenantScope:
    """Authoritative tenant scoping helper for database queries and object access enforcement."""

    @staticmethod
    def get_tenant_filter(
        model_cls: Any,
        user_id: Optional[str | Any] = None,
        team_id: Optional[str | Any] = None,
        organization_id: Optional[str | Any] = None,
        is_admin: bool = False,
    ):
        """Construct a SQLAlchemy filter expression strictly scoping queries to the caller's tenant."""
        from sqlalchemy import or_, and_, true
        import uuid

        if is_admin:
            return true()

        u_uuid = uuid.UUID(str(user_id)) if user_id else None
        t_uuid = uuid.UUID(str(team_id)) if team_id else None
        o_uuid = uuid.UUID(str(organization_id)) if organization_id else None

        conditions = []

        # Scope by team_id if model supports it and caller has team
        if hasattr(model_cls, "team_id") and t_uuid is not None:
            conditions.append(model_cls.team_id == t_uuid)

        # Scope by user_id or owner_id
        if hasattr(model_cls, "user_id") and u_uuid is not None:
            conditions.append(model_cls.user_id == u_uuid)
        elif hasattr(model_cls, "owner_id") and u_uuid is not None:
            conditions.append(model_cls.owner_id == u_uuid)

        # Scope by organization_id if model supports it and caller has org
        if hasattr(model_cls, "organization_id") and o_uuid is not None:
            conditions.append(model_cls.organization_id == o_uuid)

        if not conditions:
            # Caller has neither team nor user identity — return impossible condition
            from sqlalchemy import false
            return false()

        return or_(*conditions)

    @staticmethod
    def enforce_ownership(
        obj: Any,
        user_id: Optional[str | Any] = None,
        team_id: Optional[str | Any] = None,
        organization_id: Optional[str | Any] = None,
        is_admin: bool = False,
        resource_name: str = "Resource",
    ) -> None:
        """
        Verify tenant ownership. If caller does not own the resource, raise LookupError
        to produce a uniform HTTP 404 (eliminating timing and response-shape enumeration oracles).
        """
        if is_admin or obj is None:
            return

        u_str = str(user_id) if user_id else None
        t_str = str(team_id) if team_id else None
        o_str = str(organization_id) if organization_id else None

        # Check team match
        if t_str and hasattr(obj, "team_id") and obj.team_id:
            if str(obj.team_id) == t_str:
                return

        # Check user / owner match
        if u_str:
            if hasattr(obj, "user_id") and obj.user_id and str(obj.user_id) == u_str:
                return
            if hasattr(obj, "owner_id") and obj.owner_id and str(obj.owner_id) == u_str:
                return

        # Check organization match
        if o_str and hasattr(obj, "organization_id") and obj.organization_id:
            if str(obj.organization_id) == o_str:
                return

        # Deny access with a uniform 404 LookupError to prevent object existence enumeration
        raise LookupError(f"{resource_name} not found.")
