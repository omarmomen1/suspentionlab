#!/usr/bin/env python3
"""
CLI utility to mint self-issued signed SuspensionLab license keys.

Examples:
    python scripts/generate_license_key.py --plan PRO --days 30
    python scripts/generate_license_key.py --plan ENTERPRISE --days 365 --max-uses 10
    python scripts/generate_license_key.py --plan ENT --days 365 --raw
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from suspensionlab.backend.security.license_keys import (  # noqa: E402
    LicenseConfigError,
    generate_license_key,
    normalize_license_plan,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HMAC-SHA256 signed SLPRO-PRO-... / SLPRO-ENT-... license keys."
    )
    parser.add_argument(
        "--plan",
        required=True,
        help="Target plan tier: PRO, ENTERPRISE, or ENT.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Validity duration in days from now (default: 365). Ignored if --exp is set.",
    )
    parser.add_argument(
        "--exp",
        type=int,
        default=None,
        help="Explicit Unix timestamp for expiration (overrides --days).",
    )
    parser.add_argument(
        "--max-uses",
        type=int,
        default=1,
        help="Maximum uses encoded in the license payload (default: 1).",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="Optional signing secret override (defaults to settings.jwt_secret_key / JWT_SECRET_KEY / JWT_KEYS).",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print only the generated license key string.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan_tier = normalize_license_plan(args.plan)
        exp_ts = args.exp if args.exp is not None else int(time.time()) + args.days * 86400
        key = generate_license_key(
            plan_tier,
            max_uses=args.max_uses,
            exp=exp_ts,
            secret_override=args.secret,
        )
    except (ValueError, LicenseConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.raw:
        print(key)
        return 0

    expires_iso = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()
    print(f"Plan:      {plan_tier.value}")
    print(f"Max Uses:  {args.max_uses}")
    print(f"Expires:   {expires_iso}")
    print(f"Key:       {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
