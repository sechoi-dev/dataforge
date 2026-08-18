# DataForge

DataForge is a distributed data-quality and dataset-validation platform. The repository is
currently at **Phase 1: Foundation**: it provides the service skeleton and development
infrastructure, but intentionally does not yet accept or analyze datasets.

## Phase 1 services

- FastAPI API with liveness (`/health`) and dependency readiness (`/ready`) endpoints
- PostgreSQL 16 as the future durable source of truth
- Redis 7 for Celery transport and results
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

`/health` reports only API process liveness. `/ready` checks PostgreSQL and Redis and returns
HTTP 503 if either required dependency is unavailable.

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

The API, worker, and scheduler share one backend image and application package. PostgreSQL and
Redis use persistent named volumes. Compose waits for dependency health and for the one-shot
migration service before starting application processes. Celery beat is present as the Phase 1
scheduler process; durable database-backed scheduling belongs to Phase 7.

There are deliberately no dataset models, upload routes, object storage, validation logic,
reports, frontend, or observability stack yet. Those belong to later phases in
`docs/master-spec.md`.
