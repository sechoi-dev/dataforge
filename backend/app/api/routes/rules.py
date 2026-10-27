import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Dataset, ValidationRule
from app.db.session import get_db
from app.schemas.rules import RuleCreate, RuleRead, RuleUpdate

router = APIRouter(prefix="/api/v1/datasets/{dataset_id}/rules", tags=["validation rules"])


def require_dataset(db: Session, dataset_id: uuid.UUID) -> None:
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")


def require_rule(db: Session, dataset_id: uuid.UUID, rule_id: uuid.UUID) -> ValidationRule:
    rule = db.scalar(
        select(ValidationRule).where(
            ValidationRule.id == rule_id, ValidationRule.dataset_id == dataset_id
        )
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return rule


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    dataset_id: uuid.UUID,
    payload: RuleCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ValidationRule:
    require_dataset(db, dataset_id)
    rule = ValidationRule(
        dataset_id=dataset_id,
        column_name=payload.column_name,
        rule_type=payload.rule_type,
        parameters_json=payload.parameters,
        severity=payload.severity,
        is_enabled=payload.is_enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("", response_model=list[RuleRead])
def list_rules(
    dataset_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]
) -> list[ValidationRule]:
    require_dataset(db, dataset_id)
    return list(
        db.scalars(
            select(ValidationRule)
            .where(ValidationRule.dataset_id == dataset_id)
            .order_by(ValidationRule.created_at)
        )
    )


@router.patch("/{rule_id}", response_model=RuleRead)
def update_rule(
    dataset_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: RuleUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ValidationRule:
    rule = require_rule(db, dataset_id, rule_id)
    changes = payload.model_dump(exclude_unset=True)
    candidate = RuleCreate(
        column_name=changes.get("column_name", rule.column_name),
        rule_type=changes.get("rule_type", rule.rule_type),
        parameters=changes.get("parameters", rule.parameters_json),
        severity=changes.get("severity", rule.severity),
        is_enabled=changes.get("is_enabled", rule.is_enabled),
    )
    rule.column_name = candidate.column_name
    rule.rule_type = candidate.rule_type
    rule.parameters_json = candidate.parameters
    rule.severity = candidate.severity
    rule.is_enabled = candidate.is_enabled
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    dataset_id: uuid.UUID,
    rule_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    rule = require_rule(db, dataset_id, rule_id)
    db.delete(rule)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
