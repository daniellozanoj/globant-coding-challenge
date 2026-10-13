import uuid

import pytest

from app.core.landing import landing_key, parse_landing_key, rejected_key
from app.core.tables import TableName

JOB_ID = uuid.UUID("0ee81f35-1699-4644-aca9-21d7e0556d82")


def test_landing_key_embeds_table_and_job_id() -> None:
    key = landing_key(TableName.HIRED_EMPLOYEES, JOB_ID)

    assert key == f"landing/hired_employees/{JOB_ID}.csv"
    assert parse_landing_key(key) == (TableName.HIRED_EMPLOYEES, JOB_ID)


def test_rejected_key_mirrors_the_landing_key() -> None:
    assert rejected_key(TableName.JOBS, JOB_ID) == f"rejected/jobs/{JOB_ID}.csv"


@pytest.mark.parametrize(
    "key",
    [
        f"landing/salaries/{JOB_ID}.csv",  # unknown table
        f"landing/jobs/{JOB_ID}.txt",  # not a CSV
        "landing/jobs/not-a-uuid.csv",
        f"rejected/jobs/{JOB_ID}.csv",  # outside the landing prefix
        f"landing/jobs/nested/{JOB_ID}.csv",
    ],
)
def test_keys_outside_the_contract_are_rejected(key: str) -> None:
    with pytest.raises(ValueError, match="not a landing key"):
        parse_landing_key(key)
