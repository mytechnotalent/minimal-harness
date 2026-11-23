"""Comparative analysis and report emission for eval runs."""

from __future__ import annotations

import json
import math
from typing import Any

WILSON_Z = 1.959963984540054


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize one configuration's run records.

    Parameters
    ----------
    records : list[dict[str, Any]]
        Scored run records.

    Returns
    -------
    dict[str, Any]
        Headline numbers for the configuration.
    """
    result = _head_summary(records)
    result["errors"] = sum(1 for record in records if record.get("error"))
    result["mean_elapsed"] = _mean(records, "elapsed")
    result["prompt_tokens"] = _sum(records, "prompt_tokens")
    result["completion_tokens"] = _sum(records, "completion_tokens")
    result["cost"] = round(_sum(records, "cost"), 6)
    return result


def _head_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute case, pass, and accuracy headline numbers.

    Parameters
    ----------
    records : list[dict[str, Any]]
        Scored run records.

    Returns
    -------
    dict[str, Any]
        Case, pass, and accuracy values.
    """
    scored = [record for record in records if "score" in record]
    passed = sum(1 for record in scored if record["score"])
    return {
        "cases": len(records),
        "passed": passed,
        "accuracy": _accuracy(passed, len(scored)),
    }


def _accuracy(passed: int, total: int) -> float:
    """Return zero-guarded accuracy.

    Parameters
    ----------
    passed : int
        Passing count.
    total : int
        Scored count.

    Returns
    -------
    float
        Fraction passing.
    """
    return passed / total if total else 0.0


def _mean(records: list[dict[str, Any]], key: str) -> float:
    """Average one numeric field over records.

    Parameters
    ----------
    records : list[dict[str, Any]]
        Run records.
    key : str
        Numeric field name.

    Returns
    -------
    float
        Rounded mean, zero when empty.
    """
    values = [float(record.get(key, 0.0)) for record in records]
    return round(sum(values) / len(values), 3) if values else 0.0


def _sum(records: list[dict[str, Any]], key: str) -> float:
    """Sum one numeric field over records.

    Parameters
    ----------
    records : list[dict[str, Any]]
        Run records.
    key : str
        Numeric field name.

    Returns
    -------
    float
        Field total.
    """
    return sum(float(record.get(key, 0.0)) for record in records)


