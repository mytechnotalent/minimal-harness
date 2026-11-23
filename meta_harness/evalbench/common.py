"""Shared helpers for the evalbench runners."""

from __future__ import annotations

import time
from typing import Any

from meta_harness.evalbench.cases import Case
from meta_harness.evalbench.cases import normalize_call
from meta_harness.evalbench.cases import score_case

FIELDS = (
    "call_count",
    "prompt_tokens",
    "completion_tokens",
    "cost",
    "model_seconds",
)


def snapshot(client: Any) -> dict[str, float]:
    """Capture a client's cumulative usage counters.

    Parameters
    ----------
    client : Any
        Model client with usage attributes.

    Returns
    -------
    dict[str, float]
        Usage values at capture time.
    """
    return {name: float(getattr(client, name, 0.0)) for name in FIELDS}


def delta(
    before: dict[str, float], after: dict[str, float]
) -> dict[str, float]:
    """Compute per-field usage differences.

    Parameters
    ----------
    before : dict[str, float]
        Usage before the case.
    after : dict[str, float]
        Usage after the case.

    Returns
    -------
    dict[str, float]
        Per-field usage deltas.
    """
    return {
        name: after.get(name, 0.0) - before.get(name, 0.0) for name in FIELDS
    }


def error_text(exc: Exception) -> str:
    """Format and bound an exception for a run record.

    Parameters
    ----------
    exc : Exception
        The failure.

    Returns
    -------
    str
        Bounded error text.
    """
    return str(exc)[:400]


def core_record(
    case: Case,
    answer: str,
    calls: list[dict[str, Any]],
    error: str,
    started: float,
) -> dict[str, Any]:
    """Build the scored record body shared by both runners.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text.
    calls : list[dict[str, Any]]
        Executed tool calls.
    error : str
        Error text, empty on success.
    started : float
        Monotonic start time.

    Returns
    -------
    dict[str, Any]
        Scored run record without usage fields.
    """
    normalized = [normalize_call(call) for call in calls]
    head = {"case_id": case.id, "kind": case.kind, "prompt": case.prompt}
    body = {"answer": answer, "tool_calls": normalized, "error": error}
    body["score"] = bool(not error and score_case(case, answer, normalized))
    body["elapsed"] = round(time.monotonic() - started, 3)
    return {**head, **body}
