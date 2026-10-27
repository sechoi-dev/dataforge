import hashlib
import json
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

import pandas as pd


class ComparisonError(ValueError):
    """Raised when two dataset versions cannot be compared as requested."""


def compare_frames(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    selected_key_columns: list[str] | None = None,
    normalize_text: bool = False,
) -> dict[str, Any]:
    keys = selected_key_columns or []
    _validate_keys(left, right, keys)
    schema = _schema_comparison(left, right)
    missingness = _missingness_changes(left, right)
    categories = _category_changes(left, right)
    uniqueness = _uniqueness_changes(left, right)
    row_counts = _row_count_change(len(left.index), len(right.index))
    changes = [
        *schema["changes"],
        *missingness,
        *categories,
        *uniqueness,
        row_counts,
    ]
    return {
        "schema": schema,
        "profile": {
            "row_count": row_counts,
            "missingness_changes": missingness,
            "uniqueness_changes": uniqueness,
        },
        "category_changes": categories,
        "overlap": {
            "exact_rows": _exact_overlap(left, right, normalize_text=normalize_text),
            "selected_keys": _key_overlap(left, right, keys, normalize_text=normalize_text)
            if keys
            else None,
        },
        "changes": changes,
        "severity_summary": {
            severity: sum(change["severity"] == severity for change in changes)
            for severity in ("critical", "warning", "info")
        },
        "limitations": [
            "Renamed columns are heuristic suggestions based on name similarity and data type.",
            "Category details are capped at 100 added and 100 removed values per column.",
            "Text normalization trims whitespace and applies Unicode-aware lowercase conversion.",
        ],
    }


def _schema_comparison(left: pd.DataFrame, right: pd.DataFrame) -> dict[str, Any]:
    left_columns = {str(column): str(dtype) for column, dtype in left.dtypes.items()}
    right_columns = {str(column): str(dtype) for column, dtype in right.dtypes.items()}
    added = sorted(right_columns.keys() - left_columns.keys())
    removed = sorted(left_columns.keys() - right_columns.keys())
    type_changes = [
        {"column": column, "left": left_columns[column], "right": right_columns[column]}
        for column in sorted(left_columns.keys() & right_columns.keys())
        if left_columns[column] != right_columns[column]
    ]
    renamed = _renamed_candidates(removed, added, left_columns, right_columns)
    changes = [
        _change("column_added", "info", f"Column '{column}' was added.", column=column)
        for column in added
    ]
    changes.extend(
        _change("column_removed", "critical", f"Column '{column}' was removed.", column=column)
        for column in removed
    )
    changes.extend(
        _change(
            "data_type_changed",
            "critical",
            f"Column '{item['column']}' changed from {item['left']} to {item['right']}.",
            column=str(item["column"]),
        )
        for item in type_changes
    )
    changes.extend(
        _change(
            "possible_rename",
            "info",
            f"Removed column '{item['from']}' may have been renamed to '{item['to']}'.",
        )
        for item in renamed
    )
    return {
        "added_columns": added,
        "removed_columns": removed,
        "type_changes": type_changes,
        "possible_renames": renamed,
        "changes": changes,
    }


