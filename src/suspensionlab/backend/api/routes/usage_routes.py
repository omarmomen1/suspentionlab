"""
backend/api/routes/usage_routes.py
===================================
Simulation usage metering API (Tier A4).

GET /api/v1/usage → current-month consumption against the plan quota.
Powers the in-app UsageBadge and any future billing reconciliation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from suspensionlab.backend.core.compute_governance import (
    SIM_QUOTAS,
    get_monthly_usage,
    monthly_usage_key,
)
from suspensionlab.backend.security.auth import UserContext, verify_api_key

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def get_usage(user: UserContext = Depends(verify_api_key)):
    """Current-month simulation usage for the authenticated principal."""
    used = await get_monthly_usage(user.user_id)
    quota = SIM_QUOTAS.get(str(user.plan), SIM_QUOTAS["FREE"])
    remaining = max(0, quota - used)
    return {
        "month": monthly_usage_key(user.user_id).rsplit(":", 1)[-1],
        "plan": str(user.plan),
        "sims_used": used,
        "quota": quota,
        "remaining": remaining,
        "utilization_pct": round(min(100.0, (used / quota) * 100.0), 1) if quota else 100.0,
    }
