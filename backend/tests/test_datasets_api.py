from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import comparisons as comparisons_module
from app.api.routes import versions as versions_module
from app.db.base import Base
from app.db.models import DatasetVersion, Job, JobStatus
from app.db.session import get_db
from app.main import app


class FakeStorage:
    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    def ensure_bucket(self) -> None:
        return None

    def upload_file(self, object_key: str, path: Any, content_type: str) -> None:
        del content_type
        self.uploaded[object_key] = path.read_bytes()

    def get_bytes(self, object_key: str) -> bytes:
        return self.uploaded[object_key]

    def download_file(self, object_key: str, path: Any) -> None:
        path.write_bytes(self.uploaded[object_key])

    def put_bytes(self, object_key: str, content: bytes, content_type: str) -> None:
        del content_type
        self.uploaded[object_key] = content


@pytest.fixture
def api_context(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    storage = FakeStorage()
    queued_jobs: list[str] = []

    def override_db() -> Generator[Session, None, None]:
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[versions_module.get_storage] = lambda: storage
    app.dependency_overrides[comparisons_module.get_storage] = lambda: storage
    monkeypatch.setattr(versions_module, "enqueue_analysis", queued_jobs.append)
    with TestClient(app) as client:
        yield client, test_sessions, storage, queued_jobs
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_dataset_and_queue_csv_upload(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, test_sessions, storage, queued_jobs = api_context
    dataset_response = client.post(
        "/api/v1/datasets", json={"name": "Survey responses", "description": "Fall survey"}
    )
    assert dataset_response.status_code == 201
    dataset_id = dataset_response.json()["id"]

    upload_response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        headers={"Idempotency-Key": "survey-upload-1"},
        files={"file": ("survey.csv", b"id,name\n1,Ada\n", "text/csv")},
        data={"description": "First export"},
    )

    assert upload_response.status_code == 202
    payload = upload_response.json()
    assert payload["job"]["status"] == "QUEUED"
    assert payload["dataset_version"]["version_number"] == 1
    assert payload["dataset_version"]["description"] == "First export"
    assert len(storage.uploaded) == 1
    assert queued_jobs == [payload["job"]["id"]]

    with test_sessions() as session:
        version = session.scalar(select(DatasetVersion))
        job = session.scalar(select(Job))
        assert version is not None and version.file_sha256
        assert job is not None and job.status == JobStatus.QUEUED


def test_report_is_unavailable_before_worker_finishes(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, _, _, _ = api_context
    dataset_id = client.post("/api/v1/datasets", json={"name": "Example"}).json()["id"]
    version = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        headers={"Idempotency-Key": "example-upload-1"},
        files={"file": ("example.csv", b"id\n1\n", "text/csv")},
    ).json()["dataset_version"]

    response = client.get(f"/api/v1/datasets/{dataset_id}/versions/{version['id']}/report")
    assert response.status_code == 409


def test_identical_idempotent_upload_returns_existing_job(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, test_sessions, _, queued_jobs = api_context
    dataset_id = client.post("/api/v1/datasets", json={"name": "Idempotent"}).json()["id"]
    url = f"/api/v1/datasets/{dataset_id}/versions"
    headers = {"Idempotency-Key": "stable-key"}
    files = {"file": ("same.csv", b"id\n1\n", "text/csv")}

    first = client.post(url, headers=headers, files=files)
    second = client.post(url, headers=headers, files=files)

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(queued_jobs) == 1
    with test_sessions() as session:
        assert len(list(session.scalars(select(Job)))) == 1
        assert len(list(session.scalars(select(DatasetVersion)))) == 1


def test_idempotency_key_reuse_with_different_input_conflicts(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, _, _, _ = api_context
    dataset_id = client.post("/api/v1/datasets", json={"name": "Conflict"}).json()["id"]
    url = f"/api/v1/datasets/{dataset_id}/versions"
    headers = {"Idempotency-Key": "reused-key"}

    assert (
        client.post(
            url, headers=headers, files={"file": ("data.csv", b"id\n1\n", "text/csv")}
        ).status_code
        == 202
    )
    conflict = client.post(
        url, headers=headers, files={"file": ("data.csv", b"id\n2\n", "text/csv")}
    )
    assert conflict.status_code == 409


def test_upload_requires_idempotency_key(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, _, _, _ = api_context
    dataset_id = client.post("/api/v1/datasets", json={"name": "Required key"}).json()["id"]
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        files={"file": ("data.csv", b"id\n1\n", "text/csv")},
    )
    assert response.status_code == 422


def test_validation_rule_crud(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, _, _, _ = api_context
    dataset_id = client.post("/api/v1/datasets", json={"name": "Validated"}).json()["id"]
    url = f"/api/v1/datasets/{dataset_id}/rules"

    created = client.post(
        url,
        json={
            "column_name": "age",
            "rule_type": "range",
            "parameters": {"minimum": 0, "maximum": 120},
            "severity": "critical",
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert client.get(url).json()[0]["parameters"] == {"minimum": 0, "maximum": 120}

    updated = client.patch(f"{url}/{rule_id}", json={"is_enabled": False})
    assert updated.status_code == 200
    assert updated.json()["is_enabled"] is False
    assert client.delete(f"{url}/{rule_id}").status_code == 204
    assert client.get(url).json() == []


def test_validation_rule_rejects_invalid_configuration(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, _, _, _ = api_context
    dataset_id = client.post("/api/v1/datasets", json={"name": "Invalid rule"}).json()["id"]
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/rules",
        json={
            "column_name": "age",
            "rule_type": "range",
            "parameters": {"minimum": 120, "maximum": 0},
        },
    )
    assert response.status_code == 422


def test_compare_versions_and_download_report(
    api_context: tuple[TestClient, sessionmaker[Session], FakeStorage, list[str]],
) -> None:
    client, _, _, _ = api_context
    dataset_id = client.post("/api/v1/datasets", json={"name": "History"}).json()["id"]
    versions_url = f"/api/v1/datasets/{dataset_id}/versions"
    left = client.post(
        versions_url,
        headers={"Idempotency-Key": "history-left"},
        files={"file": ("left.csv", b"id,status\n1,active\n2,inactive\n", "text/csv")},
    ).json()["dataset_version"]
    right = client.post(
        versions_url,
        headers={"Idempotency-Key": "history-right"},
        files={"file": ("right.csv", b"id,status\n1,active\n3,pending\n", "text/csv")},
    ).json()["dataset_version"]

    response = client.post(
        "/api/v1/comparisons",
        json={
            "left_version_id": left["id"],
            "right_version_id": right["id"],
            "selected_key_columns": ["id"],
        },
    )

    assert response.status_code == 201
    comparison = response.json()
    assert comparison["status"] == "SUCCEEDED"
    report_response = client.get(f"/api/v1/comparisons/{comparison['id']}/report")
    assert report_response.status_code == 200
    assert "attachment" in report_response.headers["content-disposition"]
    assert report_response.json()["overlap"]["selected_keys"]["overlapping_row_count"] == 1
