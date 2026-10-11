import asyncio
import sys
import os

sys.path.append(os.getcwd() + "/src")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import uuid
import secrets
from datetime import datetime, timezone, timedelta

from suspensionlab.backend.database.core import Base, get_db_dependency
import suspensionlab.backend.database.models
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.database.models.billing import StripeEvent, LemonEvent

from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user_api_key import UserApiKey
from suspensionlab.backend.database.models.session import SimSession, SessionComment
from suspensionlab.backend.database.models.shared_report import SharedReport


from suspensionlab.backend.security.jwt_utils import hash_password

async def main():
    db_path = "sqlite+aiosqlite:///./data/suspensionlab.db"
    
    # Delete old db if it exists
    if os.path.exists("./data/suspensionlab.db"):
        os.remove("./data/suspensionlab.db")
        print("Deleted old database.")

    engine = create_async_engine(db_path)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Recreated database schema.")

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        admin_email = "james@company.com"
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        team_id = uuid.uuid4()

        org = Organization(
            id=org_id,
            name="Williams Grand Prix Engineering",
            slug="williams-racing",
            plan="ENTERPRISE",
        )
        team = Team(
            id=team_id,
            name="Vehicle Dynamics",
            slug="vehicle-dynamics",
            organization_id=org_id,
            owner_id=user_id,
            plan="ENTERPRISE",
        )
        user = User(
            id=user_id,
            email=admin_email,
            password_hash=hash_password("admin123!"),
            name="James Hunt",
            plan="ENTERPRISE",
            is_admin=True,
            org_role="ORG_ADMIN",
            organization_id=org_id,
            team_id=team_id,
            team_role="OWNER",
            onboarding_complete=True,
            api_key=f"sk_{secrets.token_urlsafe(32)}"
        )
        db.add_all([org, team, user])
        await db.commit()
        print(f"Admin user created! Email: {admin_email} | Role: ORG_ADMIN / OWNER | Org: Williams Racing")

if __name__ == "__main__":
    asyncio.run(main())
