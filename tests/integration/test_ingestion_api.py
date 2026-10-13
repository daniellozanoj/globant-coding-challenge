from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from tests.support import DATA_DIR

pytestmark = pytest.mark.integration


def upload(client: TestClient, table: str, content: bytes, filename: str = "file.csv", **params):
    return client.post(
        f"/api/v1/ingestions/{table}",
        files={"file": (filename, content, "text/csv")},
        params=params,
    )


def upload_sample(client: TestClient, table: str):
    return upload(client, table, (DATA_DIR / f"{table}.csv").read_bytes(), f"{table}.csv")


# --- Upload ---


def test_upload_loads_the_file_and_returns_the_job(client: TestClient) -> None:
    response = upload_sample(client, "departments")

    assert response.status_code == 201
    job = response.json()
    assert job["table_name"] == "departments"
    assert job["source"] == "upload:departments.csv"
    assert job["status"] == "SUCCEEDED"
    assert (job["rows_read"], job["rows_loaded"], job["rows_rejected"]) == (12, 12, 0)
    assert response.headers["location"].endswith(f"/api/v1/ingestions/{job['id']}")


def test_uploading_the_sample_files_in_order_migrates_them(client: TestClient) -> None:
    upload_sample(client, "departments")
    upload_sample(client, "jobs")

    job = upload_sample(client, "hired_employees").json()

    assert (job["rows_read"], job["rows_loaded"], job["rows_rejected"]) == (1999, 1929, 70)


def test_upload_can_skip_a_header_row(client: TestClient) -> None:
    job = upload(client, "jobs", b"id,job\n1,Recruiter\n", has_header=True).json()

    assert (job["rows_read"], job["rows_loaded"]) == (1, 1)


def test_unknown_table_is_rejected(client: TestClient) -> None:
    response = upload(client, "salaries", b"1,x\n")

    assert response.status_code == 422


def test_only_csv_files_are_accepted(client: TestClient) -> None:
    response = upload(client, "jobs", b"1,Recruiter\n", filename="jobs.xlsx")

    assert response.status_code == 415


def test_files_over_the_size_limit_are_rejected(client: TestClient, settings: Settings) -> None:
    too_big = b"1,Recruiter\n" * (settings.max_upload_mb * 1024 * 1024 // 12 + 1)

    response = upload(client, "jobs", too_big)

    assert response.status_code == 413


def test_non_utf8_file_fails_the_job_with_400(client: TestClient) -> None:
    response = upload(client, "departments", "1,Logística\n".encode("latin-1"))

    assert response.status_code == 400
    job_id = response.json()["job_id"]
    job = client.get(f"/api/v1/ingestions/{job_id}").json()
    assert job["status"] == "FAILED"
    assert job["error"].startswith("UnicodeDecodeError")


# --- Historical migration ---


def test_historical_migration_loads_the_three_files_in_order(client: TestClient) -> None:
    response = client.post("/api/v1/ingestions/historical")

    assert response.status_code == 201
    jobs = response.json()
    assert [job["table_name"] for job in jobs] == ["departments", "jobs", "hired_employees"]
    assert [job["rows_loaded"] for job in jobs] == [12, 183, 1929]
    assert all(job["status"] == "SUCCEEDED" for job in jobs)


def test_historical_migration_fails_fast_when_a_file_is_missing(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    (tmp_path / "departments.csv").write_text("1,Sales\n")
    settings.local_data_dir = tmp_path

    response = client.post("/api/v1/ingestions/historical")

    assert response.status_code == 404
    assert "jobs.csv, hired_employees.csv" in response.json()["detail"]


# --- Job inspection ---


def test_get_job_returns_its_status(client: TestClient) -> None:
    created = upload_sample(client, "departments").json()

    response = client.get(f"/api/v1/ingestions/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_unknown_job_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/ingestions/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_rejections_are_paginated_and_ordered_by_line(client: TestClient) -> None:
    client.post("/api/v1/ingestions/historical")
    jobs = client.post("/api/v1/ingestions/historical").json()
    employees_job = jobs[2]["id"]

    first = client.get(f"/api/v1/ingestions/{employees_job}/rejections", params={"limit": 2})
    last = client.get(
        f"/api/v1/ingestions/{employees_job}/rejections", params={"limit": 10, "offset": 65}
    )

    page = first.json()
    assert (page["total"], page["limit"], page["offset"]) == (70, 2, 0)
    assert page["items"] == [
        {
            "line_number": 2,
            "raw_record": ["2", "Ty Hofer", "2021-05-30T05:43:46Z", "8", ""],
            "errors": ["job_id: Field required"],
        },
        {
            "line_number": 67,
            "raw_record": ["67", "Thia Morican", "2021-03-10T19:27:10Z", "", "104"],
            "errors": ["department_id: Field required"],
        },
    ]
    assert len(last.json()["items"]) == 5
