"""CSV ingestion endpoints: upload a file, migrate the historical files, inspect jobs."""

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import ErrorOut, IngestionJobOut, RejectionPage
from app.config import Settings, get_settings
from app.core.csv_reader import text_stream
from app.core.loader import load_csv
from app.core.tables import LOAD_ORDER, TableName
from app.db.models import IngestionJob, LoadRejection
from app.db.session import get_session

router = APIRouter(prefix="/ingestions", tags=["ingestions"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_FAILED_LOAD = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorOut, "description": "File is not a UTF-8 CSV"},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorOut, "description": "Load failed"},
}


# Declared before /{table} so "historical" is not parsed as a table name.
@router.post(
    "/historical",
    status_code=status.HTTP_201_CREATED,
    summary="Migrate the historical CSV files from the server data directory",
    responses={status.HTTP_404_NOT_FOUND: {"description": "A CSV file is missing"}, **_FAILED_LOAD},
)
def ingest_historical(session: SessionDep, settings: SettingsDep) -> list[IngestionJobOut]:
    """Load `departments.csv`, `jobs.csv` and `hired_employees.csv` from `LOCAL_DATA_DIR`,
    in dependency order. The directory is configuration, never client input."""
    paths = {table: settings.local_data_dir / f"{table}.csv" for table in LOAD_ORDER}
    missing = [path.name for path in paths.values() if not path.is_file()]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Missing files in {settings.local_data_dir}: {', '.join(missing)}",
        )

    jobs = []
    for table, path in paths.items():
        with path.open(encoding="utf-8-sig", newline="") as file:
            jobs.append(load_csv(session, table, file, source=f"file:{path}"))
    return [IngestionJobOut.model_validate(job) for job in jobs]


@router.post(
    "/{table}",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV file and load it into a table",
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "File too large"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "Not a .csv file"},
        **_FAILED_LOAD,
    },
)
def ingest_upload(
    table: TableName,
    file: UploadFile,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    has_header: Annotated[bool, Query(description="Skip the first row")] = False,
) -> IngestionJobOut:
    """Valid rows are upserted; invalid rows are stored as rejections of the returned job."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only .csv files are accepted")
    if file.size is not None and file.size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File exceeds the {settings.max_upload_mb} MB limit",
        )

    job = load_csv(
        session,
        table,
        text_stream(file.file),
        source=f"upload:{file.filename}",
        has_header=has_header,
    )
    response.headers["Location"] = str(request.url_for("get_ingestion", job_id=job.id))
    return IngestionJobOut.model_validate(job)


@router.get(
    "/{job_id}",
    summary="Get the status and counters of an ingestion job",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Job not found"}},
)
def get_ingestion(job_id: uuid.UUID, session: SessionDep) -> IngestionJobOut:
    return IngestionJobOut.model_validate(_get_job_or_404(session, job_id))


@router.get(
    "/{job_id}/rejections",
    summary="List the rows rejected by an ingestion job",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Job not found"}},
)
def list_rejections(
    job_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RejectionPage:
    _get_job_or_404(session, job_id)
    by_job = LoadRejection.job_id == job_id
    total = session.scalar(select(func.count()).where(by_job))
    rejections = session.scalars(
        select(LoadRejection)
        .where(by_job)
        .order_by(LoadRejection.line_number)
        .limit(limit)
        .offset(offset)
    ).all()
    return RejectionPage.model_validate(
        {"items": rejections, "total": total, "limit": limit, "offset": offset},
        from_attributes=True,
    )


def _get_job_or_404(session: Session, job_id: uuid.UUID) -> IngestionJob:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Ingestion job {job_id} not found")
    return job
