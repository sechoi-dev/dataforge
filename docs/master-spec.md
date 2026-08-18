You are helping me build a portfolio-quality software engineering project called DataForge.

# 1. Product overview

DataForge is a distributed data-quality and dataset-validation platform.

Users upload CSV datasets, and DataForge analyzes them in the background to detect problems before the data is used for research, reporting, analytics, or machine learning.

The platform should help users answer questions such as:

- Are important values missing?
- Are there duplicate records?
- Did the dataset schema unexpectedly change?
- Are columns using inconsistent data types?
- Are numeric values outside expected ranges?
- Are categorical columns using unexpected values?
- Does a new dataset differ significantly from an older version?
- Is there accidental overlap between two datasets?
- Did overall data quality improve or decline?

DataForge should generate a clear, downloadable data-quality report while demonstrating serious backend engineering:

- asynchronous job processing;
- durable job state;
- multiple worker processes;
- retries and failure recovery;
- idempotent submissions;
- cancellation;
- scheduled validation;
- schema-drift detection;
- observability;
- performance measurement;
- Dockerized deployment;
- automated testing.

The project must be a real product with a clear user workflow, not an abstract queue demonstration or a simple CSV notebook.

# 2. Target users

Initial target users include:

- university researchers;
- machine-learning students;
- nonprofit organizations;
- student organizations;
- instructors;
- small analytics teams;
- developers receiving recurring CSV exports.

The initial release should focus on individual users. Team workspaces can be added later.

# 3. Primary user story

A user uploads a CSV file.

DataForge immediately creates a validation job and returns a job ID.

A background worker analyzes the file while the API remains responsive.

The user can view:

- whether the job is queued, running, completed, failed, or cancelled;
- current processing progress;
- detected data-quality problems;
- an overall quality score;
- a downloadable report;
- warnings and recommendations;
- prior versions of the same dataset;
- changes between versions.

# 4. Initial product scope

The first complete release must support:

1. CSV upload
2. Asynchronous dataset analysis
3. Job status tracking
4. Dataset profile generation
5. Missing-value analysis
6. Duplicate-row detection
7. Data-type consistency checks
8. Numeric outlier detection
9. Categorical-value analysis
10. Downloadable JSON and HTML reports
11. Dataset version comparison
12. Schema-drift detection
13. User-defined validation rules
14. Progress updates
15. Job cancellation
16. Retry and dead-letter handling
17. Idempotent job submissions
18. Worker crash recovery
19. Metrics and structured logs
20. A small web dashboard
21. Dockerized local setup
22. Automated tests
23. Reproducible load tests
24. Clear architecture and benchmark documentation

Do not implement every feature at once. Follow the phased implementation plan later in this specification.

# 5. Required technology stack

Use the following stack unless there is a strong and documented reason to change it.

## Backend

- Python 3.12
- FastAPI
- Pydantic v2
- pydantic-settings
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- psycopg

## Background processing

- Redis
- Celery
- Celery Beat or a durable database-backed scheduler

## Data processing

- pandas
- NumPy where useful
- Python standard library
- memory-conscious chunked CSV processing where practical

## Object storage

- MinIO for local development
- S3-compatible storage abstraction

## Frontend

- Next.js
- TypeScript
- React
- a simple component library if helpful
- no unnecessary visual complexity

## Observability

- structured JSON logging
- Prometheus
- Grafana

## Testing and quality

- pytest
- pytest-asyncio where needed
- HTTPX
- Ruff
- mypy
- pre-commit
- Locust or k6
- GitHub Actions

## Infrastructure

- Docker
- Docker Compose

Do not introduce Kubernetes, Kafka, or microservices in the initial version.

# 6. High-level architecture

The intended architecture is:

Client / Next.js Dashboard
        |
        v
FastAPI API
        |
        +---- PostgreSQL
        |
        +---- MinIO / S3-compatible storage
        |
        +---- Redis / Celery queues
                    |
                    +---- Worker 1
                    +---- Worker 2
                    +---- Worker N
                    |
                    +---- Scheduler

Prometheus collects metrics from the API and workers.

Grafana displays operational dashboards.

PostgreSQL is the durable source of truth for job and dataset state.

Redis is not the authoritative database.

