import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy import select

from app.analysis.basic import analyze_csv
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.db.models import DatasetVersion, Job, JobStatus
from app.db.session import SessionLocal
from app.services.storage import StorageService


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


@celery_app.task(name="dataforge.analyze_dataset_version")  # type: ignore[untyped-decorator]
def analyze_dataset_version(job_id: str) -> None:
    parsed_job_id = uuid.UUID(job_id)
    settings = get_settings()
    storage = StorageService(settings)

    with SessionLocal() as session:
        job = session.scalar(select(Job).where(Job.id == parsed_job_id))
        if job is None or job.status != JobStatus.QUEUED:
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        session.commit()

        try:
            version = session.get(DatasetVersion, job.dataset_version_id)
            if version is None:
                raise RuntimeError("Dataset version no longer exists.")
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
            report_key = f"reports/{version.dataset_id}/{version.id}.json"
            storage.put_bytes(report_key, report_bytes, "application/json")

            profile = analysis["profile"]
            version.report_object_key = report_key
            version.row_count = int(profile["row_count"])
            version.column_count = int(profile["column_count"])
            version.schema_json = dict(profile["inferred_data_types"])
            version.profile_summary_json = profile
            version.analysis_completed_at = datetime.now(UTC)
            job.status = JobStatus.SUCCEEDED
            job.completed_at = datetime.now(UTC)
            session.commit()
        except Exception as exc:
            session.rollback()
            failed_job = session.get(Job, parsed_job_id)
            if failed_job is not None:
                failed_job.status = JobStatus.FAILED
                failed_job.error_message = str(exc)[:2_000]
                failed_job.completed_at = datetime.now(UTC)
                session.commit()
            raise
