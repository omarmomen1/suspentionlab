"""
backend/api/routes/retention_routes.py
======================================
Compliance, Data Retention, and PII Erasure Endpoints.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import UserContext, verify_api_key, require_permission
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.retention_service import (
    anonymize_user_pii,
    execute_retention_purge,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["Compliance & Retention"])


class UserErasureRequest(BaseModel):
    reason: str = Field(default="GDPR Article 17 Right to Erasure", max_length=255)


class PurgeRequest(BaseModel):
    organization_id: Optional[str] = None
    dry_run: bool = False


@router.post("/erasure/user/{user_id}", status_code=status.HTTP_200_OK)
async def request_user_erasure(
    user_id: str,
    req: UserErasureRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Execute GDPR/CCPA personal data erasure for a user account.
    Permanently erases PII and credentials while preserving engineering provenance.
    """
    # Authorization: User can erase own account, or ORG_ADMIN/Platform Admin can erase org members
    is_self = user.user_id == user_id
    is_authorized_admin = user.is_admin or user.org_role == "ORG_ADMIN"

    if not (is_self or is_authorized_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission Denied: You do not have permission to erase this user account.",
        )

    try:
        res = await anonymize_user_pii(db, user_id=user_id, reason=req.reason)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Error erasing user PII: %s", e)
        raise HTTPException(status_code=500, detail="Failed to execute PII erasure.")


@router.post("/retention/purge", status_code=status.HTTP_200_OK)
async def trigger_retention_purge(
    req: PurgeRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Trigger data retention policy purge across database and storage artifacts.
    """
    if user.is_trial:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission Denied: Trial users cannot execute retention purge.",
        )
    if not user.is_admin and user.org_role != "ORG_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission Denied: Only ORG_ADMIN can execute retention purge.",
        )

    target_org = req.organization_id or user.organization_id
    if not user.is_admin and target_org != user.organization_id:
        raise HTTPException(status_code=403, detail="Cross-tenant purge is forbidden.")

    res = await execute_retention_purge(db, organization_id=target_org, dry_run=req.dry_run)
    return res
