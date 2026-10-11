#!/usr/bin/env python3
"""
scripts/manage_trial.py
=======================
Owner CLI to inspect, extend, or simulate expiration for evaluation accounts.
Directly communicates with the trial database without public admin APIs.

Usage:
  # Check status:
  python scripts/manage_trial.py --email engineer@race-engineering.com --inspect

  # Extend trial by 7 days:
  python scripts/manage_trial.py --email engineer@race-engineering.com --extend-days 7 --add-sims 25

  # Manually expire trial:
  python scripts/manage_trial.py --email engineer@race-engineering.com --expire
"""
from __future__ import annotations

import os
import sys
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.trial_env_utils import load_or_create_trial_env
load_or_create_trial_env()


async def handle_manage_action(
    identifier: str,
    inspect_only: bool,
    extend_days: int | None,
    add_sims: int | None,
    expire: bool,
    activate: bool,
    db_url_override: str | None = None,
):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from suspensionlab.backend.services.trial_service import TrialService

    db_url = db_url_override or os.getenv("DATABASE_URL")
    if not db_url:
        sqlite_path = PROJECT_ROOT / "data" / "trial_suspensionlab.db"
        db_url = f"sqlite+aiosqlite:///{sqlite_path.as_posix()}"

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as db:
        if expire:
            # Force expiration
            from sqlalchemy import select, or_
            from suspensionlab.backend.database.models.trial import Trial
            from suspensionlab.backend.database.models.user import User

            res = await db.execute(
                select(Trial)
                .join(User, Trial.user_id == User.id)
                .where(
                    or_(
                        Trial.contact_email == identifier.lower().strip(),
                        User.email == identifier.lower().strip(),
                    ),
                    Trial.deleted_at.is_(None),
                )
            )
            trial = res.scalar_one_or_none()
            if not trial:
                print(f"Error: Trial not found for identifier '{identifier}'")
                return

            trial.status = "EXPIRED"
            trial.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            await db.commit()
            print(f"\n[OK] Trial for '{identifier}' has been manually set to EXPIRED.")
            print(f"     Status: {trial.status}, Expires At: {trial.expires_at.isoformat()}\n")

        elif activate or (extend_days is not None or add_sims is not None):
            res = await TrialService.extend_trial(
                db=db,
                identifier=identifier,
                additional_days=extend_days or 0,
                additional_simulations=add_sims or 0,
                new_status="ACTIVE",
            )
            print("\n" + "=" * 60)
            print("  SuspensionLab PRO — Trial Extended / Activated")
            print("=" * 60)
            print(f"  Identifier:        {identifier}")
            print(f"  Status:            {res['status']}")
            print(f"  Expires At:        {res['expires_at']}")
            print(f"  Days Remaining:    {res['days_remaining']}")
            print(f"  Simulations Cap:   {res['simulation_run_limit']}")
            print(f"  Simulations Left:  {res['simulations_remaining']}")
            print("=" * 60 + "\n")

        # Always print summary if inspect_only
        if inspect_only or not (expire or activate or extend_days or add_sims):
            summary = await TrialService.get_trial_summary(db=db, identifier=identifier)
            print("\n" + "=" * 60)
            print("  SuspensionLab PRO — Trial Summary")
            print("=" * 60)
            print(f"  Trial ID:          {summary['trial_id']}")
            print(f"  Evaluator Email:   {summary['user_email']}")
            print(f"  Evaluator Name:    {summary['user_name']}")
            print(f"  Evaluation Title:  {summary['evaluation_title']}")
            print(f"  Status:            {summary['status']}")
            print(f"  Expires At:        {summary['expires_at']}")
            print(f"  Days Remaining:    {summary['days_remaining']}")
            print(f"  Simulations Used:  {summary['simulation_run_count']} / {summary['simulation_run_limit']}")
            print("-" * 60)
            checklist_items = summary["checklist"].get("items", {})
            print(f"  Checklist Progress ({summary['checklist'].get('completed_count', 0)} / {summary['checklist'].get('total_count', 6)}):")
            for k, is_done in checklist_items.items():
                status_icon = "[X]" if is_done else "[ ]"
                title = k.replace("_", " ").title()
                print(f"    {status_icon} {title}")
            if summary.get("feedback"):
                print("-" * 60)
                print("  Submitted Customer Feedback:")
                print(f"    Most Valuable:    {summary['feedback'].get('most_valuable')}")
                print(f"    Prevented Usage:  {summary['feedback'].get('prevented_usage')}")
            print("=" * 60 + "\n")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Manage SuspensionLab PRO trial evaluations.")
    parser.add_argument("--email", required=True, help="Customer evaluator email or trial UUID")
    parser.add_argument("--inspect", action="store_true", help="Print full trial usage summary")
    parser.add_argument("--extend-days", type=int, help="Extend trial by N days")
    parser.add_argument("--add-sims", type=int, help="Add N simulation executions to quota")
    parser.add_argument("--expire", action="store_true", help="Manually expire the trial")
    parser.add_argument("--activate", action="store_true", help="Set status back to ACTIVE")
    parser.add_argument("--db", help="Database URL override")

    args = parser.parse_args()

    asyncio.run(
        handle_manage_action(
            identifier=args.email,
            inspect_only=args.inspect,
            extend_days=args.extend_days,
            add_sims=args.add_sims,
            expire=args.expire,
            activate=args.activate,
            db_url_override=args.db,
        )
    )


if __name__ == "__main__":
    main()
