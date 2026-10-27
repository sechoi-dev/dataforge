from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from app.analysis.rich import rich_profile
from app.analysis.rules import RuleSpec, evaluate_rules
from app.analysis.scoring import calculate_quality_score


class CsvAnalysisError(ValueError):
    """Raised when a CSV cannot be safely analyzed."""


def analyze_csv(
    path: Path,
    *,
    file_size_bytes: int,
    max_rows: int,
    max_columns: int,
    rules: list[RuleSpec] | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    try:
        frame = pd.read_csv(path, nrows=max_rows + 1, low_memory=False)
    except (EmptyDataError, ParserError, UnicodeDecodeError) as exc:
        raise CsvAnalysisError("The uploaded file is not a readable UTF-8 CSV.") from exc

    if len(frame.index) > max_rows:
        raise CsvAnalysisError(f"CSV exceeds the configured row limit of {max_rows}.")
    if len(frame.columns) == 0:
        raise CsvAnalysisError("CSV must contain at least one column.")
    if len(frame.columns) > max_columns:
        raise CsvAnalysisError(f"CSV exceeds the configured column limit of {max_columns}.")

    row_count = int(len(frame.index))
    missing = frame.isna()
    missing_by_column = {
        str(column): {
            "missing_count": int(missing[column].sum()),
            "missing_percentage": round(float(missing[column].mean() * 100), 4)
            if row_count
            else 0.0,
        }
        for column in frame.columns
    }
    schema = {str(column): str(dtype) for column, dtype in frame.dtypes.items()}

    analysis: dict[str, Any] = {
        "profile": {
            "row_count": row_count,
            "column_count": int(len(frame.columns)),
            "column_names": [str(column) for column in frame.columns],
            "inferred_data_types": schema,
            "memory_estimate_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
            "file_size_bytes": file_size_bytes,
            "duplicate_row_count": int(frame.duplicated().sum()),
            "fully_empty_row_count": int(missing.all(axis=1).sum()),
            "processing_duration_ms": 0.0,
        },
        "missing_values": missing_by_column,
        "limitations": [
            "Type inference uses pandas and may not reflect domain-specific expectations.",
            "Duplicate analysis detects exact duplicate rows only.",
            "IQR outliers are observations for review, not proof of invalid data.",
        ],
    }
    analysis.update(rich_profile(frame))
    analysis["validation_rule_results"] = evaluate_rules(frame, rules or [])
    analysis["automatic_issues"].extend(
        _dataset_issues(
            row_count=row_count,
            duplicate_row_count=int(frame.duplicated().sum()),
            missing_by_column=missing_by_column,
        )
    )
    analysis["quality_score"] = calculate_quality_score(analysis)
    analysis["recommendations"] = _recommendations(analysis)
    analysis["profile"]["processing_duration_ms"] = round(
        (perf_counter() - started) * 1000, 2
    )
    return analysis


def _dataset_issues(
    *,
    row_count: int,
    duplicate_row_count: int,
    missing_by_column: dict[str, dict[str, int | float]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if duplicate_row_count:
        percentage = duplicate_row_count / row_count * 100 if row_count else 0.0
        issues.append(
            _issue(
                "duplicate_rows",
                "warning",
                duplicate_row_count,
                percentage,
                f"{duplicate_row_count} exact duplicate rows were found.",
            )
        )
    for column, values in missing_by_column.items():
        percentage = float(values["missing_percentage"])
        if percentage:
            issues.append(
                _issue(
                    "missing_values",
                    "critical" if percentage > 50 else "warning",
                    int(values["missing_count"]),
                    percentage,
                    f"Column '{column}' is {percentage:.2f}% missing.",
                    column,
                )
            )
    return issues


def _issue(
    check_name: str,
    severity: str,
    affected_count: int,
    affected_percentage: float,
    message: str,
    column: str | None = None,
) -> dict[str, Any]:
    return {
        "validation_rule_id": None,
        "category": "automatic",
        "check_name": check_name,
        "status": "observed",
        "severity": severity,
        "affected_count": affected_count,
        "affected_percentage": round(affected_percentage, 4),
        "message": message,
        "details": {"column": column},
    }


def _recommendations(analysis: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    if any(item["missing_count"] for item in analysis["missing_values"].values()):
        recommendations.append("Review missing values and document whether they are expected.")
    if analysis["profile"]["duplicate_row_count"]:
        recommendations.append("Review exact duplicate rows before downstream aggregation.")
    if analysis["mixed_type_issues"]:
        recommendations.append("Normalize columns containing mixed apparent types.")
    if any(result["status"] == "failed" for result in analysis["validation_rule_results"]):
        recommendations.append("Resolve failed validation rules or revise documented expectations.")
    if not recommendations:
        recommendations.append("No immediate quality remediation was identified.")
    return recommendations
