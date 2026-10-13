"""Pass-through endpoint for non-HTTP Lambda events.

The AWS Lambda Web Adapter POSTs SQS batches and direct invocations to AWS_LWA_PASS_THROUGH_PATH.
This router is mounted only when ENABLE_EVENT_HANDLERS is true (the loader Lambda), so it is never
reachable through API Gateway.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.handlers.events import UnsupportedEvent, dispatch

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.post("/events")
def handle_event(
    event: Annotated[dict[str, Any], Body()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    try:
        return dispatch(event, settings)
    except UnsupportedEvent as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
