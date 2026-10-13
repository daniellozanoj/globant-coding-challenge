"""Response models of the HTTP API."""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.core.tables import TableName


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_name: str
    source: str
    status: str
    rows_read: int
    rows_loaded: int
    rows_rejected: int
    error: str | None
    created_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None


class RejectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_number: int
    raw_record: list[str]
    errors: list[str]


class RejectionPage(BaseModel):
    items: list[RejectionOut]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    detail: str
    job_id: uuid.UUID | None = None


class UploadRequest(BaseModel):
    table: TableName


class UploadTicket(BaseModel):
    job_id: uuid.UUID
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str]
    expires_in: int
    status_url: str
