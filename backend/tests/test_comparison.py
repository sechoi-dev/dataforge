import pandas as pd

from app.analysis.comparison import compare_frames


def test_comparison_detects_drift_and_classifies_changes() -> None:
    left = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "status": ["active", "active", "inactive"],
            "legacy": [10, 20, 30],
        }
    )
    right = pd.DataFrame(
        {
            "id": [1, 2, 4, 5],
            "status": ["active", None, "pending", "pending"],
            "new_value": [10, 20, 40, 50],
        }
    )

    report = compare_frames(left, right, selected_key_columns=["id"])

    assert report["schema"]["added_columns"] == ["new_value"]
    assert report["schema"]["removed_columns"] == ["legacy"]
    assert report["profile"]["row_count"]["details"]["right_count"] == 4
    assert report["category_changes"][0]["details"]["added_values"] == ["pending"]
    assert report["overlap"]["exact_rows"]["comparable"] is False
    assert report["overlap"]["selected_keys"]["overlapping_row_count"] == 2
    assert report["severity_summary"]["critical"] >= 1
    assert all(change["message"] for change in report["changes"])


def test_exact_overlap_is_duplicate_aware_and_can_normalize_text() -> None:
    left = pd.DataFrame({"id": [1, 1, 2], "name": [" Ada ", " Ada ", "Bob"]})
    right = pd.DataFrame({"name": ["ada", "ada", "ada"], "id": [1, 1, 1]})

    report = compare_frames(left, right, normalize_text=True)

    overlap = report["overlap"]["exact_rows"]
    assert overlap["comparable"] is True
    assert overlap["overlapping_row_count"] == 2
    assert overlap["left_percentage"] == 66.6667
