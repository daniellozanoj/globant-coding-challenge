"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api import batches, ingestions
from app.api.errors import register_exception_handlers

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Globant Data Engineering Challenge API",
        version="0.1.0",
        description="Migrates historical CSV data into a SQL database and exposes batch inserts.",
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    app.include_router(ingestions.router, prefix=API_PREFIX)
    app.include_router(batches.router, prefix=API_PREFIX)
    register_exception_handlers(app)
    return app


app = create_app()
