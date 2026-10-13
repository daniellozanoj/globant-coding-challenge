"""Engine and session management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping transparently replaces connections dropped while the database was idle
    # (e.g. Aurora Serverless v2 auto-pause).
    return create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    with get_sessionmaker()() as session:
        yield session
