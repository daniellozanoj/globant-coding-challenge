import datetime as dt

import pytest
from pydantic import ValidationError

from app.core.schemas import DepartmentRecord, HiredEmployeeRecord, JobRecord

VALID_EMPLOYEE = {
    "id": "4535",
    "name": "Marcelo Gonzalez",
    "datetime": "2021-07-27T16:02:08Z",
    "department_id": "1",
    "job_id": "2",
}


def test_valid_employee_is_coerced_to_typed_values() -> None:
    record = HiredEmployeeRecord.model_validate(VALID_EMPLOYEE)

    assert record.id == 4535
    assert record.datetime == dt.datetime(2021, 7, 27, 16, 2, 8, tzinfo=dt.UTC)
    assert (record.department_id, record.job_id) == (1, 2)


def test_datetime_with_offset_is_normalized_to_utc() -> None:
    record = HiredEmployeeRecord.model_validate(
        {**VALID_EMPLOYEE, "datetime": "2021-07-27T11:02:08-05:00"}
    )

    assert record.datetime == dt.datetime(2021, 7, 27, 16, 2, 8, tzinfo=dt.UTC)
    assert record.datetime.tzinfo == dt.UTC


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("2021-07-27T16:02:08", "must include a timezone"),
        ("2021-07-27", "must include a timezone"),
        ("27/07/2021 16:02", "must be an ISO 8601 datetime"),
        ("1627401728", "must be an ISO 8601 datetime"),
    ],
)
def test_datetime_must_be_iso8601_with_timezone(value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        HiredEmployeeRecord.model_validate({**VALID_EMPLOYEE, "datetime": value})


@pytest.mark.parametrize("field", ["id", "department_id", "job_id"])
@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_ids_must_be_positive_integers(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        HiredEmployeeRecord.model_validate({**VALID_EMPLOYEE, field: value})


def test_text_is_trimmed() -> None:
    record = DepartmentRecord.model_validate({"id": 1, "department": "  Supply Chain "})

    assert record.department == "Supply Chain"


@pytest.mark.parametrize("value", ["", "   ", "x" * 256])
def test_text_must_have_1_to_255_characters(value: str) -> None:
    with pytest.raises(ValidationError):
        JobRecord.model_validate({"id": 1, "job": value})


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        JobRecord.model_validate({"id": 1, "job": "Recruiter", "salary": 10})
