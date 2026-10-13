"""Section 2 metrics on a hand-made dataset (expected values computed by hand) and on the
sample files."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.schemas import DepartmentRecord, HiredEmployeeRecord, JobRecord
from app.core.tables import TableName
from app.db import repository
from app.db.session import get_session

pytestmark = pytest.mark.integration

HIRES_BY_QUARTER = "/api/v1/metrics/hires-by-quarter"

DEPARTMENTS = {1: "Supply Chain", 2: "Staff", 3: "Maintenance"}
JOBS = {1: "Recruiter", 2: "Manager", 3: "GIS Analyst", 4: "Geologist"}
# (department_id, job_id, hire datetime)
HIRES = [
    (2, 1, "2021-01-15T09:00:00Z"),  # Staff / Recruiter, Q1
    (2, 1, "2021-03-31T23:59:59Z"),  # last second of Q1
    (2, 1, "2021-04-01T00:00:00Z"),  # first second of Q2
    (2, 1, "2021-12-31T23:59:59Z"),  # last second of the year, Q4
    (2, 1, "2021-03-31T20:00:00-05:00"),  # 2021-04-01T01:00Z: Q2 in UTC, Q1 in Bogota time
    (2, 2, "2021-07-01T00:00:00Z"),  # Staff / Manager, Q3
    (1, 2, "2021-06-30T23:59:59Z"),  # Supply Chain / Manager, Q2
    (1, 4, "2021-02-01T10:00:00Z"),  # Supply Chain / Geologist, Q1
    (1, 3, "2021-02-02T10:00:00Z"),  # Supply Chain / GIS Analyst, Q1
    (2, 1, "2020-12-31T23:59:59Z"),  # previous year: excluded
    (2, 1, "2022-01-01T00:00:00Z"),  # next year: excluded
]

EXPECTED_2021 = [
    {"department": "Staff", "job": "Manager", "Q1": 0, "Q2": 0, "Q3": 1, "Q4": 0},
    {"department": "Staff", "job": "Recruiter", "Q1": 2, "Q2": 2, "Q3": 0, "Q4": 1},
    # Alphabetical (linguistic) order: "Geologist" < "GIS Analyst", unlike byte order.
    {"department": "Supply Chain", "job": "Geologist", "Q1": 1, "Q2": 0, "Q3": 0, "Q4": 0},
    {"department": "Supply Chain", "job": "GIS Analyst", "Q1": 1, "Q2": 0, "Q3": 0, "Q4": 0},
    {"department": "Supply Chain", "job": "Manager", "Q1": 0, "Q2": 1, "Q3": 0, "Q4": 0},
]


@pytest.fixture
def hires(session: Session) -> None:
    repository.upsert_records(
        session,
        TableName.DEPARTMENTS,
        [DepartmentRecord(id=i, department=name) for i, name in DEPARTMENTS.items()],
    )
    repository.upsert_records(
        session, TableName.JOBS, [JobRecord(id=i, job=name) for i, name in JOBS.items()]
    )
    repository.upsert_records(
        session,
        TableName.HIRED_EMPLOYEES,
        [
            HiredEmployeeRecord.model_validate(
                {
                    "id": i,
                    "name": f"Employee {i}",
                    "datetime": hired_at,
                    "department_id": department_id,
                    "job_id": job_id,
                }
            )
            for i, (department_id, job_id, hired_at) in enumerate(HIRES, start=1)
        ],
    )
    session.commit()


# --- Hires by quarter ---


def test_hires_by_quarter_defaults_to_2021(client: TestClient, hires: None) -> None:
    response = client.get(HIRES_BY_QUARTER)

    assert response.status_code == 200
    assert response.json() == EXPECTED_2021


def test_quarters_are_computed_in_utc_whatever_the_session_time_zone(
    client: TestClient, hires: None, database_url: str
) -> None:
    bogota_engine = create_engine(
        database_url, connect_args={"options": "-c timezone=America/Bogota"}
    )
    bogota_sessions = sessionmaker(bind=bogota_engine)

    def bogota_session() -> Iterator[Session]:
        with bogota_sessions() as session:
            yield session

    client.app.dependency_overrides[get_session] = bogota_session
    try:
        response = client.get(HIRES_BY_QUARTER)
    finally:
        bogota_engine.dispose()

    assert response.json() == EXPECTED_2021


def test_hires_by_quarter_for_another_year(client: TestClient, hires: None) -> None:
    response = client.get(HIRES_BY_QUARTER, params={"year": 2022})

    assert response.json() == [
        {"department": "Staff", "job": "Recruiter", "Q1": 1, "Q2": 0, "Q3": 0, "Q4": 0}
    ]


def test_year_without_hires_returns_an_empty_list(client: TestClient, hires: None) -> None:
    assert client.get(HIRES_BY_QUARTER, params={"year": 2019}).json() == []


@pytest.mark.parametrize("year", ["1999", "2101", "last"])
def test_invalid_year_is_rejected(client: TestClient, year: str) -> None:
    assert client.get(HIRES_BY_QUARTER, params={"year": year}).status_code == 422


@pytest.mark.parametrize(
    ("headers", "params"),
    [({"Accept": "text/csv"}, {}), ({}, {"format": "csv"})],
)
def test_hires_by_quarter_as_csv(
    client: TestClient, hires: None, headers: dict, params: dict
) -> None:
    response = client.get(HIRES_BY_QUARTER, headers=headers, params=params)

    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="hires_by_quarter_2021.csv"' in response.headers["content-disposition"]
    assert response.text.splitlines()[:3] == [
        "department,job,Q1,Q2,Q3,Q4",
        "Staff,Manager,0,0,1,0",
        "Staff,Recruiter,2,2,0,1",
    ]


def test_format_json_overrides_the_accept_header(client: TestClient, hires: None) -> None:
    response = client.get(
        HIRES_BY_QUARTER, headers={"Accept": "text/csv"}, params={"format": "json"}
    )

    assert response.json() == EXPECTED_2021


def test_hires_by_quarter_on_the_sample_files(client: TestClient) -> None:
    client.post("/api/v1/ingestions/historical")

    rows = client.get(HIRES_BY_QUARTER).json()

    assert len(rows) == 933
    assert sum(row["Q1"] + row["Q2"] + row["Q3"] + row["Q4"] for row in rows) == 1643
    assert rows[0] == {
        "department": "Accounting",
        "job": "Account Representative IV",
        "Q1": 1,
        "Q2": 0,
        "Q3": 0,
        "Q4": 0,
    }
