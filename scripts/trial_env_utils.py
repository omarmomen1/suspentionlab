"""
scripts/trial_env_utils.py
==========================
Shared helper for trial environment initialization and secret management.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_TRIAL_FILE = PROJECT_ROOT / ".env.trial"
DATA_DIR = PROJECT_ROOT / "data"


def load_or_create_trial_env() -> dict[str, str]:
    """Ensure .env.trial exists with 32+ character cryptographically secure secrets and load into os.environ."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    trial_db_path = DATA_DIR / "trial_suspensionlab.db"
    db_url = f"sqlite+aiosqlite:///{trial_db_path.as_posix()}"

    secrets_dict: dict[str, str] = {}
    if ENV_TRIAL_FILE.exists():
        with open(ENV_TRIAL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    secrets_dict[k.strip()] = v.strip()

    updated = False
    if secrets_dict.get("ENVIRONMENT") != "TRIAL":
        secrets_dict["ENVIRONMENT"] = "TRIAL"
        updated = True

    if "DATABASE_URL" not in secrets_dict:
        secrets_dict["DATABASE_URL"] = db_url
        updated = True

    if "TRIAL_JWT_SECRET" not in secrets_dict or len(secrets_dict["TRIAL_JWT_SECRET"]) < 32:
        secrets_dict["TRIAL_JWT_SECRET"] = secrets.token_hex(32)
        updated = True

    # Also map JWT_SECRET_KEY and API_KEY for backend Settings
    if "JWT_SECRET_KEY" not in secrets_dict or len(secrets_dict["JWT_SECRET_KEY"]) < 32:
        secrets_dict["JWT_SECRET_KEY"] = secrets_dict["TRIAL_JWT_SECRET"]
        updated = True

    if "TRIAL_API_KEY" not in secrets_dict or len(secrets_dict["TRIAL_API_KEY"]) < 32:
        secrets_dict["TRIAL_API_KEY"] = f"sk_trial_{secrets.token_hex(32)}"
        updated = True

    if "API_KEY" not in secrets_dict or len(secrets_dict["API_KEY"]) < 32:
        secrets_dict["API_KEY"] = secrets_dict["TRIAL_API_KEY"]
        updated = True

    if "TRIAL_METRICS_PASS" not in secrets_dict or len(secrets_dict["TRIAL_METRICS_PASS"]) < 32:
        secrets_dict["TRIAL_METRICS_PASS"] = secrets.token_hex(20)
        updated = True

    if "METRICS_PASSWORD" not in secrets_dict:
        secrets_dict["METRICS_PASSWORD"] = secrets_dict["TRIAL_METRICS_PASS"]
        updated = True

    if "METRICS_USERNAME" not in secrets_dict:
        secrets_dict["METRICS_USERNAME"] = "trial_admin"
        updated = True

    if "TRIAL_EXTERNAL_URL" not in secrets_dict:
        secrets_dict["TRIAL_EXTERNAL_URL"] = "https://trial.suspensionlab.com"
        updated = True

    if "APP_BASE_URL" not in secrets_dict:
        secrets_dict["APP_BASE_URL"] = secrets_dict["TRIAL_EXTERNAL_URL"]
        updated = True

    if "ALLOW_ORIGINS" not in secrets_dict:
        secrets_dict["ALLOW_ORIGINS"] = f"{secrets_dict['TRIAL_EXTERNAL_URL']},http://localhost:3000,http://127.0.0.1:3000,http://127.0.0.1:3001"
        updated = True

    if updated or not ENV_TRIAL_FILE.exists():
        with open(ENV_TRIAL_FILE, "w", encoding="utf-8") as f:
            f.write("# SuspensionLab PRO — Auto-Generated Hardened Trial Configuration\n")
            for k, v in sorted(secrets_dict.items()):
                f.write(f"{k}={v}\n")

    # Inject into current process environment
    for k, v in secrets_dict.items():
        os.environ[k] = v

    return secrets_dict
