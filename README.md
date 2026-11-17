# DataForge

DataForge is a distributed data-quality and dataset-validation platform implementing the complete
ten-phase plan. Users can define dataset validation rules,
upload a CSV version idempotently, poll its background job, inspect attempts, and retrieve JSON
or HTML quality reports with explainable scores and deductions. Versions can be compared for
schema and profile drift, category changes, and dataset overlap. Jobs expose durable progress,
cooperative cancellation, scheduled dispatch, worker leases, and killed-worker recovery.

## Current services

- FastAPI API with liveness (`/health`) and dependency readiness (`/ready`) endpoints
- PostgreSQL 16 as the durable source of truth
- Redis 7 for Celery transport and results
- MinIO for S3-compatible input and report storage
- Separate Celery worker and beat scheduler processes
- Alembic migration baseline, applied before backend services start
- Numeric and categorical profiling, mixed-type detection, and IQR outlier observations
- Persisted validation results and explainable quality scoring
- JSON and escaped, human-readable HTML reports
- Persisted, downloadable version-comparison reports with severity-classified changes
- Durable scheduled jobs, progress events, cancellation, leases, and crash recovery
- JSON logs, correlation IDs, Prometheus metrics, and a provisioned Grafana dashboard
- Responsive browser workflow for datasets, versions, reports, jobs, and comparisons
- Ruff, mypy, pytest, and GitHub Actions checks

## Start locally

Requirements: Docker with Compose v2.

```bash
docker compose up --build
```

Then open the dashboard at <http://localhost:8080>, API documentation at
<http://localhost:8000/docs>, Grafana at <http://localhost:3000> (`admin` / `dataforge`), or
Prometheus at <http://localhost:9090>. You can also check:

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
  -H "Idempotency-Key: monthly-export-2026-08" \
  -F "file=@sample.csv;type=text/csv"
```

The upload returns HTTP 202 with a version and job. Poll
`GET /api/v1/jobs/JOB_ID`, then retrieve
`GET /api/v1/datasets/DATASET_ID/versions/VERSION_ID/report` after the job succeeds.
Identical requests with the same idempotency key return the original version and job. Reusing a
key with different input returns HTTP 409. Attempt history is available at
`GET /api/v1/jobs/JOB_ID/attempts`; failed and dead-lettered jobs can be resubmitted through
`POST /api/v1/jobs/JOB_ID/retry`.

Create dataset-level validation rules before uploading a version at
`POST /api/v1/datasets/DATASET_ID/rules`. Supported checks include nullability, uniqueness,
numeric bounds and ranges, allowed values, regular expressions, expected types, parseable dates,
minimum row counts, and maximum missing or duplicate percentages. Retrieve the readable HTML
report by adding `?format=html` to the report URL.

Uploads accept optional `scheduled_at` (timezone-aware ISO timestamp) and `priority` form fields.
Poll a job to read its progress fields or retrieve the durable timeline at
`GET /api/v1/jobs/JOB_ID/events`. Cancel and retry controls are available through the API and UI.

Compare two versions, optionally using identifier columns and normalized text for overlap:

```bash
curl -X POST http://localhost:8000/api/v1/comparisons \
  -H "Content-Type: application/json" \
  -d '{"left_version_id":"LEFT_VERSION_ID","right_version_id":"RIGHT_VERSION_ID","selected_key_columns":["id"],"normalize_text":true}'
```

The response includes a comparison ID. Download its JSON report from
`GET /api/v1/comparisons/COMPARISON_ID/report`.

Stop the stack with `docker compose down`. Add `--volumes` only when you intentionally want to
delete local PostgreSQL, Redis, and MinIO data.

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
stored under deterministic MinIO keys; pandas analysis runs only in the Celery worker. Workers
use an atomic conditional update to claim jobs, so duplicate Celery delivery cannot start two
attempts. Delivery is at least once, not exactly once.

Analysis includes numeric and categorical summaries, mixed-type detection, exact duplicates,
IQR outlier observations, custom validation rules, and an explainable weighted quality score.
Reports are stored as JSON and escaped standalone HTML. Transient failures use exponential
backoff with jitter and eventually dead-letter while preserving attempt history; malformed CSVs
fail immediately. Scheduled work is claimed durably by Celery Beat. Workers renew leases at safe
checkpoints; expired leases are recovered into a new attempt. Authentication and arbitrary user
code execution remain explicit non-goals.

## Evidence and demonstration

- [Architecture](docs/architecture.md)
- [Job state machine](docs/state-machine.md)
- [Failure model](docs/failure-model.md)
- [Scoring methodology](docs/scoring-methodology.md)
- [Benchmark procedure and recorded results](docs/benchmarks.md)
- [Three-minute demo](docs/demo.md)

The k6 scenario in `load-tests/k6.js` exercises 50-job runs and duplicate submissions. Benchmark
documentation distinguishes recorded measurements from pending runs; no numbers are estimated or
fabricated.
