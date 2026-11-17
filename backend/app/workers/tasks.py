import json
import logging
import os
import socket
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from minio.error import S3Error
from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from urllib3.exceptions import HTTPError

from app.analysis.basic import CsvAnalysisError, analyze_csv
from app.analysis.rules import RuleSpec
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.observability import JOB_OUTCOMES
from app.db.models import (
    DatasetVersion,
    Job,
    JobAttempt,
    JobStatus,
    Severity,
    ValidationResult,
    ValidationRule,
)
from app.db.session import SessionLocal
from app.services.idempotency import html_report_object_key, report_object_key
from app.services.jobs import (
    JobCancelled,
    JobLeaseLost,
    add_job_event,
    claim_job,
    progress_checkpoint,
    retry_delay_seconds,
    transition_job,
)
from app.services.reporting import build_html_report
from app.services.storage import StorageService

TRANSIENT_S3_CODES = {"InternalError", "RequestTimeout", "ServiceUnavailable", "SlowDown"}
logger = logging.getLogger(__name__)


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def checkpoint(
    session: Session,
    job_id: uuid.UUID,
    *,
    percent: int,
    stage: str,
    message: str,
) -> Job:
    settings = get_settings()
    job = progress_checkpoint(
        session,
        job_id,
        percent=percent,
        stage=stage,
        message=message,
        lease_seconds=settings.worker_lease_seconds,
    )
    if settings.failure_injection_stage == stage and settings.environment != "production":
        raise RuntimeError(f"Injected failure at stage '{stage}'.")
    return job


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
    uploaded_keys: list[str] = []

    with SessionLocal() as session:
        claimed = claim_job(
            session,
            job_id,
            worker_id=worker_identity(),
            lease_seconds=settings.worker_lease_seconds,
        )
        if claimed is None:
            return None
        job, attempt = claimed

        try:
            version = session.get(DatasetVersion, job.dataset_version_id)
            if version is None:
                raise ValueError("Dataset version no longer exists.")
            checkpoint(
                session,
                job_id,
                percent=15,
                stage="reading_metadata",
                message="Reading file metadata and validation rules",
            )
            configured_rules = list(
                session.scalars(
                    select(ValidationRule).where(
                        ValidationRule.dataset_id == version.dataset_id,
                        ValidationRule.is_enabled.is_(True),
                    )
                )
            )
            rule_specs = [
                RuleSpec(
                    id=rule.id,
                    column_name=rule.column_name,
                    rule_type=rule.rule_type,
                    parameters=rule.parameters_json,
                    severity=rule.severity,
                )
                for rule in configured_rules
            ]
            with TemporaryDirectory(prefix="dataforge-") as temporary_directory:
                input_path = Path(temporary_directory) / "input.csv"
                storage.download_file(version.input_object_key, input_path)
                checkpoint(
                    session,
                    job_id,
                    percent=25,
                    stage="loading_dataset",
                    message="Dataset downloaded and ready to load",
                )
                checkpoint(
                    session,
                    job_id,
                    percent=40,
                    stage="profiling_columns",
                    message="Profiling columns and distributions",
                )
                analysis = analyze_csv(
                    input_path,
                    file_size_bytes=version.file_size_bytes,
                    max_rows=settings.maximum_rows,
                    max_columns=settings.maximum_columns,
                    rules=rule_specs,
                )
            checkpoint(
                session,
                job_id,
                percent=70,
                stage="running_validation",
                message="Validation rules and quality checks complete",
            )
            checkpoint(
                session,
                job_id,
                percent=82,
                stage="comparison_check",
                message="Automatic prior-version comparison not requested",
            )

            checkpoint(
                session,
                job_id,
                percent=90,
                stage="generating_report",
                message="Generating JSON and HTML reports",
            )
            report = build_report(version, analysis)
            report_bytes = json.dumps(report, separators=(",", ":"), sort_keys=True).encode()
            if len(report_bytes) > settings.maximum_report_size_bytes:
                raise ValueError("Generated report exceeds the configured size limit.")
            report_key = report_object_key(version.dataset_id, version.id)
            checkpoint(
                session,
                job_id,
                percent=97,
                stage="uploading_report",
                message="Uploading JSON report",
            )
            storage.put_bytes(report_key, report_bytes, "application/json")
            uploaded_keys.append(report_key)
            html_bytes = build_html_report(report)
            if len(html_bytes) > settings.maximum_report_size_bytes:
                raise ValueError("Generated HTML report exceeds the configured size limit.")
            html_key = html_report_object_key(version.dataset_id, version.id)
            checkpoint(
                session,
                job_id,
                percent=98,
                stage="uploading_report",
                message="Uploading HTML report",
            )
            storage.put_bytes(html_key, html_bytes, "text/html; charset=utf-8")
            uploaded_keys.append(html_key)
            checkpoint(
                session,
                job_id,
                percent=99,
                stage="finalizing",
                message="Finalizing persisted analysis results",
            )

            session.execute(
                delete(ValidationResult).where(ValidationResult.dataset_version_id == version.id)
            )
            for result in [
                *analysis["automatic_issues"],
                *analysis["validation_rule_results"],
            ]:
                rule_id = result["validation_rule_id"]
                session.add(
                    ValidationResult(
                        dataset_version_id=version.id,
                        validation_rule_id=uuid.UUID(rule_id) if rule_id else None,
                        category=str(result["category"]),
                        check_name=str(result["check_name"]),
                        status=str(result["status"]),
                        severity=Severity(str(result["severity"])),
                        affected_count=int(result["affected_count"]),
                        affected_percentage=float(result["affected_percentage"]),
                        message=str(result["message"]),
                        details_json=dict(result["details"]),
                    )
                )

            profile = analysis["profile"]
            version.report_object_key = report_key
            version.html_report_object_key = html_key
            version.row_count = int(profile["row_count"])
            version.column_count = int(profile["column_count"])
            version.schema_json = dict(profile["inferred_data_types"])
            version.profile_summary_json = profile
            version.quality_score = float(analysis["quality_score"]["overall_score"])
            version.analysis_completed_at = datetime.now(UTC)
            completed_at = datetime.now(UTC)
            succeeded_id = session.scalar(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status == JobStatus.RUNNING,
                    Job.cancel_requested_at.is_(None),
                )
                .values(
                    status=JobStatus.SUCCEEDED,
                    completed_at=completed_at,
                    next_retry_at=None,
                    error_code=None,
                    error_message=None,
                    progress_percent=100,
                    progress_message="Complete",
                    current_stage="complete",
                )
                .returning(Job.id)
            )
            if succeeded_id is None:
                raise JobCancelled
            finish_attempt(attempt, status="SUCCEEDED")
            add_job_event(
                session,
                job_id,
                "job_succeeded",
                {"progress_percent": 100, "stage": "complete"},
            )
            session.commit()
            JOB_OUTCOMES.labels(JobStatus.SUCCEEDED.value).inc()
            logger.info(
                "Analysis job succeeded",
                extra={
                    "service": "worker",
                    "request_id": job.correlation_id or "-",
                    "job_id": str(job_id),
                    "dataset_id": str(version.dataset_id),
                    "dataset_version_id": str(version.id),
                    "attempt_id": str(attempt.id),
                    "worker_id": worker_identity(),
                },
            )
            return JobStatus.SUCCEEDED, None
        except JobCancelled:
            session.rollback()
            cleanup_failures: list[str] = []
            for object_key in uploaded_keys:
                try:
                    storage.remove_object(object_key)
                except Exception:
                    cleanup_failures.append(object_key)
            cancelled_job = session.get(Job, job_id)
            cancelled_attempt = session.get(JobAttempt, attempt.id)
            if cancelled_job is None or cancelled_attempt is None:
                raise
            now = datetime.now(UTC)
            if cancelled_job.status == JobStatus.RUNNING:
                transition_job(cancelled_job, JobStatus.CANCELLED)
            cancelled_job.cancel_requested_at = cancelled_job.cancel_requested_at or now
            cancelled_job.cancelled_at = now
            cancelled_job.completed_at = now
            cancelled_job.next_retry_at = None
            cancelled_job.progress_message = "Cancelled"
            cancelled_job.current_stage = "cancelled"
            finish_attempt(cancelled_attempt, status="CANCELLED")
            add_job_event(
                session,
                job_id,
                "job_cancelled",
                {
                    "mode": "cooperative",
                    "removed_partial_outputs": len(uploaded_keys) - len(cleanup_failures),
                    "cleanup_failures": len(cleanup_failures),
                },
            )
            session.commit()
            JOB_OUTCOMES.labels(JobStatus.CANCELLED.value).inc()
            return JobStatus.CANCELLED, None
        except JobLeaseLost:
            session.rollback()
            for object_key in uploaded_keys:
                with suppress(Exception):
                    storage.remove_object(object_key)
            return None
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
            failed_job.progress_message = "Processing failed"
            failed_job.current_stage = "failed"

            if is_retryable_error(exc) and failed_job.retry_count < failed_job.max_retries:
                failed_job.retry_count += 1
                delay = retry_delay_seconds(
                    failed_job.retry_count,
                    base_seconds=settings.retry_base_seconds,
                    maximum_seconds=settings.retry_maximum_seconds,
                )
                transition_job(failed_job, JobStatus.RETRYING)
                failed_job.progress_message = "Waiting to retry"
                failed_job.current_stage = "retrying"
                failed_job.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
                failed_job.completed_at = None
                add_job_event(
                    session,
                    job_id,
                    "job_retry_scheduled",
                    {"retry_count": failed_job.retry_count, "delay_seconds": delay},
                )
                session.commit()
                return JobStatus.RETRYING, delay

            target = JobStatus.DEAD_LETTERED if is_retryable_error(exc) else JobStatus.FAILED
            transition_job(failed_job, target)
            failed_job.next_retry_at = None
            add_job_event(
                session,
                job_id,
                "job_failed",
                {"status": target.value, "error_code": failed_job.error_code or "UNKNOWN"},
            )
            session.commit()
            JOB_OUTCOMES.labels(target.value).inc()
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
            .values(
                status=JobStatus.QUEUED,
                next_retry_at=None,
                progress_message="Queued for retry",
                current_stage="queued",
            )
            .returning(Job.id)
        )
        if changed_id is not None:
            add_job_event(session, parsed_job_id, "job_requeued", {})
        session.commit()
    if changed_id is not None:
        analyze_dataset_version.delay(job_id)


