"""Translate domain exceptions into HTTP responses."""

import csv

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorOut
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


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IngestionError, _ingestion_error_handler)
