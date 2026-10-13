"""Engine and session management."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

import boto3
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def engine_options(settings: Settings) -> dict[str, Any]:
    """Keyword arguments for `create_engine`."""
    return {
        # Replaces connections dropped while the database was idle (Aurora auto-pause).
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        # IAM authentication requires TLS.
        "connect_args": {"sslmode": "require"} if settings.db_iam_auth else {},
    }


def build_engine(settings: Settings) -> Engine:
    engine = create_engine(settings.sqlalchemy_url, **engine_options(settings))
    if settings.db_iam_auth:
        _use_iam_tokens(engine, settings)
    return engine


def iam_token_provider(settings: Settings) -> Any:
    """Return a function producing RDS IAM auth tokens (valid 15 minutes).

    The token is signed locally with the Lambda role credentials: no network call, and no
    password stored anywhere.
    """
    rds = boto3.client("rds", region_name=settings.aws_region)

    def token() -> str:
        return rds.generate_db_auth_token(
            DBHostname=settings.db_host,
            Port=settings.db_port,
            DBUsername=settings.db_user,
            Region=settings.aws_region,
        )

    return token


def _use_iam_tokens(engine: Engine, settings: Settings) -> None:
    token = iam_token_provider(settings)

    @event.listens_for(engine, "do_connect")
    def _provide_token(dialect: Any, conn_rec: Any, cargs: Any, cparams: dict[str, Any]) -> None:
        # Only new physical connections need a token; pooled ones are reused as they are.
        cparams["password"] = token()


@lru_cache
def get_engine() -> Engine:
    return build_engine(get_settings())


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    with get_sessionmaker()() as session:
        yield session
