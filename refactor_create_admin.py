import os

filepath = r"C:\Users\omaar\Downloads\project\create_admin.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

old_main = """async def main():
    db_path = "sqlite+aiosqlite:///./data/suspensionlab.db"
    print(f"Connecting to {db_path}...")
    engine = create_async_engine(db_path)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        admin_email = "james@company.com"
        # Check if already exists
        from sqlalchemy import select
        existing = await db.execute(select(User).where(User.email == admin_email))
        if existing.scalar_one_or_none():
            print(f"Admin user {admin_email} already exists!")
            return

        user = User(
            id=uuid.uuid4(),
            email=admin_email,
            password_hash=hash_password("admin123!"),
            name="James Hunt",
            plan="ENTERPRISE",
            tier="ENTERPRISE",
            onboarding_complete=True,
            api_key=f"sk_{secrets.token_urlsafe(32)}"
        )
        db.add(user)
        await db.commit()
        print(f"Admin user created! Email: {admin_email} | Password: admin123!")

if __name__ == "__main__":
    asyncio.run(main())"""

new_main = """import argparse
from suspensionlab.shared.models import PlanTier

async def main(email: str, password: str, name: str):
    db_path = "sqlite+aiosqlite:///./data/suspensionlab.db"
    print(f"Connecting to {db_path}...")
    engine = create_async_engine(db_path)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Check if already exists
        from sqlalchemy import select
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"Admin user {email} already exists!")
            return

        user = User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(password),
            name=name,
            plan=PlanTier.ENTERPRISE,
            tier=PlanTier.ENTERPRISE,
            onboarding_complete=True,
            api_key=f"sk_{secrets.token_urlsafe(32)}"
        )
        db.add(user)
        await db.commit()
        print(f"Admin user created! Email: {email}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an admin user.")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", required=True, help="Admin password")
    parser.add_argument("--name", default="Admin User", help="Admin name")
    args = parser.parse_args()
    
    asyncio.run(main(args.email, args.password, args.name))"""

content = content.replace(old_main, new_main)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("create_admin.py refactored.")
