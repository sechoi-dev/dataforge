# Failure model

| Failure | Classification | Response |
|---|---|---|
| Malformed or oversized CSV | Permanent | Fail immediately with a stable error code |
| MinIO timeout or transient network error | Retryable | Exponential backoff, then dead letter |
| Duplicate Celery delivery | Expected | Atomic claim lets only one delivery run |
| Worker process killed | Recoverable | Expired lease is requeued and prior attempt is abandoned |
| Cancellation during output upload | User requested | Uploaded partial report objects are removed |
| Database failure before final commit | Retryable | No successful state is published |

Failure injection is disabled in production. In development, set
`DATAFORGE_FAILURE_INJECTION_STAGE` to a checkpoint name such as `profiling_columns` or
`uploading_report`. The script at `scripts/failure-demo.ps1` describes a repeatable demonstration.