# 7. Core domain concepts

## User

Owns datasets, validation rules, and jobs.

Authentication may be deferred until the core processing pipeline works, but all domain models should be structured so ownership can be added cleanly.

## Dataset

Represents a logical dataset, such as:

- Monthly Volunteer Records
- Survey Responses
- Training Dataset
- Donor Export

A dataset may have many uploaded versions.

## Dataset version

Represents one uploaded CSV file for a dataset.

Each version stores:

- upload metadata;
- file hash;
- object-storage key;
- schema;
- row and column counts;
- timestamps;
- validation result;
- quality score.

## Validation job

Represents asynchronous work performed on a dataset version.

## Validation rule

Represents a user-configured expectation.

Examples:

- `age` must be between 0 and 120;
- `email` must not be null;
- `status` must be one of `active`, `inactive`, or `pending`;
- `student_id` must be unique;
- `created_at` must be parseable as a date;
- row count must not decrease by more than 20% from the previous version.

## Validation result

Represents one detected issue or successful rule evaluation.

## Report

Contains the complete analysis of a dataset version.

# 8. Dataset-analysis features

## 8.1 Basic profile

Generate:

- row count;
- column count;
- column names;
- inferred data types;
- memory estimate;
- file size;
- duplicate-row count;
- fully empty row count;
- processing duration.

## 8.2 Missing-value analysis

For every column, calculate:

- missing count;
- missing percentage;
- whether missingness exceeds a configured threshold;
- change in missingness compared with the previous version.

Flag severe missingness clearly.

## 8.3 Unique-value analysis

For each column, calculate:

- unique-value count;
- uniqueness ratio;
- likely identifier-column warning;
- constant-column warning;
- near-constant-column warning.

## 8.4 Numeric analysis

For numeric columns, calculate:

- minimum;
- maximum;
- mean;
- median;
- standard deviation;
- selected percentiles;
- zero count;
- negative count;
- outlier count.

Use a clearly documented outlier method such as IQR.

Do not claim outliers are necessarily invalid. Report them as observations.

## 8.5 Categorical analysis

For categorical columns, calculate:

- most common values;
- value frequencies;
- rare-category count;
- unexpected categories when rules exist;
- category changes compared with the previous version.

## 8.6 Data-type consistency

Detect:

- columns containing mixed apparent types;
- numeric columns containing nonnumeric strings;
- date columns with unparsable values;
- boolean columns using inconsistent encodings;
- unexpected type changes between versions.

## 8.7 Duplicate analysis

Support:

- exact duplicate rows;
- duplicate values in columns expected to be unique;
- duplicate counts by selected key columns.

Near-duplicate detection may be a later enhancement.

## 8.8 Schema drift

When a dataset has prior versions, detect:

- added columns;
- removed columns;
- renamed-looking columns where reasonably inferred;
- changed data types;
- changed nullability;
- changed category sets;
- major row-count changes;
- changed uniqueness behavior.

Do not automatically treat every schema change as an error.

Classify changes as informational, warning, or critical.

## 8.9 Dataset overlap

Allow users to compare two dataset versions and detect overlap using:

- exact row hashes;
- selected identifier columns;
- normalized text values where configured.

This is particularly useful for detecting accidental overlap between machine-learning train, validation, and test datasets.

## 8.10 Correlation analysis

Optionally calculate correlations for numeric columns.

Limit or sample this operation for very wide datasets.

Do not allow correlation calculation to consume unbounded resources.

# 9. Quality score

Generate an overall quality score from 0 to 100.

The score must be explainable.

It should be based on weighted categories such as:

- completeness;
- uniqueness;
- validity;
- consistency;
- schema stability.

Do not present the score as objective truth.

The report must show:

- category scores;
- deductions;
- reasons for each deduction;
- severity of detected issues.

Allow scoring weights to be configured later.

# 10. Validation-rule system

Support rules such as:

- `not_null`
- `unique`
- `min_value`
- `max_value`
- `allowed_values`
- `regex`
- `expected_type`
- `date_parseable`
- `minimum_row_count`
- `maximum_missing_percentage`
- `maximum_duplicate_percentage`

Example rule:

