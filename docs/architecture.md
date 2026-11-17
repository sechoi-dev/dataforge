# Architecture

DataForge separates request handling from dataset processing. FastAPI validates and persists
uploads, MinIO stores immutable CSV inputs and deterministic reports, PostgreSQL owns workflow
state, Redis transports Celery tasks, and workers perform bounded pandas analysis. Celery Beat
dispatches durable scheduled jobs and recovers expired worker leases.

```text
Browser -> nginx frontend -> FastAPI -> PostgreSQL
                              |  |-> Redis -> Celery workers
                              |  +-> MinIO
                              +-> /metrics -> Prometheus -> Grafana
```

The delivery guarantee is at least once. Atomic database transitions prevent two workers from
owning one job concurrently; deterministic object keys and repeatable analysis make retries safe.
The API never performs CSV analysis in the request path.

## Data flow

1. The API streams and hashes a bounded CSV upload into MinIO.
2. A dataset version and queued or scheduled job are committed together.
3. A worker atomically claims the job, records an attempt, and renews its lease at checkpoints.
4. Analysis evaluates profiles and rules, then writes JSON and HTML reports.
5. A final conditional update succeeds only if the worker still owns an uncancelled job.
6. Prometheus scrapes bounded-label API metrics; structured logs carry request and job context.
