import uuid
from pathlib import Path
from typing import cast

import pandas as pd

from app.analysis.basic import analyze_csv
from app.analysis.rules import RuleSpec, evaluate_rules
from app.db.models import DatasetVersion, RuleType, Severity
from app.services.reporting import build_html_report
from app.workers.tasks import build_report


def rule(
    rule_type: RuleType,
    *,
    column: str | None = None,
    parameters: dict[str, object] | None = None,
    severity: Severity = Severity.WARNING,
) -> RuleSpec:
    return RuleSpec(uuid.uuid4(), column, rule_type, parameters or {}, severity)


def test_rich_profile_finds_summaries_mixed_types_and_iqr_outliers(tmp_path: Path) -> None:
    csv_path = tmp_path / "quality.csv"
    csv_path.write_text(
        "amount,code,status\n1,100,active\n2,ABC,active\n3,200,inactive\n1000,XYZ,active\n",
        encoding="utf-8",
    )

    analysis = analyze_csv(
        csv_path,
        file_size_bytes=csv_path.stat().st_size,
        max_rows=100,
        max_columns=10,
    )

    assert analysis["numeric_analysis"]["amount"]["median"] == 2.5
    assert analysis["numeric_analysis"]["amount"]["outlier_count"] == 1
    assert analysis["categorical_analysis"]["status"]["total_categories"] == 2
    assert analysis["mixed_type_issues"][0]["column"] == "code"
    issue_counts = {
        issue["check_name"]: issue["affected_count"] for issue in analysis["automatic_issues"]
    }
    assert issue_counts == {"numeric_outliers": 1, "mixed_type": 2}
    assert analysis["quality_score"]["category_scores"]["consistency"] < 100
    assert analysis["quality_score"]["deductions"]


def test_custom_rules_return_explainable_failures() -> None:
    frame = pd.DataFrame(
        {
            "email": ["ada@example.com", None, "invalid"],
            "age": [20, 150, "unknown"],
            "status": ["active", "unknown", "inactive"],
        }
    )
    rules = [
        rule(RuleType.NOT_NULL, column="email", severity=Severity.CRITICAL),
        rule(RuleType.REGEX, column="email", parameters={"pattern": r"[^@]+@[^@]+"}),
        rule(RuleType.RANGE, column="age", parameters={"minimum": 0, "maximum": 120}),
        rule(
            RuleType.ALLOWED_VALUES,
            column="status",
            parameters={"values": ["active", "inactive"]},
        ),
        rule(RuleType.MINIMUM_ROW_COUNT, parameters={"value": 5}),
    ]

    results = evaluate_rules(frame, rules)

    assert [result["affected_count"] for result in results] == [1, 1, 2, 1, 2]
    assert all(result["status"] == "failed" for result in results)
    assert results[0]["severity"] == "critical"
    assert results[1]["details"]["sample_offending_values"] == ["invalid"]


def test_html_report_escapes_uploaded_content(tmp_path: Path) -> None:
    csv_path = tmp_path / "unsafe.csv"
    csv_path.write_text("name\n<script>alert(1)</script>\n", encoding="utf-8")
    analysis = analyze_csv(
        csv_path,
        file_size_bytes=csv_path.stat().st_size,
        max_rows=100,
        max_columns=10,
    )

    class Version:
        dataset_id = uuid.uuid4()
        id = uuid.uuid4()
        version_number = 1
        original_filename = "<unsafe>.csv"
        file_size_bytes = csv_path.stat().st_size
        file_sha256 = "0" * 64

    html = build_html_report(build_report(cast(DatasetVersion, Version()), analysis)).decode()

    assert "DataForge quality report" in html
    assert "&lt;unsafe&gt;.csv" in html
    assert "<unsafe>.csv" not in html
    assert "Score deductions" in html
