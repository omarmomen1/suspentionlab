import asyncio
import argparse
from sqlalchemy import select
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.user import User
from suspensionlab.shared.models import PlanTier

async def main():
    parser = argparse.ArgumentParser(description="Create a SuspensionLab user")
    parser.add_argument("--tier", default=PlanTier.FREE, choices=[PlanTier.FREE, PlanTier.PRO, PlanTier.ENTERPRISE], help="User tier")
    args = parser.parse_args()

    async with SessionLocal() as db:
        pass

        import secrets
        from suspensionlab.backend.security.jwt_utils import hash_password
        
        raw_key = f"sk_{secrets.token_urlsafe(32)}"
        
        new_user = User(
            api_key=hash_password(raw_key),
            tier=args.tier,
            onboarding_complete=False
        )
        db.add(new_user)
        await db.commit()
        print(f"User created: {new_user.id} | Tier: {new_user.tier}")
        print(f"API Key (SAVE THIS - not stored in plaintext): {raw_key}")

if __name__ == "__main__":
    asyncio.run(main())
