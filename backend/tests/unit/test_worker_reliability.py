import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    Dataset,
    DatasetVersion,
    Job,
    JobAttempt,
    JobEvent,
    JobStatus,
    RuleType,
    Severity,
    ValidationResult,
    ValidationRule,
)
from app.services.jobs import claim_job
from app.services.storage import StorageService
from app.workers import tasks


class FailingStorage(StorageService):
    def __init__(self, error: Exception) -> None:
        self.error = error

    def download_file(self, object_key: str, path: Path) -> None:
        del object_key, path
        raise self.error


class ContentStorage(StorageService):
    def __init__(self, content: bytes) -> None:
        self.content = content

    def download_file(self, object_key: str, path: Path) -> None:
        del object_key
        path.write_bytes(self.content)

    def put_bytes(self, object_key: str, content: bytes, content_type: str) -> None:
        del object_key, content, content_type


class RecordingStorage(ContentStorage):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.reports: dict[str, tuple[bytes, str]] = {}

    def put_bytes(self, object_key: str, content: bytes, content_type: str) -> None:
        self.reports[object_key] = (content, content_type)

    def remove_object(self, object_key: str) -> None:
        self.reports.pop(object_key, None)


class CancellingStorage(RecordingStorage):
    def __init__(
        self,
        content: bytes,
        sessions: sessionmaker[Session],
        job_id: uuid.UUID,
    ) -> None:
        super().__init__(content)
        self.sessions = sessions
        self.job_id = job_id
        self.removed: list[str] = []

    def put_bytes(self, object_key: str, content: bytes, content_type: str) -> None:
        super().put_bytes(object_key, content, content_type)
        with self.sessions() as session:
            session.execute(
                update(Job)
                .where(Job.id == self.job_id)
                .values(cancel_requested_at=datetime.now(UTC))
            )
            session.commit()

    def remove_object(self, object_key: str) -> None:
        self.removed.append(object_key)
        super().remove_object(object_key)


@pytest.fixture
def reliability_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[sessionmaker[Session], uuid.UUID]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'reliability.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(tasks, "SessionLocal", sessions)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(retry_base_seconds=0.01, retry_maximum_seconds=0.01),
    )
    with sessions() as session:
        dataset = Dataset(name="reliability")
        version = DatasetVersion(
            dataset=dataset,
            version_number=1,
            original_filename="data.csv",
            content_type="text/csv",
            file_size_bytes=5,
            file_sha256="c" * 64,
            input_object_key="input.csv",
        )
        job = Job(dataset_version=version, max_retries=3)
        session.add(job)
        session.commit()
        return sessions, job.id


def test_retryable_failure_moves_job_to_retrying(
    reliability_db: tuple[sessionmaker[Session], uuid.UUID],
) -> None:
    sessions, job_id = reliability_db
    result = tasks.run_analysis_job(job_id, FailingStorage(ConnectionError("temporary")))
    assert result is not None and result[0] == JobStatus.RETRYING
    with sessions() as session:
        job = session.get(Job, job_id)
        attempt = session.scalar(select(JobAttempt))
        assert job is not None and job.retry_count == 1
        assert attempt is not None and attempt.status == "FAILED"


def test_non_retryable_csv_failure_fails_immediately(
    reliability_db: tuple[sessionmaker[Session], uuid.UUID],
) -> None:
    sessions, job_id = reliability_db
    result = tasks.run_analysis_job(job_id, ContentStorage(b"\xff"))
    assert result == (JobStatus.FAILED, None)
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.retry_count == 0
        assert job.error_code == "INVALID_CSV"


def test_exhausted_retryable_failure_dead_letters(
    reliability_db: tuple[sessionmaker[Session], uuid.UUID],
) -> None:
    sessions, job_id = reliability_db
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.max_retries = 0
        session.commit()

    result = tasks.run_analysis_job(job_id, FailingStorage(TimeoutError("still unavailable")))
    assert result == (JobStatus.DEAD_LETTERED, None)
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.status == JobStatus.DEAD_LETTERED
        assert len(list(session.scalars(select(JobAttempt)))) == 1


