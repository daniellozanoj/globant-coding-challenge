"""Section 2 metrics. The SQL lives in app/db/queries/*.sql so it can be reviewed as plain SQL."""

import datetime as dt
from collections.abc import Sequence
from functools import cache
from importlib.resources import files

from sqlalchemy import RowMapping, TextClause, text
from sqlalchemy.orm import Session


@cache
def _query(name: str) -> TextClause:
    return text(files("app.db.queries").joinpath(f"{name}.sql").read_text(encoding="utf-8"))


def year_bounds(year: int) -> dict[str, dt.datetime]:
    """Half-open UTC interval [Jan 1 of `year`, Jan 1 of `year + 1`) as query parameters."""
    return {
        "year_start": dt.datetime(year, 1, 1, tzinfo=dt.UTC),
        "next_year_start": dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC),
    }


def hires_by_quarter(session: Session, year: int) -> Sequence[RowMapping]:
    return session.execute(_query("hires_by_quarter"), year_bounds(year)).mappings().all()
