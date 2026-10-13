"""Section 2 endpoints: hiring metrics requested by the stakeholders."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.responses import CSV_RESPONSE_DOC, ResponseFormat, csv_response, wants_csv
from app.db import metrics
from app.db.session import get_session

router = APIRouter(prefix="/metrics", tags=["metrics"])

SessionDep = Annotated[Session, Depends(get_session)]
YearQuery = Annotated[int, Query(ge=2000, le=2100, description="Hiring year (UTC)")]
FormatQuery = Annotated[
    ResponseFormat | None,
    Query(alias="format", description="Override content negotiation (`Accept: text/csv`)"),
]


class QuarterlyHires(BaseModel):
    department: str
    job: str
    Q1: int
    Q2: int
    Q3: int
    Q4: int


@router.get(
    "/hires-by-quarter",
    response_model=list[QuarterlyHires],
    summary="Hires per department and job, by quarter",
    responses={200: CSV_RESPONSE_DOC},
)
def hires_by_quarter(
    request: Request,
    session: SessionDep,
    year: YearQuery = 2021,
    response_format: FormatQuery = None,
) -> Any:
    """Number of employees hired for each department and job in `year`, divided by quarter,
    ordered alphabetically by department and job. Only combinations with hires are listed."""
    rows = metrics.hires_by_quarter(session, year)
    if wants_csv(request, response_format):
        return csv_response(rows, list(QuarterlyHires.model_fields), f"hires_by_quarter_{year}.csv")
    return rows


class DepartmentHires(BaseModel):
    id: int
    department: str
    hired: int


@router.get(
    "/departments-above-mean",
    response_model=list[DepartmentHires],
    summary="Departments that hired more than the mean",
    responses={200: CSV_RESPONSE_DOC},
)
def departments_above_mean(
    request: Request,
    session: SessionDep,
    year: YearQuery = 2021,
    response_format: FormatQuery = None,
) -> Any:
    """Id, name and number of employees hired in `year` of each department that hired more than
    the mean of all departments that year (departments without hires count as 0), ordered by
    the number of employees hired, descending."""
    rows = metrics.departments_above_mean(session, year)
    if wants_csv(request, response_format):
        return csv_response(
            rows, list(DepartmentHires.model_fields), f"departments_above_mean_{year}.csv"
        )
    return rows
