import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Job, JobAttempt, JobStatus

VALID_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING}),
    JobStatus.RUNNING: frozenset(
        {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.RETRYING, JobStatus.DEAD_LETTERED}
    ),
    JobStatus.RETRYING: frozenset({JobStatus.QUEUED, JobStatus.DEAD_LETTERED}),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    JobStatus.DEAD_LETTERED: frozenset({JobStatus.QUEUED}),
    JobStatus.SUCCEEDED: frozenset(),
}


def retry_delay_seconds(
    retry_number: int,
    *,
    base_seconds: float = 2.0,
    maximum_seconds: float = 300.0,
    jitter_ratio: float = 0.25,
    random_value: float | None = None,
) -> float:
    if retry_number < 1:
        raise ValueError("retry_number must be at least 1")
    value = random.random() if random_value is None else random_value
    exponential = min(maximum_seconds, base_seconds * (2 ** (retry_number - 1)))
    return float(round(exponential * (1 + jitter_ratio * value), 3))


def claim_job(session: Session, job_id: uuid.UUID) -> tuple[Job, JobAttempt] | None:
    started_at = datetime.now(UTC)
    claimed_id = session.scalar(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
        .values(status=JobStatus.RUNNING, started_at=started_at, completed_at=None)
        .returning(Job.id)
    )
    if claimed_id is None:
        session.rollback()
        return None
    attempt_number = (
        int(
            session.scalar(
                select(func.coalesce(func.max(JobAttempt.attempt_number), 0)).where(
                    JobAttempt.job_id == job_id
                )
            )
            or 0
        )
        + 1
    )
    attempt = JobAttempt(
        job_id=job_id,
        attempt_number=attempt_number,
        status="RUNNING",
        started_at=started_at,
    )
    session.add(attempt)
    session.commit()
    job = session.get(Job, job_id)
    if job is None:
        raise RuntimeError("Claimed job disappeared.")
    return job, attempt


def transition_job(job: Job, target: JobStatus) -> None:
    if target not in VALID_TRANSITIONS[job.status]:
        raise ValueError(f"Invalid job transition: {job.status} -> {target}")
    job.status = target


def retry_failed_job(session: Session, job_id: uuid.UUID) -> uuid.UUID | None:
    retried_id = session.scalar(
        update(Job)
        .where(Job.id == job_id, Job.status.in_([JobStatus.FAILED, JobStatus.DEAD_LETTERED]))
        .values(
            status=JobStatus.QUEUED,
            retry_count=0,
            next_retry_at=None,
            started_at=None,
            completed_at=None,
            error_code=None,
            error_message=None,
        )
        .returning(Job.id)
    )
    if retried_id is None:
        session.rollback()
        return None
    session.commit()
    return retried_id
