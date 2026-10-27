import re
import uuid
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.db.models import RuleType, Severity


@dataclass(frozen=True)
class RuleSpec:
    id: uuid.UUID
    column_name: str | None
    rule_type: RuleType
    parameters: dict[str, Any]
    severity: Severity


def safe_samples(series: pd.Series[Any], mask: pd.Series[bool]) -> list[str]:
    values = series[mask].dropna().astype(str).drop_duplicates().head(5)
    return [value[:100] for value in values.tolist()]


def apparent_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "float"
    text = str(value).strip()
    lowered = text.lower()
    if lowered in {"true", "false", "yes", "no", "y", "n"}:
        return "boolean"
    if re.fullmatch(r"[+-]?\d+", text):
        return "integer"
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)", text):
        return "float"
    return "string"


def evaluate_rules(frame: pd.DataFrame, rules: list[RuleSpec]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    row_count = len(frame.index)
    duplicate_percentage = float(frame.duplicated().mean() * 100) if row_count else 0.0

    for rule in rules:
        if rule.column_name is not None and rule.column_name not in frame.columns:
            results.append(
                _result(
                    rule,
                    affected_count=row_count,
                    row_count=row_count,
                    message=f"Required column '{rule.column_name}' is missing.",
                    samples=[],
                )
            )
            continue

        series = frame[rule.column_name] if rule.column_name is not None else None
        mask = pd.Series(False, index=frame.index, dtype=bool)
        message = "Rule passed."

        if rule.rule_type == RuleType.NOT_NULL and series is not None:
            mask = series.isna()
            message = f"{int(mask.sum())} rows contain missing values."
        elif rule.rule_type == RuleType.UNIQUE and series is not None:
            mask = series.notna() & series.duplicated(keep=False)
            message = f"{int(mask.sum())} rows contain duplicate values."
        elif (
            rule.rule_type in {RuleType.MIN_VALUE, RuleType.MAX_VALUE, RuleType.RANGE}
            and series is not None
        ):
            numeric = pd.to_numeric(series, errors="coerce")
            mask = series.notna() & numeric.isna()
            if rule.rule_type == RuleType.MIN_VALUE:
                mask |= numeric < float(rule.parameters["value"])
            elif rule.rule_type == RuleType.MAX_VALUE:
                mask |= numeric > float(rule.parameters["value"])
            else:
                mask |= (numeric < float(rule.parameters["minimum"])) | (
                    numeric > float(rule.parameters["maximum"])
                )
            message = f"{int(mask.sum())} rows fall outside the numeric expectation."
        elif rule.rule_type == RuleType.ALLOWED_VALUES and series is not None:
            mask = series.notna() & ~series.isin(rule.parameters["values"])
            message = f"{int(mask.sum())} rows contain unexpected values."
        elif rule.rule_type == RuleType.REGEX and series is not None:
            matches = series.astype("string").str.fullmatch(rule.parameters["pattern"], na=False)
            mask = series.notna() & ~matches
            message = f"{int(mask.sum())} rows do not match the required pattern."
        elif rule.rule_type == RuleType.EXPECTED_TYPE and series is not None:
            expected = str(rule.parameters["type"])
            observed = series.dropna().map(apparent_type)
            accepted = {
                "number": {"integer", "float"},
                "float": {"integer", "float"},
                "integer": {"integer"},
                "string": {"string"},
                "boolean": {"boolean"},
            }
            if expected == "date":
                parsed = pd.to_datetime(series, errors="coerce")
                mask = series.notna() & parsed.isna()
            else:
                bad_indexes = observed[~observed.isin(accepted[expected])].index
                mask.loc[bad_indexes] = True
            message = f"{int(mask.sum())} rows do not match expected type '{expected}'."
        elif rule.rule_type == RuleType.DATE_PARSEABLE and series is not None:
            parsed = pd.to_datetime(series, errors="coerce")
            mask = series.notna() & parsed.isna()
            message = f"{int(mask.sum())} rows are not parseable dates."
        elif rule.rule_type == RuleType.MINIMUM_ROW_COUNT:
            minimum = int(rule.parameters["value"])
            affected = max(0, minimum - row_count)
            results.append(
                _result(
                    rule,
                    affected_count=affected,
                    row_count=max(row_count, minimum),
                    message=f"Dataset has {row_count} rows; minimum is {minimum}.",
                    samples=[],
                )
            )
            continue
        elif rule.rule_type == RuleType.MAXIMUM_MISSING_PERCENTAGE and series is not None:
            actual = float(series.isna().mean() * 100) if row_count else 0.0
            exceeded = actual > float(rule.parameters["value"])
            mask = series.isna() if exceeded else mask
            message = f"Missingness is {actual:.2f}%."
        elif rule.rule_type == RuleType.MAXIMUM_DUPLICATE_PERCENTAGE:
            exceeded = duplicate_percentage > float(rule.parameters["value"])
            mask = frame.duplicated() if exceeded else mask
            message = f"Duplicate-row percentage is {duplicate_percentage:.2f}%."

        results.append(
            _result(
                rule,
                affected_count=int(mask.sum()),
                row_count=row_count,
                message=message,
                samples=safe_samples(series, mask) if series is not None else [],
            )
        )
    return results


def _result(
    rule: RuleSpec,
    *,
    affected_count: int,
    row_count: int,
    message: str,
    samples: list[str],
) -> dict[str, Any]:
    percentage = (affected_count / row_count * 100) if row_count else 0.0
    return {
        "validation_rule_id": str(rule.id),
        "category": "custom_rule",
        "check_name": rule.rule_type.value,
        "status": "failed" if affected_count else "passed",
        "severity": rule.severity.value,
        "affected_count": affected_count,
        "affected_percentage": round(percentage, 4),
        "message": message,
        "details": {"column": rule.column_name, "sample_offending_values": samples},
    }
