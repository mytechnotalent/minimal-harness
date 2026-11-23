"""Benchmark case schema, deterministic scoring, and file loaders."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

KINDS = ("reasoning", "instruction", "tool", "qa", "error", "context")
SCORERS = ("contains", "exact", "regex", "numeric", "tool_call")


@dataclass
class Case:
    """One scored benchmark item shared by both runner configurations."""

    id: str
    kind: str
    prompt: str
    expected: Any = None
    scorer: str = "contains"
    tools: list[str] | None = None
    system: str = ""
    tolerance: float = 1e-6
    schemas: list[dict[str, Any]] | None = None


def load_cases(path: Path | str) -> list[Case]:
    """Load and validate cases from a JSON or JSONL file.

    Parameters
    ----------
    path : pathlib.Path or str
        Case file path ending in .json or .jsonl.

    Returns
    -------
    list[Case]
        Validated cases in file order.

    Raises
    ------
    ValueError
        When a record is invalid or the suffix is unsupported.
    """
    records = _read_records(Path(path))
    problems = []
    for index, raw in enumerate(records, 1):
        problems.extend(_record_problems(raw, index))
    if problems:
        raise ValueError("; ".join(problems))
    return [build_case(raw) for raw in records]


def _record_problems(raw: dict[str, Any], index: int) -> list[str]:
    """Prefix validation problems with a record position.

    Parameters
    ----------
    raw : dict[str, Any]
        One parsed JSON case record.
    index : int
        One-based record position.

    Returns
    -------
    list[str]
        Prefixed problem strings.
    """
    return [f"record {index}: {issue}" for issue in validate_record(raw)]


def _read_records(path: Path) -> list[dict[str, Any]]:
    """Read records from a JSON or JSONL case file.

    Parameters
    ----------
    path : pathlib.Path
        Case file path.

    Returns
    -------
    list[dict[str, Any]]
        Parsed records.

    Raises
    ------
    ValueError
        When the suffix is unsupported.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return _jsonl_records(text)
    if path.suffix == ".json":
        return _json_records(text)
    raise ValueError(f"unsupported case file suffix: {path.suffix}")


def _jsonl_records(text: str) -> list[dict[str, Any]]:
    """Parse every non-empty JSONL line into records.

    Parameters
    ----------
    text : str
        File text.

    Returns
    -------
    list[dict[str, Any]]
        Parsed records.
    """
    kept = [line for line in text.splitlines() if line.strip()]
    return [_parse_record(line, n) for n, line in enumerate(kept, 1)]


def _json_records(text: str) -> list[dict[str, Any]]:
    """Read a top-level JSON array of case records.

    Parameters
    ----------
    text : str
        File text.

    Returns
    -------
    list[dict[str, Any]]
        Parsed records.
    """
    value = json.loads(text)
    if not isinstance(value, list):
        raise ValueError("JSON case file must contain a list of records")
    return value


def _parse_record(text: str, line: int) -> dict[str, Any]:
    """Parse one JSONL line into a record dict.

    Parameters
    ----------
    text : str
        One JSONL line.
    line : int
        Line number for error reporting.

    Returns
    -------
    dict[str, Any]
        Parsed record.
    """
    try:
        record = json.loads(text)
        return record if isinstance(record, dict) else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"record {line}: invalid JSON: {exc}") from exc


def validate_record(raw: dict[str, Any]) -> list[str]:
    """Return every problem found in one raw case record.

    Parameters
    ----------
    raw : dict[str, Any]
        One parsed JSON case record.

    Returns
    -------
    list[str]
        Human-readable validation problems, empty when valid.
    """
    issues = _field_problems(raw)
    issues.extend(_type_problems(raw))
    return issues


def _field_problems(raw: dict[str, Any]) -> list[str]:
    """Validate the required text fields of a record.

    Parameters
    ----------
    raw : dict[str, Any]
        One parsed JSON case record.

    Returns
    -------
    list[str]
        Problems with id, kind, and prompt.
    """
    issues = []
    if not str(raw.get("id", "")).strip():
        issues.append("id is required")
    if raw.get("kind") not in KINDS:
        issues.append(f"kind must be one of {sorted(KINDS)}")
    if not str(raw.get("prompt", "")).strip():
        issues.append("prompt is required")
    return issues


