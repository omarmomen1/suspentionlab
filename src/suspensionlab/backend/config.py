import os
import json
import re
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List

# Secrets that must NEVER be used in production.
_KNOWN_DEFAULT_SECRET_PATTERNS = re.compile(
    r"(dev_jwt_secret|dev_secret|changeme|change_me|secret_key|placeholder|"
    r"example|dummy|test_secret|123456|abcdef|qwerty)",
    re.IGNORECASE,
)
_MIN_SECRET_LENGTH = 32


def _validate_secret_strength(name: str, value: str, environment: str) -> None:
    """Reject weak/default cryptographic secrets in PROD. Fail-fast, no fallbacks."""
    if environment != "PROD":
        return
    if not value or not value.strip():
        raise ValueError(
            f"CRITICAL: {name} is empty in PROD environment. "
            f"Refusing to start — configure a cryptographically strong secret."
        )
    if len(value) < _MIN_SECRET_LENGTH:
        raise ValueError(
            f"CRITICAL: {name} is shorter than {_MIN_SECRET_LENGTH} characters in PROD. "
            f"Refusing to start — use a generated secret (e.g. `openssl rand -hex 32`)."
        )
    if _KNOWN_DEFAULT_SECRET_PATTERNS.search(value):
        raise ValueError(
            f"CRITICAL: {name} matches a known default/weak secret pattern in PROD. "
            f"Refusing to start — generate a unique random secret."
        )


def validate_prod_secrets() -> None:
    """
    Startup gate for production deployments.

    Validates every cryptographic secret used by the application and raises
    RuntimeError on any of the following conditions when ENVIRONMENT=PROD:
      * JWT_KEYS / JWT_SECRET_KEY missing entirely
      * Any JWT secret shorter than 32 characters
      * Any JWT secret matching a known default pattern (e.g. 'dev_jwt_secret_12345')
      * SCIM bearer token missing when SCIM is enabled

    Called from the FastAPI lifespan handler — the process refuses to boot
    rather than silently falling back to an insecure default.
    """
    env = os.getenv("ENVIRONMENT", "DEV")
    if env != "PROD":
        return

    # ── JWT signing secrets ────────────────────────────────────────────────
    jwt_keys_env = os.getenv("JWT_KEYS")
    jwt_legacy = os.getenv("JWT_SECRET_KEY")
    active_kid = os.getenv("JWT_ACTIVE_KEY", "v1")

    keys: dict = {}
    if jwt_keys_env:
        try:
            keys = json.loads(jwt_keys_env)
        except Exception as exc:
            raise RuntimeError(f"CRITICAL: JWT_KEYS is not valid JSON: {exc}")
    if not keys and jwt_legacy:
        keys[active_kid] = jwt_legacy
    if not keys:
        raise RuntimeError(
            "CRITICAL: ENVIRONMENT=PROD but neither JWT_KEYS nor JWT_SECRET_KEY "
            "is configured. Refusing to start with unsigned/forgeable tokens."
        )
    if active_kid not in keys:
        raise RuntimeError(
            f"CRITICAL: JWT_ACTIVE_KEY '{active_kid}' not present in JWT_KEYS in PROD."
        )
    for kid, secret in keys.items():
        _validate_secret_strength(f"JWT key '{kid}'", str(secret), "PROD")

    # ── SCIM provisioning token ────────────────────────────────────────────
    scim_token = os.getenv("SCIM_BEARER_TOKEN", "")
    scim_enabled = os.getenv("SCIM_ENABLED", "false").lower() in ("1", "true", "yes")
    if scim_enabled:
        _validate_secret_strength("SCIM_BEARER_TOKEN", scim_token, "PROD")

    # ── OIDC client secret ─────────────────────────────────────────────────
    oidc_enabled = os.getenv("OIDC_ENABLED", "false").lower() in ("1", "true", "yes")
    if oidc_enabled:
        for var in ("OIDC_ISSUER", "OIDC_CLIENT_ID"):
            if not os.getenv(var):
                raise RuntimeError(f"CRITICAL: OIDC_ENABLED=true but {var} is not set.")
        _validate_secret_strength(
            "OIDC_CLIENT_SECRET", os.getenv("OIDC_CLIENT_SECRET", ""), "PROD"
        )


class Settings(BaseSettings):
    environment: str = "DEV"
    api_key: str = "dev_secret_key"
    allow_origins: str = "http://localhost:8501,http://localhost:3000,http://localhost:3001"
    
    rate_limit_optimize: str = "10/minute"
    rate_limit_simulate: str = "300/minute"
    rate_limit_checkout: str = "10/minute"
    rate_limit_login: str = "10/minute"
    rate_limit_auth: str = "5/minute"

    gumroad_product_permalink: str = "suspensionlab-pro"
    
    database_url: str = "sqlite+aiosqlite:///./data/suspensionlab.db"
    app_base_url: str = "http://localhost:3000"
    sentry_dsn: str = ""

    # ── Enterprise SSO (OIDC) ──────────────────────────────────────────────
    oidc_enabled: bool = False
    oidc_issuer: str = ""                 # e.g. https://idp.example.com/realms/suspensionlab
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid email profile"

    # ── Enterprise SCIM 2.0 provisioning ───────────────────────────────────
    scim_enabled: bool = False
    scim_bearer_token: str = ""           # IdP presents this as `Authorization: Bearer ...`
    scim_default_team_role: str = "Viewer"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("api_key")
    @classmethod
    def check_api_key_in_prod(cls, v: str, info) -> str:
        env = info.data.get("environment", "DEV")
        if env == "PROD":
            _validate_secret_strength("api_key", v, "PROD")
        return v

    @field_validator("database_url")
    @classmethod
    def check_db_url_in_prod(cls, v: str, info) -> str:
        env = info.data.get("environment", "DEV")
        if env == "PROD" and "sqlite" in v:
            raise ValueError("database_url must point to a proper database (e.g., PostgreSQL) in PROD environment, not SQLite.")
        return v

    @property
    def allow_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allow_origins.split(",") if o.strip()]

    @property
    def database_url_async(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

settings = Settings()
