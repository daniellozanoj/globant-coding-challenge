# One image for every runtime: local Docker, docker compose and AWS Lambda
# (through the AWS Lambda Web Adapter extension, inactive outside Lambda).

ARG PYTHON_VERSION=3.12

FROM ghcr.io/astral-sh/uv:0.12.22 AS uv
FROM public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 AS lambda-adapter

# --- Build stage: resolve the production dependencies into a virtualenv ---
FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
# Dependencies first: this layer is reused until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Runtime stage: only the virtualenv and the application code ---
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AWS_LWA_PORT=8000 \
    AWS_LWA_READINESS_CHECK_PATH=/health

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

WORKDIR /app
COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
