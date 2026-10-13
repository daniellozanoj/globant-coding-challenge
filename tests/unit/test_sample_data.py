"""Profiles the CSV files provided with the challenge (data/)."""

from collections import Counter
from pathlib import Path

import pytest

from app.core.csv_reader import RejectedRow, ValidRow, read_rows
from app.core.tables import TABLES, TableName

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load(table: TableName) -> list:
    path = DATA_DIR / f"{table}.csv"
    if not path.exists():
        pytest.skip(f"sample file {path.name} not available")
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(read_rows(file, TABLES[table]))


@pytest.mark.parametrize(
    ("table", "expected_rows"),
    [(TableName.DEPARTMENTS, 12), (TableName.JOBS, 183)],
)
def test_catalog_files_are_fully_valid(table: TableName, expected_rows: int) -> None:
    rows = load(table)

    assert len(rows) == expected_rows
    assert all(isinstance(row, ValidRow) for row in rows)


def test_hired_employees_has_70_rows_with_one_missing_field() -> None:
    rows = load(TableName.HIRED_EMPLOYEES)
    rejected = [row for row in rows if isinstance(row, RejectedRow)]

    assert len(rows) == 1999
    assert len(rejected) == 70
    assert Counter(row.errors[0] for row in rejected) == {
        "department_id: Field required": 21,
        "name: Field required": 19,
        "job_id: Field required": 16,
        "datetime: Field required": 14,
    }
