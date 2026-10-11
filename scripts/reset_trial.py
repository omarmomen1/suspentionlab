#!/usr/bin/env python3
"""
scripts/reset_trial.py
======================
Owner CLI to cleanly reset an evaluator's trial workspace to a fresh
Formula Student Evaluation Garage state without destroying tenant isolation.

Features:
1. Deletes all user-created experiments, decisions, custom questions, and feedback.
2. Re-seeds the clean Formula Student baseline vehicle twin, setups, session, and hero question.
3. Resets trial expiration counter to 7 days (or configured days) and simulation runs to 0.
4. Optionally updates temporary password.

Usage:
  python scripts/reset_trial.py --email evaluator@apex-motorsport.com
  python scripts/reset_trial.py --email evaluator@apex-motorsport.com --password "NewPass123!45"
"""
from __future__ import annotations

import os
import sys
import argparse
import asyncio
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.trial_env_utils import load_or_create_trial_env
load_or_create_trial_env()


async def reset_evaluator(
    email: str,
    new_password: str | None = None,
    duration_days: int = 7,
    db_url_override: str | None = None,
):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from suspensionlab.backend.services.trial_service import TrialService

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

    clean_email = email.lower().strip()

    async with async_session() as db:
        result = await TrialService.reset_trial_organization(
            db=db,
            identifier=clean_email,
            new_password=new_password,
            duration_days=duration_days,
        )

    await engine.dispose()

    ext_url = os.getenv("TRIAL_EXTERNAL_URL", "https://trial.suspensionlab.com").rstrip("/")

    print("\n" + "=" * 72)
    print("      SUSPENSIONLAB PRO — EVALUATOR WORKSPACE RESET SUCCESSFUL")
    print("=" * 72)
    print(f"EVALUATOR EMAIL:      {result['contact_email']}")
    print(f"TRIAL STATUS:         {result['status']}")
    print(f"DAYS REMAINING:       {result['days_remaining']} Days")
    print(f"EXPIRES AT:           {result['expires_at']}")
    print(f"SIMULATIONS RUN:      0 / {result['simulation_run_limit']}")
    print(f"PRELOADED VEHICLE:    SLP-FS-EV-01 (Formula Student EV)")
    print(f"PRELOADED QUESTION:   Q-FS-01 (Front tire-load variation spike)")
    if new_password:
        print(f"UPDATED PASSWORD:     {new_password}")
    print("-" * 72)
    print(f"CUSTOMER LOGIN:       {ext_url}/login")
    print(f"CUSTOMER WORKSPACE:   {ext_url}/evaluation")
    print("=" * 72 + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="Reset an evaluator to clean Formula Student trial state.")
    parser.add_argument("--email", required=True, help="Evaluator email address")
    parser.add_argument("--password", help="Optional new temporary password")
    parser.add_argument("--days", type=int, default=7, help="Evaluation duration in days (default: 7)")
    parser.add_argument("--db", help="Database URL override")
    args = parser.parse_args()

    asyncio.run(
        reset_evaluator(
            email=args.email,
            new_password=args.password,
            duration_days=args.days,
            db_url_override=args.db,
        )
    )


if __name__ == "__main__":
    main()
