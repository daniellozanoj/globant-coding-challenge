"""Alembic environment: runs migrations with the application's settings and metadata."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db.base import Base
from app.db.session import build_engine

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests inject the URL of their throwaway database through the config attributes.
    return config.attributes.get("sqlalchemy_url") or get_settings().sqlalchemy_url


def run_migrations_offline() -> None:
    """Emit the SQL to stdout instead of executing it (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A caller (e.g. the migration Lambda) may hand over an open connection.
    if (connection := config.attributes.get("connection")) is not None:
        _run(connection)
        return

    if url := config.attributes.get("sqlalchemy_url"):
        engine = create_engine(url, poolclass=pool.NullPool)
    else:
        # Same engine as the application, including IAM authentication on AWS.
        engine = build_engine(get_settings())
    with engine.connect() as connection:
        _run(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
