"""Validation schemas for one record of each migrated table.

The same schemas validate CSV rows and the JSON payloads of the batch endpoint.
"""

import datetime as dt
from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    PositiveInt,
    StringConstraints,
    field_validator,
)

MAX_BATCH_ROWS = 1000

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class Record(BaseModel):
    """Common base: every table is keyed by a positive id coming from the source system."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PositiveInt


class DepartmentRecord(Record):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"id": 1, "department": "Supply Chain"}]}
    )

    department: NonEmptyStr


class JobRecord(Record):
    model_config = ConfigDict(json_schema_extra={"examples": [{"id": 1, "job": "Recruiter"}]})

    job: NonEmptyStr


class HiredEmployeeRecord(Record):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 4535,
                    "name": "Marcelo Gonzalez",
                    "datetime": "2021-07-27T16:02:08Z",
                    "department_id": 1,
                    "job_id": 2,
                }
            ]
        }
    )

    name: NonEmptyStr
    datetime: AwareDatetime
    department_id: PositiveInt
    job_id: PositiveInt

    @field_validator("datetime", mode="before")
    @classmethod
    def _parse_iso8601(cls, value: Any) -> Any:
        """Accept only ISO 8601 strings with a timezone and normalize them to UTC.

        Pydantic would also accept Unix timestamps; the source contract is ISO 8601, so anything
        else is treated as a data quality issue.
        """
        if not isinstance(value, str):
            return value
        try:
            parsed = dt.datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("must be an ISO 8601 datetime, e.g. 2021-07-27T16:02:08Z") from None
        if parsed.tzinfo is None:
            raise ValueError("must include a timezone, e.g. 2021-07-27T16:02:08Z")
        return parsed.astimezone(dt.UTC)
