import json
from html import escape
from typing import Any


def build_html_report(report: dict[str, Any]) -> bytes:
    profile = report["profile"]
    score = report["quality_score"]
    issues = [*report["automatic_issues"], *report["validation_rule_results"]]
    sections = [
        _heading(report, score),
        _overview(profile),
        _scorecard(score),
        _issues(issues),
        _missing(report["missing_values"]),
        _details("Numeric analysis", report["numeric_analysis"]),
        _details("Categorical analysis", report["categorical_analysis"]),
        _list_section("Recommendations", report["recommendations"]),
        _list_section("Limitations", report["limitations"]),
    ]
    body = "".join(sections)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>DataForge quality report</title><style>"
        "body{font:15px system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;"
        "color:#17202a}h1,h2{color:#12344d}table{border-collapse:collapse;width:100%;"
        "margin:12px 0 28px}th,td{border:1px solid #d8dee4;padding:8px;text-align:left;"
        "vertical-align:top}th{background:#f4f7f9}.score{font-size:2.2rem;font-weight:700}"
        ".critical{color:#a40e26}.warning{color:#8a5700}.info{color:#0969da}"
        "code{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#57606a}</style></head>"
        f"<body>{body}</body></html>"
    ).encode()


def _heading(report: dict[str, Any], score: dict[str, Any]) -> str:
    source = report["source"]
    return (
        "<header><h1>DataForge quality report</h1>"
        f"<p><strong>{escape(str(source['filename']))}</strong> &middot; version "
        f"{escape(str(report['version_number']))}</p>"
        f"<p class='score'>{escape(str(score['overall_score']))} / 100</p>"
        f"<small>{escape(str(score['disclaimer']))}</small></header>"
    )


def _overview(profile: dict[str, Any]) -> str:
    rows = {
        "Rows": profile["row_count"],
        "Columns": profile["column_count"],
        "Duplicate rows": profile["duplicate_row_count"],
        "Fully empty rows": profile["fully_empty_row_count"],
        "Processing time (ms)": profile["processing_duration_ms"],
    }
    return "<h2>Overview</h2>" + _mapping_table(rows)


def _scorecard(score: dict[str, Any]) -> str:
    score_rows = "".join(
        f"<tr><td>{escape(name.replace('_', ' ').title())}</td><td>{value}</td>"
        f"<td>{score['weights'][name] * 100:.0f}%</td></tr>"
        for name, value in score["category_scores"].items()
    )
    deductions = (
        "".join(
            f"<tr><td>{escape(str(item['category']))}</td><td>{item['points']}</td>"
            f"<td class='{escape(str(item['severity']))}'>{escape(str(item['severity']))}</td>"
            f"<td>{escape(str(item['reason']))}</td></tr>"
            for item in score["deductions"]
        )
        or "<tr><td colspan='4'>No score deductions.</td></tr>"
    )
    return (
        "<h2>Quality score</h2><table><thead><tr><th>Category</th><th>Score</th>"
        f"<th>Weight</th></tr></thead><tbody>{score_rows}</tbody></table>"
        "<h2>Score deductions</h2><table><thead><tr><th>Category</th><th>Points</th>"
        f"<th>Severity</th><th>Reason</th></tr></thead><tbody>{deductions}</tbody></table>"
    )


def _issues(issues: list[dict[str, Any]]) -> str:
    rows = (
        "".join(
            f"<tr><td>{escape(str(item['check_name']))}</td><td>{escape(str(item['status']))}</td>"
            f"<td class='{escape(str(item['severity']))}'>{escape(str(item['severity']))}</td>"
            f"<td>{item['affected_count']} ({item['affected_percentage']}%)</td>"
            f"<td>{escape(str(item['message']))}</td></tr>"
            for item in issues
        )
        or "<tr><td colspan='5'>No issues or custom-rule results.</td></tr>"
    )
    return (
        "<h2>Issues and validation results</h2><table><thead><tr><th>Check</th>"
        "<th>Status</th><th>Severity</th><th>Affected</th><th>Explanation</th></tr>"
        f"</thead><tbody>{rows}</tbody></table>"
    )


def _missing(values: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{escape(column)}</td><td>{item['missing_count']}</td>"
        f"<td>{item['missing_percentage']}%</td></tr>"
        for column, item in values.items()
    )
    return (
        "<h2>Missing values</h2><table><thead><tr><th>Column</th><th>Count</th>"
        f"<th>Percentage</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _details(title: str, values: dict[str, Any]) -> str:
    rows = (
        "".join(
            f"<tr><td>{escape(column)}</td><td><code>{escape(json.dumps(detail, sort_keys=True))}"
            "</code></td></tr>"
            for column, detail in values.items()
        )
        or "<tr><td colspan='2'>None.</td></tr>"
    )
    return f"<h2>{escape(title)}</h2><table><tbody>{rows}</tbody></table>"


def _list_section(title: str, values: list[str]) -> str:
    items = "".join(f"<li>{escape(value)}</li>" for value in values)
    return f"<h2>{escape(title)}</h2><ul>{items}</ul>"


def _mapping_table(values: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><th>{escape(name)}</th><td>{escape(str(value))}</td></tr>"
        for name, value in values.items()
    )
    return f"<table><tbody>{rows}</tbody></table>"
