from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models import user, job, team, profile, session, billing  # noqa
from suspensionlab.backend.database.models import shared_report  # noqa — shared_reports table
import asyncio

target_metadata = Base.metadata

def do_run_migrations(connection):
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    from suspensionlab.backend.config import settings
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

def run_migrations_online():
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    pass
else:
    run_migrations_online()
