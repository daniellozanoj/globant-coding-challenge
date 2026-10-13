"""Event-driven loader: SQS batches with S3 notifications, processed with mocked S3."""

import json
import uuid
from collections.abc import Iterator
from urllib.parse import quote_plus

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import Session, sessionmaker

from app.aws.s3 import s3_client
from app.config import Settings, get_settings
from app.core.landing import landing_key, rejected_key
from app.core.tables import TableName
from app.db import repository
from app.db.models import IngestionJob, IngestionStatus
from app.handlers.migrations import run_migrations
from app.handlers.s3_loader import handle_sqs_event
from app.main import create_app
from tests.support import DATA_DIR

pytestmark = pytest.mark.integration

BUCKET = "globant-raw-test"


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    settings.raw_bucket = BUCKET
    s3_client.cache_clear()
    with mock_aws():
        client = boto3.client("s3", region_name=settings.aws_region)
        client.create_bucket(Bucket=BUCKET)
        yield client
    s3_client.cache_clear()


def put_landing_file(s3, table: TableName, content: bytes, job_id: uuid.UUID | None = None) -> str:
    key = landing_key(table, job_id or uuid.uuid4())
    s3.put_object(Bucket=BUCKET, Key=key, Body=content)
    return key


def sqs_event(*keys: str, message_id: str = "msg-1") -> dict:
    """An SQS batch with one message wrapping an S3 ObjectCreated notification."""
    s3_event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {"bucket": {"name": BUCKET}, "object": {"key": quote_plus(key)}},
            }
            for key in keys
        ]
    }
    return {
        "Records": [
            {"messageId": message_id, "eventSource": "aws:sqs", "body": json.dumps(s3_event)}
        ]
    }


def get_job(session_factory: sessionmaker[Session], job_id: uuid.UUID) -> IngestionJob:
    with session_factory() as session:
        return session.get(IngestionJob, job_id)


def job_id_of(key: str) -> uuid.UUID:
    return uuid.UUID(key.rsplit("/", 1)[1].removesuffix(".csv"))


def load_catalogs(s3, session_factory, settings) -> None:
    for table in (TableName.DEPARTMENTS, TableName.JOBS):
        key = put_landing_file(s3, table, (DATA_DIR / f"{table}.csv").read_bytes())
        handle_sqs_event(sqs_event(key), session_factory, settings)


def test_uploaded_files_are_loaded_and_rejections_mirrored_to_s3(
    s3, session_factory, settings
) -> None:
    load_catalogs(s3, session_factory, settings)
    key = put_landing_file(
        s3, TableName.HIRED_EMPLOYEES, (DATA_DIR / "hired_employees.csv").read_bytes()
    )

    result = handle_sqs_event(sqs_event(key), session_factory, settings)

    assert result == {"batchItemFailures": []}
    job = get_job(session_factory, job_id_of(key))
    assert job.status == IngestionStatus.SUCCEEDED
    assert job.source == f"s3://{BUCKET}/{key}"
    assert (job.rows_read, job.rows_loaded, job.rows_rejected) == (1999, 1929, 70)

    rejected = s3.get_object(Bucket=BUCKET, Key=rejected_key(TableName.HIRED_EMPLOYEES, job.id))
    lines = rejected["Body"].read().decode().splitlines()
    assert lines[0] == "line_number,raw_record,errors"
    assert len(lines) == 71
    assert lines[1] == '2,"2,Ty Hofer,2021-05-30T05:43:46Z,8,",job_id: Field required'


def test_job_created_by_post_uploads_is_reused(s3, session_factory, settings) -> None:
    with session_factory() as session:
        job_id = uuid.uuid4()
        repository.create_ingestion_job(session, TableName.JOBS, "s3://...", job_id=job_id)
    key = put_landing_file(s3, TableName.JOBS, b"1,Recruiter\n", job_id=job_id)

    handle_sqs_event(sqs_event(key), session_factory, settings)

    assert get_job(session_factory, job_id).status == IngestionStatus.SUCCEEDED


