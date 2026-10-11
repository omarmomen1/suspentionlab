"""
backend/security/permissions.py
===============================
SuspensionLab PRO — Enterprise Role-Based Access Control (RBAC) & Permissions

Defines formal granular capability/permission objects rather than hardcoded string checks.

Roles:
- OWNER / SUPER_ADMIN : Full control across organization, billing, team, and engineering
- ADMIN               : Team management, billing, engineering setup approval, audit logs
- ENGINEER            : Simulation execution, telemetry ingestion, setup approval, reports
- CREW                : Operational setup views, telemetry viewing, simulation inspection
- VIEWER              : Read-only access to simulations and reports
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Set


class DataClassification(str, Enum):
    """Enterprise engineering data classification levels (Finding 86)."""
    PUBLIC = "PUBLIC"              # Unclassified, can be shared externally
    INTERNAL = "INTERNAL"          # Internal team access, normal export
    CONFIDENTIAL = "CONFIDENTIAL"  # Sensitive team telemetry/setups, restricted export
    RESTRICTED = "RESTRICTED"      # Highly sensitive OEM/F1 proprietary data (exports disabled, no public sharing)


class Permission(str, Enum):
    """Granular enterprise permission capabilities."""
    # Vehicle & Hardpoints
    VEHICLE_READ = "vehicle:read"
    VEHICLE_WRITE = "vehicle:write"
    VEHICLE_DELETE = "vehicle:delete"

    # Simulations & Compute
    SIMULATION_RUN = "simulation:run"
    SIMULATION_CANCEL = "simulation:cancel"
    SIMULATION_READ = "simulation:read"
    SIMULATION_DELETE = "simulation:delete"

    # Setups & Engineering Git
    SETUP_CREATE = "setup:create"
    SETUP_APPROVE = "setup:approve"
    SETUP_MODIFY = "setup:modify"

    # Telemetry & Calibration
    TELEMETRY_UPLOAD = "telemetry:upload"
    TELEMETRY_WRITE = "telemetry:write"
    TELEMETRY_READ = "telemetry:read"
    CALIBRATION_RUN = "calibration:run"

    # Reports & Exports
    REPORT_EXPORT = "report:export"
    REPORT_SHARE = "report:share"

    # Audit & Compliance
    AUDIT_READ = "audit:read"

    # Administration
    TEAM_ADMIN = "team:admin"
    TEAM_MANAGE = "team:manage"
    BILLING_ADMIN = "billing:admin"
    BILLING_MANAGE = "billing:manage"
    ORG_ADMIN = "org:admin"
    DATA_POLICY_MANAGE = "data_policy:manage"
    SCIM_MANAGE = "scim:manage"
    SAML_MANAGE = "saml:manage"


# Mapping from User Roles to Granted Permissions
ROLE_PERMISSIONS_MAP: Dict[str, Set[Permission]] = {
    "owner": set(Permission),
    "super_admin": set(Permission),
    "org_admin": set(Permission),

    "billing_admin": {
        Permission.BILLING_ADMIN,
        Permission.BILLING_MANAGE,
        Permission.AUDIT_READ,
        Permission.REPORT_EXPORT,
    },

    "admin": {
        Permission.VEHICLE_READ, Permission.VEHICLE_WRITE, Permission.VEHICLE_DELETE,
        Permission.SIMULATION_RUN, Permission.SIMULATION_CANCEL, Permission.SIMULATION_READ, Permission.SIMULATION_DELETE,
        Permission.SETUP_CREATE, Permission.SETUP_APPROVE, Permission.SETUP_MODIFY,
        Permission.TELEMETRY_UPLOAD, Permission.TELEMETRY_WRITE, Permission.TELEMETRY_READ, Permission.CALIBRATION_RUN,
        Permission.REPORT_EXPORT, Permission.REPORT_SHARE,
        Permission.TEAM_ADMIN, Permission.TEAM_MANAGE,
        Permission.BILLING_ADMIN, Permission.BILLING_MANAGE,
        Permission.AUDIT_READ, Permission.SCIM_MANAGE,
    },

    "team_admin": {
        Permission.VEHICLE_READ, Permission.VEHICLE_WRITE, Permission.VEHICLE_DELETE,
        Permission.SIMULATION_RUN, Permission.SIMULATION_CANCEL, Permission.SIMULATION_READ, Permission.SIMULATION_DELETE,
        Permission.SETUP_CREATE, Permission.SETUP_APPROVE, Permission.SETUP_MODIFY,
        Permission.TELEMETRY_UPLOAD, Permission.TELEMETRY_WRITE, Permission.TELEMETRY_READ, Permission.CALIBRATION_RUN,
        Permission.REPORT_EXPORT, Permission.REPORT_SHARE,
        Permission.TEAM_ADMIN, Permission.TEAM_MANAGE,
        Permission.BILLING_ADMIN, Permission.BILLING_MANAGE,
        Permission.AUDIT_READ,
    },

    "chief_engineer": {
        Permission.VEHICLE_READ, Permission.VEHICLE_WRITE,
        Permission.SIMULATION_RUN, Permission.SIMULATION_CANCEL, Permission.SIMULATION_READ,
        Permission.SETUP_CREATE, Permission.SETUP_APPROVE, Permission.SETUP_MODIFY,
        Permission.TELEMETRY_UPLOAD, Permission.TELEMETRY_WRITE, Permission.TELEMETRY_READ, Permission.CALIBRATION_RUN,
        Permission.REPORT_EXPORT, Permission.REPORT_SHARE,
        Permission.AUDIT_READ,
    },

    "lead_engineer": {
        Permission.VEHICLE_READ, Permission.VEHICLE_WRITE,
        Permission.SIMULATION_RUN, Permission.SIMULATION_CANCEL, Permission.SIMULATION_READ,
        Permission.SETUP_CREATE, Permission.SETUP_APPROVE, Permission.SETUP_MODIFY,
        Permission.TELEMETRY_UPLOAD, Permission.TELEMETRY_WRITE, Permission.TELEMETRY_READ, Permission.CALIBRATION_RUN,
        Permission.REPORT_EXPORT, Permission.REPORT_SHARE,
    },

    "lead": {
        Permission.VEHICLE_READ, Permission.VEHICLE_WRITE,
        Permission.SIMULATION_RUN, Permission.SIMULATION_CANCEL, Permission.SIMULATION_READ,
        Permission.SETUP_CREATE, Permission.SETUP_APPROVE, Permission.SETUP_MODIFY,
        Permission.TELEMETRY_UPLOAD, Permission.TELEMETRY_WRITE, Permission.TELEMETRY_READ, Permission.CALIBRATION_RUN,
        Permission.REPORT_EXPORT, Permission.REPORT_SHARE,
    },

    "engineer": {
        Permission.VEHICLE_READ, Permission.VEHICLE_WRITE,
        Permission.SIMULATION_RUN, Permission.SIMULATION_CANCEL, Permission.SIMULATION_READ,
        Permission.SETUP_CREATE, Permission.SETUP_MODIFY,
        Permission.TELEMETRY_UPLOAD, Permission.TELEMETRY_WRITE, Permission.TELEMETRY_READ, Permission.CALIBRATION_RUN,
        Permission.REPORT_EXPORT, Permission.REPORT_SHARE,
    },

    "member": {
        Permission.VEHICLE_READ,
        Permission.SIMULATION_READ,
        Permission.TELEMETRY_READ,
    },

    "crew": {
        Permission.VEHICLE_READ,
        Permission.SIMULATION_READ,
        Permission.TELEMETRY_READ,
    },

    "viewer": {
        Permission.VEHICLE_READ,
        Permission.SIMULATION_READ,
        Permission.TELEMETRY_READ,
    },
}



def has_permission(user_role: str, permission: Permission) -> bool:
    """Check whether a user role possesses the required granular permission."""
    role_key = (user_role or "viewer").lower().strip()
    granted = ROLE_PERMISSIONS_MAP.get(role_key, ROLE_PERMISSIONS_MAP["viewer"])
    return permission in granted


def get_role_permissions(user_role: str) -> List[str]:
    """Retrieve all permission capability strings granted to a role."""
    role_key = (user_role or "viewer").lower().strip()
    granted = ROLE_PERMISSIONS_MAP.get(role_key, ROLE_PERMISSIONS_MAP["viewer"])
    return sorted([p.value for p in granted])


def can_share_externally(classification: DataClassification | str) -> bool:
    """Evaluate whether an engineering artifact can be shared publicly (Finding 86)."""
    val = DataClassification(classification) if isinstance(classification, str) else classification
    return val == DataClassification.PUBLIC


def can_export_artifact(classification: DataClassification | str, user_role: str) -> bool:
    """Evaluate whether an engineering artifact can be exported based on classification (Finding 86)."""
    val = DataClassification(classification) if isinstance(classification, str) else classification
    if val == DataClassification.RESTRICTED:
        # Strictly restricted: Only owner / super_admin can export
        role_key = (user_role or "viewer").lower().strip()
        return role_key in ("owner", "super_admin")
    return has_permission(user_role, Permission.REPORT_EXPORT)

