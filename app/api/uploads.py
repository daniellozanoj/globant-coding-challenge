"""Direct-to-S3 uploads: the client gets a presigned URL and uploads the CSV to S3 itself.

The file never goes through API Gateway or Lambda (no payload limits). S3 then notifies SQS and
the loader Lambda processes the file asynchronously (see docs/architecture.md, ADR-003).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import UploadRequest, UploadTicket
from app.aws.s3 import CSV_CONTENT_TYPE, presign_upload
from app.config import Settings, get_settings
from app.core.landing import landing_key
from app.db import repository
from app.db.session import get_session

router = APIRouter(prefix="/uploads", tags=["uploads"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Get a presigned URL to upload a CSV file directly to S3",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Direct uploads are not configured"}
    },
)
def create_upload(
    payload: UploadRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> UploadTicket:
    """Creates a PENDING ingestion job and returns where to PUT the file. Poll `status_url`
    to follow the asynchronous load."""
    if not settings.raw_bucket:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Direct uploads are not configured (RAW_BUCKET); use POST /api/v1/ingestions/{table}",
        )

    job_id = uuid.uuid4()
    key = landing_key(payload.table, job_id)
    job = repository.create_ingestion_job(
        session, payload.table, source=f"s3://{settings.raw_bucket}/{key}", job_id=job_id
    )

    status_url = str(request.url_for("get_ingestion", job_id=job.id))
    response.headers["Location"] = status_url
    return UploadTicket(
        job_id=job.id,
        upload_url=presign_upload(
            settings.aws_region,
            settings.raw_bucket,
            key,
            settings.upload_url_expiration_seconds,
        ),
        headers={"Content-Type": CSV_CONTENT_TYPE},
        expires_in=settings.upload_url_expiration_seconds,
        status_url=status_url,
    )
