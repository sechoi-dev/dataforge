import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Job, JobAttempt, JobEvent, JobStatus


class JobCancelled(Exception):
    """Raised when a worker reaches a checkpoint after cancellation was requested."""


class JobLeaseLost(Exception):
    """Raised when a stale worker no longer owns a running job."""


VALID_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.SCHEDULED: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.RETRYING,
            JobStatus.DEAD_LETTERED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RETRYING: frozenset({JobStatus.QUEUED, JobStatus.DEAD_LETTERED, JobStatus.CANCELLED}),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    JobStatus.DEAD_LETTERED: frozenset({JobStatus.QUEUED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
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


def claim_job(
    session: Session,
    job_id: uuid.UUID,
    *,
    worker_id: str = "unknown-worker",
    lease_seconds: int = 60,
) -> tuple[Job, JobAttempt] | None:
    started_at = datetime.now(UTC)
    claimed_id = session.scalar(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
        .values(
            status=JobStatus.RUNNING,
            started_at=started_at,
            completed_at=None,
            progress_percent=5,
            progress_message="Validating job input",
            current_stage="validating_input",
            worker_id=worker_id,
            lease_expires_at=started_at + timedelta(seconds=lease_seconds),
        )
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
        worker_id=worker_id,
    )
    session.add(attempt)
    add_job_event(
        session,
        job_id,
        "job_started",
        {
            "progress_percent": 5,
            "stage": "validating_input",
            "worker_id": worker_id,
        },
    )
    session.commit()
    job = session.get(Job, job_id)
    if job is None:
        raise RuntimeError("Claimed job disappeared.")
    return job, attempt


def transition_job(job: Job, target: JobStatus) -> None:
    if target not in VALID_TRANSITIONS[job.status]:
        raise ValueError(f"Invalid job transition: {job.status} -> {target}")
    job.status = target


def add_job_event(
    session: Session, job_id: uuid.UUID, event_type: str, payload: dict[str, object]
) -> None:
    session.add(JobEvent(job_id=job_id, event_type=event_type, payload_json=dict(payload)))


def progress_checkpoint(
    session: Session,
    job_id: uuid.UUID,
    *,
    percent: int,
    stage: str,
    message: str,
    lease_seconds: int = 60,
) -> Job:
    session.expire_all()
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError("Job no longer exists.")
    if job.cancel_requested_at is not None:
        raise JobCancelled
    if job.status != JobStatus.RUNNING:
        raise JobLeaseLost
    job.progress_percent = percent
    job.current_stage = stage
    job.progress_message = message
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    add_job_event(
        session,
        job.id,
        "progress_updated",
        {"progress_percent": percent, "stage": stage, "message": message},
    )
    session.commit()
    return job


def request_job_cancellation(session: Session, job_id: uuid.UUID) -> Job | None:
    now = datetime.now(UTC)
    immediate_id = session.scalar(
        update(Job)
        .where(
            Job.id == job_id,
            Job.status.in_([JobStatus.SCHEDULED, JobStatus.QUEUED, JobStatus.RETRYING]),
        )
        .values(
            status=JobStatus.CANCELLED,
            cancel_requested_at=now,
            cancelled_at=now,
            completed_at=now,
            next_retry_at=None,
            lease_expires_at=None,
            worker_id=None,
            progress_message="Cancelled before processing",
            current_stage="cancelled",
        )
        .returning(Job.id)
    )
    if immediate_id is not None:
        add_job_event(session, job_id, "job_cancelled", {"mode": "immediate"})
        session.commit()
        return session.get(Job, job_id)

    requested_id = session.scalar(
        update(Job)
        .where(
            Job.id == job_id,
            Job.status == JobStatus.RUNNING,
            Job.cancel_requested_at.is_(None),
        )
        .values(
            cancel_requested_at=now,
            progress_message="Cancellation requested",
        )
        .returning(Job.id)
    )
    if requested_id is not None:
        add_job_event(session, job_id, "cancellation_requested", {})
        session.commit()
        return session.get(Job, job_id)
    session.rollback()
    return session.get(Job, job_id)


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
            progress_percent=0,
            progress_message="Queued for manual retry",
            current_stage="queued",
            cancel_requested_at=None,
            cancelled_at=None,
            queued_at=datetime.now(UTC),
            worker_id=None,
            lease_expires_at=None,
        )
        .returning(Job.id)
    )
    if retried_id is None:
        session.rollback()
        return None
    add_job_event(session, job_id, "job_retried", {})
    session.commit()
    return retried_id
