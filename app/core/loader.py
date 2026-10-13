"""Chunked, idempotent loader: validated CSV rows → database, invalid rows → load_rejections."""

import datetime as dt
import logging
from collections.abc import Iterable, Sequence
from itertools import batched

from sqlalchemy.orm import Session

from app.core.csv_reader import ParsedRow, RejectedRow, ValidRow, read_rows
from app.core.schemas import HiredEmployeeRecord
from app.core.tables import TABLES, TableName
from app.db import repository
from app.db.models import IngestionJob, IngestionStatus

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1000


def load_csv(
    session: Session,
    table: TableName,
    lines: Iterable[str],
    *,
    source: str,
    has_header: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> IngestionJob:
    """Create an ingestion job and load a CSV stream into `table`."""
    job = repository.create_ingestion_job(session, table, source)
    rows = read_rows(lines, TABLES[table], has_header=has_header)
    return load_rows(session, job, rows, chunk_size=chunk_size)


def load_rows(
    session: Session,
    job: IngestionJob,
    rows: Iterable[ParsedRow],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> IngestionJob:
    """Load parsed rows in chunks, committing each chunk.

    Committing per chunk keeps transactions short and memory constant. A failed load can simply
    be retried: writes are upserts, so already committed chunks are not duplicated.
    """
    table = TableName(job.table_name)
    job.status = IngestionStatus.RUNNING
    job.started_at = _now()
    session.commit()

    try:
        for chunk in batched(rows, chunk_size):
            _load_chunk(session, job, table, chunk)
            session.commit()
    except Exception as exc:
        session.rollback()
        job.status = IngestionStatus.FAILED
        job.error = f"{type(exc).__name__}: {exc}"
        job.finished_at = _now()
        session.commit()
        logger.exception("Ingestion job %s failed", job.id)
        raise

    job.status = IngestionStatus.SUCCEEDED
    job.finished_at = _now()
    session.commit()
    logger.info(
        "Ingestion job %s loaded %s rows into %s (%s rejected)",
        job.id,
        job.rows_loaded,
        table,
        job.rows_rejected,
    )
    return job


def find_reference_errors(
    session: Session, records: Sequence[HiredEmployeeRecord]
) -> list[list[str]]:
    """Foreign key check for employees: one list of errors per record (empty when valid)."""
    departments = repository.existing_ids(
        session, TableName.DEPARTMENTS, (r.department_id for r in records)
    )
    jobs = repository.existing_ids(session, TableName.JOBS, (r.job_id for r in records))
    errors = []
    for record in records:
        record_errors = []
        if record.department_id not in departments:
            record_errors.append(f"department_id: {record.department_id} does not exist")
        if record.job_id not in jobs:
            record_errors.append(f"job_id: {record.job_id} does not exist")
        errors.append(record_errors)
    return errors


def _load_chunk(
    session: Session, job: IngestionJob, table: TableName, chunk: Sequence[ParsedRow]
) -> None:
    valid = [row for row in chunk if isinstance(row, ValidRow)]
    rejected = [row for row in chunk if isinstance(row, RejectedRow)]

    if table is TableName.HIRED_EMPLOYEES and valid:
        reference_errors = find_reference_errors(session, [row.record for row in valid])
        rejected += [
            RejectedRow(row.line_number, row.raw, errors)
            for row, errors in zip(valid, reference_errors, strict=True)
            if errors
        ]
        valid = [row for row, errors in zip(valid, reference_errors, strict=True) if not errors]

    # A repeated id within the chunk keeps its last occurrence, like successive upserts would.
    records = list({row.record.id: row.record for row in valid}.values())
    repository.upsert_records(session, table, records)
    repository.add_rejections(session, job.id, rejected)

    job.rows_read += len(chunk)
    job.rows_loaded += len(valid)
    job.rows_rejected += len(rejected)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
