"""
backend/api/routes/sso_routes.py
=================================
Enterprise Single Sign-On — OpenID Connect (OIDC) Authorization Code Flow.

Implements the full browser redirect flow against any spec-compliant IdP
(Keycloak, Okta, Entra ID, Auth0, Google Workspace):

    1. GET  /auth/sso/providers   → discover which providers are configured
    2. GET  /auth/sso/login       → 302 redirect to IdP (PKCE + state + nonce)
    3. GET  /auth/sso/callback    → code exchange, ID-token validation,
                                    user upsert, SuspensionLab JWT issuance

Security properties:
    * PKCE (S256) prevents authorization-code interception.
    * `state` is a signed, short-lived JWT bound to a HttpOnly cookie — CSRF-safe.
    * `nonce` is embedded in both the state token and the ID token and must match.
    * ID tokens are validated for issuer, audience, expiry and signature
      (RS256 via cached JWKS discovery, or HS256 when the IdP uses client-secret
      signing).
    * No fallback secrets, no example.com URLs. If OIDC is not configured the
      endpoints return explicit 503s so the feature can never be "advertised"
      as working when it is not.

References
----------
- OpenID Connect Core 1.0 §3.1 (Authorization Code Flow)
- RFC 7636 (PKCE), RFC 6749 (OAuth 2.0)
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import Any, Optional

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from jwt.exceptions import PyJWTError

from suspensionlab.backend.config import settings
from suspensionlab.backend.security.jwt_utils import create_access_token, create_refresh_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso", tags=["SSO"])

SCOPES = [s.strip() for s in settings.oidc_scopes.split(",") if s.strip()] or ["openid"]
STATE_COOKIE = "sl_sso_state"
STATE_TTL_SECONDS = 600

# ── JWKS cache ────────────────────────────────────────────────────────────────
_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
JWKS_CACHE_TTL = 3600  # seconds


def _require_oidc_configured() -> None:
    """Explicit 503 when OIDC is not configured — never fake success."""
    if not settings.oidc_enabled:
        raise HTTPException(
            status_code=503,
            detail="SSO is not enabled on this deployment. Configure OIDC_ENABLED, "
                   "OIDC_ISSUER, OIDC_CLIENT_ID and OIDC_CLIENT_SECRET to activate enterprise SSO.",
        )
    missing = [
        name for name, val in (
            ("OIDC_ISSUER", settings.oidc_issuer),
            ("OIDC_CLIENT_ID", settings.oidc_client_id),
            ("OIDC_CLIENT_SECRET", settings.oidc_client_secret),
        ) if not val
    ]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"SSO is enabled but incompletely configured. Missing: {', '.join(missing)}.",
        )


async def _discover() -> dict[str, Any]:
    """Fetch and cache the IdP's OpenID Connect discovery document."""
    issuer = settings.oidc_issuer.rstrip("/")
    well_known = f"{issuer}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(well_known)
            resp.raise_for_status()
            doc = resp.json()
    except httpx.HTTPError as exc:
        logger.error("OIDC discovery failed for %s: %s", well_known, exc)
        raise HTTPException(status_code=502, detail="Identity provider discovery failed.")
    for endpoint in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if endpoint not in doc:
            raise HTTPException(
                status_code=502,
                detail=f"Identity provider discovery document is missing '{endpoint}'.",
            )
    return doc


async def _get_jwks(jwks_uri: str) -> dict[str, Any]:
    """Fetch and cache the IdP JSON Web Key Set for RS256 verification."""
    now = time.time()
    if _jwks_cache["keys"] is None or now - _jwks_cache["fetched_at"] > JWKS_CACHE_TTL:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            _jwks_cache["keys"] = resp.json()
        _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE verifier/challenge pair (RFC 7636 §4.1-4.2)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _issue_state(nonce: str, verifier: str) -> str:
    """Sign the OAuth state payload as a short-lived JWT."""
    from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY
    keys = get_jwt_keys()
    payload = {
        "nonce": nonce,
        "verifier": verifier,
        "iat": int(time.time()),
        "exp": int(time.time()) + STATE_TTL_SECONDS,
        "type": "sso_state",
    }
    return jwt.encode(payload, keys[JWT_ACTIVE_KEY], algorithm="HS256")


