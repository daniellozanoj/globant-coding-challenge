import uuid
from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.aws.s3 import s3_client
from app.config import Settings

pytestmark = pytest.mark.integration

BUCKET = "globant-raw-test"


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator[None]:
    """Mocked AWS with a raw bucket configured."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    settings.raw_bucket = BUCKET
    s3_client.cache_clear()
    with mock_aws():
        yield
    s3_client.cache_clear()


def test_upload_ticket_points_to_the_landing_key_of_a_pending_job(
    client: TestClient, aws: None
) -> None:
    response = client.post("/api/v1/uploads", json={"table": "hired_employees"})

    assert response.status_code == 201
    ticket = response.json()
    job_id = uuid.UUID(ticket["job_id"])

    url = urlsplit(ticket["upload_url"])
    query = parse_qs(url.query)
    assert BUCKET in url.netloc + url.path
    assert url.path.endswith(f"landing/hired_employees/{job_id}.csv")
    assert query["X-Amz-Expires"] == ["900"]
    assert "X-Amz-Signature" in query
    assert ticket["method"] == "PUT"
    assert ticket["headers"] == {"Content-Type": "text/csv"}
    assert ticket["expires_in"] == 900

    job = client.get(ticket["status_url"]).json()
    assert response.headers["location"] == ticket["status_url"]
    assert job["status"] == "PENDING"
    assert job["source"] == f"s3://{BUCKET}/landing/hired_employees/{job_id}.csv"


def test_unknown_table_is_rejected(client: TestClient, aws: None) -> None:
    assert client.post("/api/v1/uploads", json={"table": "salaries"}).status_code == 422


def test_uploads_need_a_raw_bucket(client: TestClient) -> None:
    response = client.post("/api/v1/uploads", json={"table": "jobs"})

    assert response.status_code == 503
    assert "RAW_BUCKET" in response.json()["detail"]
