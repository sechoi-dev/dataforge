# DataForge

DataForge is a distributed data-quality and dataset-validation platform. The repository is
currently includes **Phase 2: Basic asynchronous analysis**. Users can create a logical dataset,
upload a CSV version, poll its background job, and retrieve a JSON quality report.

## Current services

- FastAPI API with liveness (`/health`) and dependency readiness (`/ready`) endpoints
- PostgreSQL 16 as the durable source of truth
- Redis 7 for Celery transport and results
- MinIO for S3-compatible input and report storage
- Separate Celery worker and beat scheduler processes
- Alembic migration baseline, applied before backend services start
- Ruff, mypy, pytest, and GitHub Actions checks

## Start locally

Requirements: Docker with Compose v2.

```bash
docker compose up --build
```

Then open <http://localhost:8000/docs>, or check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`/health` reports only API process liveness. `/ready` checks PostgreSQL, Redis, and MinIO and
returns HTTP 503 if any required dependency is unavailable.

## Basic API workflow

Create a logical dataset:

```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d '{"name":"Survey responses"}'
```

Upload a CSV using the returned dataset ID:

```bash
curl -X POST http://localhost:8000/api/v1/datasets/DATASET_ID/versions \
  -F "file=@sample.csv;type=text/csv"
```

The upload returns HTTP 202 with a version and job. Poll
`GET /api/v1/jobs/JOB_ID`, then retrieve
`GET /api/v1/datasets/DATASET_ID/versions/VERSION_ID/report` after the job succeeds.

Stop the stack with `docker compose down`. Add `--volumes` only when you intentionally want to
delete local PostgreSQL and Redis data.

## Backend development

Python 3.12 is required.

```bash
cd backend
python -m venv .venv
python -m pip install -e ".[dev]"
ruff format .
ruff check .
mypy app tests
pytest
```

Copy `.env.example` to `.env` to customize runtime configuration. Every setting uses the
`DATAFORGE_` prefix.

## Architecture and boundaries

The API, worker, and scheduler share one backend image and application package. PostgreSQL,
Redis, and MinIO use persistent named volumes. Compose waits for dependency health and for the
one-shot migration service before starting application processes. CSV uploads are bounded and
stored in MinIO; pandas analysis runs only in the Celery worker.

Phase 2 analysis is intentionally limited to a basic profile, per-column missingness, exact
duplicate rows, and JSON reports. Idempotency, atomic claiming, retries, dead-lettering,
cancellation, richer validation, HTML reports, comparisons, authentication, frontend, and
observability belong to later phases in `docs/master-spec.md`.
