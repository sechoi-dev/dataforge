# Job state machine

```text
SCHEDULED -> QUEUED -> RUNNING -> SUCCEEDED
    |          |          |----> CANCELLED
    |          |          |----> FAILED
    |          |          |----> RETRYING -> QUEUED
    +----------+                         |-> DEAD_LETTERED
```

- Scheduled and queued jobs cancel immediately.
- Running jobs set `cancel_requested_at`; workers stop at the next safe checkpoint.
- Terminal jobs cannot be cancelled.
- A lease-expired running job is atomically returned to `QUEUED`; its abandoned attempt remains
  in history and only one scheduler instance wins the recovery update.
- Manual retry is limited to failed and dead-lettered jobs.

Progress and transition events are durable in `job_events`, so polling clients can reconstruct a
job timeline without relying on worker logs.
