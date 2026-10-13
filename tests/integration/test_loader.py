import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.csv_reader import ParsedRow, ValidRow
from app.core.loader import load_csv, load_rows
from app.core.schemas import DepartmentRecord
from app.core.tables import LOAD_ORDER, TableName
from app.db import repository
from app.db.models import (
    Department,
    HiredEmployee,
    IngestionJob,
    IngestionStatus,
    Job,
    LoadRejection,
)

pytestmark = pytest.mark.integration

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_text(session: Session, table: TableName, content: str, **kwargs) -> IngestionJob:
    return load_csv(session, table, io.StringIO(content, newline=""), source="inline.csv", **kwargs)


def load_sample_files(session: Session) -> dict[TableName, IngestionJob]:
    jobs = {}
    for table in LOAD_ORDER:
        path = DATA_DIR / f"{table}.csv"
        with path.open(encoding="utf-8-sig", newline="") as file:
            jobs[table] = load_csv(session, table, file, source=str(path))
    return jobs


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_sample_files_are_migrated(session: Session) -> None:
    jobs = load_sample_files(session)

    assert (count(session, Department), count(session, Job)) == (12, 183)
    assert count(session, HiredEmployee) == 1929
    assert count(session, LoadRejection) == 70

    employees_job = jobs[TableName.HIRED_EMPLOYEES]
    assert employees_job.status == IngestionStatus.SUCCEEDED
    assert (employees_job.rows_read, employees_job.rows_loaded, employees_job.rows_rejected) == (
        1999,
        1929,
        70,
    )
    assert employees_job.started_at <= employees_job.finished_at


def test_reloading_the_same_files_is_idempotent(session: Session) -> None:
    load_sample_files(session)
    load_sample_files(session)

    assert (count(session, Department), count(session, Job)) == (12, 183)
    assert count(session, HiredEmployee) == 1929


def test_existing_ids_are_updated(session: Session) -> None:
    load_text(session, TableName.DEPARTMENTS, "1,Supply Chain\n")
    load_text(session, TableName.DEPARTMENTS, "1,Logistics\n")

    assert session.scalars(select(Department.department)).all() == ["Logistics"]


def test_rejections_keep_line_number_raw_values_and_errors(session: Session) -> None:
    job = load_text(session, TableName.DEPARTMENTS, "1,Sales\n0,\n")

    rejection = session.scalars(select(LoadRejection)).one()
    assert rejection.job_id == job.id
    assert rejection.line_number == 2
    assert rejection.raw_record == ["0", ""]
    assert rejection.errors == [
        "id: Input should be greater than 0",
        "department: Field required",
    ]


def test_employees_with_unknown_department_or_job_are_rejected(session: Session) -> None:
    load_text(session, TableName.DEPARTMENTS, "1,Sales\n")
    load_text(session, TableName.JOBS, "1,Recruiter\n")

    job = load_text(
        session,
        TableName.HIRED_EMPLOYEES,
        "1,Ana,2021-01-10T10:00:00Z,1,1\n"
        "2,Luis,2021-02-10T10:00:00Z,99,1\n"
        "3,Eva,2021-03-10T10:00:00Z,1,77\n",
    )

    assert (job.rows_loaded, job.rows_rejected) == (1, 2)
    errors = dict(session.execute(select(LoadRejection.line_number, LoadRejection.errors)).all())
    assert errors == {
        2: ["department_id: 99 does not exist"],
        3: ["job_id: 77 does not exist"],
    }
    assert session.scalars(select(HiredEmployee.id)).all() == [1]


def test_duplicated_ids_in_a_file_keep_the_last_occurrence(session: Session) -> None:
    load_text(session, TableName.DEPARTMENTS, "1,Sales\n1,Legal\n2,Support\n1,Training\n")

    rows = session.execute(select(Department.id, Department.department).order_by(Department.id))
    assert rows.all() == [(1, "Training"), (2, "Support")]


def test_small_chunks_cover_every_row(session: Session) -> None:
    content = "".join(f"{i},Department {i}\n" for i in range(1, 8)) + "x,bad\n"

    job = load_text(session, TableName.DEPARTMENTS, content, chunk_size=2)

    assert (job.rows_read, job.rows_loaded, job.rows_rejected) == (8, 7, 1)
    assert count(session, Department) == 7


def test_failure_marks_the_job_failed_and_keeps_committed_chunks(session: Session) -> None:
    def rows_then_crash() -> Iterator[ParsedRow]:
        for i in (1, 2, 3):
            yield ValidRow(i, DepartmentRecord(id=i, department=f"Department {i}"))
        raise RuntimeError("connection to the source was lost")

    job = repository.create_ingestion_job(session, TableName.DEPARTMENTS, "flaky.csv")

    with pytest.raises(RuntimeError):
        load_rows(session, job, rows_then_crash(), chunk_size=2)

    session.refresh(job)
    assert job.status == IngestionStatus.FAILED
    assert job.error == "RuntimeError: connection to the source was lost"
    assert job.finished_at is not None
    # The first chunk (ids 1 and 2) was committed; the partial chunk (id 3) was never written.
    assert (job.rows_loaded, count(session, Department)) == (2, 2)
