from typing import Any


def calculate_quality_score(analysis: dict[str, Any]) -> dict[str, Any]:
    profile = analysis["profile"]
    row_count = int(profile["row_count"])
    column_count = int(profile["column_count"])
    total_cells = row_count * column_count
    total_missing = sum(
        int(item["missing_count"]) for item in analysis["missing_values"].values()
    )
    missing_percentage = total_missing / total_cells * 100 if total_cells else 0.0
    duplicate_percentage = (
        int(profile["duplicate_row_count"]) / row_count * 100 if row_count else 0.0
    )
    mixed_percentage = (
        len(analysis["mixed_type_issues"]) / column_count * 100 if column_count else 0.0
    )

    category_scores = {
        "completeness": max(0.0, 100 - missing_percentage),
        "uniqueness": max(0.0, 100 - duplicate_percentage),
        "validity": 100.0,
        "consistency": max(0.0, 100 - mixed_percentage),
        "schema_stability": 100.0,
    }
    deductions: list[dict[str, Any]] = []
    if missing_percentage:
        deductions.append(
            _deduction(
                "completeness", missing_percentage, "warning", "Missing values reduce completeness."
            )
        )
    if duplicate_percentage:
        deductions.append(
            _deduction(
                "uniqueness", duplicate_percentage, "warning", "Duplicate rows reduce uniqueness."
            )
        )
    if mixed_percentage:
        deductions.append(
            _deduction(
                "consistency",
                mixed_percentage,
                "warning",
                "Mixed apparent types reduce consistency.",
            )
        )

    severity_weights = {"critical": 0.5, "warning": 0.25, "info": 0.05}
    for result in analysis["validation_rule_results"]:
        if result["status"] != "failed":
            continue
        points = min(
            100.0,
            float(result["affected_percentage"]) * severity_weights[result["severity"]],
        )
        category_scores["validity"] = max(0.0, category_scores["validity"] - points)
        deductions.append(
            _deduction("validity", points, result["severity"], result["message"])
        )

    weights = {
        "completeness": 0.30,
        "uniqueness": 0.20,
        "validity": 0.25,
        "consistency": 0.15,
        "schema_stability": 0.10,
    }
    overall = sum(category_scores[name] * weight for name, weight in weights.items())
    return {
        "overall_score": round(overall, 2),
        "category_scores": {name: round(score, 2) for name, score in category_scores.items()},
        "weights": weights,
        "deductions": deductions,
        "disclaimer": "This score is an explainable heuristic, not objective truth.",
    }


def _deduction(category: str, points: float, severity: str, reason: str) -> dict[str, Any]:
    return {
        "category": category,
        "points": round(points, 2),
        "severity": severity,
        "reason": reason,
    }
