# Globant Data Engineering Coding Challenge

REST API that migrates historical CSV data (`departments`, `jobs`, `hired_employees`) into a SQL
database and supports batch inserts of 1 to 1000 rows per request.

The solution is built **local-first and cloud-ready**: it runs locally with Docker, and the same
code and container image target a serverless architecture on **AWS**.

## Table of contents

- [Challenge scope](#challenge-scope)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Architecture](#architecture)
- [Development workflow](#development-workflow)
- Data model _(coming soon)_
- API reference _(coming soon)_
- Data quality rules _(coming soon)_
- Assumptions _(coming soon)_

## Challenge scope

| Section | Deliverable | Status |
|---|---|---|
| 1. API | Receive historical data from CSV files | ⏳ In progress |
| 1. API | Upload the files to the new SQL database | ⏳ In progress |
| 1. API | Insert batch transactions (1 to 1000 rows) in one request | ⏳ In progress |
| 2. SQL | Hires per job and department in 2021 by quarter | 🔜 Pending |
| 2. SQL | Departments that hired above the 2021 mean | 🔜 Pending |
| Bonus | Cloud hosting (AWS), automated tests, containers | 🔜 Pending |

## Tech stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Data engineering ecosystem, typing, AWS Lambda support |
| API framework | FastAPI | Pydantic validation and automatic OpenAPI docs |
| Validation | Pydantic v2 | Per-row validation of CSV records and request payloads |
| Database | PostgreSQL (Aurora PostgreSQL Serverless v2 on AWS) | Transactional workload, native upsert (`ON CONFLICT`), rich analytical SQL |
| Package manager | [uv](https://docs.astral.sh/uv/) | Fast, reproducible installs with a lockfile |
| Lint / format | Ruff | Single fast tool for linting and formatting |
| Tests | pytest | De facto standard for Python testing |

## Repository structure

```
.
├── app/
│   ├── api/          # HTTP layer (FastAPI routers)
│   ├── core/         # Ingestion logic: CSV parsing, validation, loading (no HTTP/AWS deps)
│   ├── db/           # SQLAlchemy models, session and repositories
│   ├── handlers/     # AWS Lambda entry points (event-driven loader)
│   └── main.py       # FastAPI application factory
├── docs/             # Architecture and design decisions
├── tests/
│   ├── unit/         # Fast tests, no external services
│   └── integration/  # Tests against a real PostgreSQL
├── Makefile          # Common developer commands
└── pyproject.toml    # Dependencies and tool configuration
```

## Getting started

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs
Python 3.12 automatically if needed).

```bash
make install   # create .venv and install dependencies
make run       # start the API on http://localhost:8000
```

Open the interactive docs at http://localhost:8000/docs and check the liveness probe:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Architecture

The API runs locally with Docker and targets a **serverless, pay-per-use architecture on AWS**,
chosen because a data migration is a sporadic, bursty workload with long idle periods.

```mermaid
flowchart LR
    client["Client"] -- "HTTPS + JWT" --> apigw["API Gateway<br/>HTTP API"]
    apigw --> apiFn["Lambda: api<br/>(FastAPI)"]
    client -- "PUT CSV<br/>(presigned URL)" --> s3[("S3<br/>landing/")]
    s3 -- "ObjectCreated" --> sqs["SQS + DLQ"]
    sqs --> loaderFn["Lambda: loader"]
    apiFn --> aurora[("Aurora PostgreSQL<br/>Serverless v2")]
    loaderFn --> aurora
```

| Concern | Decision |
|---|---|
| Compute | AWS Lambda (arm64, container image) behind API Gateway HTTP API |
| CSV ingestion | Direct upload to S3 with presigned URLs → SQS → loader Lambda |
| Database | Aurora PostgreSQL Serverless v2 (scales to zero) |
| Networking | Private subnets, no NAT Gateway, IAM database authentication |
| Authentication | Amazon Cognito JWT authorizer at API Gateway |
| Infrastructure as code | Terraform |

Idle cost is estimated at **~1–3 USD/month**, versus ~70–80 USD/month for an always-on container
stack. Full details, data flows, cost model and architecture decision records (ADRs):
**[docs/architecture.md](docs/architecture.md)**.

## Development workflow

```bash
make lint      # ruff check + format check
make format    # auto-fix and format
make test      # run the test suite
```

- One `feature/*` branch per step, merged into `main` through a Pull Request.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).
