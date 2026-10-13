"""Registry of the migrated tables: CSV column order, validation schema and load order."""

from dataclasses import dataclass
from enum import StrEnum

from app.core.schemas import DepartmentRecord, HiredEmployeeRecord, JobRecord, Record


class TableName(StrEnum):
    DEPARTMENTS = "departments"
    JOBS = "jobs"
    HIRED_EMPLOYEES = "hired_employees"


@dataclass(frozen=True)
class TableSpec:
    name: TableName
    record_type: type[Record]

    @property
    def columns(self) -> tuple[str, ...]:
        """CSV column order, which is the schema field order (the files have no header)."""
        return tuple(self.record_type.model_fields)


TABLES: dict[TableName, TableSpec] = {
    TableName.DEPARTMENTS: TableSpec(TableName.DEPARTMENTS, DepartmentRecord),
    TableName.JOBS: TableSpec(TableName.JOBS, JobRecord),
    TableName.HIRED_EMPLOYEES: TableSpec(TableName.HIRED_EMPLOYEES, HiredEmployeeRecord),
}

# Catalog tables first: hired_employees references departments and jobs.
LOAD_ORDER: tuple[TableName, ...] = (
    TableName.DEPARTMENTS,
    TableName.JOBS,
    TableName.HIRED_EMPLOYEES,
)
