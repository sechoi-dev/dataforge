import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pandas.errors import EmptyDataError, ParserError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.comparison import ComparisonError, compare_frames
from app.core.config import Settings, get_settings
from app.db.models import Comparison, ComparisonStatus, DatasetVersion
from app.db.session import get_db
from app.schemas.comparisons import ComparisonCreate, ComparisonRead
from app.services.idempotency import comparison_object_key
from app.services.storage import StorageService

router = APIRouter(prefix="/api/v1/comparisons", tags=["comparisons"])


def get_storage() -> StorageService:
    return StorageService()


def _fingerprint(payload: ComparisonCreate) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _load_csv(path: Path, settings: Settings) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, nrows=settings.maximum_rows + 1, low_memory=False)
    except (EmptyDataError, ParserError, UnicodeDecodeError) as exc:
        raise ComparisonError("A dataset version is not a readable UTF-8 CSV.") from exc
    if len(frame.index) > settings.maximum_rows:
        raise ComparisonError("A dataset version exceeds the configured row limit.")
    if len(frame.columns) > settings.maximum_columns:
        raise ComparisonError("A dataset version exceeds the configured column limit.")
    return frame


def _require_version(db: Session, version_id: uuid.UUID) -> DatasetVersion:
    version = db.get(DatasetVersion, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


@router.post("", response_model=ComparisonRead, status_code=status.HTTP_201_CREATED)
def create_comparison(
    payload: ComparisonCreate,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> Comparison:
    left_version = _require_version(db, payload.left_version_id)
    right_version = _require_version(db, payload.right_version_id)
    fingerprint = _fingerprint(payload)
    existing = db.scalar(
        select(Comparison).where(
            Comparison.left_version_id == payload.left_version_id,
            Comparison.right_version_id == payload.right_version_id,
            Comparison.request_fingerprint == fingerprint,
        )
    )
    if existing is not None:
        return existing

    comparison = Comparison(
        left_version_id=payload.left_version_id,
        right_version_id=payload.right_version_id,
        status=ComparisonStatus.PROCESSING,
        selected_key_columns=payload.selected_key_columns,
        normalize_text=payload.normalize_text,
        request_fingerprint=fingerprint,
    )
    db.add(comparison)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Comparison).where(
                Comparison.left_version_id == payload.left_version_id,
                Comparison.right_version_id == payload.right_version_id,
                Comparison.request_fingerprint == fingerprint,
            )
        )
        if existing is not None:
            return existing
        raise
    db.refresh(comparison)

    try:
        with TemporaryDirectory(prefix="dataforge-comparison-") as temporary_directory:
            directory = Path(temporary_directory)
            left_path = directory / "left.csv"
            right_path = directory / "right.csv"
            storage.download_file(left_version.input_object_key, left_path)
            storage.download_file(right_version.input_object_key, right_path)
            result = compare_frames(
                _load_csv(left_path, settings),
                _load_csv(right_path, settings),
                selected_key_columns=payload.selected_key_columns,
                normalize_text=payload.normalize_text,
            )
        report = {
            "report_version": "1.0",
            "comparison_id": str(comparison.id),
            "left_version_id": str(left_version.id),
            "right_version_id": str(right_version.id),
            "selected_key_columns": payload.selected_key_columns,
            "normalize_text": payload.normalize_text,
            **result,
        }
        report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        if len(report_bytes) > settings.maximum_report_size_bytes:
            raise ComparisonError("Generated comparison report exceeds the configured size limit.")
        object_key = comparison_object_key(comparison.id)
        storage.put_bytes(object_key, report_bytes, "application/json")
        comparison.result_object_key = object_key
        comparison.status = ComparisonStatus.SUCCEEDED
        comparison.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(comparison)
        return comparison
    except ComparisonError as exc:
        comparison.status = ComparisonStatus.FAILED
        comparison.error_message = str(exc)[:2_000]
        comparison.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except Exception:
        db.rollback()
        failed = db.get(Comparison, comparison.id)
        if failed is not None:
            failed.status = ComparisonStatus.FAILED
            failed.error_message = "Comparison processing failed."
            failed.completed_at = datetime.now(UTC)
            db.commit()
        raise


@router.get("/{comparison_id}", response_model=ComparisonRead)
def get_comparison(comparison_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Comparison:
    comparison = db.get(Comparison, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found.")
    return comparison


@router.get("/{comparison_id}/report")
def download_comparison_report(
    comparison_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> Response:
    comparison = db.get(Comparison, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found.")
    if comparison.result_object_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Comparison report is not available until processing succeeds.",
        )
    return Response(
        storage.get_bytes(comparison.result_object_key),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="comparison-{comparison.id}.json"'},
    )