def _renamed_candidates(
    removed: list[str],
    added: list[str],
    left_types: dict[str, str],
    right_types: dict[str, str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    used: set[str] = set()
    for old in removed:
        matches = [
            (SequenceMatcher(None, old.lower(), new.lower()).ratio(), new)
            for new in added
            if new not in used and left_types[old] == right_types[new]
        ]
        if not matches:
            continue
        similarity, new = max(matches)
        if similarity >= 0.6:
            candidates.append({"from": old, "to": new, "similarity": round(similarity, 3)})
            used.add(new)
    return candidates


def _missingness_changes(left: pd.DataFrame, right: pd.DataFrame) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for column in sorted(set(left.columns) & set(right.columns)):
        left_percentage = float(left[column].isna().mean() * 100) if len(left.index) else 0.0
        right_percentage = float(right[column].isna().mean() * 100) if len(right.index) else 0.0
        delta = right_percentage - left_percentage
        if abs(delta) < 0.0001:
            continue
        severity = "critical" if delta >= 25 else "warning" if delta >= 5 else "info"
        changes.append(
            _change(
                "missingness_changed",
                severity,
                f"Column '{column}' missingness changed by {delta:+.2f} percentage points.",
                column=str(column),
                left_percentage=round(left_percentage, 4),
                right_percentage=round(right_percentage, 4),
                delta_percentage_points=round(delta, 4),
            )
        )
    return changes


def _category_changes(left: pd.DataFrame, right: pd.DataFrame) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for column in sorted(set(left.columns) & set(right.columns)):
        if pd.api.types.is_numeric_dtype(left[column]) and pd.api.types.is_numeric_dtype(
            right[column]
        ):
            continue
        left_values = set(left[column].dropna().astype(str))
        right_values = set(right[column].dropna().astype(str))
        added = sorted(right_values - left_values)
        removed = sorted(left_values - right_values)
        if not added and not removed:
            continue
        severity = "warning" if removed else "info"
        changes.append(
            _change(
                "category_set_changed",
                severity,
                f"Column '{column}' has {len(added)} added and {len(removed)} removed categories.",
                column=str(column),
                added_values=added[:100],
                removed_values=removed[:100],
                details_limited=len(added) > 100 or len(removed) > 100,
            )
        )
    return changes


def _uniqueness_changes(left: pd.DataFrame, right: pd.DataFrame) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for column in sorted(set(left.columns) & set(right.columns)):
        left_non_null = left[column].dropna()
        right_non_null = right[column].dropna()
        left_ratio = left_non_null.nunique() / len(left_non_null.index) if len(left_non_null) else 0
        right_ratio = (
            right_non_null.nunique() / len(right_non_null.index) if len(right_non_null) else 0
        )
        if abs(right_ratio - left_ratio) < 0.05:
            continue
        changes.append(
            _change(
                "uniqueness_changed",
                "warning" if right_ratio < left_ratio else "info",
                f"Column '{column}' uniqueness changed from {left_ratio:.2%} to {right_ratio:.2%}.",
                column=str(column),
                left_ratio=round(left_ratio, 4),
                right_ratio=round(right_ratio, 4),
            )
        )
    return changes


def _row_count_change(left_count: int, right_count: int) -> dict[str, Any]:
    percentage = (right_count - left_count) / left_count * 100 if left_count else None
    magnitude = abs(percentage) if percentage is not None else 100.0
    severity = "critical" if magnitude >= 100 else "warning" if magnitude >= 25 else "info"
    return _change(
        "row_count_changed",
        severity,
        f"Row count changed from {left_count} to {right_count}.",
        left_count=left_count,
        right_count=right_count,
        percentage_change=round(percentage, 4) if percentage is not None else None,
    )


def _exact_overlap(
    left: pd.DataFrame, right: pd.DataFrame, *, normalize_text: bool
) -> dict[str, Any]:
    left_columns = list(map(str, left.columns))
    if set(left_columns) != set(map(str, right.columns)):
        return _overlap_result(0, len(left.index), len(right.index), comparable=False)
    return _counter_overlap(
        _row_hashes(left, left_columns, normalize_text),
        _row_hashes(right, left_columns, normalize_text),
        len(left.index),
        len(right.index),
    )


def _key_overlap(
    left: pd.DataFrame,
    right: pd.DataFrame,
    keys: list[str],
    *,
    normalize_text: bool,
) -> dict[str, Any]:
    left_complete = left.dropna(subset=keys)
    right_complete = right.dropna(subset=keys)
    result = _counter_overlap(
        _row_hashes(left_complete, keys, normalize_text),
        _row_hashes(right_complete, keys, normalize_text),
        len(left_complete.index),
        len(right_complete.index),
    )
    result["columns"] = keys
    result["excluded_null_key_rows"] = {
        "left": len(left.index) - len(left_complete.index),
        "right": len(right.index) - len(right_complete.index),
    }
    return result


def _row_hashes(frame: pd.DataFrame, columns: list[Any], normalize_text: bool) -> Counter[str]:
    hashes: Counter[str] = Counter()
    for values in frame[columns].itertuples(index=False, name=None):
        normalized = [_normalize(value, normalize_text) for value in values]
        encoded = json.dumps(normalized, separators=(",", ":")).encode()
        hashes[hashlib.sha256(encoded).hexdigest()] += 1
    return hashes


def _normalize(value: Any, normalize_text: bool) -> tuple[str, str]:
    if pd.isna(value):
        return ("null", "")
    text = str(value)
    return ("value", text.strip().casefold() if normalize_text else text)


def _counter_overlap(
    left: Counter[str], right: Counter[str], left_count: int, right_count: int
) -> dict[str, Any]:
    count = sum((left & right).values())
    return _overlap_result(count, left_count, right_count, comparable=True)


def _overlap_result(
    count: int, left_count: int, right_count: int, *, comparable: bool
) -> dict[str, Any]:
    return {
        "comparable": comparable,
        "overlapping_row_count": count,
        "left_percentage": round(count / left_count * 100, 4) if left_count else 0.0,
        "right_percentage": round(count / right_count * 100, 4) if right_count else 0.0,
    }


def _validate_keys(left: pd.DataFrame, right: pd.DataFrame, keys: list[str]) -> None:
    missing_left = sorted(set(keys) - set(map(str, left.columns)))
    missing_right = sorted(set(keys) - set(map(str, right.columns)))
    if missing_left or missing_right:
        raise ComparisonError(
            f"Selected keys must exist in both versions; missing left={missing_left}, "
            f"missing right={missing_right}."
        )


def _change(change_type: str, severity: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "type": change_type,
        "severity": severity,
        "message": message,
        "details": details,
    }
