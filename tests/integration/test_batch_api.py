import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Department, HiredEmployee

pytestmark = pytest.mark.integration


def employee(id_: int, department_id: int = 1, job_id: int = 1, **overrides) -> dict:
    return {
        "id": id_,
        "name": f"Employee {id_}",
        "datetime": "2021-07-27T16:02:08Z",
        "department_id": department_id,
        "job_id": job_id,
        **overrides,
    }


def post_batch(client: TestClient, table: str, rows: list[dict]):
    return client.post(f"/api/v1/{table}/batch", json={"rows": rows})


@pytest.fixture
def catalogs(client: TestClient) -> None:
    """Departments 1-2 and jobs 1-2, created through the batch endpoints themselves."""
    post_batch(
        client, "departments", [{"id": 1, "department": "Sales"}, {"id": 2, "department": "Legal"}]
    )
    post_batch(client, "jobs", [{"id": 1, "job": "Recruiter"}, {"id": 2, "job": "Manager"}])


def count_employees(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(HiredEmployee))


# --- Happy paths ---


@pytest.mark.parametrize(
    ("table", "rows"),
    [
        ("departments", [{"id": 1, "department": "Supply Chain"}]),
        ("jobs", [{"id": 1, "job": "Recruiter"}, {"id": 2, "job": "Manager"}]),
    ],
)
def test_catalog_batches_are_inserted(client: TestClient, table: str, rows: list[dict]) -> None:
    response = post_batch(client, table, rows)

    assert response.status_code == 201
    assert response.json() == {"table": table, "rows_upserted": len(rows)}


def test_employee_batch_is_inserted(client: TestClient, catalogs: None, session_factory) -> None:
    response = post_batch(client, "hired_employees", [employee(1), employee(2, 2, 2)])

    assert response.status_code == 201
    assert response.json() == {"table": "hired_employees", "rows_upserted": 2}
    assert count_employees(session_factory) == 2


def test_batch_of_exactly_1000_rows_is_accepted(
    client: TestClient, catalogs: None, session_factory
) -> None:
    response = post_batch(client, "hired_employees", [employee(i) for i in range(1, 1001)])

    assert response.status_code == 201
    assert count_employees(session_factory) == 1000


def test_existing_rows_are_updated(client: TestClient, session_factory) -> None:
    post_batch(client, "departments", [{"id": 1, "department": "Supply Chain"}])

    response = post_batch(client, "departments", [{"id": 1, "department": "Logistics"}])

    assert response.status_code == 201
    with session_factory() as session:
        assert session.scalars(select(Department.department)).all() == ["Logistics"]


# --- Size limits ---


@pytest.mark.parametrize("size", [0, 1001])
def test_batch_size_must_be_between_1_and_1000(client: TestClient, size: int) -> None:
    rows = [{"id": i, "job": f"Job {i}"} for i in range(1, size + 1)]

    response = post_batch(client, "jobs", rows)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "rows"]


# --- Row validation ---


def test_schema_errors_point_to_the_row_and_field(client: TestClient, catalogs: None) -> None:
    rows = [employee(1), employee(2, datetime="2021-07-27T16:02:08"), employee(3, salary=10)]

    response = post_batch(client, "hired_employees", rows)

    assert response.status_code == 422
    locations = [error["loc"] for error in response.json()["detail"]]
    assert locations == [["body", "rows", 1, "datetime"], ["body", "rows", 2, "salary"]]


def test_duplicated_ids_are_rejected(client: TestClient) -> None:
    rows = [{"id": 7, "job": "A"}, {"id": 8, "job": "B"}, {"id": 7, "job": "C"}]

    response = post_batch(client, "jobs", rows)

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "loc": ["body", "rows", 2, "id"],
            "msg": "duplicated id 7 in the batch",
            "type": "duplicate_id",
        }
    ]


def test_unknown_department_and_job_are_rejected(client: TestClient, catalogs: None) -> None:
    rows = [employee(1), employee(2, department_id=99), employee(3, job_id=77)]

    response = post_batch(client, "hired_employees", rows)

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "loc": ["body", "rows", 1, "department_id"],
            "msg": "department_id: 99 does not exist",
            "type": "foreign_key_violation",
        },
        {
            "loc": ["body", "rows", 2, "job_id"],
            "msg": "job_id: 77 does not exist",
            "type": "foreign_key_violation",
        },
    ]


# --- Atomicity ---


def test_one_invalid_row_rejects_the_whole_batch(
    client: TestClient, catalogs: None, session_factory
) -> None:
    rows = [employee(i) for i in range(1, 1000)] + [employee(1000, department_id=99)]

    response = post_batch(client, "hired_employees", rows)

    assert response.status_code == 422
    assert count_employees(session_factory) == 0


def test_database_rejection_returns_409_and_writes_nothing(
    client: TestClient, catalogs: None, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a department deleted between the FK check and the insert."""
    monkeypatch.setattr("app.core.batch._reference_errors", lambda session, records: [])

    response = post_batch(client, "hired_employees", [employee(1), employee(2, department_id=99)])

    assert response.status_code == 409
    assert "nothing was written" in response.json()["detail"]
    assert count_employees(session_factory) == 0
