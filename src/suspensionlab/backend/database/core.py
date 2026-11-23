import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from suspensionlab.backend.config import settings
DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("sqlite:///") and "+aiosqlite" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
elif DATABASE_URL.startswith("postgres://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://")

engine_args = {
    "pool_pre_ping": True,
}
_ssl_ctx = None

if "+asyncpg" in DATABASE_URL:
    import ssl
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(DATABASE_URL)
    qs = parse_qs(parsed.query)
    ssl_mode = qs.get("sslmode", [None])[0] or qs.get("ssl", [None])[0]

    if ssl_mode in ("verify-full", "verify-ca"):
        _ssl_ctx = ssl.create_default_context()
        if ssl_mode == "verify-ca":
            _ssl_ctx.check_hostname = False
        qs.pop("sslmode", None)
        qs.pop("ssl", None)
        new_query = urlencode(qs, doseq=True)
        DATABASE_URL = urlunparse(parsed._replace(query=new_query))
        if "connect_args" not in engine_args:
            engine_args["connect_args"] = {}
        engine_args["connect_args"]["ssl"] = _ssl_ctx
    elif "sslmode=" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer")
if "sqlite" in DATABASE_URL:
    engine_args["connect_args"] = {"check_same_thread": False, "timeout": 60}
else:
    # Production Architecture: 
    # Connection sits behind Pgpool-II (via Bitnami postgresql-ha Helm Chart).
    # Since Pgpool-II handles transaction multiplexing, we keep a minimal local 
    # SQLAlchemy pool to avoid connection setup latency without exhausting proxy slots.
    engine_args["pool_size"] = 20
    engine_args["max_overflow"] = 10
    engine_args["pool_timeout"] = 30

engine = create_async_engine(DATABASE_URL, **engine_args)

from sqlalchemy import event

if "sqlite" in DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

from sqlalchemy import event
from suspensionlab.backend.observability import record_db_pool_metrics, record_dependency_health

def sync_db_pool_metrics() -> tuple[int, int]:
    """Inspects SQLAlchemy pool and publishes real active connections and capacity."""
    try:
        pool = engine.sync_engine.pool
        checked_out = pool.checkedout()
        size = pool.size()
        record_db_pool_metrics(active=checked_out, size=size)
        return checked_out, size
    except Exception:
        return 0, 0

try:
    @event.listens_for(engine.sync_engine.pool, "checkout")
    def receive_checkout(dbapi_connection, connection_record, connection_proxy):
        sync_db_pool_metrics()

    @event.listens_for(engine.sync_engine.pool, "checkin")
    def receive_checkin(dbapi_connection, connection_record):
        sync_db_pool_metrics()
except Exception:
    pass

SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

_worker_session_maker = None

def get_worker_session_maker():
    global _worker_session_maker
    if _worker_session_maker is None:
        worker_args = {"pool_pre_ping": True}
        if "sqlite" in DATABASE_URL:
            from sqlalchemy.pool import NullPool
            worker_args["connect_args"] = {"check_same_thread": False, "timeout": 60}
            worker_args["poolclass"] = NullPool
        else:
            worker_args.update({
                "pool_size": 20, 
                "max_overflow": 20, 
                "pool_timeout": 30,
            })
            if _ssl_ctx is not None:
                if "connect_args" not in worker_args:
                    worker_args["connect_args"] = {}
                worker_args["connect_args"]["ssl"] = _ssl_ctx
        worker_engine = create_async_engine(DATABASE_URL, **worker_args)
        _worker_session_maker = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=worker_engine, class_=AsyncSession)
    return _worker_session_maker

def get_async_db_session():
    """Returns a raw async session. Caller must close it."""
    return SessionLocal()

async def get_db_dependency():
    """FastAPI Dependency for automatic session cleanup."""
    async with SessionLocal() as db:
        yield db
