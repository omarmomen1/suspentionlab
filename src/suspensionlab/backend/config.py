import os

class ConfigError(Exception):
    pass

def get_env_or_fail(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if not val:
        env = os.environ.get("ENVIRONMENT", "")
        if env == "PROD":
            raise ConfigError(f"Missing required secret {key} in PROD environment")
        if env not in ("DEV", "TEST", ""):
            raise ConfigError(
                f"Missing required secret {key} in {env} environment. "
                "Set ENVIRONMENT=DEV explicitly for local development defaults."
            )
        return default
    return val

class Settings:
    @property
    def environment(self) -> str:
        return os.environ.get("ENVIRONMENT", "DEV")

    @property
    def api_key(self) -> str:
        return get_env_or_fail("API_KEY", "dev_secret_key")
        
    @property
    def admin_api_key(self) -> str | None:
        return os.environ.get("ADMIN_API_KEY")
    
    @property
    def allow_origins(self) -> list[str]:
        raw = os.environ.get("ALLOW_ORIGINS", "http://localhost:8501,http://localhost:3000,http://localhost:3001")
        return [o.strip() for o in raw.split(",") if o.strip()]
        
    @property
    def rate_limit_optimize(self) -> str:
        return os.environ.get("RATE_LIMIT_OPTIMIZE", "1000/minute")

    @property
    def rate_limit_simulate(self) -> str:
        return os.environ.get("RATE_LIMIT_SIMULATE", "3000/minute")

    @property
    def rate_limit_checkout(self) -> str:
        return os.environ.get("RATE_LIMIT_CHECKOUT", "500/minute")

    @property
    def rate_limit_login(self) -> str:
        return os.environ.get("RATE_LIMIT_LOGIN", "500/minute")

    @property
    def rate_limit_auth(self) -> str:
        return os.environ.get("RATE_LIMIT_AUTH", "1000/minute")

    # ── Lemon Squeezy ────────────────────────────────────────────────────────
    @property
    def gumroad_product_permalink(self) -> str:
        return os.environ.get("GUMROAD_PRODUCT_PERMALINK", "suspensionlab-pro")

    # ── Database ──────────────────────────────────────────────────────────────
    @property
    def database_url(self) -> str:
        url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/suspensionlab.db")
        # Railway/Render provide postgres:// URIs; SQLAlchemy needs postgresql+asyncpg://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def app_base_url(self) -> str:
        return os.environ.get("APP_BASE_URL", "http://localhost:3000")

    # ── Sentry ────────────────────────────────────────────────────────────────
    @property
    def sentry_dsn(self) -> str:
        return os.environ.get("SENTRY_DSN", "")

settings = Settings()
