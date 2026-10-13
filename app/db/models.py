"""Database schema: migrated business tables plus ingestion audit tables."""

import datetime as dt
import uuid
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# --- Business tables (ids come from the source system, never generated) ---


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    department: Mapped[str] = mapped_column(String(255))


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    job: Mapped[str] = mapped_column(String(255))


class HiredEmployee(Base):
    __tablename__ = "hired_employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    datetime: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)


# --- Ingestion audit tables ---


class IngestionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class IngestionJob(Base):
    """One CSV load: its source, lifecycle status and row counters."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')", name="status_valid"
        ),
        CheckConstraint(
            "table_name IN ('departments', 'jobs', 'hired_employees')", name="table_name_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    table_name: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default=IngestionStatus.PENDING, server_default=IngestionStatus.PENDING
    )
    rows_read: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class LoadRejection(Base):
    """A CSV row that failed validation, kept for auditing instead of being dropped."""

    __tablename__ = "load_rejections"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    raw_record: Mapped[list[str]] = mapped_column(JSONB)
    errors: Mapped[list[str]] = mapped_column(JSONB)
    rejected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
