# Reproducible benchmarks

No throughput numbers are checked into this document until they have been measured on a named
environment. This avoids presenting fabricated portfolio evidence.

## Procedure

Record the date, CPU, memory, Docker version, dataset size, commit, and whether volumes were warm.
For each worker count, reset application data or use a new dataset and run:

```bash
docker compose up -d --build --scale worker=1
docker run --rm --network host -v "$PWD/load-tests:/scripts" grafana/k6 run -e JOBS=50 -e VUS=10 /scripts/k6.js

docker compose up -d --scale worker=2
# repeat k6 command

docker compose up -d --scale worker=4
# repeat k6 command
```

Capture accepted-request throughput, p95 API latency, time until all 50 jobs are terminal, worker
count, failure rate, and peak memory. Then run the `duplicateSubmission` k6 function and the
worker-kill procedure in `failure-model.md`. Paste raw summaries below with the exact commit.

## Recorded results

Recorded on 2026-11-14 (America/Los_Angeles) using Docker Desktop 29.7.2 on a 12-CPU,
16,416,555,008-byte ARM64 Docker VM. The stack used warm persistent volumes and the working tree
based on commit `55cdce2`; the Phase 6-10 changes measured here were not yet committed. Each run
used the checked-in 161-byte, four-row CSV, 10 virtual users, and 50 uploads. All 150 accepted
jobs subsequently reached `SUCCEEDED`.

| Worker replicas | Accepted iterations/s | API latency p95 | HTTP failures | Time until all 50 jobs terminal |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 26.10/s | 440.29 ms | 0/51 | 1.699 s |
| 2 | 32.35/s | 278.50 ms | 0/51 | 1.449 s |
| 4 | 28.04/s | 323.56 ms | 0/51 | 1.711 s |

These are local, small-file measurements rather than production capacity claims. With such short
jobs, API upload/storage work and startup noise dominate; the 4-worker run was not faster than the
2-worker run. Larger files and repeated trials are required before drawing scaling conclusions.
The separate duplicate-submission run completed with 0/3 HTTP failures and confirmed that both
requests returned the same job ID (p95 request latency: 27.68 ms).

Run the idempotency scenario separately with:

```bash
docker run --rm --network host -v "$PWD/load-tests:/scripts" grafana/k6 run \
  -e JOBS=1 -e VUS=1 -e SCENARIO=duplicateSubmission /scripts/k6.js
```
