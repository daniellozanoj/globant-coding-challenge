"""All-or-nothing batch inserts of 1 to MAX_BATCH_ROWS records."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.loader import find_reference_errors
from app.core.schemas import HiredEmployeeRecord, Record
from app.core.tables import TableName
from app.db import repository


@dataclass(frozen=True, slots=True)
class RowError:
    index: int
    field: str
    message: str
    type: str


class BatchValidationError(Exception):
    """The batch was rejected as a whole; nothing was written."""

    def __init__(self, errors: list[RowError]) -> None:
        super().__init__(f"{len(errors)} invalid rows in the batch")
        self.errors = errors


class BatchConflictError(Exception):
    """The database rejected the batch (e.g. a referenced row disappeared after validation)."""


def insert_batch(session: Session, table: TableName, records: Sequence[Record]) -> int:
    """Validate the whole batch, then upsert it in a single transaction.

    Raises:
        BatchValidationError: duplicated ids or unknown foreign keys; nothing is written.
        BatchConflictError: the database rejected the write; the transaction is rolled back.
    """
    errors = _duplicate_id_errors(records)
    if table is TableName.HIRED_EMPLOYEES:
        errors += _reference_errors(session, records)
    if errors:
        raise BatchValidationError(sorted(errors, key=lambda error: error.index))

    try:
        written = repository.upsert_records(session, table, records)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise BatchConflictError(str(exc.orig)) from exc
    return written


def _duplicate_id_errors(records: Sequence[Record]) -> list[RowError]:
    seen: set[int] = set()
    errors = []
    for index, record in enumerate(records):
        if record.id in seen:
            errors.append(
                RowError(index, "id", f"duplicated id {record.id} in the batch", "duplicate_id")
            )
        seen.add(record.id)
    return errors


def _reference_errors(session: Session, records: Sequence[Record]) -> list[RowError]:
    employees = [record for record in records if isinstance(record, HiredEmployeeRecord)]
    return [
        RowError(index, message.split(":", 1)[0], message, "foreign_key_violation")
        for index, messages in enumerate(find_reference_errors(session, employees))
        for message in messages
    ]
