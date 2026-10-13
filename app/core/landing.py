"""Naming of raw files in the S3 landing zone: landing/{table}/{job_id}.csv.

The ingestion job id is part of the object key, so the event-driven loader knows which job an
uploaded file belongs to.
"""

import re
import uuid

from app.core.tables import TableName

LANDING_PREFIX = "landing/"
REJECTED_PREFIX = "rejected/"

_LANDING_KEY = re.compile(rf"^{LANDING_PREFIX}(?P<table>[a-z_]+)/(?P<job_id>[0-9a-f-]{{36}})\.csv$")


def landing_key(table: TableName, job_id: uuid.UUID) -> str:
    return f"{LANDING_PREFIX}{table}/{job_id}.csv"


def rejected_key(table: TableName, job_id: uuid.UUID) -> str:
    return f"{REJECTED_PREFIX}{table}/{job_id}.csv"


def parse_landing_key(key: str) -> tuple[TableName, uuid.UUID]:
    """Inverse of `landing_key`. Raises ValueError for keys outside the landing contract."""
    match = _LANDING_KEY.match(key)
    if match is None:
        raise ValueError(f"not a landing key: {key!r}")
    try:
        return TableName(match["table"]), uuid.UUID(match["job_id"])
    except ValueError as exc:
        raise ValueError(f"not a landing key: {key!r}") from exc