{
  "column": "email",
  "rule_type": "not_null",
  "severity": "critical"
}

Example:

{
  "column": "age",
  "rule_type": "range",
  "parameters": {
    "minimum": 0,
    "maximum": 120
  },
  "severity": "warning"
}

Rules must be validated before storage.

Rule evaluation results must include:

- passed or failed;
- affected-row count;
- affected percentage;
- sample offending values where safe;
- severity;
- explanation.

Do not store or expose excessive sensitive row data.

# 11. Job lifecycle

Use statuses similar to:

- PENDING
- SCHEDULED
- QUEUED
- RUNNING
- RETRYING
- SUCCEEDED
- FAILED
- CANCEL_REQUESTED
- CANCELLED
- DEAD_LETTERED

Centralize valid state transitions.

Do not allow arbitrary direct status changes.

Example transitions:

PENDING -> QUEUED
PENDING -> SCHEDULED
SCHEDULED -> QUEUED
QUEUED -> RUNNING
RUNNING -> SUCCEEDED
RUNNING -> RETRYING
RETRYING -> QUEUED
RUNNING -> CANCEL_REQUESTED
CANCEL_REQUESTED -> CANCELLED
QUEUED -> CANCELLED
RETRYING -> DEAD_LETTERED

# 12. API requirements

Use `/api/v1`.

## Health endpoints

GET `/health`

Returns process liveness.

GET `/ready`

Checks:

- PostgreSQL;
- Redis;
- object storage.

Return HTTP 503 when required dependencies are unavailable.

## Dataset endpoints

POST `/api/v1/datasets`

Create a logical dataset.

GET `/api/v1/datasets`

List datasets with pagination.

GET `/api/v1/datasets/{dataset_id}`

Return dataset metadata and recent versions.

PATCH `/api/v1/datasets/{dataset_id}`

Update user-editable metadata.

DELETE `/api/v1/datasets/{dataset_id}`

Use safe deletion behavior. Do not accidentally orphan files or active jobs.

## Dataset-version upload

POST `/api/v1/datasets/{dataset_id}/versions`

Use multipart form data.

Fields:

- file;
- optional description;
- optional validation-rule set;
- optional scheduled time.

Header:

- `Idempotency-Key`

Behavior:

1. Validate upload size and file type.
2. Calculate SHA-256.
3. Store the file in object storage.
4. Create the dataset-version record.
5. Create the validation job.
6. Enqueue immediately or schedule durably.
7. Return HTTP 202.

Repeated identical requests using the same idempotency key must return the existing resource.

Reusing a key with different input must return a conflict.

## Dataset versions

GET `/api/v1/datasets/{dataset_id}/versions`

GET `/api/v1/datasets/{dataset_id}/versions/{version_id}`

GET `/api/v1/datasets/{dataset_id}/versions/{version_id}/report`

GET `/api/v1/datasets/{dataset_id}/versions/{version_id}/download`

## Comparison

POST `/api/v1/comparisons`

Compare two dataset versions.

Support:

- schema comparison;
- profile comparison;
- missingness changes;
- category changes;
- exact row overlap;
- selected-key overlap.

Comparison should run asynchronously for sufficiently large datasets.

## Job endpoints

GET `/api/v1/jobs`

Support pagination and filtering.

GET `/api/v1/jobs/{job_id}`

POST `/api/v1/jobs/{job_id}/cancel`

POST `/api/v1/jobs/{job_id}/retry`

GET `/api/v1/jobs/{job_id}/attempts`

GET `/api/v1/jobs/{job_id}/events`

## Validation rules

POST `/api/v1/datasets/{dataset_id}/rules`

GET `/api/v1/datasets/{dataset_id}/rules`

PATCH `/api/v1/datasets/{dataset_id}/rules/{rule_id}`

DELETE `/api/v1/datasets/{dataset_id}/rules/{rule_id}`

# 13. Suggested database models

## datasets

- id
- user_id nullable initially
- name
- description
- created_at
- updated_at

## dataset_versions

- id
- dataset_id
- version_number
- original_filename
- content_type
- file_size_bytes
- file_sha256
- input_object_key
- report_object_key
- row_count
- column_count
- quality_score
- schema_json
- profile_summary_json
- created_at
- analysis_completed_at

