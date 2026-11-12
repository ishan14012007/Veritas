import asyncio
from logging.config import fileConfig
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import settings and models for autogenerate support
from app.core.config import get_settings
from app.core.models.base import Base
import app.core.models  # noqa: F401 - ensures core models are registered
import app.accord.models  # noqa: F401 - ensures accord models are registered
import app.payments.models  # noqa: F401 - ensures payment models are registered

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for 'autogenerate'
target_metadata = Base.metadata


def get_url() -> str:
    """Retrieve database URL from config or settings."""
    url = config.get_main_option("sqlalchemy.url")
    if url and url != "postgresql+asyncpg://veritas_user:veritas_dev_password@localhost:5432/veritas_db":
        return url
    settings = get_settings()
    return settings.DATABASE_URL


def include_object(object, name, type_, reflected, compare_to):
    """Filter included database objects by designated schema."""
    if type_ == "table":
        # Keep tables in schema core, accord, or argus (or unassigned in sqlite)
        if object.schema in ("core", "accord", "argus", None):
            return True
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Ensure PostgreSQL schemas exist before running migrations
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS core;"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS accord;"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS argus;"))
        connection.commit()

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connect_args = {}
    if get_url().startswith("sqlite"):
        connect_args["check_same_thread"] = False

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
