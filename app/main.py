"""FastAPI application entry point."""

from fastapi import FastAPI


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

    return app


app = create_app()
