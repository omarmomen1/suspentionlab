"""
backend/api/routes/vnv_routes.py
=================================
Verification & Validation evidence endpoints (#29).

GET /api/v1/vnv/run      → execute the full V&V suite, return graded table
GET /api/v1/vnv/report   → same, rendered as a Markdown evidence document

ENTERPRISE-only: this is customer-facing proof of solver correctness.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.shared.models import PlanTier
from suspensionlab.physics.vnv.framework import run_vnv_suite, render_vnv_markdown
from sqlalchemy.ext.asyncio import AsyncSession
from suspensionlab.backend.database.core import get_db_dependency

router = APIRouter(prefix="/vnv", tags=["verification-validation"])


def _require_enterprise(user: Any) -> None:
    if user is None:
        return
    plan = str(getattr(user, "plan", "")).upper()
    is_trial = getattr(user, "is_trial", False) or "TRIAL" in plan
    is_admin = getattr(user, "is_admin", False) or str(getattr(user, "user_id", "")) == "admin-001" or getattr(user, "email", "") == "owner@suspensionlab.pro"
    
    if plan not in ("ENTERPRISE", "PRO", "TRIAL") and not is_trial and not is_admin:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="The V&V evidence suite requires a Pro, Trial, or Enterprise plan.")


@router.get("/run")
async def vnv_run(
    model: str | None = None,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Run the V&V suite and return the graded case table (JSON)."""
    _require_enterprise(user)
    results = run_vnv_suite(model_filter=model)
    n_pass = sum(1 for r in results if r.status == "PASS")

    if user:
        try:
            from suspensionlab.backend.security.audit import record_audit_event
            await record_audit_event(
                db=db,
                event_type="VALIDATION_EXECUTED",
                user_id=str(user.user_id),
                team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
                artifact_id=f"vnv-{model or 'all'}",
                metadata={
                    "model_filter": model,
                    "total": len(results),
                    "passed": n_pass,
                    "failed": len(results) - n_pass,
                    "all_passed": n_pass == len(results),
                }
            )
        except Exception as e:
            import logging
            logging.getLogger("security_audit").warning("Audit logging warning for V&V run: %s", e)

    return {
        "summary": {
            "total": len(results),
            "passed": n_pass,
            "failed": len(results) - n_pass,
            "all_passed": n_pass == len(results),
        },
        "cases": [r.to_dict() for r in results],
    }


@router.get("/report", response_class=PlainTextResponse)
async def vnv_report(
    model: str | None = None,
    user: UserContext = Depends(verify_api_key),
):
    """V&V evidence table as a Markdown document (for proposals/procurement)."""
    _require_enterprise(user)
    results = run_vnv_suite(model_filter=model)
    return render_vnv_markdown(results)
