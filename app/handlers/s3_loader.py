"""Event-driven loader: S3 ObjectCreated notifications delivered through SQS.

Each SQS message wraps an S3 event for `landing/{table}/{job_id}.csv`. The file is streamed from
S3 into the database with the same loader as the local API. Delivery is at least once, so
processing is idempotent: a job that already SUCCEEDED is skipped, and a retried job starts from
scratch (writes are upserts).
"""

import csv
import io
import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote_plus

from sqlalchemy.orm import Session

from app.aws import s3
from app.config import Settings
from app.core.csv_reader import read_rows
from app.core.landing import parse_landing_key, rejected_key
from app.core.loader import IngestionError, load_rows
from app.core.tables import TABLES, TableName
from app.db import repository
from app.db.models import IngestionJob, IngestionStatus

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

# The file itself is invalid: retrying the message cannot succeed.
PERMANENT_ERRORS = (UnicodeDecodeError, csv.Error)


def handle_sqs_event(
    event: dict[str, Any], session_factory: SessionFactory, settings: Settings
) -> dict[str, Any]:
    """Process an SQS batch and report only the failed messages (partial batch response)."""
    failures = []
    for record in event["Records"]:
        try:
            for bucket, key in _s3_objects(json.loads(record["body"])):
                with session_factory() as session:
                    process_object(session, settings, bucket, key)
        except Exception:
            logger.exception("Message %s failed and will be retried", record["messageId"])
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def process_object(session: Session, settings: Settings, bucket: str, key: str) -> None:
    try:
        table, job_id = parse_landing_key(key)
    except ValueError:
        logger.warning("Ignoring s3://%s/%s: outside the landing contract", bucket, key)
        return

    source = f"s3://{bucket}/{key}"
    job = session.get(IngestionJob, job_id)
    if job is None:  # file dropped in the landing zone without POST /uploads
        job = repository.create_ingestion_job(session, table, source, job_id=job_id)
    elif job.status == IngestionStatus.SUCCEEDED:
        logger.info("Skipping %s: job %s already succeeded (duplicate delivery)", source, job_id)
        return
    elif job.status != IngestionStatus.PENDING:
        repository.reset_ingestion_job(session, job)

    rows = read_rows(s3.open_text(settings.aws_region, bucket, key), TABLES[table])
    try:
        load_rows(session, job, rows)
    except IngestionError as exc:
        if isinstance(exc.__cause__, PERMANENT_ERRORS):
            logger.warning("Job %s failed permanently: %s", job_id, exc)
            return
        raise

    if job.rows_rejected:
        _write_rejections(session, settings, bucket, table, job)


def _s3_objects(message: dict[str, Any]) -> list[tuple[str, str]]:
    """(bucket, key) pairs of an S3 event notification. S3 test events have no records."""
    return [
        (record["s3"]["bucket"]["name"], unquote_plus(record["s3"]["object"]["key"]))
        for record in message.get("Records", [])
        if record.get("eventSource") == "aws:s3"
    ]


def _write_rejections(
    session: Session, settings: Settings, bucket: str, table: TableName, job: IngestionJob
) -> None:
    """Mirror the rejected rows to s3://bucket/rejected/... for data stewards."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["line_number", "raw_record", "errors"])
    for rejection in repository.list_rejections(session, job.id):
        writer.writerow(
            [rejection.line_number, ",".join(rejection.raw_record), "; ".join(rejection.errors)]
        )
    s3.put_text(
        settings.aws_region, bucket, rejected_key(table, job.id), buffer.getvalue(), "text/csv"
    )
