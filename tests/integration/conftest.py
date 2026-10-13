"""Fixtures that provide a real, migrated PostgreSQL database for integration tests.

The database comes from ``TEST_DATABASE_URL`` when set (e.g. a CI service container),
otherwise a throwaway PostgreSQL 16 container is started with testcontainers.
"""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _configure_docker_host() -> None:
    """Point testcontainers to the active Docker context (Colima, OrbStack, Desktop...)."""
    if os.getenv("DOCKER_HOST"):
        return
    try:
        host = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return
    if host and host != "unix:///var/run/docker.sock":
        os.environ["DOCKER_HOST"] = host
        # The Ryuk reaper container mounts the socket path as seen from inside the Docker VM.
        os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if url := os.getenv("TEST_DATABASE_URL"):
        yield url
        return

    _configure_docker_host()
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["sqlalchemy_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config) -> Iterator[Engine]:
    """Engine bound to a database migrated to the latest revision."""
    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


def _truncate_all(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE hired_employees, departments, jobs, load_rejections, ingestion_jobs "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Session factory on an empty database; every test starts and ends with clean tables."""
    _truncate_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    _truncate_all(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session
