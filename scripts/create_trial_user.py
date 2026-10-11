#!/usr/bin/env python3
"""
scripts/create_trial_user.py
============================
Owner CLI to provision an isolated 7-day evaluation customer account.
Connects directly to the trial database without exposing admin APIs to the web.

Usage:
  python scripts/create_trial_user.py --email engineer@race-engineering.com --name "Alex Mercer" --days 7
"""
from __future__ import annotations

import os
import sys
import argparse
import secrets
import string
import asyncio
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.trial_env_utils import load_or_create_trial_env
load_or_create_trial_env()


def generate_secure_password(length: int = 16) -> str:
    """Generate a high-entropy temporary password meeting all complexity checks."""
    uppers = string.ascii_uppercase
    lowers = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*-_=+"
    all_chars = uppers + lowers + digits + symbols

    # Ensure at least 1 of each required class
    pwd = [
        secrets.choice(uppers),
        secrets.choice(lowers),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    pwd += [secrets.choice(all_chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


async def provision_user(
    email: str,
    name: str | None,
    team_name: str | None,
    duration_days: int,
    simulation_limit: int,
    password: str | None,
    external_url: str,
    db_url_override: str | None = None,
):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from suspensionlab.backend.database.core import Base
    from suspensionlab.backend.services.trial_service import TrialService

    # Resolve database URL
    db_url = db_url_override or os.getenv("DATABASE_URL")
    if not db_url:
        sqlite_path = PROJECT_ROOT / "data" / "trial_suspensionlab.db"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite+aiosqlite:///{sqlite_path.as_posix()}"

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Ensure schema exists in trial database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Resolve credentials
    clean_email = email.lower().strip()
    user_name = (name or clean_email.split("@")[0]).strip()
    plain_password = password or generate_secure_password(16)
    team = team_name or f"{user_name}'s Racing Team"

    async with async_session() as db:
        from fastapi import HTTPException
        from sqlalchemy import select
        from suspensionlab.backend.database.models.trial import Trial
        from suspensionlab.backend.database.models.user import User
        from suspensionlab.backend.database.models.organization import Organization
        import uuid as uuid_mod

        try:
            result = await TrialService.create_trial_organization(
                db=db,
                email=clean_email,
                password=plain_password,
                name=user_name,
                org_name=team,
                duration_days=duration_days,
                simulation_limit=simulation_limit,
            )
            trial_obj = result["trial"]
            org_obj = result["organization"]
            user_obj = result["user"]
        except Exception:
            # If user already exists, cleanly reset to fresh trial state
            await db.rollback()
            await TrialService.reset_trial_organization(
                db=db,
                identifier=clean_email,
                new_password=plain_password,
                duration_days=duration_days,
            )
            summary = await TrialService.get_trial_summary(db, clean_email)
            trial_res = await db.execute(select(Trial).where(Trial.id == uuid_mod.UUID(summary["trial_id"])))
            trial_obj = trial_res.scalar_one()
            user_res = await db.execute(select(User).where(User.id == uuid_mod.UUID(summary["user_id"])))
            user_obj = user_res.scalar_one()
            org_res = await db.execute(select(Organization).where(Organization.id == uuid_mod.UUID(summary["organization_id"])))
            org_obj = org_res.scalar_one()

    await engine.dispose()

    base_url = external_url.rstrip("/")
    expiration_str = trial_obj.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Print exact required customer onboarding package
    print("\n" + "=" * 72)
    print("      SUSPENSIONLAB PRO — EVALUATOR ONBOARDING CREDENTIALS")
    print("=" * 72)
    print(f"CUSTOMER URL:         {base_url}/login")
    print(f"USERNAME:             {clean_email}")
    print(f"TEMPORARY CREDENTIAL: {plain_password}")
    print(f"TRIAL EXPIRATION:     {expiration_str} ({duration_days} Days)")
    print("-" * 72)
    print(f"ORGANIZATION:         {team}")
    print(f"SIMULATION QUOTA:     {simulation_limit} Runs")
    print(f"PRELOADED VEHICLE:    SLP-FS-EV-01 (Formula Student EV)")
    print(f"DIRECT EVALUATION:    {base_url}/evaluation")
    print("=" * 72 + "\n")

    return {
        "email": clean_email,
        "password": plain_password,
        "trial_id": str(trial_obj.id),
        "organization_id": str(org_obj.id),
        "user_id": str(user_obj.id),
        "expires_at": trial_obj.expires_at.isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Create a dedicated SuspensionLab PRO trial user.")
    parser.add_argument("--email", required=True, help="Customer evaluator email address")
    parser.add_argument("--name", help="Customer evaluator full name")
    parser.add_argument("--org", "--team", dest="team", help="Customer evaluation organization / team name")
    parser.add_argument("--days", type=int, default=7, help="Evaluation duration in days (default: 7)")
    parser.add_argument("--sims", type=int, default=50, help="Simulation runs allowed (default: 50)")
    parser.add_argument("--password", help="Explicit password (auto-generated if omitted)")
    parser.add_argument(
        "--url",
        default=os.getenv("TRIAL_EXTERNAL_URL", "https://trial.suspensionlab.com"),
        help="External HTTPS base URL (default: https://trial.suspensionlab.com)",
    )
    parser.add_argument("--db", help="Database URL override")

    args = parser.parse_args()

    asyncio.run(
        provision_user(
            email=args.email,
            name=args.name,
            team_name=args.team,
            duration_days=args.days,
            simulation_limit=args.sims,
            password=args.password,
            external_url=args.url,
            db_url_override=args.db,
        )
    )


if __name__ == "__main__":
    main()
