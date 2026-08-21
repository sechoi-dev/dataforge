from pathlib import Path

import pytest

from app.analysis.basic import CsvAnalysisError, analyze_csv


def test_analyze_csv_profiles_missing_and_duplicate_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("id,name,score\n1,Ada,10\n2,,20\n2,,20\n", encoding="utf-8")

    report = analyze_csv(
        csv_path,
        file_size_bytes=csv_path.stat().st_size,
        max_rows=100,
        max_columns=10,
    )

    assert report["profile"]["row_count"] == 3
    assert report["profile"]["column_count"] == 3
    assert report["profile"]["duplicate_row_count"] == 1
    assert report["missing_values"]["name"] == {
        "missing_count": 2,
        "missing_percentage": pytest.approx(66.6667),
    }


def test_analyze_csv_rejects_row_limit(tmp_path: Path) -> None:
    csv_path = tmp_path / "large.csv"
    csv_path.write_text("id\n1\n2\n", encoding="utf-8")

    with pytest.raises(CsvAnalysisError, match="row limit"):
        analyze_csv(csv_path, file_size_bytes=8, max_rows=1, max_columns=10)
