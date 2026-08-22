"""
backend/api/routes/vnv_routes.py
=================================
Verification & Validation evidence endpoints (#29).

GET /api/v1/vnv/run      → execute the full V&V suite, return graded table
GET /api/v1/vnv/report   → same, rendered as a Markdown evidence document

ENTERPRISE-only: this is customer-facing proof of solver correctness.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.shared.models import PlanTier
from suspensionlab.physics.vnv.framework import run_vnv_suite, render_vnv_markdown

router = APIRouter(prefix="/vnv", tags=["verification-validation"])


def _require_enterprise(user: dict) -> None:
    if user.plan not in (PlanTier.ENTERPRISE,) and user.user_id != "admin-001":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="The V&V evidence suite requires the Enterprise plan.")


@router.get("/run")
async def vnv_run(
    model: str | None = None,
    user: dict = Depends(verify_api_key),
):
    """Run the V&V suite and return the graded case table (JSON)."""
    _require_enterprise(user)
    results = run_vnv_suite(model_filter=model)
    n_pass = sum(1 for r in results if r.status == "PASS")
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
    user: dict = Depends(verify_api_key),
):
    """V&V evidence table as a Markdown document (for proposals/procurement)."""
    _require_enterprise(user)
    results = run_vnv_suite()
    return render_vnv_markdown(results)
