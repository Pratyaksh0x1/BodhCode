import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlmodel import SQLModel, create_engine

from alembic import context
from app.config import get_settings
from app.models.repo import Repo  # noqa: F401
from app.models.user import User  # noqa: F401

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point target_metadata to SQLModel metadata
target_metadata = SQLModel.metadata


def get_url() -> str:
    """Retrieve database URL from environment or app settings (prefer unpooled for migrations)."""
    unpooled = os.environ.get("DATABASE_URL_UNPOOLED")
    if unpooled:
        return unpooled
    settings = get_settings()
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_url()
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
