"""Calibrate reviewer verdicts against gate-2 outcomes."""

import argparse
import json
from pathlib import Path
from typing import Any


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load JSONL review records.

    Parameters
    ----------
    path : pathlib.Path
        JSONL file with ``review`` and ``truth`` booleans.

    Returns
    -------
    list of dict
        Decoded non-empty records.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute confusion counts and rates.

    Parameters
    ----------
    records : list of dict
        Records with ``review`` and ``truth`` booleans.

    Returns
    -------
    dict
        Counts, precision, recall, false-positive rate, and accuracy.
    """
    counts = _counts(records)
    return {**counts, **_rates(counts)}


def _counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """Count reviewer outcomes into a confusion matrix.

    Parameters
    ----------
    records : list of dict
        Records with ``review`` and ``truth`` booleans.

    Returns
    -------
    dict[str, int]
        True-positive, false-positive, true-negative, and false-negative.
    """
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for record in records:
        counts[_cell(record)] += 1
    return counts


def _cell(record: dict[str, Any]) -> str:
    """Return the confusion cell for one record.

    Parameters
    ----------
    record : dict
        Record with ``review`` and ``truth`` booleans.

    Returns
    -------
    str
        One of ``tp``, ``fp``, ``tn``, or ``fn``.
    """
    review = bool(record.get("review"))
    truth = bool(record.get("truth"))
    if review:
        return "tp" if truth else "fp"
    return "fn" if truth else "tn"


def _rates(counts: dict[str, int]) -> dict[str, float]:
    """Compute rates from a confusion matrix.

    Parameters
    ----------
    counts : dict[str, int]
        Confusion counts.

    Returns
    -------
    dict[str, float]
        Precision, recall, false-positive rate, and accuracy.
    """
    total = sum(counts.values())
    tp, fp, tn, fn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
    return {
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "false_positive_rate": _ratio(fp, fp + tn),
        "accuracy": _ratio(tp + tn, total),
    }


def _ratio(numerator: int, denominator: int) -> float:
    """Return a safe ratio.

    Parameters
    ----------
    numerator : int
        Top value.
    denominator : int
        Bottom value.

    Returns
    -------
    float
        Ratio, or zero when the denominator is zero.
    """
    if denominator == 0:
        return 0.0
    return numerator / denominator


def main() -> None:
    """Print the calibration summary for one JSONL file.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The summary is printed as JSON.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    summary = summarize(load_records(args.path))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
