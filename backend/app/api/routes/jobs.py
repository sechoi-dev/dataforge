import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job, JobAttempt, JobStatus
from app.db.session import get_db
from app.schemas.datasets import JobAttemptRead, JobRead
from app.services.jobs import retry_failed_job
from app.workers.tasks import analyze_dataset_version

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRead])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Job]:
    statement = select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)
    if job_status is not None:
        statement = statement.where(Job.status == job_status)
    return list(db.scalars(statement))


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@router.get("/{job_id}/attempts", response_model=list[JobAttemptRead])
def list_job_attempts(
    job_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]
) -> list[JobAttempt]:
    if db.get(Job, job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return list(
        db.scalars(
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number)
        )
    )


@router.post("/{job_id}/retry", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def retry_job(job_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Job:
    retried_id = retry_failed_job(db, job_id)
    if retried_id is None:
        if db.get(Job, job_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed or dead-lettered jobs can be retried.",
        )
    db.commit()
    job = db.get(Job, retried_id)
    if job is None:
        raise RuntimeError("Retried job disappeared.")
    analyze_dataset_version.delay(str(job.id))
    return job
