import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    Dataset,
    DatasetVersion,
    Job,
    JobAttempt,
    JobStatus,
    RuleType,
    Severity,
    ValidationResult,
    ValidationRule,
)
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
