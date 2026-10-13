import io

import pytest

from app.core.csv_reader import RejectedRow, ValidRow, read_rows, text_stream
from app.core.schemas import DepartmentRecord
from app.core.tables import TABLES, TableName

DEPARTMENTS = TABLES[TableName.DEPARTMENTS]
EMPLOYEES = TABLES[TableName.HIRED_EMPLOYEES]


def parse(content: str, spec=DEPARTMENTS, **kwargs) -> list:
    return list(read_rows(io.StringIO(content, newline=""), spec, **kwargs))


def test_valid_rows_become_records() -> None:
    rows = parse("1,Supply Chain\n2,Maintenance\n")

    assert rows == [
        ValidRow(1, DepartmentRecord(id=1, department="Supply Chain")),
        ValidRow(2, DepartmentRecord(id=2, department="Maintenance")),
    ]


def test_crlf_line_endings_and_missing_final_newline() -> None:
    rows = parse("1,Supply Chain\r\n2,Maintenance")

    assert [row.record.department for row in rows] == ["Supply Chain", "Maintenance"]


def test_blank_lines_are_skipped_but_line_numbers_are_kept() -> None:
    rows = parse("1,Sales\n\n   \n4,Legal\n")

    assert [row.line_number for row in rows] == [1, 4]


def test_header_is_skipped_when_requested() -> None:
    rows = parse("id,department\n1,Sales\n", has_header=True)

    assert [row.record.id for row in rows] == [1]


def test_quoted_values_may_contain_commas() -> None:
    rows = parse('1,"Research, Development"\n')

    assert rows[0].record.department == "Research, Development"


@pytest.mark.parametrize("line", ["1", "1,Sales,extra"])
def test_wrong_number_of_columns_is_rejected(line: str) -> None:
    (row,) = parse(line)

    assert isinstance(row, RejectedRow)
    assert row.errors[0].startswith("expected 2 columns (id, department)")


def test_empty_cell_is_reported_as_required_field() -> None:
    (row,) = parse("157,Kellia Barribal,,4,61\n", spec=EMPLOYEES)

    assert row == RejectedRow(
        line_number=1,
        raw=["157", "Kellia Barribal", "", "4", "61"],
        errors=["datetime: Field required"],
    )


def test_every_invalid_field_is_reported() -> None:
    (row,) = parse("abc,,not-a-date,0,\n", spec=EMPLOYEES)

    assert isinstance(row, RejectedRow)
    assert {error.split(":")[0] for error in row.errors} == {
        "id",
        "name",
        "datetime",
        "department_id",
        "job_id",
    }


def test_invalid_rows_do_not_stop_the_stream() -> None:
    rows = parse("1,Sales\nx,Bad\n3,Legal\n")

    assert [type(row) for row in rows] == [ValidRow, RejectedRow, ValidRow]


def test_text_stream_drops_utf8_bom() -> None:
    binary = io.BytesIO("﻿1,Sales\r\n".encode())

    (row,) = list(read_rows(text_stream(binary), DEPARTMENTS))

    assert row.record.id == 1
