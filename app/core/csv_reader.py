"""Streaming CSV reader that turns each line into a validated record or a rejection."""

import csv
import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import BinaryIO, TextIO

from pydantic import ValidationError

from app.core.schemas import Record
from app.core.tables import TableSpec


@dataclass(frozen=True, slots=True)
class ValidRow:
    line_number: int
    record: Record
    # Original values, kept in case a later check (e.g. foreign keys) rejects the row.
    raw: list[str] = field(default_factory=list, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class RejectedRow:
    line_number: int
    raw: list[str]
    errors: list[str]


ParsedRow = ValidRow | RejectedRow


def text_stream(binary: BinaryIO) -> TextIO:
    """Decode a binary stream as UTF-8, dropping a BOM and keeping newlines for the csv module."""
    return io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")


def read_rows(
    lines: Iterable[str], spec: TableSpec, *, has_header: bool = False
) -> Iterator[ParsedRow]:
    """Lazily parse and validate CSV lines, so memory stays constant for any file size.

    Blank lines are skipped. Line numbers are physical line numbers in the file.
    """
    reader = csv.reader(lines)
    header_pending = has_header
    for values in reader:
        if not any(value.strip() for value in values):
            continue
        if header_pending:
            header_pending = False
            continue
        yield parse_row(spec, values, reader.line_num)


def parse_row(spec: TableSpec, values: list[str], line_number: int) -> ParsedRow:
    if len(values) != len(spec.columns):
        expected = f"{len(spec.columns)} columns ({', '.join(spec.columns)})"
        return RejectedRow(line_number, values, [f"expected {expected}, got {len(values)}"])

    # Empty cells are omitted so they are reported as "Field required".
    data = {
        column: value.strip()
        for column, value in zip(spec.columns, values, strict=True)
        if value.strip()
    }
    try:
        return ValidRow(line_number, spec.record_type.model_validate(data), values)
    except ValidationError as exc:
        return RejectedRow(line_number, values, format_errors(exc))


def format_errors(exc: ValidationError) -> list[str]:
    """Flatten Pydantic errors into readable `field: message` strings."""
    messages = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "record"
        message = error["msg"].removeprefix("Value error, ")
        messages.append(f"{field}: {message}")
    return messages
