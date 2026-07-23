import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List

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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("api_key")
    @classmethod
    def check_api_key_in_prod(cls, v: str, info) -> str:
        env = info.data.get("environment", "DEV")
        if env == "PROD" and v == "dev_secret_key":
            raise ValueError("api_key must be configured in PROD environment.")
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