def compare(
    baseline: list[dict[str, Any]], harness: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare paired baseline and harness runs.

    Parameters
    ----------
    baseline : list[dict[str, Any]]
        Baseline run records.
    harness : list[dict[str, Any]]
        Harness run records.

    Returns
    -------
    dict[str, Any]
        Summaries, per-case rows, and headline deltas.
    """
    base = summary(baseline)
    ring = summary(harness)
    rows = [pair_row(b, h) for b, h in zip(baseline, harness)]
    result = {"baseline": base, "harness": ring, "rows": rows}
    result["deltas"] = _deltas(base, ring)
    return result


def pair_row(
    baseline: dict[str, Any], harness: dict[str, Any]
) -> dict[str, Any]:
    """Build one per-case comparison row.

    Parameters
    ----------
    baseline : dict[str, Any]
        Baseline record.
    harness : dict[str, Any]
        Harness record.

    Returns
    -------
    dict[str, Any]
        Case id, both scores, and an outcome label.
    """
    base_score = baseline.get("score", False)
    ring_score = harness.get("score", False)
    return {
        "case_id": baseline.get("case_id", harness.get("case_id", "")),
        "baseline": base_score,
        "harness": ring_score,
        "outcome": _outcome(base_score, ring_score),
    }


def _outcome(base_score: bool, ring_score: bool) -> str:
    """Label a paired outcome.

    Parameters
    ----------
    base_score : bool
        Baseline pass.
    ring_score : bool
        Harness pass.

    Returns
    -------
    str
        Outcome label.
    """
    if base_score and ring_score:
        return "both_pass"
    if ring_score:
        return "harness_only"
    if base_score:
        return "baseline_only"
    return "both_fail"


def _deltas(base: dict[str, Any], ring: dict[str, Any]) -> dict[str, Any]:
    """Compute headline deltas between two summaries.

    Parameters
    ----------
    base : dict[str, Any]
        Baseline summary.
    ring : dict[str, Any]
        Harness summary.

    Returns
    -------
    dict[str, Any]
        Accuracy, error, and overhead deltas.
    """
    points = ring["accuracy"] - base["accuracy"]
    percent = 100.0 * points / base["accuracy"] if base["accuracy"] else 0.0
    core = {
        "absolute": round(points, 4),
        "relative_percent": round(percent, 2),
        "error_reduction": base["errors"] - ring["errors"],
    }
    return {**core, **_overhead_deltas(base, ring)}


def _overhead_deltas(
    base: dict[str, Any], ring: dict[str, Any]
) -> dict[str, Any]:
    """Compute time, token, and cost overhead deltas.

    Parameters
    ----------
    base : dict[str, Any]
        Baseline summary.
    ring : dict[str, Any]
        Harness summary.

    Returns
    -------
    dict[str, Any]
        Overhead deltas.
    """
    elapsed = round(ring["mean_elapsed"] - base["mean_elapsed"], 3)
    tokens = ring["prompt_tokens"] + ring["completion_tokens"]
    tokens -= base["prompt_tokens"] + base["completion_tokens"]
    return {
        "elapsed_overhead": elapsed,
        "token_overhead": tokens,
        "cost_delta": round(ring["cost"] - base["cost"], 6),
    }


def repeat_stats(runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Aggregate repeat runs with a Wilson interval on pass rates.

    Parameters
    ----------
    runs : list[list[dict[str, Any]]]
        One record list per repeat.

    Returns
    -------
    dict[str, Any]
        Per-case fraction statistics and a pooled Wilson bound.
    """
    fractions = _per_case_fractions(runs)
    pooled = [fraction for fraction in fractions.values()]
    return {
        "runs": len(runs),
        "cases": len(fractions),
        "mean": round(sum(pooled) / len(pooled), 4) if pooled else 0.0,
        "wilson_low": wilson(sum(pooled), len(pooled)) if pooled else 0.0,
    }


def _per_case_fractions(runs: list[list[dict[str, Any]]]) -> dict[str, float]:
    """Average each case's pass outcome across repeat runs.

    Parameters
    ----------
    runs : list[list[dict[str, Any]]]
        One record list per repeat.

    Returns
    -------
    dict[str, float]
        Case id to mean pass fraction.
    """
    totals: dict[str, list[float]] = {}
    for run in runs:
        for record in run:
            key = str(record.get("case_id", ""))
            totals.setdefault(key, []).append(
                1.0 if record.get("score") else 0.0
            )
    return {key: sum(values) / len(values) for key, values in totals.items()}


def wilson(passed: float, total: int) -> float:
    """Return the lower Wilson bound of a pass rate.

    Parameters
    ----------
    passed : float
        Passing count.
    total : int
        Sample count.

    Returns
    -------
    float
        Lower 95 percent confidence bound.
    """
    if not total:
        return 0.0
    return _wilson_low(passed, total)


def _wilson_low(passed: float, total: int) -> float:
    """Compute the interval bound for a positive total.

    Parameters
    ----------
    passed : float
        Passing count.
    total : int
        Sample count.

    Returns
    -------
    float
        Lower Wilson bound.
    """
    z = WILSON_Z
    phat = passed / total
    denominator = 1.0 + z * z / total
    center = phat + z * z / (2.0 * total)
    variance = phat * (1.0 - phat) / total
    margin = z * math.sqrt(variance + z * z / (4.0 * total * total))
    return (center - margin) / denominator


def markdown_report(
    comparison: dict[str, Any], notes: dict[str, Any] | None = None
) -> str:
    """Render the comparison as a markdown document.

    Parameters
    ----------
    comparison : dict[str, Any]
        Comparison payload.
    notes : dict[str, Any] or None
        Optional configuration notes.

    Returns
    -------
    str
        Markdown report.
    """
    base = comparison["baseline"]
    ring = comparison["harness"]
    deltas = comparison["deltas"]
    parts = [_report_head(comparison, notes), _summary_table(base, ring)]
    parts.extend([_delta_table(deltas), _rows_table(comparison["rows"])])
    return "\n\n".join(parts)


def _report_head(
    comparison: dict[str, Any], notes: dict[str, Any] | None
) -> str:
    """Render the report title and configuration block.

    Parameters
    ----------
    comparison : dict[str, Any]
        Comparison payload.
    notes : dict[str, Any] or None
        Optional configuration notes.

    Returns
    -------
    str
        Head block.
    """
    base = comparison["baseline"]
    ring = comparison["harness"]
    lines = ["# Comparative Evaluation Report"]
    lines.append(f"Baseline accuracy: {_pct(base['accuracy'])}")
    lines.append(f"Harness accuracy: {_pct(ring['accuracy'])}")
    if notes:
        lines.extend(_note_lines(notes))
    return "\n".join(lines)


def _note_lines(notes: dict[str, Any]) -> list[str]:
    """Render configuration notes as markdown bullets.

    Parameters
    ----------
    notes : dict[str, Any]
        Configuration notes.

    Returns
    -------
    list[str]
        Bullet lines.
    """
    lines = ["## Configuration"]
    lines.extend(f"- {key}: {value}" for key, value in sorted(notes.items()))
    return lines


def _summary_table(base: dict[str, Any], ring: dict[str, Any]) -> str:
    """Render the headline summary table.

    Parameters
    ----------
    base : dict[str, Any]
        Baseline summary.
    ring : dict[str, Any]
        Harness summary.

    Returns
    -------
    str
        Markdown table.
    """
    rows = [_metric_row("cases", base, ring)]
    rows.append(_metric_row("passed", base, ring))
    rows.append(_metric_row("accuracy", base, ring, percent=True))
    rows.append(_metric_row("errors", base, ring))
    rows.append(_metric_row("mean_elapsed", base, ring))
    rows.append(_metric_row("cost", base, ring))
    return _table("Summary", ["metric", "baseline", "harness"], rows)


def _metric_row(
    name: str,
    base: dict[str, Any],
    ring: dict[str, Any],
    percent: bool = False,
) -> tuple:
    """Format one summary row with optional percentage rendering.

    Parameters
    ----------
    name : str
        Metric name.
    base : dict[str, Any]
        Baseline summary.
    ring : dict[str, Any]
        Harness summary.
    percent : bool
        Render values as percentages.

    Returns
    -------
    tuple
        Row of three cells.
    """
    left = _pct(base[name]) if percent else base[name]
    right = _pct(ring[name]) if percent else ring[name]
    return (name, left, right)


def _delta_table(deltas: dict[str, Any]) -> str:
    """Render the delta table.

    Parameters
    ----------
    deltas : dict[str, Any]
        Headline deltas.

    Returns
    -------
    str
        Markdown table.
    """
    first = ["absolute", "relative_percent", "error_reduction"]
    second = ["elapsed_overhead", "token_overhead", "cost_delta"]
    rows = [(name, deltas.get(name)) for name in first + second]
    return _table("Deltas (harness minus baseline)", ["metric", "value"], rows)


def _rows_table(rows: list[dict[str, Any]]) -> str:
    """Render the per-case outcome table.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Per-case comparison rows.

    Returns
    -------
    str
        Markdown table.
    """
    rendered = []
    for row in rows:
        rendered.append(_row_cells(row))
    return _table(
        "Per-case outcomes",
        ["case", "baseline", "harness", "outcome"],
        rendered,
    )


def _row_cells(row: dict[str, Any]) -> tuple:
    """Format one per-case row.

    Parameters
    ----------
    row : dict[str, Any]
        Per-case comparison row.

    Returns
    -------
    tuple
        Four cell values.
    """
    return (
        row["case_id"],
        _tick(row["baseline"]),
        _tick(row["harness"]),
        row["outcome"],
    )


def _table(title: str, headers: list[str], rows: list[tuple]) -> str:
    """Render a markdown table from rows of values.

    Parameters
    ----------
    title : str
        Section title.
    headers : list[str]
        Column names.
    rows : list[tuple]
        Cell values per row.

    Returns
    -------
    str
        Markdown table block.
    """
    head = "| " + " | ".join(headers) + " |"
    rule = "|" + "---|" * len(headers)
    lines = [f"## {title}", "", head, rule]
    lines.extend(
        "| " + " | ".join(str(cell) for cell in row) + " |" for row in rows
    )
    return "\n".join(lines)


def _pct(value: float) -> str:
    """Format a fraction as a percentage string.

    Parameters
    ----------
    value : float
        Fraction.

    Returns
    -------
    str
        Percentage with two decimals.
    """
    return f"{100.0 * value:.2f}%"


def _tick(value: Any) -> str:
    """Render a boolean as pass or fail.

    Parameters
    ----------
    value : Any
        Boolean-ish value.

    Returns
    -------
    str
        Pass or fail label.
    """
    return "pass" if value else "fail"


def json_report(
    comparison: dict[str, Any], notes: dict[str, Any] | None = None
) -> str:
    """Serialize a comparison to pretty JSON.

    Parameters
    ----------
    comparison : dict[str, Any]
        Comparison payload.
    notes : dict[str, Any] or None
        Optional configuration notes.

    Returns
    -------
    str
        Pretty JSON text.
    """
    payload = {"notes": notes or {}, "comparison": comparison}
    return json.dumps(payload, indent=2, default=str)
