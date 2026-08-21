import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dataset
from app.db.session import get_db
from app.schemas.datasets import DatasetCreate, DatasetRead

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


@router.post("", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
def create_dataset(payload: DatasetCreate, db: Annotated[Session, Depends(get_db)]) -> Dataset:
    dataset = Dataset(name=payload.name.strip(), description=payload.description)
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("", response_model=list[DatasetRead])
def list_datasets(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Dataset]:
    return list(
        db.scalars(select(Dataset).order_by(Dataset.created_at.desc()).offset(offset).limit(limit))
    )


@router.get("/{dataset_id}", response_model=DatasetRead)
def get_dataset(dataset_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return dataset