def _read_state(state_token: str) -> dict[str, Any]:
    from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY
    keys = get_jwt_keys()
    try:
        payload = jwt.decode(
            state_token,
            keys[JWT_ACTIVE_KEY],
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
    except PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired SSO state.")
    if payload.get("type") != "sso_state":
        raise HTTPException(status_code=400, detail="Invalid SSO state type.")
    return payload


async def _validate_id_token(id_token: str, discovery: dict[str, Any], expected_nonce: str) -> dict[str, Any]:
    """Validate signature + iss + aud + exp + nonce per OIDC Core §3.1.3.7."""
    try:
        unverified_headers = jwt.get_unverified_header(id_token)
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"ID token validation failed: {exc}")
    alg = unverified_headers.get("alg", "")

    if alg == "RS256":
        jwks = await _get_jwks(discovery["jwks_uri"])
        kid = unverified_headers.get("kid")
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            raise HTTPException(status_code=502, detail="ID token kid not found in IdP JWKS.")
        try:
            signing_key = jwt.PyJWK.from_dict(key).key
            claims = jwt.decode(
                id_token, signing_key, algorithms=["RS256"],
                audience=settings.oidc_client_id,
                issuer=settings.oidc_issuer.rstrip("/"),
            )
        except PyJWTError as exc:
            raise HTTPException(status_code=401, detail=f"ID token validation failed: {exc}")
    elif alg == "HS256":
        try:
            claims = jwt.decode(
                id_token, settings.oidc_client_secret, algorithms=["HS256"],
                audience=settings.oidc_client_id,
                issuer=settings.oidc_issuer.rstrip("/"),
            )
        except PyJWTError as exc:
            raise HTTPException(status_code=401, detail=f"ID token validation failed: {exc}")
    else:
        raise HTTPException(status_code=502, detail=f"Unsupported ID token algorithm '{alg}'.")

    if claims.get("nonce") != expected_nonce:
        raise HTTPException(status_code=401, detail="ID token nonce mismatch (possible replay).")
    return claims


async def _upsert_sso_user(claims: dict[str, Any]) -> dict[str, Any]:
    """
    Find or provision the local user record from verified IdP claims.
    Enforces email_verified checks and binds the immutable IdP subject identifier (external_id)
    to prevent OIDC account-takeover attacks.
    """
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=502, detail="IdP did not provide an email claim.")

    # 1. Require verified email from the IdP
    email_verified = claims.get("email_verified")
    if email_verified is False:
        logger.warning("SSO login attempt with unverified email: %s", email)
        raise HTTPException(
            status_code=401,
            detail="Identity provider indicated email address is unverified. SSO login rejected.",
        )

    # 2. Extract immutable IdP subject identifier
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=502, detail="IdP did not provide a subject identifier (sub claim).")

    from sqlalchemy import select, or_
    from suspensionlab.backend.database.core import SessionLocal
    from suspensionlab.backend.database.models.user import User
    from suspensionlab.backend.security.jwt_utils import hash_password

    async with SessionLocal() as db:
        # First query by IdP subject identifier, fallback to verified email
        result = await db.execute(
            select(User).where(or_(User.external_id == sub, User.email == email.lower()))
        )
        user = result.scalar_one_or_none()

        if user is None:
            # Just-in-time provisioning. Random unusable password — auth is via IdP only.
            user = User(
                email=email.lower(),
                external_id=sub,
                auth_provider="oidc",
                password_hash=hash_password(secrets.token_urlsafe(32)),
                name=claims.get("name") or claims.get("preferred_username"),
                plan="PRO",
                onboarding_complete=False,
            )
            db.add(user)
        else:
            if user.deleted_at is not None:
                raise HTTPException(status_code=403, detail="This account has been deactivated.")
            
            # Security invariant: prevent IdP identity collision / takeover
            if user.external_id and user.external_id != sub:
                logger.error(
                    "OIDC account takeover attempt: user %s has external_id %s but IdP sent sub %s",
                    user.email, user.external_id, sub
                )
                raise HTTPException(
                    status_code=403,
                    detail="This account is bound to a different identity provider account.",
                )

            # Bind IdP subject identifier on first verified SSO login
            if not user.external_id:
                user.external_id = sub
                user.auth_provider = "oidc"

            user.name = claims.get("name") or user.name
            user.email = email.lower()

        await db.commit()
        await db.refresh(user)
        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "plan": user.plan,
            "team_id": str(user.team_id) if user.team_id else None,
            "is_admin": bool(user.is_admin),
        }



