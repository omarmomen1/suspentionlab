import asyncio
import sqlite3
from sqlalchemy import create_engine
from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.shared_report import SharedReport
import suspensionlab.backend.database.models  # ensure all models registered

def recreate_tables():
    sync_engine = create_engine("sqlite:///data/suspensionlab.db")
    # Drop and recreate shared_reports table so it exactly matches the latest model
    SharedReport.__table__.drop(sync_engine, checkfirst=True)
    SharedReport.__table__.create(sync_engine, checkfirst=True)
    print("Recreated shared_reports table successfully.")

    # Also run create_all for any other missing tables
    Base.metadata.create_all(sync_engine)
    print("All tables synced.")

if __name__ == "__main__":
    recreate_tables()
