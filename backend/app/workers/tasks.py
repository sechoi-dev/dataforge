import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from minio.error import S3Error
from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from urllib3.exceptions import HTTPError

from app.analysis.basic import CsvAnalysisError, analyze_csv
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.db.models import DatasetVersion, Job, JobAttempt, JobStatus
from app.db.session import SessionLocal
from app.services.idempotency import report_object_key
from app.services.jobs import claim_job, retry_delay_seconds, transition_job
from app.services.storage import StorageService

TRANSIENT_S3_CODES = {"InternalError", "RequestTimeout", "ServiceUnavailable", "SlowDown"}


def build_report(version: DatasetVersion, analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_version": "1.0",
        "dataset_id": str(version.dataset_id),
        "dataset_version_id": str(version.id),
        "version_number": version.version_number,
        "source": {
            "filename": version.original_filename,
            "file_size_bytes": version.file_size_bytes,
            "sha256": version.file_sha256,
        },
        **analysis,
    }


def is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (CsvAnalysisError, ValueError)):
        return False
    if isinstance(error, S3Error):
        return error.code in TRANSIENT_S3_CODES
    return isinstance(error, (ConnectionError, TimeoutError, HTTPError, OperationalError))


def error_code(error: Exception) -> str:
    if isinstance(error, CsvAnalysisError):
        return "INVALID_CSV"
    if isinstance(error, S3Error):
        return f"OBJECT_STORAGE_{(error.code or 'UNKNOWN').upper()}"
    return type(error).__name__.upper()


def finish_attempt(attempt: JobAttempt, *, status: str, error: Exception | None = None) -> None:
    finished_at = datetime.now(UTC)
    started_at = attempt.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    attempt.status = status
    attempt.finished_at = finished_at
    attempt.duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1_000))
    if error is not None:
        attempt.error_code = error_code(error)
        attempt.error_message = str(error)[:2_000]


def run_analysis_job(
    job_id: uuid.UUID, storage: StorageService | None = None
) -> tuple[JobStatus, float | None] | None:
    settings = get_settings()
    storage = storage or StorageService(settings)

    with SessionLocal() as session:
        claimed = claim_job(session, job_id)
        if claimed is None:
            return None
        job, attempt = claimed

        try:
            version = session.get(DatasetVersion, job.dataset_version_id)
            if version is None:
                raise ValueError("Dataset version no longer exists.")
            with TemporaryDirectory(prefix="dataforge-") as temporary_directory:
                input_path = Path(temporary_directory) / "input.csv"
                storage.download_file(version.input_object_key, input_path)
                analysis = analyze_csv(
                    input_path,
                    file_size_bytes=version.file_size_bytes,
                    max_rows=settings.maximum_rows,
                    max_columns=settings.maximum_columns,
                )

            report = build_report(version, analysis)
            report_bytes = json.dumps(report, separators=(",", ":"), sort_keys=True).encode()
            if len(report_bytes) > settings.maximum_report_size_bytes:
                raise ValueError("Generated report exceeds the configured size limit.")
            report_key = report_object_key(version.dataset_id, version.id)
            storage.put_bytes(report_key, report_bytes, "application/json")

            profile = analysis["profile"]
            version.report_object_key = report_key
            version.row_count = int(profile["row_count"])
            version.column_count = int(profile["column_count"])
            version.schema_json = dict(profile["inferred_data_types"])
            version.profile_summary_json = profile
            version.analysis_completed_at = datetime.now(UTC)
            transition_job(job, JobStatus.SUCCEEDED)
            job.completed_at = datetime.now(UTC)
            job.next_retry_at = None
            job.error_code = None
            job.error_message = None
            finish_attempt(attempt, status="SUCCEEDED")
            session.commit()
            return JobStatus.SUCCEEDED, None
        except Exception as exc:
            session.rollback()
            failed_job = session.get(Job, job_id)
            failed_attempt = session.get(JobAttempt, attempt.id)
            if failed_job is None or failed_attempt is None:
                raise
            finish_attempt(failed_attempt, status="FAILED", error=exc)
            failed_job.error_code = error_code(exc)
            failed_job.error_message = str(exc)[:2_000]
            failed_job.completed_at = datetime.now(UTC)

            if is_retryable_error(exc) and failed_job.retry_count < failed_job.max_retries:
                failed_job.retry_count += 1
                delay = retry_delay_seconds(
                    failed_job.retry_count,
                    base_seconds=settings.retry_base_seconds,
                    maximum_seconds=settings.retry_maximum_seconds,
                )
                transition_job(failed_job, JobStatus.RETRYING)
                failed_job.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
                failed_job.completed_at = None
                session.commit()
                return JobStatus.RETRYING, delay

            target = JobStatus.DEAD_LETTERED if is_retryable_error(exc) else JobStatus.FAILED
            transition_job(failed_job, target)
            failed_job.next_retry_at = None
            session.commit()
            return target, None


@celery_app.task(name="dataforge.analyze_dataset_version")  # type: ignore[untyped-decorator]
def analyze_dataset_version(job_id: str) -> None:
    result = run_analysis_job(uuid.UUID(job_id))
    if result is not None and result[0] == JobStatus.RETRYING:
        requeue_job.apply_async(args=[job_id], countdown=result[1] or 0)


@celery_app.task(name="dataforge.requeue_job")  # type: ignore[untyped-decorator]
def requeue_job(job_id: str) -> None:
    parsed_job_id = uuid.UUID(job_id)
    with SessionLocal() as session:
        changed_id = session.scalar(
            update(Job)
            .where(Job.id == parsed_job_id, Job.status == JobStatus.RETRYING)
            .values(status=JobStatus.QUEUED, next_retry_at=None)
            .returning(Job.id)
        )
        session.commit()
    if changed_id is not None:
        analyze_dataset_version.delay(job_id)