def test_duplicate_delivery_of_a_succeeded_job_is_skipped(s3, session_factory, settings) -> None:
    key = put_landing_file(s3, TableName.DEPARTMENTS, b"1,Sales\nx,bad\n")
    handle_sqs_event(sqs_event(key), session_factory, settings)
    first = get_job(session_factory, job_id_of(key))

    handle_sqs_event(sqs_event(key), session_factory, settings)

    again = get_job(session_factory, job_id_of(key))
    assert (again.rows_read, again.rows_rejected, again.finished_at) == (
        first.rows_read,
        first.rows_rejected,
        first.finished_at,
    )


def test_retry_of_a_failed_job_starts_from_scratch(s3, session_factory, settings) -> None:
    job_id = uuid.uuid4()
    with session_factory() as session:
        job = repository.create_ingestion_job(
            session, TableName.DEPARTMENTS, "s3://", job_id=job_id
        )
        job.status, job.rows_read, job.error = IngestionStatus.FAILED, 99, "boom"
        session.commit()
    key = put_landing_file(s3, TableName.DEPARTMENTS, b"1,Sales\n2,Legal\n", job_id=job_id)

    handle_sqs_event(sqs_event(key), session_factory, settings)

    job = get_job(session_factory, job_id)
    assert (job.status, job.rows_read, job.error) == (IngestionStatus.SUCCEEDED, 2, None)


def test_keys_outside_the_landing_zone_are_ignored(s3, session_factory, settings) -> None:
    s3.put_object(Bucket=BUCKET, Key="landing/notes.txt", Body=b"hello")

    result = handle_sqs_event(sqs_event("landing/notes.txt"), session_factory, settings)

    assert result == {"batchItemFailures": []}


def test_s3_test_events_are_ignored(session_factory, settings) -> None:
    event = {
        "Records": [
            {
                "messageId": "msg-1",
                "eventSource": "aws:sqs",
                "body": json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent"}),
            }
        ]
    }

    assert handle_sqs_event(event, session_factory, settings) == {"batchItemFailures": []}


def test_invalid_file_fails_the_job_without_retrying(s3, session_factory, settings) -> None:
    key = put_landing_file(s3, TableName.DEPARTMENTS, "1,Logística\n".encode("latin-1"))

    result = handle_sqs_event(sqs_event(key), session_factory, settings)

    assert result == {"batchItemFailures": []}
    job = get_job(session_factory, job_id_of(key))
    assert job.status == IngestionStatus.FAILED
    assert job.error.startswith("UnicodeDecodeError")


def test_transient_failures_are_reported_for_retry(s3, session_factory, settings) -> None:
    ok = put_landing_file(s3, TableName.DEPARTMENTS, b"1,Sales\n")
    missing = landing_key(TableName.DEPARTMENTS, uuid.uuid4())  # never uploaded: NoSuchKey
    event = sqs_event(ok, message_id="ok")
    event["Records"] += sqs_event(missing, message_id="broken")["Records"]

    result = handle_sqs_event(event, session_factory, settings)

    assert result == {"batchItemFailures": [{"itemIdentifier": "broken"}]}
    assert get_job(session_factory, job_id_of(ok)).status == IngestionStatus.SUCCEEDED


def test_migration_handler_reports_the_current_revision(engine) -> None:
    assert run_migrations(engine) == "0001"


# --- Pass-through endpoint (AWS Lambda Web Adapter) ---


def test_internal_events_endpoint_is_not_exposed_by_default(client: TestClient) -> None:
    assert client.post("/internal/events", json={"action": "migrate"}).status_code == 404


def test_internal_events_endpoint_dispatches_sqs_batches(
    s3, session_factory, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.enable_event_handlers = True
    monkeypatch.setattr("app.handlers.events.get_sessionmaker", lambda: session_factory)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    key = put_landing_file(s3, TableName.JOBS, b"1,Recruiter\n")

    with TestClient(app) as client:
        response = client.post("/internal/events", json=sqs_event(key))
        unsupported = client.post("/internal/events", json={"action": "dance"})

    assert response.json() == {"batchItemFailures": []}
    assert get_job(session_factory, job_id_of(key)).status == IngestionStatus.SUCCEEDED
    assert unsupported.status_code == 400