## jobs

- id
- dataset_version_id nullable for non-version jobs
- job_type
- status
- priority
- progress_percent
- progress_message
- idempotency_key
- request_fingerprint
- scheduled_at
- queued_at
- started_at
- completed_at
- retry_count
- max_retries
- next_retry_at
- worker_id
- lease_expires_at
- cancel_requested_at
- cancelled_at
- error_code
- error_message
- created_at
- updated_at
- version

## job_attempts

- id
- job_id
- attempt_number
- worker_id
- status
- started_at
- finished_at
- duration_ms
- error_code
- error_message
- created_at

## job_events

- id
- job_id
- event_type
- payload_json
- created_at

## validation_rules

- id
- dataset_id
- column_name nullable for dataset-level rules
- rule_type
- parameters_json
- severity
- is_enabled
- created_at
- updated_at

## validation_results

- id
- dataset_version_id
- validation_rule_id nullable for automatic checks
- category
- check_name
- status
- severity
- affected_count
- affected_percentage
- message
- details_json
- created_at

## comparisons

- id
- left_version_id
- right_version_id
- status
- result_object_key
- created_at
- completed_at

Use UUIDs unless another identifier is clearly more appropriate.

Add appropriate foreign keys, indexes, uniqueness constraints, and check constraints.

# 14. File and memory safety

Support configuration for:

- maximum upload size;
- maximum rows;
- maximum columns;
- CSV chunk size;
- job timeout;
- maximum report size.

Data processing must be memory-conscious.

Avoid:

- unnecessary full DataFrame copies;
- repeatedly loading the same CSV;
- retaining large intermediate structures;
- unbounded unique-value collections;
- unbounded correlation matrices.

Use chunked reading where practical.

For operations that require the entire dataset, document the limitation and enforce configured size limits.

Reject clearly unsupported inputs with useful errors.

# 15. Idempotency

Idempotency is mandatory.

Each upload accepts an `Idempotency-Key`.

The system must:

- store the key;
- calculate a request fingerprint;
- use a database uniqueness constraint;
- safely handle concurrent duplicate requests;
- return the existing job for identical retries;
- reject key reuse with different files or parameters.

Do not rely solely on an application-level existence check.

# 16. Job claiming and execution guarantees

Workers must atomically claim eligible jobs.

Two workers must not successfully claim the same database job at the same time.

Use:

- atomic conditional updates;
- row-level locking; or
- optimistic concurrency.

Document the system as providing at-least-once delivery.

Do not claim exactly-once execution.

Make processing idempotent through:

- deterministic object keys;
- atomic state transitions;
- safe report replacement;
- database constraints;
- repeatable analysis behavior.

# 17. Retries and dead-letter handling

Classify errors as retryable or non-retryable.

Retryable examples:

- object-storage timeout;
- Redis interruption;
- temporary database failure;
- transient networking failure.

Non-retryable examples:

- malformed CSV;
- unsupported encoding;
- empty file;
- invalid parameters;
- configured limits exceeded.

Use exponential backoff with jitter.

After maximum retry attempts, mark the job as `DEAD_LETTERED`.

Dead-lettered jobs must:

- retain attempt history;
- retain the final error;
- remain visible;
- support a controlled manual retry.

# 18. Worker leases and crash recovery

Workers may crash after claiming work.

Implement:

- worker IDs;
- lease expiration;
- periodic lease renewal;
- detection of expired running jobs;
- safe recovery or retry;
- attempt-history recording.

Provide a demonstration in which a worker is killed during processing and another worker eventually completes or safely retries the job.

# 19. Cancellation

Use cooperative cancellation.

Queued and scheduled jobs can cancel immediately.

Running workers must check cancellation state at safe processing checkpoints.

On cancellation:

- stop processing;
- clean up partial outputs;
- preserve job history;
- mark the job `CANCELLED`.

Do not use forceful process termination as the main cancellation design.

# 20. Progress reporting

Persist:

- progress percentage;
- progress message;
- current stage.

Suggested stages:

5% Validating upload
15% Reading file metadata
25% Loading dataset
40% Profiling columns
55% Evaluating missing values and duplicates
70% Running validation rules
82% Comparing with prior version
90% Generating report
97% Uploading report
100% Complete