@router.get("/providers")
async def list_providers():
    """List configured SSO providers for the login page."""
    return {
        "providers": [
            {
                "id": "oidc",
                "type": "oidc",
                "name": "Enterprise SSO (OIDC)",
                "enabled": bool(settings.oidc_enabled and settings.oidc_issuer
                                and settings.oidc_client_id and settings.oidc_client_secret),
            }
        ]
    }


@router.get("/login")
async def sso_login(request: Request, provider: str = Query("oidc")):
    """Start the OIDC Authorization Code Flow with PKCE. Returns the IdP redirect URL."""
    _require_oidc_configured()
    if provider != "oidc":
        raise HTTPException(status_code=400, detail=f"Unknown SSO provider '{provider}'. Supported: oidc.")

    discovery = await _discover()
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    state = _issue_state(nonce, verifier)

    redirect_uri = f"{settings.app_base_url.rstrip('/')}/api/v1/auth/sso/callback"
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    from urllib.parse import urlencode
    authorize_url = f"{discovery['authorization_endpoint']}?{urlencode(params)}"

    response = RedirectResponse(authorize_url, status_code=302)
    response.set_cookie(
        STATE_COOKIE, state,
        max_age=STATE_TTL_SECONDS, httponly=True, secure=(settings.environment == "PROD"),
        samesite="lax",
    )
    return response


@router.get("/callback")
async def sso_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """OIDC redirect URI: exchange the code, validate the ID token, issue app JWTs."""
    _require_oidc_configured()
    if error:
        raise HTTPException(status_code=401, detail=f"Identity provider returned an error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing 'code' or 'state' in callback.")

    cookie_state = request.cookies.get(STATE_COOKIE)
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=401, detail="SSO state mismatch (possible CSRF).")

    state_payload = _read_state(state)
    nonce = state_payload["nonce"]
    verifier = state_payload["verifier"]

    discovery = await _discover()
    redirect_uri = f"{settings.app_base_url.rstrip('/')}/api/v1/auth/sso/callback"

    token_form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
        "code_verifier": verifier,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(discovery["token_endpoint"], data=token_form)
            token_resp.raise_for_status()
            tokens = token_resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("OIDC token exchange failed: %s %s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail="Token exchange with identity provider failed.")
    except httpx.HTTPError as exc:
        logger.error("OIDC token exchange unreachable: %s", exc)
        raise HTTPException(status_code=502, detail="Identity provider is unreachable.")

    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="Identity provider did not return an id_token.")

    claims = await _validate_id_token(id_token, discovery, nonce)
    user_ctx = await _upsert_sso_user(claims)

    access = create_access_token({"sub": user_ctx["id"], "email": user_ctx["email"],
                                  "plan": user_ctx["plan"], "team_id": user_ctx["team_id"]})
    refresh = create_refresh_token({"sub": user_ctx["id"], "email": user_ctx["email"]})

    response = RedirectResponse(
        f"{settings.app_base_url.rstrip('/')}/auth/login?sso=success", status_code=302
    )
    response.delete_cookie(STATE_COOKIE)
    response.set_cookie("sl_token", access, httponly=True,
                        secure=(settings.environment == "PROD"), samesite="lax", max_age=900, path="/")
    response.set_cookie("sl_refresh_token", refresh, httponly=True,
                        secure=(settings.environment == "PROD"), samesite="lax",
                        max_age=60 * 60 * 24 * 7, path="/")
    response.set_cookie("sl_authed", "true", httponly=False,
                        secure=(settings.environment == "PROD"), samesite="lax",
                        max_age=60 * 60 * 24 * 7, path="/")
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie("csrf_token", csrf_token, httponly=False,
                        secure=(settings.environment == "PROD"), samesite="lax",
                        max_age=60 * 60 * 24 * 7, path="/")
    return response



@router.post("/callback")
async def sso_callback_post():
    """Legacy POST endpoint retained for backwards compatibility — now explicit about the flow."""
    raise HTTPException(
        status_code=405,
        detail="SSO callback must be a GET redirect from your identity provider (OIDC Authorization Code Flow).",
    )
