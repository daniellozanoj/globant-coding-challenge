from urllib.parse import parse_qs, urlsplit

import pytest

from app.config import Settings
from app.db.session import build_engine, engine_options, iam_token_provider


@pytest.fixture(autouse=True)
def _fake_aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)


def iam_settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        db_host="aurora.cluster-abc.us-east-1.rds.amazonaws.com",
        db_user="app_iam",
        db_iam_auth=True,
        aws_region="us-east-1",
        **overrides,
    )


def test_iam_token_is_a_presigned_rds_connect_request() -> None:
    token = iam_token_provider(iam_settings())()

    url = urlsplit(f"https://{token}")
    query = parse_qs(url.query)
    assert url.hostname == "aurora.cluster-abc.us-east-1.rds.amazonaws.com"
    assert url.port == 5432
    assert query["Action"] == ["connect"]
    assert query["DBUser"] == ["app_iam"]
    assert "X-Amz-Signature" in query


def test_iam_engine_requires_tls_and_injects_a_token_per_connection() -> None:
    engine = build_engine(iam_settings())

    assert engine_options(iam_settings())["connect_args"] == {"sslmode": "require"}
    (provide_token,) = list(engine.dialect.dispatch.do_connect)

    params: dict = {}
    provide_token(engine.dialect, None, (), params)
    assert "X-Amz-Signature" in params["password"]


def test_password_engine_has_no_token_listener() -> None:
    settings = Settings(_env_file=None)
    engine = build_engine(settings)

    assert engine_options(settings)["connect_args"] == {}
    assert len(engine.dialect.dispatch.do_connect) == 0
