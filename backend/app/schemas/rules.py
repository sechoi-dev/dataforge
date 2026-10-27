import re
import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import RuleType, Severity

DATASET_LEVEL_RULES = {
    RuleType.MINIMUM_ROW_COUNT,
    RuleType.MAXIMUM_DUPLICATE_PERCENTAGE,
}
NO_PARAMETER_RULES = {RuleType.NOT_NULL, RuleType.UNIQUE, RuleType.DATE_PARSEABLE}


class RuleCreate(BaseModel):
    column_name: str | None = Field(default=None, max_length=255)
    rule_type: RuleType
    parameters: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Severity.WARNING
    is_enabled: bool = True

    @model_validator(mode="after")
    def validate_rule(self) -> Self:
        if self.column_name is not None:
            self.column_name = self.column_name.strip() or None
        if self.rule_type in DATASET_LEVEL_RULES:
            if self.column_name is not None:
                raise ValueError("Dataset-level rules cannot specify column_name.")
        elif self.column_name is None:
            raise ValueError("This rule type requires column_name.")

        parameters = self.parameters
        if self.rule_type in NO_PARAMETER_RULES and parameters:
            raise ValueError("This rule type does not accept parameters.")
        if self.rule_type in {RuleType.MIN_VALUE, RuleType.MAX_VALUE}:
            _require_number(parameters, "value")
        elif self.rule_type == RuleType.RANGE:
            minimum = _require_number(parameters, "minimum")
            maximum = _require_number(parameters, "maximum")
            if minimum > maximum:
                raise ValueError("minimum cannot exceed maximum.")
        elif self.rule_type == RuleType.ALLOWED_VALUES:
            values = parameters.get("values")
            if not isinstance(values, list) or not values or len(values) > 1_000:
                raise ValueError("values must be a non-empty list with at most 1000 items.")
        elif self.rule_type == RuleType.REGEX:
            pattern = parameters.get("pattern")
            if not isinstance(pattern, str) or not pattern or len(pattern) > 500:
                raise ValueError("pattern must be a non-empty string of at most 500 characters.")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError("pattern must be a valid regular expression.") from exc
        elif self.rule_type == RuleType.EXPECTED_TYPE:
            expected = parameters.get("type")
            if expected not in {"string", "integer", "float", "number", "boolean", "date"}:
                raise ValueError("type must be string, integer, float, number, boolean, or date.")
        elif self.rule_type == RuleType.MINIMUM_ROW_COUNT:
            value = parameters.get("value")
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("value must be a non-negative integer.")
        elif self.rule_type in {
            RuleType.MAXIMUM_MISSING_PERCENTAGE,
            RuleType.MAXIMUM_DUPLICATE_PERCENTAGE,
        }:
            value = _require_number(parameters, "value")
            if not 0 <= value <= 100:
                raise ValueError("percentage value must be between 0 and 100.")
        return self


def _require_number(parameters: dict[str, Any], name: str) -> float:
    value = parameters.get(name)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric.")
    return float(value)


class RuleUpdate(BaseModel):
    column_name: str | None = Field(default=None, max_length=255)
    rule_type: RuleType | None = None
    parameters: dict[str, Any] | None = None
    severity: Severity | None = None
    is_enabled: bool | None = None


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    column_name: str | None
    rule_type: RuleType
    parameters: dict[str, Any] = Field(validation_alias="parameters_json")
    severity: Severity
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
