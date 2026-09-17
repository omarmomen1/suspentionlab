"""
backend/database/seed.py
Automatic database table creation and demo user seeding for development & testing.
"""
import uuid
import logging
from sqlalchemy import select
from suspensionlab.backend.database.core import engine, Base, SessionLocal
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.jwt_utils import hash_password
from suspensionlab.shared.models import PlanTier

logger = logging.getLogger(__name__)

async def seed_demo_users():
    """Ensure database schema exists and seed default demo / development users."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.warning("Auto create_all encountered exception (likely already migrated): %s", e)

    from suspensionlab.backend.database.models.organization import Organization
    from suspensionlab.backend.database.models.team import Team

    async with SessionLocal() as db:
        # Ensure default enterprise organization and team exist
        org_slug = "williams-racing"
        res_org = await db.execute(select(Organization).where(Organization.slug == org_slug))
        org = res_org.scalar_one_or_none()
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                name="Williams Grand Prix Engineering",
                slug=org_slug,
                plan="ENTERPRISE",
            )
            db.add(org)
            await db.flush()

        res_team = await db.execute(select(Team).where(Team.organization_id == org.id))
        team = res_team.scalar_one_or_none()
        james_id = uuid.uuid4()
        res_james_existing = await db.execute(select(User).where(User.email == "james@company.com"))
        existing_james = res_james_existing.scalar_one_or_none()
        if existing_james:
            james_id = existing_james.id

        if not team:
            team = Team(
                id=uuid.uuid4(),
                name="Vehicle Dynamics",
                slug="vehicle-dynamics",
                organization_id=org.id,
                owner_id=james_id,
                plan="ENTERPRISE",
            )
            db.add(team)
            await db.flush()

        import os
        env = os.getenv("ENVIRONMENT", "DEV").upper()
        if env in ("PROD", "PRODUCTION", "TRIAL"):
            raise RuntimeError("CRITICAL: Refusing to seed default demo accounts in non-development environment.")

        if os.getenv("ALLOW_DEMO_SEEDING", "true").lower() not in ("true", "1", "yes"):
            logger.info("Demo user seeding skipped: ALLOW_DEMO_SEEDING is disabled.")
            return

        admin_cred = os.getenv("DEMO_ADMIN_PASSWORD")
        if not admin_cred:
            admin_cred = "admin123!"  # noqa: SEC007
        user_cred = os.getenv("DEMO_USER_PASSWORD")
        if not user_cred:
            user_cred = "demo1234"

        demo_accounts = [
            {
                "email": "james@company.com",
                "password": admin_cred,
                "name": "James Engineer",
                "plan": PlanTier.ENTERPRISE,
                "is_admin": True,
                "org_role": "ORG_ADMIN",
                "team_role": "OWNER",
                "organization_id": org.id,
                "team_id": team.id,
                "onboarding_complete": True,
            },
            {
                "email": "demo@suspensionlab.io",
                "password": user_cred,
                "name": "Demo Engineer",
                "plan": PlanTier.PRO,
                "is_admin": True,
                "org_role": "ORG_ADMIN",
                "team_role": "OWNER",
                "organization_id": None,
                "team_id": None,
                "onboarding_complete": True,
            },
        ]

        for acc in demo_accounts:
            res = await db.execute(select(User).where(User.email == acc["email"].lower()))
            existing = res.scalar_one_or_none()
            if not existing:
                new_user = User(
                    id=uuid.uuid4(),
                    email=acc["email"].lower(),
                    password_hash=hash_password(acc["password"]),
                    name=acc["name"],
                    plan=acc["plan"],
                    is_admin=acc["is_admin"],
                    org_role=acc["org_role"],
                    team_role=acc["team_role"],
                    organization_id=acc["organization_id"],
                    team_id=acc["team_id"],
                    onboarding_complete=acc["onboarding_complete"],
                )
                db.add(new_user)
                logger.info("Seeded demo user: %s", acc["email"])
            else:
                # Update password hash to match demo password in dev environment
                existing.password_hash = hash_password(acc["password"])
                existing.plan = acc["plan"]
                existing.is_admin = acc["is_admin"]
                existing.org_role = acc["org_role"]
                existing.team_role = acc["team_role"]
                if acc["organization_id"] and not existing.organization_id:
                    existing.organization_id = acc["organization_id"]
                if acc["team_id"] and not existing.team_id:
                    existing.team_id = acc["team_id"]
                existing.onboarding_complete = True

        await db.commit()
