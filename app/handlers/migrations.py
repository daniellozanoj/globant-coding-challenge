"""Apply the database migrations from inside the VPC (invoked once per deployment)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_migrations(engine: Engine) -> str:
    """Upgrade to the latest revision and return the resulting revision."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision() or "base"
