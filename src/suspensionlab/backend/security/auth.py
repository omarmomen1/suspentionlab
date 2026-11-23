"""
backend/security/auth.py
Supports two auth methods:
  1. X-API-Key header (legacy + per-user named keys)
  2. Authorization: Bearer <JWT> (new email/password login)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request, Depends, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.audit import log_audit_event
from suspensionlab.backend.security.jwt_utils import decode_access_token
from suspensionlab.shared.models import PlanTier

# Plan tiers ordered by privilege level
PLAN_LEVELS = {PlanTier.FREE: 0, PlanTier.PRO: 1, PlanTier.ENTERPRISE: 2, PlanTier.TRIAL: 1}


from typing import Any
from pydantic import BaseModel, Field
from suspensionlab.backend.security.permissions import (
    Permission,
    ROLE_PERMISSIONS_MAP,
    has_permission as check_has_permission,
    get_role_permissions,
)

def _is_user_trial(trial: Any, user_plan: str | None, organization: Any) -> bool:
    """Safely evaluate whether user or their organization is on trial, always returning strict bool."""
    active_or_expired_trial = trial is not None and getattr(trial, "status", None) != "CONVERTED"
    return bool(
        active_or_expired_trial
        or (user_plan == PlanTier.TRIAL.value)
        or bool(organization and getattr(organization, "plan", None) == PlanTier.TRIAL.value)
    )


def _normalize_plan_key(plan: Any) -> str:
    if isinstance(plan, PlanTier):
        return plan.value.upper()
    return str(plan or PlanTier.FREE.value).upper()


def _format_trial_expiry(trial: Any) -> str | None:
    expires_at = getattr(trial, "expires_at", None)
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.isoformat()


def _is_trial_context_expired(user: "UserContext") -> bool:
    if (user.trial_status or "").upper() == "EXPIRED":
        return True
    exp_raw = getattr(user, "trial_expires_at", None)
    if exp_raw:
        try:
            exp_dt = (
                exp_raw
                if isinstance(exp_raw, datetime)
                else datetime.fromisoformat(str(exp_raw).replace("Z", "+00:00"))
            )
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt <= datetime.now(timezone.utc):
                return True
        except (ValueError, TypeError):
            return True
    return False


class UserContext(BaseModel):
    user_id: str
    plan: str
    email: str
    name: str = ""
    onboarding_complete: bool = True
    organization_id: str | None = None
    org_role: str | None = None          # ORG_ADMIN | BILLING_ADMIN | MEMBER
    team_id: str | None = None
    team_role: str | None = None          # OWNER | ADMIN | ENGINEER | CREW | VIEWER
    is_admin: bool = False
    is_trial: bool = False
    trial_status: str | None = None      # ACTIVE | EXPIRED
    trial_expires_at: str | None = None
    permissions: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.permissions:
            perms = set()
            if self.team_id and self.team_role:
                perms.update(get_role_permissions(self.team_role))
            if self.organization_id and self.org_role:
                perms.update(get_role_permissions(self.org_role))
            if self.is_admin and not self.is_trial:
                perms.update([p.value for p in Permission])
            if not self.team_id and not self.organization_id:
                perms.update(get_role_permissions("solo"))
            object.__setattr__(self, "permissions", sorted(list(perms)))

    def can(self, permission: Permission | str) -> bool:
        perm_val = permission.value if isinstance(permission, Permission) else str(permission)
        if self.is_trial:
            # Trial users are restricted from administrative, audit, and billing permissions
            admin_perms = {
                Permission.AUDIT_READ.value,
                Permission.SCIM_MANAGE.value,
                Permission.SAML_MANAGE.value,
                Permission.BILLING_ADMIN.value,
                Permission.BILLING_MANAGE.value,
                Permission.ORG_ADMIN.value,
                Permission.TEAM_ADMIN.value,
                Permission.TEAM_MANAGE.value,
                Permission.DATA_POLICY_MANAGE.value,
            }
            if perm_val in admin_perms:
                return False
            return True
        if self.is_admin or (self.team_role and self.team_role.upper() == "OWNER") or (self.org_role and self.org_role.upper() == "ORG_ADMIN"):
            return True
        return perm_val in self.permissions


# Seat-role hierarchy (Tier A3). Higher number = more capability.
TEAM_ROLE_LEVELS = {
    "OWNER": 4,
    "ADMIN": 3,
    "CHIEF_ENGINEER": 3,
    "LEAD_ENGINEER": 3,
    "LEAD": 3,
    "ENGINEER": 2,
    "CREW": 1,
    "VIEWER": 0,
}


def require_team_role(minimum_role: str):
    """
    FastAPI dependency factory enforcing a minimum team seat role.
    Non-team members always fail. Usage:
        Depends(require_team_role("Engineer"))
    """
    minimum = TEAM_ROLE_LEVELS.get((minimum_role or "").upper(), 99)

    async def _check(user: UserContext = Depends(verify_api_key)):
        if not user.team_id or not user.team_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action requires a team workspace membership.",
            )
        level = TEAM_ROLE_LEVELS.get(user.team_role.upper(), -1)
        if level < minimum:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the {minimum_role} seat role or higher.",
            )
        return user
    return _check


def require_permission(required_permission: Permission | str):
    """
    FastAPI dependency factory enforcing a granular capability permission.
    Replaces scattered string role checks with formal RBAC verification.
    """
    perm_val = required_permission.value if isinstance(required_permission, Permission) else str(required_permission)

    async def _check_perm(user: UserContext = Depends(verify_api_key)):
        if not user.can(perm_val):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission Denied: User lacks required capability '{perm_val}'.",
            )
        return user
    return _check_perm

async def verify_api_key(
    request:  Request,
    api_key:  str | None = Header(alias="X-API-Key",      default=None),
    bearer:   str | None = Header(alias="Authorization",  default=None),
    db:       AsyncSession = Depends(get_db_dependency),
) -> UserContext:
    """
    Authenticate the request via:
      - Bearer JWT token (preferred — from email/password login)
      - X-API-Key header (legacy admin key or per-user named key)
    Returns a dict with user_id, tier/plan, onboarding_complete.
    """
    from suspensionlab.backend.core.errors import AuthenticationError
    ip = request.client.host if request.client else "unknown"

    if not bearer:
        sl_token = request.cookies.get("sl_token")
        if sl_token:
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                csrf_token_header = request.headers.get("X-CSRF-Token")
                csrf_token_cookie = request.cookies.get("csrf_token")
                if not csrf_token_header or not csrf_token_cookie or csrf_token_header != csrf_token_cookie:
                    from suspensionlab.backend.core.errors import AuthenticationError
                    raise AuthenticationError("CSRF token missing or mismatch.")
            bearer = f"Bearer {sl_token}"

    # ── 1. Bearer JWT (preferred) ─────────────────────────────────────────
    if bearer and bearer.startswith("Bearer "):
        token   = bearer.removeprefix("Bearer ").strip()
        payload = decode_access_token(token)
        if payload:
            if payload.get("type") != "access":
                from suspensionlab.backend.core.errors import AuthenticationError
                raise AuthenticationError("Invalid token type. Only access tokens are allowed here.")
            
            from suspensionlab.backend.security.jwt_utils import is_jti_revoked
            if await is_jti_revoked(payload.get("jti")):
                log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "Revoked Bearer token"})
                from suspensionlab.backend.core.errors import AuthenticationError
                raise AuthenticationError("Token has been revoked.")

            user_id = payload.get("sub")
            plan    = payload.get("plan", PlanTier.FREE)
            import uuid
            try:
                user_uuid = uuid.UUID(str(user_id))
            except ValueError:
                from suspensionlab.backend.core.errors import AuthenticationError
                raise AuthenticationError("Invalid token subject")
            from sqlalchemy.orm import joinedload
            from suspensionlab.backend.database.rls import set_session_tenant_context
            result = await db.execute(
                select(User).options(
                    joinedload(User.team),
                    joinedload(User.organization)
                ).where(User.id == user_uuid, User.deleted_at == None)
            )
            user: User | None = result.scalar_one_or_none()
            if not user:
                log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "JWT user not found"})
                raise AuthenticationError("User not found.")
            request.state.user_id = str(user.id)
            log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)

            effective_plan = user.plan
            if user.organization and user.organization.plan:
                effective_plan = user.organization.plan
            elif user.team and user.team.plan:
                effective_plan = user.team.plan

            # Calculate granted permissions
            perms = set()
            if user.team_id and user.team_role:
                perms.update(get_role_permissions(user.team_role))
            if user.organization_id and user.org_role:
                perms.update(get_role_permissions(user.org_role))
            if user.is_admin:
                perms.update([p.value for p in Permission])
            if not user.team_id and not user.organization_id:
                perms.update(get_role_permissions("solo"))

            # Apply PostgreSQL session tenant context
            await set_session_tenant_context(
                db,
                organization_id=str(user.organization_id) if user.organization_id else None,
                team_id=str(user.team_id) if user.team_id else None,
                user_id=str(user.id),
                is_super_admin=bool(user.is_admin),
            )

            # Check trial status
            from suspensionlab.backend.database.models.trial import Trial
            trial_check = await db.execute(
                select(Trial).where(
                    or_(Trial.user_id == user.id, Trial.organization_id == user.organization_id),
                    Trial.deleted_at.is_(None)
                )
            )
            trial = trial_check.scalar_one_or_none()
            is_trial = _is_user_trial(trial, user.plan, user.organization)
            trial_status = None
            trial_expires_at = None
            if trial and getattr(trial, "status", None) != "CONVERTED":
                if trial.is_expired():
                    trial.status = "EXPIRED"
                trial_status = trial.status
                trial_expires_at = _format_trial_expiry(trial)

            return UserContext(
                user_id=str(user.id),
                plan=effective_plan,
                email=user.email,
                name=user.name or "",
                onboarding_complete=user.onboarding_complete,
                organization_id=str(user.organization_id) if user.organization_id else None,
                org_role=user.org_role if user.organization_id else None,
                team_id=str(user.team_id) if user.team_id else None,
                team_role=user.team_role if user.team_id else None,
                is_admin=False if is_trial else bool(user.is_admin),
                is_trial=is_trial,
                trial_status=trial_status,
                trial_expires_at=trial_expires_at,
                permissions=sorted(list(perms)),
            )


        # Token present but invalid — do not fall through to API key
        log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "Invalid Bearer token"})
        raise AuthenticationError("Invalid or expired token.")

    # ── 2. X-API-Key header ───────────────────────────────────────────────
    if api_key:
        # 2c. Look up per-user named API key (O(1) prefix lookup)
        from suspensionlab.backend.database.models.user_api_key import UserApiKey
        from suspensionlab.backend.security.jwt_utils import verify_password
        from datetime import datetime, timezone
        
        # All valid generated keys start with slk_ and use 12 chars for prefix
        if api_key.startswith("slk_") and len(api_key) > 12:
            prefix = api_key[:12]
            key_results = await db.execute(
                select(UserApiKey).where(UserApiKey.key_prefix == prefix, UserApiKey.is_active == True)
            )
            for named_key in key_results.scalars():
                # Skip expired keys
                if named_key.expires_at and datetime.now(timezone.utc) > named_key.expires_at:
                    continue
                import asyncio
                is_valid, _ = await asyncio.to_thread(verify_password, api_key, named_key.key_hash)
                if is_valid:
                    # Update last_used
                    named_key.last_used = datetime.now(timezone.utc)
                    await db.commit()

                    from sqlalchemy.orm import joinedload
                    from suspensionlab.backend.database.rls import set_session_tenant_context
                    user_result = await db.execute(
                        select(User).options(
                            joinedload(User.team),
                            joinedload(User.organization)
                        ).where(User.id == named_key.user_id, User.deleted_at == None)
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        request.state.user_id = str(user.id)
                        log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
                        effective_plan = user.plan
                        if user.organization and user.organization.plan:
                            effective_plan = user.organization.plan
                        elif user.team and user.team.plan:
                            effective_plan = user.team.plan

                        perms = set()
                        if user.team_id and user.team_role:
                            perms.update(get_role_permissions(user.team_role))
                        if user.organization_id and user.org_role:
                            perms.update(get_role_permissions(user.org_role))
                        if user.is_admin:
                            perms.update([p.value for p in Permission])
                        if not user.team_id and not user.organization_id:
                            perms.update(get_role_permissions("solo"))

                        await set_session_tenant_context(
                            db,
                            organization_id=str(user.organization_id) if user.organization_id else None,
                            team_id=str(user.team_id) if user.team_id else None,
                            user_id=str(user.id),
                            is_super_admin=bool(user.is_admin),
                        )

                        # Check trial status
                        from suspensionlab.backend.database.models.trial import Trial
                        trial_check = await db.execute(
                            select(Trial).where(
                                or_(Trial.user_id == user.id, Trial.organization_id == user.organization_id),
                                Trial.deleted_at.is_(None)
                            )
                        )
                        trial = trial_check.scalar_one_or_none()
                        is_trial = _is_user_trial(trial, user.plan, user.organization)
                        trial_status = None
                        trial_expires_at = None
                        if trial and getattr(trial, "status", None) != "CONVERTED":
                            if trial.is_expired():
                                trial.status = "EXPIRED"
                            trial_status = trial.status
                            trial_expires_at = _format_trial_expiry(trial)

                        return UserContext(
                            user_id=str(user.id),
                            plan=effective_plan,
                            email=user.email,
                            name=user.name or "",
                            onboarding_complete=user.onboarding_complete,
                            organization_id=str(user.organization_id) if user.organization_id else None,
                            org_role=user.org_role if user.organization_id else None,
                            team_id=str(user.team_id) if user.team_id else None,
                            team_role=user.team_role if user.team_id else None,
                            is_admin=False if is_trial else bool(user.is_admin),
                            is_trial=is_trial,
                            trial_status=trial_status,
                            trial_expires_at=trial_expires_at,
                            permissions=sorted(list(perms)),
                        )

        # 2d. Fallback for legacy user.api_key verification (supports both SHA-256 hashed and plaintext)
        import hashlib
        hashed_api_key = hashlib.sha256(api_key.encode()).hexdigest()
        from sqlalchemy.orm import joinedload
        from suspensionlab.backend.database.rls import set_session_tenant_context
        legacy_res = await db.execute(
            select(User).options(
                joinedload(User.team),
                joinedload(User.organization)
            ).where(
                or_(User.api_key == hashed_api_key, User.api_key == api_key),
                User.deleted_at == None
            )
        )
        user = legacy_res.scalar_one_or_none()
        if user:
            request.state.user_id = str(user.id)
            log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
            effective_plan = user.plan
            if user.organization and user.organization.plan:
                effective_plan = user.organization.plan
            elif user.team and user.team.plan:
                effective_plan = user.team.plan

            perms = set()
            if user.team_id and user.team_role:
                perms.update(get_role_permissions(user.team_role))
            if user.organization_id and user.org_role:
                perms.update(get_role_permissions(user.org_role))
            if user.is_admin:
                perms.update([p.value for p in Permission])
            if not user.team_id and not user.organization_id:
                perms.update(get_role_permissions("solo"))

            await set_session_tenant_context(
                db,
                organization_id=str(user.organization_id) if user.organization_id else None,
                team_id=str(user.team_id) if user.team_id else None,
                user_id=str(user.id),
                is_super_admin=bool(user.is_admin),
            )

            from suspensionlab.backend.database.models.trial import Trial
            trial_check = await db.execute(
                select(Trial).where(
                    or_(Trial.user_id == user.id, Trial.organization_id == user.organization_id),
                    Trial.deleted_at.is_(None)
                )
            )
            trial = trial_check.scalar_one_or_none()
            is_trial = _is_user_trial(trial, user.plan, user.organization)
            trial_status = None
            trial_expires_at = None
            if trial and getattr(trial, "status", None) != "CONVERTED":
                if trial.is_expired():
                    trial.status = "EXPIRED"
                trial_status = trial.status
                trial_expires_at = _format_trial_expiry(trial)

            return UserContext(
                user_id=str(user.id),
                plan=effective_plan,
                email=user.email,
                name=user.name or "",
                onboarding_complete=user.onboarding_complete,
                organization_id=str(user.organization_id) if user.organization_id else None,
                org_role=user.org_role if user.organization_id else None,
                team_id=str(user.team_id) if user.team_id else None,
                team_role=user.team_role if user.team_id else None,
                is_admin=False if is_trial else bool(user.is_admin),
                is_trial=is_trial,
                trial_status=trial_status,
                trial_expires_at=trial_expires_at,
                permissions=sorted(list(perms)),
            )

        # API key provided but invalid
        log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "Invalid API key"})
        raise AuthenticationError("Invalid API key.")

    # ── 3. No credentials found ───────────────────────────────────────────
    log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "No credentials provided"})
    raise AuthenticationError("Authentication required. Provide a Bearer token or X-API-Key header.")


async def optional_verify_api_key(
    request:  Request,
    api_key:  str | None = Header(alias="X-API-Key",      default=None),
    bearer:   str | None = Header(alias="Authorization",  default=None),
    db:       AsyncSession = Depends(get_db_dependency),
) -> UserContext | None:
    """
    Authenticate if credentials are provided. Returns None if no credentials are provided.
    If credentials are provided but invalid or expired, fails closed with 401.
    """
    cookie_token = request.cookies.get("sl_token") or request.cookies.get("access_token")
    if not api_key and not bearer and not cookie_token:
        return None
    return await verify_api_key(request, api_key, bearer, db)


def require_plan(minimum_plan: str):
    """
    FastAPI dependency factory that enforces a minimum plan tier.
    Usage:  Depends(require_plan(PlanTier.PRO))
    """
    async def _check(user: UserContext = Depends(verify_api_key)):
        plan_key = _normalize_plan_key(user.plan)
        is_trial_user = bool(user.is_trial or plan_key == PlanTier.TRIAL.value)
        trial_expired = is_trial_user and _is_trial_context_expired(user)

        if is_trial_user:
            user_level = 0 if trial_expired else max(PLAN_LEVELS.get(plan_key, 0), PLAN_LEVELS[PlanTier.TRIAL])
        else:
            user_level = PLAN_LEVELS.get(plan_key, 0)

        required_key = _normalize_plan_key(minimum_plan)
        required = PLAN_LEVELS.get(required_key, 0)
        if user_level < required:
            detail = (
                f"Your trial has expired. This feature requires the {required_key} plan. "
                f"Upgrade at /pricing to unlock it."
                if trial_expired
                else f"This feature requires the {required_key} plan. "
                     f"Upgrade at /pricing to unlock it."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail,
            )
        return user
    return _check
