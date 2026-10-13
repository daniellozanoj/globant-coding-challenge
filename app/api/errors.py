"""Translate domain exceptions into HTTP responses."""

import csv

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorOut
from app.core.batch import BatchConflictError, BatchValidationError
from app.core.loader import IngestionError

# Failures caused by the content of the file (client errors) rather than by the server.
_INVALID_FILE_ERRORS = (UnicodeDecodeError, csv.Error)


async def _ingestion_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, IngestionError)
    if isinstance(exc.__cause__, _INVALID_FILE_ERRORS):
        status_code = status.HTTP_400_BAD_REQUEST
        detail = f"The file could not be read as a UTF-8 CSV: {exc}"
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "The load failed unexpectedly; it can be safely retried."
    body = ErrorOut(detail=detail, job_id=exc.job_id)
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def _batch_validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Same shape as FastAPI request validation errors, so clients parse a single format."""
    assert isinstance(exc, BatchValidationError)
    detail = [
        {"loc": ["body", "rows", e.index, e.field], "msg": e.message, "type": e.type}
        for e in exc.errors
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": detail}
    )


async def _batch_conflict_error_handler(_: Request, exc: Exception) -> JSONResponse:
    body = ErrorOut(detail=f"The database rejected the batch, nothing was written: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=body.model_dump(mode="json", exclude_none=True),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IngestionError, _ingestion_error_handler)
    app.add_exception_handler(BatchValidationError, _batch_validation_error_handler)
    app.add_exception_handler(BatchConflictError, _batch_conflict_error_handler)
