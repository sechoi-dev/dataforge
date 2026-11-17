import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import JobStatus


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class DatasetVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    version_number: int
    original_filename: str
    description: str | None
    content_type: str
    file_size_bytes: int
    file_sha256: str
    row_count: int | None
    column_count: int | None
    schema_details: dict[str, Any] | None = Field(
        validation_alias="schema_json", serialization_alias="schema_json"
    )
    profile_summary_json: dict[str, Any] | None
    quality_score: float | None
    created_at: datetime
    analysis_completed_at: datetime | None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_version_id: uuid.UUID
    job_type: str
    status: JobStatus
    retry_count: int
    max_retries: int
    next_retry_at: datetime | None
    priority: int
    scheduled_at: datetime | None
    queued_at: datetime | None
    progress_percent: int
    progress_message: str
    current_stage: str
    cancel_requested_at: datetime | None
    cancelled_at: datetime | None
    worker_id: str | None
    lease_expires_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    attempt_number: int
    status: str
    worker_id: str | None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None


class JobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    event_type: str
    payload_json: dict[str, Any]
    created_at: datetime


class UploadAccepted(BaseModel):
    dataset_version: DatasetVersionRead
    job: JobRead
