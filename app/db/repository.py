"""Data access functions used by the ingestion core."""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.csv_reader import RejectedRow
from app.core.schemas import Record
from app.core.tables import TableName
from app.db.base import Base
from app.db.models import Department, HiredEmployee, IngestionJob, Job, LoadRejection

MODELS: dict[TableName, type[Base]] = {
    TableName.DEPARTMENTS: Department,
    TableName.JOBS: Job,
    TableName.HIRED_EMPLOYEES: HiredEmployee,
}


def upsert_records(session: Session, table: TableName, records: Sequence[Record]) -> int:
    """Insert records or update them when the id already exists (idempotent writes).

    The records must have unique ids: PostgreSQL cannot update the same row twice in one statement.
    """
    if not records:
        return 0
    target = MODELS[table].__table__
    statement = pg_insert(target).values([record.model_dump() for record in records])
    statement = statement.on_conflict_do_update(
        index_elements=[target.c.id],
        set_={c.name: statement.excluded[c.name] for c in target.columns if not c.primary_key},
    )
    session.execute(statement)
    return len(records)


def existing_ids(session: Session, table: TableName, ids: Iterable[int]) -> set[int]:
    """Return the subset of `ids` that exists in `table`."""
    ids = set(ids)
    if not ids:
        return set()
    model = MODELS[table]
    return set(session.scalars(select(model.id).where(model.id.in_(ids))))


def add_rejections(session: Session, job_id: uuid.UUID, rows: Sequence[RejectedRow]) -> None:
    if not rows:
        return
    session.execute(
        insert(LoadRejection),
        [
            {
                "job_id": job_id,
                "line_number": row.line_number,
                "raw_record": row.raw,
                "errors": row.errors,
            }
            for row in rows
        ],
    )


def create_ingestion_job(session: Session, table: TableName, source: str) -> IngestionJob:
    job = IngestionJob(table_name=table, source=source)
    session.add(job)
    session.commit()
    return job