@celery_app.task(name="dataforge.dispatch_scheduled_jobs")  # type: ignore[untyped-decorator]
def dispatch_scheduled_jobs() -> int:
    settings = get_settings()
    now = datetime.now(UTC)
    dispatched: list[uuid.UUID] = []
    with SessionLocal() as session:
        candidates = list(
            session.scalars(
                select(Job.id)
                .where(Job.status == JobStatus.SCHEDULED, Job.scheduled_at <= now)
                .order_by(Job.priority.desc(), Job.scheduled_at, Job.id)
                .limit(settings.scheduler_batch_size)
            )
        )
        for job_id in candidates:
            changed_id = session.scalar(
                update(Job)
                .where(Job.id == job_id, Job.status == JobStatus.SCHEDULED)
                .values(
                    status=JobStatus.QUEUED,
                    queued_at=now,
                    progress_message="Queued by scheduler",
                    current_stage="queued",
                )
                .returning(Job.id)
            )
            if changed_id is not None:
                add_job_event(session, job_id, "job_dispatched", {})
                dispatched.append(changed_id)
        session.commit()
    for job_id in dispatched:
        analyze_dataset_version.delay(str(job_id))
    return len(dispatched)


@celery_app.task(name="dataforge.recover_expired_leases")  # type: ignore[untyped-decorator]
def recover_expired_leases() -> int:
    settings = get_settings()
    now = datetime.now(UTC)
    recovered: list[uuid.UUID] = []
    with SessionLocal() as session:
        candidates = list(
            session.scalars(
                select(Job.id)
                .where(
                    Job.status == JobStatus.RUNNING,
                    Job.lease_expires_at.is_not(None),
                    Job.lease_expires_at < now,
                )
                .limit(settings.scheduler_batch_size)
            )
        )
        for job_id in candidates:
            changed_id = session.scalar(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status == JobStatus.RUNNING,
                    Job.lease_expires_at < now,
                )
                .values(
                    status=JobStatus.QUEUED,
                    queued_at=now,
                    worker_id=None,
                    lease_expires_at=None,
                    progress_message="Recovered after worker lease expired",
                    current_stage="queued",
                    retry_count=Job.retry_count + 1,
                )
                .returning(Job.id)
            )
            if changed_id is None:
                continue
            attempt = session.scalar(
                select(JobAttempt)
                .where(JobAttempt.job_id == job_id, JobAttempt.status == "RUNNING")
                .order_by(JobAttempt.attempt_number.desc())
                .limit(1)
            )
            if attempt is not None:
                finish_attempt(
                    attempt, status="ABANDONED", error=TimeoutError("Worker lease expired.")
                )
            add_job_event(session, job_id, "lease_expired_recovery", {})
            recovered.append(changed_id)
        session.commit()
    for job_id in recovered:
        analyze_dataset_version.delay(str(job_id))
    return len(recovered)
