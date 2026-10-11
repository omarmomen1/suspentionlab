import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# Ensure src is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from suspensionlab.backend.database.core import Base
# Import all database models so target_metadata is complete
from suspensionlab.backend.database.models.user import User  # noqa: F401
from suspensionlab.backend.database.models.team import Team  # noqa: F401
from suspensionlab.backend.database.models.job import JobRecord  # noqa: F401
from suspensionlab.backend.database.models.profile import VehicleProfile  # noqa: F401
from suspensionlab.backend.database.models.session import SimSession, SessionComment  # noqa: F401
from suspensionlab.backend.database.models.audit import AuditLog, EngineeringAuditLog  # noqa: F401
from suspensionlab.backend.database.models.user_api_key import UserApiKey  # noqa: F401
from suspensionlab.backend.database.models.user_session import UserSession  # noqa: F401
from suspensionlab.backend.database.models.shared_report import SharedReport  # noqa: F401
from suspensionlab.backend.database.models.simulation_run import SimulationRun  # noqa: F401
from suspensionlab.backend.database.models.setup_proposal import SetupProposal  # noqa: F401
from suspensionlab.backend.database.models.setup_score import SetupScore  # noqa: F401
from suspensionlab.backend.database.models.webhook import WebhookEndpoint  # noqa: F401
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin, CalibrationObservation  # noqa: F401
from suspensionlab.backend.database.models.billing import LemonEvent, StripeEvent  # noqa: F401

target_metadata = Base.metadata

def get_url() -> str:
    from suspensionlab.backend.config import settings
    url = os.environ.get("DATABASE_URL") or context.config.get_main_option("sqlalchemy.url") or settings.database_url
    if url.startswith("sqlite:///") and "+aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///")
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    elif url.startswith("postgres://") and "+asyncpg" not in url:
        url = url.replace("postgres://", "postgresql+asyncpg://")
    return url

def do_run_migrations(connection):
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    url = get_url()
    connectable = create_async_engine(url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_offline():
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
