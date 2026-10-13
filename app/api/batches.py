"""Batch insert endpoints: one typed route per table, generated from the table registry."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, create_model
from sqlalchemy.orm import Session

from app.core.batch import insert_batch
from app.core.schemas import MAX_BATCH_ROWS
from app.core.tables import TABLES, TableName, TableSpec
from app.db.session import get_session

router = APIRouter(tags=["batch inserts"])

SessionDep = Annotated[Session, Depends(get_session)]


class BatchResult(BaseModel):
    table: TableName
    rows_upserted: int


def _add_batch_route(spec: TableSpec) -> None:
    request_model = create_model(
        f"{spec.record_type.__name__.removesuffix('Record')}BatchRequest",
        rows=(
            list[spec.record_type],
            Field(min_length=1, max_length=MAX_BATCH_ROWS, description="1 to 1000 records"),
        ),
    )

    def insert_rows(payload: request_model, session: SessionDep) -> BatchResult:
        written = insert_batch(session, spec.name, payload.rows)
        return BatchResult(table=spec.name, rows_upserted=written)

    insert_rows.__doc__ = (
        f"Insert or update 1 to {MAX_BATCH_ROWS} `{spec.name}` rows in a single transaction. "
        "If any row is invalid, nothing is written and every error is reported."
    )
    router.add_api_route(
        f"/{spec.name}/batch",
        insert_rows,
        methods=["POST"],
        status_code=status.HTTP_201_CREATED,
        name=f"batch_{spec.name}",
        summary=f"Batch insert {spec.name}",
        responses={
            status.HTTP_409_CONFLICT: {"description": "The database rejected the batch"},
            status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Invalid rows, nothing written"},
        },
    )


for _spec in TABLES.values():
    _add_batch_route(_spec)
