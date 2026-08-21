import hashlib
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Dataset, DatasetVersion, Job
from app.db.session import get_db
from app.schemas.datasets import DatasetVersionRead, UploadAccepted
from app.services.storage import StorageService
from app.workers.tasks import analyze_dataset_version

router = APIRouter(prefix="/api/v1/datasets/{dataset_id}/versions", tags=["dataset versions"])
ALLOWED_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}


def get_storage() -> StorageService:
    return StorageService()


def enqueue_analysis(job_id: str) -> None:
    analyze_dataset_version.delay(job_id)


def copy_upload(upload: UploadFile, destination: Path, maximum_bytes: int) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    with destination.open("wb") as output:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > maximum_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Upload exceeds the {maximum_bytes}-byte limit.",
                )
            digest.update(chunk)
            output.write(chunk)
    if size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="CSV is empty."
        )
    return size, digest.hexdigest()


@router.post("", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
def upload_version(
    dataset_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[StorageService, Depends(get_storage)],
    description: Annotated[str | None, Form(max_length=2_000)] = None,
) -> UploadAccepted:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    safe_filename = Path(file.filename or "").name
    if not safe_filename or Path(safe_filename).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .csv files are supported.",
        )
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported CSV content type.",
        )

    version_id = uuid.uuid4()
    with TemporaryDirectory(prefix="dataforge-upload-") as temporary_directory:
        input_path = Path(temporary_directory) / "input.csv"
        file_size, file_hash = copy_upload(file, input_path, settings.maximum_upload_size_bytes)
        current_version = db.scalar(
            select(func.coalesce(func.max(DatasetVersion.version_number), 0)).where(
                DatasetVersion.dataset_id == dataset_id
            )
        )
        version_number = int(current_version or 0) + 1
        object_key = f"datasets/{dataset_id}/versions/{version_id}/input.csv"
        storage.ensure_bucket()
        storage.upload_file(object_key, input_path, file.content_type or "text/csv")

    version = DatasetVersion(
        id=version_id,
        dataset_id=dataset_id,
        version_number=version_number,
        original_filename=safe_filename,
        description=description,
        content_type=file.content_type or "text/csv",
        file_size_bytes=file_size,
        file_sha256=file_hash,
        input_object_key=object_key,
    )
    job = Job(dataset_version=version)
    db.add_all([version, job])
    db.commit()
    db.refresh(version)
    db.refresh(job)
    enqueue_analysis(str(job.id))
    return UploadAccepted(dataset_version=DatasetVersionRead.model_validate(version), job=job)


@router.get("", response_model=list[DatasetVersionRead])
def list_versions(
    dataset_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]
) -> list[DatasetVersion]:
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return list(
        db.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc())
        )
    )


def find_version(db: Session, dataset_id: uuid.UUID, version_id: uuid.UUID) -> DatasetVersion:
    version = db.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset_id
        )
    )
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


@router.get("/{version_id}", response_model=DatasetVersionRead)
def get_version(
    dataset_id: uuid.UUID, version_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]
) -> DatasetVersion:
    return find_version(db, dataset_id, version_id)


@router.get("/{version_id}/report")
def get_report(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> Response:
    version = find_version(db, dataset_id, version_id)
    if version.report_object_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report is not available until analysis succeeds.",
        )
    return Response(storage.get_bytes(version.report_object_key), media_type="application/json")