def _type_problems(raw: dict[str, Any]) -> list[str]:
    """Validate the scorer and tools fields of a record.

    Parameters
    ----------
    raw : dict[str, Any]
        One parsed JSON case record.

    Returns
    -------
    list[str]
        Problems with scorer and tools types.
    """
    issues = []
    if raw.get("scorer") not in SCORERS:
        issues.append(f"scorer must be one of {sorted(SCORERS)}")
    if raw.get("tools") is not None and not isinstance(raw["tools"], list):
        issues.append("tools must be a list of names or null")
    return issues


def build_case(raw: dict[str, Any]) -> Case:
    """Build a case from a raw record.

    Parameters
    ----------
    raw : dict[str, Any]
        One parsed JSON case record.

    Returns
    -------
    Case
        The benchmark case.
    """
    base = Case(str(raw["id"]), raw["kind"], raw["prompt"])
    return _filled_case(base, raw)


def _filled_case(base: Case, raw: dict[str, Any]) -> Case:
    """Fill optional case fields from a raw record.

    Parameters
    ----------
    base : Case
        Case with required fields.
    raw : dict[str, Any]
        One parsed JSON case record.

    Returns
    -------
    Case
        The complete case.
    """
    fields = _filled_fields(raw)
    return replace(base, **fields)


def _filled_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Collect optional case fields from a raw record.

    Parameters
    ----------
    raw : dict[str, Any]
        One parsed JSON case record.

    Returns
    -------
    dict[str, Any]
        Optional field values.
    """
    fields = {"expected": raw.get("expected")}
    fields["scorer"] = raw.get("scorer", "contains")
    fields["tools"] = raw.get("tools")
    fields["system"] = raw.get("system", "")
    fields["tolerance"] = float(raw.get("tolerance", 1e-6))
    fields["schemas"] = raw.get("schemas")
    return fields


def dump_cases(path: Path | str, cases: list[Case]) -> None:
    """Write cases to a JSONL file for archive and reruns.

    Parameters
    ----------
    path : pathlib.Path or str
        Destination JSONL path.
    cases : list[Case]
        Cases to persist.

    Returns
    -------
    None
        The file is written.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(case), ensure_ascii=False) for case in cases]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def score_case(
    case: Case, answer: str, tool_calls: list[dict[str, Any]] | None = None
) -> bool:
    """Score one answer against the case's deterministic criterion.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text.
    tool_calls : list[dict[str, Any]] or None
        Tool calls executed by the run.

    Returns
    -------
    bool
        Whether the answer passes.
    """
    calls = tool_calls or []
    return _score_kind(case, answer, calls)


def _score_kind(case: Case, answer: str, calls: list[dict[str, Any]]) -> bool:
    """Dispatch one scorer name.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text.
    calls : list[dict[str, Any]]
        Executed tool calls.

    Returns
    -------
    bool
        Scorer outcome.
    """
    scorer = _SCORERS.get(case.scorer, _contains_score)
    return scorer(case, answer, calls)


def _contains_score(
    case: Case, answer: str, calls: list[dict[str, Any]]
) -> bool:
    """Score a fragment-containment expectation.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text.
    calls : list[dict[str, Any]]
        Executed tool calls, unused.

    Returns
    -------
    bool
        Whether every fragment appears in the answer.
    """
    expected = case.expected
    fragments = expected if isinstance(expected, list) else [str(expected)]
    lowered = answer.lower()
    return all(str(fragment).lower() in lowered for fragment in fragments)


def _exact_score(case: Case, answer: str, calls: list[dict[str, Any]]) -> bool:
    """Score normalized exact-match equality.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text.
    calls : list[dict[str, Any]]
        Executed tool calls, unused.

    Returns
    -------
    bool
        Whether normalized texts are equal.
    """
    return _normalized(str(case.expected)) == _normalized(answer)


