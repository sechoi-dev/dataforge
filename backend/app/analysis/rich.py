from typing import Any

import pandas as pd
from pandas.api.types import is_numeric_dtype

from app.analysis.rules import apparent_type


def rich_profile(frame: pd.DataFrame) -> dict[str, Any]:
    row_count = len(frame.index)
    unique_analysis: dict[str, Any] = {}
    numeric_analysis: dict[str, Any] = {}
    categorical_analysis: dict[str, Any] = {}
    mixed_type_issues: list[dict[str, Any]] = []
    automatic_issues: list[dict[str, Any]] = []

    for column in frame.columns:
        name = str(column)
        series = frame[column]
        non_null = series.dropna()
        unique_count = int(non_null.nunique())
        uniqueness_ratio = unique_count / len(non_null.index) if len(non_null.index) else 0.0
        top_frequency = int(non_null.value_counts().iloc[0]) if len(non_null.index) else 0
        unique_analysis[name] = {
            "unique_count": unique_count,
            "uniqueness_ratio": round(uniqueness_ratio, 4),
            "likely_identifier": bool(row_count and uniqueness_ratio == 1 and row_count > 1),
            "constant": unique_count == 1 and row_count > 0,
            "near_constant": bool(
                row_count and top_frequency / row_count >= 0.95 and unique_count > 1
            ),
        }

        apparent_types = non_null.map(apparent_type)
        observed_types = sorted(set(apparent_types.tolist()))
        normalized_types = set(observed_types)
        is_mixed = len(normalized_types) > 1 and not normalized_types <= {"integer", "float"}
        if is_mixed:
            message = f"Column '{name}' contains mixed apparent types: {', '.join(observed_types)}."
            issue = {
                "column": name,
                "observed_types": observed_types,
                "message": message,
            }
            mixed_type_issues.append(issue)
            type_counts = apparent_types.value_counts()
            affected_count = int(len(apparent_types.index) - type_counts.max())
            automatic_issues.append(
                _automatic(
                    "mixed_type",
                    "warning",
                    message,
                    name,
                    affected_count=affected_count,
                    row_count=row_count,
                )
            )

        if is_numeric_dtype(series.dtype):
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            if numeric.empty:
                continue
            first_quartile = float(numeric.quantile(0.25))
            third_quartile = float(numeric.quantile(0.75))
            iqr = third_quartile - first_quartile
            lower = first_quartile - 1.5 * iqr
            upper = third_quartile + 1.5 * iqr
            outlier_count = int(((numeric < lower) | (numeric > upper)).sum()) if iqr else 0
            numeric_analysis[name] = {
                "minimum": _number(numeric.min()),
                "maximum": _number(numeric.max()),
                "mean": _number(numeric.mean()),
                "median": _number(numeric.median()),
                "standard_deviation": _number(numeric.std()),
                "percentiles": {
                    "25": _number(first_quartile),
                    "50": _number(numeric.quantile(0.5)),
                    "75": _number(third_quartile),
                },
                "zero_count": int((numeric == 0).sum()),
                "negative_count": int((numeric < 0).sum()),
                "outlier_count": outlier_count,
                "outlier_method": "IQR (1.5 × interquartile range)",
            }
            if outlier_count:
                automatic_issues.append(
                    _automatic(
                        "numeric_outliers",
                        "info",
                        f"Column '{name}' has {outlier_count} IQR outlier observations; "
                        "they are not necessarily invalid.",
                        name,
                        affected_count=outlier_count,
                        row_count=row_count,
                    )
                )
        else:
            counts = non_null.astype(str).value_counts()
            rare_threshold = max(1, int(row_count * 0.01))
            categorical_analysis[name] = {
                "most_common_values": [
                    {"value": str(value)[:100], "count": int(count)}
                    for value, count in counts.head(10).items()
                ],
                "rare_category_count": int((counts <= rare_threshold).sum()),
                "total_categories": int(len(counts.index)),
                "frequencies_limited": len(counts.index) > 10,
            }

    return {
        "unique_values": unique_analysis,
        "numeric_analysis": numeric_analysis,
        "categorical_analysis": categorical_analysis,
        "mixed_type_issues": mixed_type_issues,
        "automatic_issues": automatic_issues,
    }


def _number(value: Any) -> float | None:
    result = float(value)
    return round(result, 6) if pd.notna(result) else None


def _automatic(
    check: str,
    severity: str,
    message: str,
    column: str | None,
    *,
    affected_count: int = 0,
    row_count: int = 0,
) -> dict[str, Any]:
    return {
        "validation_rule_id": None,
        "category": "automatic",
        "check_name": check,
        "status": "observed",
        "severity": severity,
        "affected_count": affected_count,
        "affected_percentage": round(affected_count / row_count * 100, 4) if row_count else 0.0,
        "message": message,
        "details": {"column": column},
    }