Do not write progress updates so frequently that PostgreSQL becomes overloaded.

Start with REST polling.

Add Server-Sent Events or WebSockets later.

# 21. Report format

Generate a structured JSON report and an easy-to-read HTML report.

Report sections:

1. Executive summary
2. Quality score
3. Dataset overview
4. Critical issues
5. Warnings
6. Missing-data profile
7. Duplicate analysis
8. Column-by-column profile
9. Validation-rule results
10. Schema changes from prior version
11. Distribution changes
12. Dataset-overlap results where requested
13. Recommendations
14. Processing metadata and limitations

Recommendations should be deterministic and grounded in detected checks.

# 22. Frontend requirements

After the backend is reliable, build a focused dashboard.

Pages:

## Dashboard

Show:

- recent datasets;
- recent jobs;
- failed jobs;
- average quality score;
- recent schema changes.

## Dataset list

Show datasets with:

- latest version;
- quality score;
- last validation time;
- issue count.

## Dataset details

Show:

- version history;
- quality trend;
- rules;
- recent changes;
- upload button.

## Version report

Show:

- score;
- issues by severity;
- missingness chart;
- duplicate count;
- column summaries;
- schema drift;
- report download.

## Job details

Show:

- status;
- progress;
- attempt history;
- cancellation;
- retry;
- errors.

## Comparison page

Allow users to compare two versions.

The frontend must include usable loading, empty, success, and error states.

The frontend is not the primary engineering focus. Keep it polished but controlled.

# 23. Security requirements

At minimum:

- generate server-controlled object keys;
- sanitize display filenames;
- validate extensions and content types;
- impose upload limits;
- do not trust client file paths;
- do not expose internal stack traces;
- do not log secrets;
- avoid logging raw sensitive dataset values;
- use environment variables for secrets;
- use signed download URLs;
- configure CORS narrowly;
- reject unsupported operations;
- protect against CSV formula injection in generated exports where relevant.

Later, add authentication and authorization.

When authentication is added:

- users may access only their datasets;
- ownership checks must occur server-side;
- object-storage access must not bypass authorization.

# 24. Observability

## Logging

Use structured JSON logs containing:

- timestamp;
- level;
- service;
- request ID;
- job ID;
- dataset ID;
- dataset-version ID;
- worker ID;
- attempt ID;
- event;
- duration;
- error type.

Do not log passwords, storage secrets, full connection strings, or raw user datasets.

## Metrics

Expose Prometheus metrics such as:

- HTTP request count;
- HTTP latency;
- datasets uploaded;
- jobs submitted;
- jobs running;
- jobs completed;
- jobs failed;
- retries;
- dead-lettered jobs;
- cancellations;
- queue wait time;
- processing duration;
- queue depth;
- active workers;
- lease expirations;
- CSV rows processed;
- report generation time.

Avoid high-cardinality labels such as job IDs.

## Grafana

Create dashboards for:

- API health;
- queue depth;
- job throughput;
- success and failure rates;
- retries;
- average queue wait;
- average processing duration;
- active workers;
- dead-letter count.

# 25. Docker Compose

The local stack should eventually contain:

- api
- worker
- scheduler
- postgres
- redis
- minio
- frontend
- prometheus
- grafana

Use one reusable backend image where practical.

Support:

docker compose up --build

Support scaling:

docker compose up --scale worker=4

Use health checks.

Do not rely exclusively on `depends_on` for service readiness.

Use named volumes for persistent services.

Run containers as non-root where practical.

# 26. Testing requirements

## Unit tests

Test:

- validation rules;
- quality-score calculations;
- schema comparison;
- retry-delay calculation;
- valid status transitions;
- request fingerprinting;
- deterministic object keys;
- CSV validation;
- duplicate analysis;
- missingness calculations;
- cancellation checkpoints.

## Integration tests

Test:

- API and PostgreSQL;
- API and Redis;
- MinIO upload and retrieval;
- job creation;
- worker execution;
- report storage;
- retry transitions;
- dead-letter transitions;
- scheduled-job claiming;
- dataset-version comparison.

## Concurrency tests

Verify:

- concurrent requests with one idempotency key create one job;
- two workers cannot claim one job simultaneously;
- scheduled jobs enqueue once;
- manual retries cannot launch twice;
- duplicate dataset version numbers are prevented.

## End-to-end tests

Test:

1. Create a dataset.
2. Upload a CSV.
3. Receive HTTP 202.
4. Worker processes the job.
5. Job reaches `SUCCEEDED`.
6. Report is available.
7. Version appears in dataset history.

Also test:

- malformed CSV;
- empty file;
- oversized file;
- cancellation;
- temporary failure;
- permanent failure;
- worker crash;
- comparison between versions.

# 27. Load testing and evidence

Create reproducible load tests.

Measure:

- API request throughput;
- job queue wait time;
- processing duration;
- total completion time;
- worker utilization;
- failure rate;
- memory usage where practical.

Run scenarios such as:

- 1 worker, 50 jobs;
- 2 workers, 50 jobs;
- 4 workers, 50 jobs.

Also test concurrent duplicate submissions.

Document:

- hardware or environment;
- dataset sizes;
- exact commands;
- real measurements;
- limitations.

Never fabricate benchmark results.

# 28. Portfolio demonstration

The final project should support a two-to-three-minute demo showing:

1. Upload a dataset.
2. Watch it enter the queue.
3. View processing progress.
4. Open the generated quality report.
5. Upload a changed version.
6. Show schema drift and quality changes.
7. Submit many jobs.
8. Scale from one worker to four.
9. Show improved throughput.
10. Kill a worker.
11. Show recovery.
12. Submit duplicate requests.
13. Show one job was created.
14. Trigger retries and dead-letter handling.
15. End on Grafana metrics and passing CI.

# 29. Recommended repository structure

dataforge/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   ├── errors.py
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       ├── datasets.py
│   │   │       ├── versions.py
│   │   │       ├── jobs.py
│   │   │       ├── comparisons.py
│   │   │       └── rules.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── metrics.py
│   │   │   └── celery_app.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── models/
│   │   │   └── repositories/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── dataset_service.py
│   │   │   ├── version_service.py
│   │   │   ├── job_service.py
│   │   │   ├── state_service.py
│   │   │   ├── storage_service.py
│   │   │   ├── idempotency_service.py
│   │   │   ├── comparison_service.py
│   │   │   └── report_service.py
│   │   ├── analysis/
│   │   │   ├── profiler.py
│   │   │   ├── missingness.py
│   │   │   ├── duplicates.py
│   │   │   ├── outliers.py
│   │   │   ├── schema.py
│   │   │   ├── overlap.py
│   │   │   ├── rules.py
│   │   │   └── scoring.py
│   │   ├── workers/
│   │   │   ├── tasks.py
│   │   │   ├── leases.py
│   │   │   ├── recovery.py
│   │   │   └── scheduler.py
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── concurrency/
│   │   └── e2e/
│   ├── pyproject.toml
│   ├── alembic.ini
│   └── Dockerfile
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── package.json
│   └── Dockerfile
├── monitoring/
│   ├── prometheus.yml
│   └── grafana/
├── load-tests/
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── state-machine.md
│   ├── failure-model.md
│   ├── scoring-methodology.md
│   └── benchmarks.md
├── .github/
│   └── workflows/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
└── README.md

Keep the structure proportional to the current implementation phase.

Do not create empty modules for every future feature merely to match this tree.

# 30. Development phases

Implement the project incrementally.

## Phase 1 — Foundation

Build:

- repository structure;
- FastAPI;
- typed settings;
- PostgreSQL;
- Redis;
- Celery worker;
- scheduler process;
- Alembic;
- Docker Compose;
- `/health`;
- `/ready`;
- Ruff;
- mypy;
- pytest;
- GitHub Actions;
- initial README.

Do not implement dataset processing yet.

Acceptance criteria:

- `docker compose up --build` starts the essential backend services;
- API is reachable;
- PostgreSQL and Redis checks pass;
- worker starts;
- scheduler starts;
- migrations run;
- tests, linting, and type checks pass.

## Phase 2 — Dataset creation and basic asynchronous analysis

Build:

- datasets;
- dataset versions;
- MinIO;
- CSV upload;
- job creation;
- asynchronous worker execution;
- basic dataset profile;
- missing-value analysis;
- duplicate analysis;
- JSON report.

Acceptance criteria:

- upload returns HTTP 202;
- API does not process the CSV synchronously;
- worker generates a report;
- job status reaches `SUCCEEDED`;
- report can be retrieved.

## Phase 3 — Reliable job processing

Build:

- atomic job claiming;
- idempotency;
- retries;
- exponential backoff;
- dead-letter handling;
- job attempts;
- deterministic output keys;
- concurrency tests.

Acceptance criteria:

- concurrent duplicate requests create one job;
- two workers do not claim the same job;
- retryable failures retry;
- non-retryable failures fail immediately;
- exhausted jobs dead-letter.

## Phase 4 — Rich validation

Build:

- numeric summaries;
- categorical analysis;
- mixed-type detection;
- outlier detection;
- validation rules;
- quality scoring;
- HTML reports.

Acceptance criteria:

- report explains every detected issue;
- quality score deductions are visible;
- custom rules are evaluated correctly.

## Phase 5 — Version comparison

Build:

- dataset history;
- schema drift;
- profile changes;
- category changes;
- row-count changes;
- exact overlap;
- selected-key overlap.

Acceptance criteria:

- two versions can be compared;
- changes are classified by severity;
- comparison report is downloadable.

## Phase 6 — Progress and cancellation

Build:

- meaningful progress stages;
- job events;
- cancellation endpoint;
- cooperative cancellation;
- cleanup of partial output.

Acceptance criteria:

- queued jobs cancel immediately;
- running jobs stop at safe checkpoints;
- progress is visible;
- completed jobs cannot be cancelled.

## Phase 7 — Scheduling and worker crash recovery

Build:

- durable scheduled jobs;
- scheduler claiming;
- worker leases;
- heartbeat renewal;
- expired-lease recovery;
- failure-injection tools.

Acceptance criteria:

- scheduled jobs survive restarts;
- jobs enqueue once;
- killed-worker jobs recover safely.

## Phase 8 — Observability

Build:

- JSON logs;
- request correlation IDs;
- Prometheus metrics;
- Grafana dashboards.

Acceptance criteria:

- system activity is visible;
- logs correlate request, dataset, version, job, and attempt;
- metrics avoid high-cardinality labels.

## Phase 9 — Frontend

Build:

- dashboard;
- dataset list;
- dataset detail;
- upload workflow;
- version report;
- job progress;
- comparison page;
- cancellation and retry controls.

Acceptance criteria:

- complete product workflow is usable from the browser;
- errors and empty states are handled.

## Phase 10 — Load testing and portfolio polish

Build:

- reproducible load tests;
- benchmarks;
- worker-scaling comparisons;
- failure demonstrations;
- complete documentation;
- demo assets.

Acceptance criteria:

- real results are documented;
- README contains architecture and evidence;
- project can be demonstrated clearly in under three minutes.

# 31. Non-goals

Do not prioritize:

- arbitrary user code execution;
- dozens of file formats;
- Kubernetes;
- Kafka;
- billing;
- multi-region architecture;
- enterprise RBAC;
- complex machine-learning models;
- mobile applications;
- real-time collaborative editing.

CSV is sufficient for the first complete version.

# 32. Engineering principles

1. Build one working vertical slice before adding breadth.
2. Keep PostgreSQL authoritative.
3. Treat queue delivery as at least once.
4. Make processing idempotent.
5. Use atomic state changes.
6. Do not hide errors.
7. Preserve execution history.
8. Measure actual behavior.
9. Do not fabricate tests or benchmarks.
10. Do not claim exactly-once execution.
11. Prefer clear code over unnecessary abstractions.
12. Keep data processing memory-conscious.
13. Add tests with each feature.
14. Preserve working behavior during later phases.
15. Document limitations honestly.
16. Do not let the frontend delay backend correctness.
17. Do not implement future-phase placeholders as fake completed features.

# 33. Immediate instruction

Start with Phase 1 only.

Do not implement CSV uploads, datasets, reports, quality scoring, comparisons, or frontend pages yet.

The immediate goal is a clean and verifiable foundation that future phases can safely extend.