def _regex_score(case: Case, answer: str, calls: list[dict[str, Any]]) -> bool:
    """Score a regular-expression match.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text.
    calls : list[dict[str, Any]]
        Executed tool calls, unused.

    Returns
    -------
    bool
        Whether the pattern matches.
    """
    return (
        re.search(str(case.expected), answer, flags=re.IGNORECASE) is not None
    )


def _numeric_score(
    case: Case, answer: str, calls: list[dict[str, Any]]
) -> bool:
    """Score a numeric answer within tolerance.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text.
    calls : list[dict[str, Any]]
        Executed tool calls, unused.

    Returns
    -------
    bool
        Whether a number in the answer is within tolerance.
    """
    numbers = _numbers(answer)
    if not numbers:
        return False
    return any(
        abs(n - float(case.expected)) <= case.tolerance for n in numbers
    )


def _tool_score(case: Case, answer: str, calls: list[dict[str, Any]]) -> bool:
    """Score expected tool calls against executed calls.

    Parameters
    ----------
    case : Case
        The benchmark case.
    answer : str
        Final answer text, unused.
    calls : list[dict[str, Any]]
        Executed tool-call records.

    Returns
    -------
    bool
        Whether every expected call has a matching executed call and the
        counts match.
    """
    wanted = case.expected or []
    if len(wanted) != len(calls):
        return False
    return all(_call_matches(item, calls) for item in wanted)


def _normalized(text: str) -> str:
    """Lowercase and collapse whitespace.

    Parameters
    ----------
    text : str
        Raw text.

    Returns
    -------
    str
        Normalized text.
    """
    return " ".join(text.lower().split())


def _numbers(text: str) -> list[float]:
    """Extract every numeric literal from a text answer.

    Parameters
    ----------
    text : str
        Text to scan.

    Returns
    -------
    list[float]
        Numeric literals in order.
    """
    pattern = r"-?\d+(?:\.\d+)?"
    return [float(match) for match in re.findall(pattern, text)]


_SCORERS = {
    "contains": _contains_score,
    "exact": _exact_score,
    "regex": _regex_score,
    "numeric": _numeric_score,
    "tool_call": _tool_score,
}


def _call_matches(
    expected: dict[str, Any], calls: list[dict[str, Any]]
) -> bool:
    """Check whether one expected call was executed.

    Parameters
    ----------
    expected : dict[str, Any]
        Expected call with name and optional arguments.
    calls : list[dict[str, Any]]
        Executed tool-call records.

    Returns
    -------
    bool
        Whether a matching executed call exists.
    """
    name = str(expected.get("name", ""))
    arguments = expected.get("arguments") or {}
    for call in calls:
        if call.get("name") != name:
            continue
        if _arguments_subset(arguments, call.get("arguments") or {}):
            return True
    return False


def _arguments_subset(
    expected: dict[str, Any], actual: dict[str, Any]
) -> bool:
    """Check whether expected arguments appear in the actual ones.

    Parameters
    ----------
    expected : dict[str, Any]
        Expected argument subset.
    actual : dict[str, Any]
        Executed arguments.

    Returns
    -------
    bool
        Whether every expected value matches.
    """
    return all(actual.get(key) == value for key, value in expected.items())


def parse_arguments(raw: Any) -> dict[str, Any]:
    """Parse a tool call's JSON arguments.

    Parameters
    ----------
    raw : Any
        JSON string or already-parsed arguments.

    Returns
    -------
    dict[str, Any]
        Argument mapping, empty on failure.
    """
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def normalize_call(call: dict[str, Any]) -> dict[str, Any]:
    """Normalize one raw tool call to name and arguments.

    Parameters
    ----------
    call : dict[str, Any]
        OpenAI-shaped or already-normalized tool call.

    Returns
    -------
    dict[str, Any]
        Record with name and parsed arguments.
    """
    function = call.get("function") or {}
    name = str(function.get("name", call.get("name", "")))
    raw = function.get("arguments", call.get("arguments", {}))
    return {"name": name, "arguments": parse_arguments(raw)}
