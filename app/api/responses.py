"""Content negotiation helpers: metrics are served as JSON (default) or CSV."""

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Literal

from fastapi import Request, Response

ResponseFormat = Literal["json", "csv"]

CSV_RESPONSE_DOC = {"content": {"text/csv": {"schema": {"type": "string"}}}}


def wants_csv(request: Request, response_format: ResponseFormat | None) -> bool:
    """CSV when requested explicitly with ?format=csv, or with an `Accept: text/csv` header."""
    if response_format is not None:
        return response_format == "csv"
    return "text/csv" in request.headers.get("accept", "")


def csv_response(
    rows: Sequence[Mapping[str, object]], columns: Sequence[str], filename: str
) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([row[column] for column in columns] for row in rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
