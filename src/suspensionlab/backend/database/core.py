import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from suspensionlab.backend.config import settings
DATABASE_URL = settings.database_url

engine_args = {
    "pool_pre_ping": True,
}
if "sqlite" in DATABASE_URL:
    engine_args["connect_args"] = {"check_same_thread": False}
else:
    # Production Architecture: 
    # Connection sits behind Pgpool-II (via Bitnami postgresql-ha Helm Chart).
    # Since Pgpool-II handles transaction multiplexing, we keep a minimal local 
    # SQLAlchemy pool to avoid connection setup latency without exhausting proxy slots.
    engine_args["pool_size"] = 20
    engine_args["max_overflow"] = 10
    engine_args["pool_timeout"] = 30

engine = create_async_engine(DATABASE_URL, **engine_args)

SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

def get_worker_session_maker():
    worker_engine = create_async_engine(
        DATABASE_URL, 
        pool_size=5, 
        max_overflow=10, 
        pool_timeout=30,
        pool_pre_ping=True
    )
    return async_sessionmaker(autocommit=False, autoflush=False, bind=worker_engine, class_=AsyncSession)

def get_async_db_session():
    """Returns a raw async session. Caller must close it."""
    return SessionLocal()

async def get_db_dependency():
    """FastAPI Dependency for automatic session cleanup."""
    async with SessionLocal() as db:
        yield db
