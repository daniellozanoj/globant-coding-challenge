"""Dispatcher for non-HTTP Lambda events forwarded by the AWS Lambda Web Adapter."""

import logging
from typing import Any

from app.config import Settings
from app.db.session import get_engine, get_sessionmaker
from app.handlers.migrations import run_migrations
from app.handlers.s3_loader import handle_sqs_event

logger = logging.getLogger(__name__)


class UnsupportedEvent(ValueError):
    pass


def dispatch(event: dict[str, Any], settings: Settings) -> dict[str, Any]:
    records = event.get("Records") or []
    if records and all(record.get("eventSource") == "aws:sqs" for record in records):
        return handle_sqs_event(event, get_sessionmaker(), settings)
    if event.get("action") == "migrate":
        revision = run_migrations(get_engine())
        logger.info("Database migrated to revision %s", revision)
        return {"status": "migrated", "revision": revision}
    raise UnsupportedEvent("expected an SQS batch or {'action': 'migrate'}")
