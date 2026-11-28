"""
backend/api/routes/saml_routes.py
=================================
Enterprise SAML 2.0 Single Sign-On Routes (SP-Initiated, ACS, Metadata, IdP-Initiated).
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response as PlainResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.config import settings
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.jwt_utils import create_access_token, create_refresh_token, hash_password
from suspensionlab.backend.security.saml import (
    generate_sp_metadata_xml,
    generate_relay_state,
    validate_relay_state,
    create_authn_request,
    parse_and_validate_saml_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/saml", tags=["SAML 2.0 SSO"])


def _require_saml_enabled() -> None:
    """Fail-closed gate for hand-rolled SAML login/ACS routes until python3-saml/signxml migration."""
    enabled = settings.enable_saml_sso or os.getenv("ENABLE_SAML_SSO", "false").lower() in ("1", "true", "yes")
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML SSO is currently disabled",
        )


@router.get("/metadata", response_class=PlainResponse)
async def get_saml_metadata(
    org_slug: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Serve SP EntityDescriptor Metadata XML."""
    sp_entity_id = f"{settings.app_base_url.rstrip('/')}/api/v1/auth/saml/metadata"
    acs_url = f"{settings.app_base_url.rstrip('/')}/api/v1/auth/saml/acs"
    org_name = "SuspensionLab PRO Enterprise"

    if org_slug:
        org = (await db.execute(select(Organization).where(Organization.slug == org_slug.lower()))).scalar_one_or_none()
        if org:
            sp_entity_id = org.saml_sp_entity_id or f"{settings.app_base_url.rstrip('/')}/api/v1/auth/saml/{org.slug}/metadata"
            org_name = f"SuspensionLab PRO — {org.name}"

    xml_metadata = generate_sp_metadata_xml(sp_entity_id=sp_entity_id, acs_url=acs_url, org_name=org_name)
    return PlainResponse(content=xml_metadata, media_type="application/xml")


@router.get("/login")
async def saml_login(
    org_slug: str = Query(..., description="Organization slug initiating SAML login"),
    return_to: str = Query("/dashboard"),
    db: AsyncSession = Depends(get_db_dependency),
):
    """SP-Initiated SAML Login redirect."""
    _require_saml_enabled()
    org = (
        await db.execute(select(Organization).where(Organization.slug == org_slug.lower(), Organization.deleted_at == None))
    ).scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{org_slug}' not found.")

    if not org.saml_enabled or not org.saml_idp_sso_url:
        raise HTTPException(
            status_code=400,
            detail=f"SAML SSO is not configured or enabled for organization '{org.name}'.",
        )

    sp_entity_id = org.saml_sp_entity_id or f"{settings.app_base_url.rstrip('/')}/api/v1/auth/saml/{org.slug}/metadata"
    acs_url = f"{settings.app_base_url.rstrip('/')}/api/v1/auth/saml/acs"

    relay_state = generate_relay_state(org_id=str(org.id), return_to=return_to)
    redirect_url, request_id = create_authn_request(
        idp_sso_url=org.saml_idp_sso_url,
        sp_entity_id=sp_entity_id,
        acs_url=acs_url,
        relay_state=relay_state,
    )

    return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)


@router.post("/acs")
async def saml_acs(
    request: Request,
    SAMLResponse: str = Form(...),
    RelayState: Optional[str] = Form(None),
    org_slug: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Assertion Consumer Service (ACS) endpoint handling SAMLResponse POST."""
    _require_saml_enabled()
    org: Optional[Organization] = None
    target_return_to = "/dashboard"

    if RelayState:
        try:
            org_id_str, target_return_to = validate_relay_state(RelayState)
            org = (await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id_str)))).scalar_one_or_none()
        except Exception as e:
            logger.warning("RelayState validation error in ACS: %s", e)
            raise HTTPException(status_code=400, detail=f"Invalid RelayState token: {e}")

    if not org and org_slug:
        org = (await db.execute(select(Organization).where(Organization.slug == org_slug.lower()))).scalar_one_or_none()


    if not org:
        raise HTTPException(status_code=400, detail="Unable to identify target SAML organization.")

    sp_entity_id = org.saml_sp_entity_id or f"{settings.app_base_url.rstrip('/')}/api/v1/auth/saml/{org.slug}/metadata"
    acs_url = f"{settings.app_base_url.rstrip('/')}/api/v1/auth/saml/acs"
    request_acs_url = str(request.url).split("?")[0]

    try:
        validated_assertion = parse_and_validate_saml_response(
            saml_response_b64=SAMLResponse,
            expected_audience=sp_entity_id,
            expected_recipient=[acs_url, request_acs_url],
            expected_idp_entity_id=org.saml_idp_entity_id,
            idp_x509_cert_pem=org.saml_idp_x509_cert,
        )
    except Exception as exc:
        logger.error("SAML assertion validation error: %s", exc)
        raise HTTPException(status_code=401, detail=f"SAML Assertion validation failed: {exc}")

    email = validated_assertion["email"].lower()
    name = validated_assertion["name"]

    # JIT Provisioning or account linking
    user = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            name=name,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            organization_id=org.id,
            org_role="MEMBER",
            plan=org.plan,
            auth_provider="saml",
            external_id=validated_assertion["name_id"],
            onboarding_complete=True,
        )
        db.add(user)
    else:
        if user.deleted_at is not None:
            raise HTTPException(status_code=403, detail="Your account has been deactivated.")
        user.organization_id = org.id
        user.auth_provider = "saml"
        user.external_id = validated_assertion["name_id"]
        if not user.name:
            user.name = name

    await db.flush()

    # Log SAML audit event
    audit_ev = AuditLog(
        event="SAML_LOGIN_SUCCESS",
        user_id=user.id,
        organization_id=org.id,
        ip=request.client.host if request.client else None,
        event_data={"name_id": validated_assertion["name_id"], "assertion_id": validated_assertion["assertion_id"]},
    )
    db.add(audit_ev)
    await db.commit()
    await db.refresh(user)

    # Issue Application JWTs
    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "plan": user.plan,
        "organization_id": str(org.id),
        "team_id": str(user.team_id) if user.team_id else None,
    })
    refresh_token = create_refresh_token({
        "sub": str(user.id),
        "email": user.email,
    })

    redirect_dest = f"{settings.app_base_url.rstrip('/')}{target_return_to}"
    resp = RedirectResponse(redirect_dest, status_code=status.HTTP_302_FOUND)
    resp.set_cookie("sl_token", access_token, httponly=True, secure=(settings.environment == "PROD"), samesite="lax", max_age=900, path="/")
    resp.set_cookie("sl_refresh_token", refresh_token, httponly=True, secure=(settings.environment == "PROD"), samesite="lax", max_age=60*60*24*7, path="/")
    resp.set_cookie("sl_authed", "true", httponly=False, secure=(settings.environment == "PROD"), samesite="lax", max_age=60*60*24*7, path="/")
    csrf_token = secrets.token_urlsafe(32)
    resp.set_cookie("csrf_token", csrf_token, httponly=False, secure=(settings.environment == "PROD"), samesite="lax", max_age=60*60*24*7, path="/")

    return resp
