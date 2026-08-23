from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Dataset, DatasetVersion, Job, JobAttempt, JobStatus
from app.services.jobs import claim_job, retry_failed_job


def test_two_workers_cannot_claim_the_same_job(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'claims.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        dataset = Dataset(name="claims")
        version = DatasetVersion(
            dataset=dataset,
            version_number=1,
            original_filename="data.csv",
            content_type="text/csv",
            file_size_bytes=5,
            file_sha256="a" * 64,
            input_object_key="input.csv",
        )
        job = Job(dataset_version=version)
        session.add(job)
        session.commit()
        job_id = job.id

    def claim() -> bool:
        with sessions() as session:
            return claim_job(session, job_id) is not None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))

    assert sorted(results) == [False, True]
    with Session(engine) as session:
        stored_job = session.get(Job, job_id)
        assert stored_job is not None and stored_job.status == JobStatus.RUNNING
        assert len(list(session.scalars(select(JobAttempt)))) == 1
    engine.dispose()


def test_concurrent_manual_retry_launches_once(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'retries.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        dataset = Dataset(name="retry")
        version = DatasetVersion(
            dataset=dataset,
            version_number=1,
            original_filename="data.csv",
            content_type="text/csv",
            file_size_bytes=5,
            file_sha256="d" * 64,
            input_object_key="retry-input.csv",
        )
        retryable_job = Job(dataset_version=version, status=JobStatus.DEAD_LETTERED)
        session.add(retryable_job)
        session.commit()
        job_id = retryable_job.id

    def retry() -> bool:
        with sessions() as session:
            return retry_failed_job(session, job_id) is not None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: retry(), range(2)))

    assert sorted(results) == [False, True]
    engine.dispose()
