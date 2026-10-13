import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore the developer's .env file and DB_* variables."""
    for var in ("DATABASE_URL", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)


def test_defaults_point_to_local_postgres() -> None:
    settings = Settings()

    assert (
        settings.sqlalchemy_url == "postgresql+psycopg://postgres:postgres@localhost:5432/globant"
    )


def test_url_is_built_from_environment_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_HOST", "aurora.cluster.local")
    monkeypatch.setenv("DB_PORT", "6543")
    monkeypatch.setenv("DB_USER", "app")
    monkeypatch.setenv("DB_PASSWORD", "p@ss:w/rd")

    settings = Settings()

    assert settings.sqlalchemy_url == (
        "postgresql+psycopg://app:p%40ss%3Aw%2Frd@aurora.cluster.local:6543/globant"
    )


def test_database_url_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/other")
    monkeypatch.setenv("DB_HOST", "ignored")

    assert Settings().sqlalchemy_url == "postgresql+psycopg://u:p@db:5432/other"


def test_invalid_port_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_PORT", "70000")

    with pytest.raises(ValueError):
        Settings()
