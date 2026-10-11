"""
tests/test_backend_architecture_and_security.py
===============================================
Tests for Enterprise Backend Architecture, Security, Tenancy, RBAC, and Quotas (Findings 41-50).
"""

import pytest

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
from suspensionlab.backend.services.compute_governance import (
    ComputeQuotaEnforcer,
    ComputeQuotaExceededException,
    PLAN_QUOTAS,
)
from suspensionlab.backend.services.artifact_sharing import (
    ImmutableSharedReport,
)
from suspensionlab.backend.security.audit import (
    compute_merkle_audit_hash,
    verify_audit_merkle_chain,
)
from suspensionlab.backend.security.jwt_utils import (
    TokenRevocationRegistry,
    get_public_jwks,
)


def test_formal_rbac_permissions():
    # Admin has management & write
    assert has_permission("admin", Permission.TEAM_MANAGE)
    assert has_permission("admin", Permission.SIMULATION_RUN)
    
    # Engineer has simulations, but cannot approve setups (separation of duties) nor manage teams
    assert has_permission("engineer", Permission.SIMULATION_RUN)
    assert not has_permission("engineer", Permission.SETUP_APPROVE)
    assert not has_permission("engineer", Permission.TEAM_MANAGE)
    
    # Viewer is read-only
    assert has_permission("viewer", Permission.SIMULATION_READ)
    assert not has_permission("viewer", Permission.SIMULATION_RUN)
    assert not has_permission("viewer", Permission.VEHICLE_WRITE)


def test_tenant_context_and_repository_isolation():
    tenant_a = TenantContext(user_id="usr-1", organization_id="org-1", team_id="team-alpha", role="engineer")
    tenant_b = TenantContext(user_id="usr-2", organization_id="org-1", team_id="team-bravo", role="engineer")

    repo_a = TenantScopedRepository(tenant_a)
    
    data = [
        {"id": "sim-1", "team_id": "team-alpha", "name": "Run 1"},
        {"id": "sim-2", "team_id": "team-bravo", "name": "Run 2"},
        {"id": "sim-3", "team_id": "team-alpha", "name": "Run 3"},
    ]

    scoped = repo_a.filter_scope(data)
    assert len(scoped) == 2
    assert all(item["team_id"] == "team-alpha" for item in scoped)

    # Cross-tenant IDOR access rejection
    with pytest.raises(TenantSecurityException):
        repo_a.verify_ownership("team-bravo", "SimulationRun")


def test_compute_governance_quotas():
    enforcer = ComputeQuotaEnforcer()
    tenant_free = TenantContext(user_id="usr-free", organization_id="org-free", team_id="team-free", role="engineer")
    
    # Free plan concurrent job limit is 1
    enforcer.check_simulation_quota(tenant_free, plan_name="free", requested_samples=50)
    enforcer.record_job_start("team-free")
    
    # Second job violates concurrent job quota
    with pytest.raises(ComputeQuotaExceededException):
        enforcer.check_simulation_quota(tenant_free, plan_name="free", requested_samples=50)
        
    enforcer.record_job_finish("team-free", cpu_seconds_used=5.0)


def test_immutable_shared_report_integrity():
    report = ImmutableSharedReport.create(
        report_id="REP-901",
        team_id="team-f1",
        vehicle_id="VEH-2026",
        setup_id="SET-04",
        model_version="7DOF-v12",
        solver_version="rk4-v2",
        input_params={"k_spring": 45000.0, "c_damper": 2200.0},
        simulation_results={"lap_time_s": 84.12, "peak_lat_g": 3.85},
        summary_metrics={"f_n_s": 2.4},
    )

    assert report.verify_integrity(report.input_hash, report.result_hash)
    assert not report.verify_integrity("tampered_input_hash", report.result_hash)


def test_tamper_evident_merkle_audit_chain():
    # Build legitimate audit chain
    records = []
    prev_h = "GENESIS"
    
    events = [
        {"action": "LOGIN", "user": "usr-1", "ts": 100},
        {"action": "SETUP_UPDATE", "user": "usr-1", "ts": 105, "setup_id": "S-1"},
        {"action": "SETUP_APPROVE", "user": "usr-lead", "ts": 110, "setup_id": "S-1"},
    ]

    for ev in events:
        curr_h = compute_merkle_audit_hash(prev_h, ev)
        rec = {**ev, "previous_hash": prev_h, "current_hash": curr_h}
        records.append(rec)
        prev_h = curr_h

    # Chain passes verification
    assert verify_audit_merkle_chain(records)

    # Tamper with an event payload
    tampered = [dict(r) for r in records]
    tampered[1]["action"] = "SETUP_DELETE"
    assert not verify_audit_merkle_chain(tampered)


def test_token_revocation_and_jwks():
    # Test revocation
    assert not TokenRevocationRegistry.is_revoked("test-jti-1")
    TokenRevocationRegistry.revoke_jti("test-jti-1")
    assert TokenRevocationRegistry.is_revoked("test-jti-1")

    # Test refresh token reuse detection
    assert TokenRevocationRegistry.register_refresh_use("refresh-jti-alpha")
    # Second use of same refresh token should detect replay attack
    assert not TokenRevocationRegistry.register_refresh_use("refresh-jti-alpha")

    # JWKS export
    jwks = get_public_jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) > 0
    assert jwks["keys"][0]["kty"] == "oct"
