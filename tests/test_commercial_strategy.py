"""
tests/test_commercial_strategy.py
=================================
Tests for commercial pricing tiers, compute governance quotas, and valuation framework (Findings 80-87).
"""

import pytest

from suspensionlab.backend.services.compute_governance import (
    PLAN_QUOTAS,
    ComputeQuotaEnforcer,
    PlanComputeQuota,
    ComputeQuotaExceededException,
)
from suspensionlab.backend.security.tenancy import TenantContext



def test_commercial_plan_quotas_alignment():
    # Verify that plan quotas exist for Free, Pro (Individual), Team (Motorsport), Enterprise (OEM)
    assert "free" in PLAN_QUOTAS
    assert "pro" in PLAN_QUOTAS
    assert "team" in PLAN_QUOTAS
    assert "enterprise" in PLAN_QUOTAS

    pro_quota = PLAN_QUOTAS["pro"]
    assert pro_quota.max_concurrent_jobs >= 4
    assert pro_quota.max_monthly_cpu_seconds >= 3600.0
    assert pro_quota.allow_custom_solvers

    team_quota = PLAN_QUOTAS["team"]
    assert team_quota.max_concurrent_jobs >= 10
    assert team_quota.max_telemetry_upload_mb >= 1000.0  # >= 1 GB
    assert team_quota.max_monte_carlo_samples >= 10000

    enterprise_quota = PLAN_QUOTAS["enterprise"]
    assert enterprise_quota.max_concurrent_jobs >= 50
    assert enterprise_quota.max_monthly_cpu_seconds >= 360000.0  # 100 hours
    assert enterprise_quota.max_telemetry_upload_mb >= 50000.0   # 50 GB


def test_compute_quota_enforcer_comprehensive_governance():
    enforcer = ComputeQuotaEnforcer()
    tenant_free = TenantContext(user_id="usr-free", organization_id="org-free", team_id="team-free", role="engineer")
    tenant_pro = TenantContext(user_id="usr-pro", organization_id="org-pro", team_id="team-pro", role="engineer")

    # 1. Monte Carlo sample cap enforcement on Free plan
    with pytest.raises(ComputeQuotaExceededException, match="Requested sample size"):
        enforcer.check_simulation_quota(tenant_free, plan_name="free", requested_samples=500)

    # Pro plan allows 500 samples
    enforcer.check_simulation_quota(tenant_pro, plan_name="pro", requested_samples=500)

    # 2. Concurrency limit enforcement
    enforcer.record_job_start("team-free")
    with pytest.raises(ComputeQuotaExceededException, match="Concurrent job limit"):
        enforcer.check_simulation_quota(tenant_free, plan_name="free", requested_samples=10)

    # Release job
    enforcer.record_job_finish("team-free", cpu_seconds_used=10.0)
    # Should now succeed
    enforcer.check_simulation_quota(tenant_free, plan_name="free", requested_samples=10)

    # 3. Monthly CPU budget exhaustion
    enforcer.record_job_finish("team-free", cpu_seconds_used=350.0) # Free limit is 300.0s
    with pytest.raises(ComputeQuotaExceededException, match="Monthly compute budget"):
        enforcer.check_simulation_quota(tenant_free, plan_name="free", requested_samples=1)


