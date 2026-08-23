import uuid

import pytest

from app.db.models import Job, JobStatus
from app.services.idempotency import input_object_key, report_object_key, request_fingerprint
from app.services.jobs import retry_delay_seconds, transition_job


def test_request_fingerprint_is_stable_and_input_sensitive() -> None:
    dataset_id = uuid.uuid4()
    first = request_fingerprint(
        dataset_id=dataset_id,
        file_sha256="a" * 64,
        filename="data.csv",
        content_type="text/csv",
        description="first",
    )
    assert first == request_fingerprint(
        dataset_id=dataset_id,
        file_sha256="a" * 64,
        filename="data.csv",
        content_type="text/csv",
        description="first",
    )
    assert first != request_fingerprint(
        dataset_id=dataset_id,
        file_sha256="a" * 64,
        filename="data.csv",
        content_type="text/csv",
        description="changed",
    )


def test_object_keys_are_deterministic() -> None:
    dataset_id = uuid.uuid4()
    version_id = uuid.uuid4()
    assert input_object_key(dataset_id, "b" * 64) == input_object_key(dataset_id, "b" * 64)
    assert report_object_key(dataset_id, version_id) == report_object_key(dataset_id, version_id)


def test_exponential_backoff_with_bounded_jitter() -> None:
    assert retry_delay_seconds(1, random_value=0) == 2.0
    assert retry_delay_seconds(2, random_value=1) == 5.0
    assert retry_delay_seconds(20, maximum_seconds=30, random_value=1) == 37.5


def test_invalid_status_transition_is_rejected() -> None:
    job = Job(dataset_version_id=uuid.uuid4(), status=JobStatus.SUCCEEDED)
    with pytest.raises(ValueError, match="Invalid job transition"):
        transition_job(job, JobStatus.RUNNING)
