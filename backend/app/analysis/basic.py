from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError, ParserError


class CsvAnalysisError(ValueError):
    """Raised when a CSV cannot be safely analyzed."""


def analyze_csv(
    path: Path, *, file_size_bytes: int, max_rows: int, max_columns: int
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

    return {
        "profile": {
            "row_count": row_count,
            "column_count": int(len(frame.columns)),
            "column_names": [str(column) for column in frame.columns],
            "inferred_data_types": schema,
            "memory_estimate_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
            "file_size_bytes": file_size_bytes,
            "duplicate_row_count": int(frame.duplicated().sum()),
            "fully_empty_row_count": int(missing.all(axis=1).sum()),
            "processing_duration_ms": round((perf_counter() - started) * 1000, 2),
        },
        "missing_values": missing_by_column,
        "limitations": [
            "Type inference uses pandas and may not reflect domain-specific expectations.",
            "Duplicate analysis detects exact duplicate rows only.",
        ],
    }
