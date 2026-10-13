import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.db.base import Base

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "departments",
    "jobs",
    "hired_employees",
    "ingestion_jobs",
    "load_rejections",
}


def test_migration_creates_all_tables(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())

    assert EXPECTED_TABLES.issubset(tables)


def test_hired_employees_references_departments_and_jobs(engine: Engine) -> None:
    foreign_keys = {
        (fk["constrained_columns"][0], fk["referred_table"])
        for fk in inspect(engine).get_foreign_keys("hired_employees")
    }

    assert foreign_keys == {("department_id", "departments"), ("job_id", "jobs")}


def test_hired_employees_has_query_indexes(engine: Engine) -> None:
    indexed_columns = {
        index["column_names"][0] for index in inspect(engine).get_indexes("hired_employees")
    }

    assert {"datetime", "department_id", "job_id"} <= indexed_columns


def test_models_and_migrations_are_in_sync(engine: Engine) -> None:
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == [], f"Models and migrations differ, create a new revision: {diff}"


def test_migration_downgrades_and_upgrades_cleanly(engine: Engine, alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    assert EXPECTED_TABLES.isdisjoint(inspect(engine).get_table_names())

    command.upgrade(alembic_config, "head")
    assert EXPECTED_TABLES.issubset(inspect(engine).get_table_names())