def test_success_persists_score_results_and_both_reports(
    reliability_db: tuple[sessionmaker[Session], uuid.UUID],
) -> None:
    sessions, job_id = reliability_db
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job is not None
        version = session.get(DatasetVersion, job.dataset_version_id)
        assert version is not None
        session.add(
            ValidationRule(
                dataset_id=version.dataset_id,
                column_name="age",
                rule_type=RuleType.MAX_VALUE,
                parameters_json={"value": 120},
                severity=Severity.CRITICAL,
            )
        )
        session.commit()

    storage = RecordingStorage(b"name,age\nAda,30\n,150\n")
    result = tasks.run_analysis_job(job_id, storage)

    assert result == (JobStatus.SUCCEEDED, None)
    assert sorted(content_type for _, content_type in storage.reports.values()) == [
        "application/json",
        "text/html; charset=utf-8",
    ]
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job is not None
        version = session.get(DatasetVersion, job.dataset_version_id)
        assert version is not None and version.quality_score is not None
        assert version.quality_score < 100
        assert version.report_object_key is not None
        assert version.html_report_object_key is not None
        results = list(session.scalars(select(ValidationResult)))
        assert any(item.check_name == "max_value" and item.status == "failed" for item in results)
        assert any(item.check_name == "missing_values" for item in results)
        events = list(session.scalars(select(JobEvent).order_by(JobEvent.created_at)))
        assert events[-1].event_type == "job_succeeded"
        assert job.progress_percent == 100


def test_running_job_cancels_at_checkpoint_and_removes_partial_report(
    reliability_db: tuple[sessionmaker[Session], uuid.UUID],
) -> None:
    sessions, job_id = reliability_db
    storage = CancellingStorage(b"name,age\nAda,30\n", sessions, job_id)

    result = tasks.run_analysis_job(job_id, storage)

    assert result == (JobStatus.CANCELLED, None)
    assert len(storage.removed) == 1
    assert storage.reports == {}
    with sessions() as session:
        job = session.get(Job, job_id)
        attempt = session.scalar(select(JobAttempt))
        events = list(session.scalars(select(JobEvent).order_by(JobEvent.created_at)))
        assert job is not None and job.status == JobStatus.CANCELLED
        assert job.current_stage == "cancelled"
        assert attempt is not None and attempt.status == "CANCELLED"
        assert events[-1].event_type == "job_cancelled"


def test_scheduler_dispatches_due_job_once(
    reliability_db: tuple[sessionmaker[Session], uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions, job_id = reliability_db
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = JobStatus.SCHEDULED
        job.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    enqueued: list[str] = []
    monkeypatch.setattr(tasks.analyze_dataset_version, "delay", enqueued.append)

    assert tasks.dispatch_scheduled_jobs() == 1
    assert tasks.dispatch_scheduled_jobs() == 0
    assert enqueued == [str(job_id)]


def test_expired_worker_lease_is_recovered(
    reliability_db: tuple[sessionmaker[Session], uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions, job_id = reliability_db
    with sessions() as session:
        claimed = claim_job(session, job_id, worker_id="dead-worker", lease_seconds=60)
        assert claimed is not None
        job, _ = claimed
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    enqueued: list[str] = []
    monkeypatch.setattr(tasks.analyze_dataset_version, "delay", enqueued.append)

    assert tasks.recover_expired_leases() == 1

    with sessions() as session:
        recovered_job = session.get(Job, job_id)
        attempt = session.scalar(select(JobAttempt))
        assert recovered_job is not None and recovered_job.status == JobStatus.QUEUED
        assert recovered_job.worker_id is None and recovered_job.retry_count == 1
        assert attempt is not None and attempt.status == "ABANDONED"
    assert enqueued == [str(job_id)]
