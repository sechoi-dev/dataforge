import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import ComparisonStatus


class ComparisonCreate(BaseModel):
    left_version_id: uuid.UUID
    right_version_id: uuid.UUID
    selected_key_columns: list[str] = Field(default_factory=list, max_length=20)
    normalize_text: bool = False

    @model_validator(mode="after")
    def validate_comparison(self) -> "ComparisonCreate":
        if self.left_version_id == self.right_version_id:
            raise ValueError("Two different dataset versions are required.")
        cleaned = [column.strip() for column in self.selected_key_columns]
        if any(not column for column in cleaned):
            raise ValueError("Selected key columns cannot be blank.")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Selected key columns must be unique.")
        self.selected_key_columns = cleaned
        return self


class ComparisonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    left_version_id: uuid.UUID
    right_version_id: uuid.UUID
    status: ComparisonStatus
    selected_key_columns: list[str]
    normalize_text: bool
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
