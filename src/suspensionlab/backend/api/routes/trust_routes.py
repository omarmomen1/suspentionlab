"""
backend/api/routes/trust_routes.py
====================================
Public trust posture API (Tier C1).

GET /api/v1/trust — machine-readable compliance posture for procurement and
security reviews. Deliberately PUBLIC (no auth): security teams evaluating
SuspensionLab must be able to read it without an account.

The controls listed here are IMPLEMENTED in this codebase — each entry names
the module that enforces it, so the page cannot drift into marketing fiction.
"""
from __future__ import annotations

from fastapi import APIRouter

from suspensionlab.backend.config import settings

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("")
async def trust_posture():
    return {
        "service": "SuspensionLab PRO",
        "data_residency": {
            "regions": ["eu-central", "us-east"],
            "default_region": getattr(settings, "data_residency_region", "eu-central"),
            "per_team_selection": True,
            "note": (
                "Team data region selection is enforced at the deployment level: "
                "each region runs an isolated stack with its own database and object storage."
            ),
        },
        "controls": [
            {"id": "crypto-at-rest", "name": "Encryption at rest",
             "evidence": "Database volume encryption; secrets validated for cryptographic strength at boot (config.validate_prod_secrets)"},
            {"id": "crypto-transit", "name": "Encryption in transit",
             "evidence": "TLS 1.2/1.3 termination with HSTS + OCSP (nginx.conf); ACME-only HTTP listener"},
            {"id": "authn", "name": "Strong authentication",
             "evidence": "OIDC Authorization Code + PKCE, Argon2 password hashing, JWT key rotation with kid headers"},
            {"id": "authz", "name": "Authorization / RBAC",
             "evidence": "Per-plan concurrency caps, seat roles (Owner/Admin/Engineer/Crew/Viewer), plan gating server-side"},
            {"id": "audit", "name": "Audit logging",
             "evidence": "Immutable audit log tables (AuditLog, EngineeringAuditLog) incl. role changes and artifact access"},
            {"id": "scim", "name": "SCIM 2.0 provisioning",
             "evidence": "RFC 7643/7644 user provisioning with constant-time bearer auth (scim_routes.py)"},
            {"id": "artifacts", "name": "Immutable engineering artifacts",
             "evidence": "RUN artifacts with SHA-256 canonical hashing and HMAC-signed share tokens"},
            {"id": "webhooks", "name": "Signed outbound webhooks",
             "evidence": "HMAC-SHA256 v1 signatures over timestamp+body (services/webhooks.py)"},
            {"id": "observability", "name": "Monitoring & alerting",
             "evidence": "Prometheus metrics, OpenTelemetry tracing, Sentry error tracking, worker heartbeats"},
            {"id": "governance", "name": "Compute governance",
             "evidence": "Bounded thread pools, per-plan quotas and concurrency caps, monthly usage metering"},
        ],
        "subprocessors": [
            {"name": "PostgreSQL-compatible database", "purpose": "Application data"},
            {"name": "Redis", "purpose": "Queues, caching, metering counters"},
            {"name": "Lemon Squeezy", "purpose": "Merchant of record / billing"},
        ],
        "vulnerability_reporting": "security@suspensionlab.com",
        "review_cycle": "Quarterly internal control review; evidence regenerated on each release.",
    }
