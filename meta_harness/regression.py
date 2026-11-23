"""Load and evaluate permanent benchmark regression entries."""

import hashlib
import json
import re
from pathlib import Path

_CHECK_TYPES = (
    "contains",
    "not_contains",
    "regex",
    "file_exists",
    "status_in",
)
_REQUIRED = (
    "id",
    "purpose",
    "prompt_version",
    "sequence",
    "config",
    "checks",
)


def load_entry(path: Path | str) -> dict:
    """Load one regression entry from JSON.

    Parameters
    ----------
    path : pathlib.Path or str
        Entry file.

    Returns
    -------
    dict
        Parsed entry.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_entry(entry: dict) -> list[str]:
    """Return validation errors for one entry.

    Parameters
    ----------
    entry : dict
        Regression entry.

    Returns
    -------
    list of str
        Empty when the entry is usable.
    """
    errors = [f"missing {key}" for key in _REQUIRED if not entry.get(key)]
    errors.extend(_sequence_errors(entry))
    errors.extend(_check_errors(entry))
    return errors


def _sequence_errors(entry: dict) -> list[str]:
    """Return errors for the prompt sequence.

    Parameters
    ----------
    entry : dict
        Regression entry.

    Returns
    -------
    list of str
        Empty when every prompt is a non-empty string.
    """
    sequence = entry.get("sequence") or []
    if not isinstance(sequence, list):
        return ["sequence must be a list of prompts"]
    if not all(isinstance(item, str) and item.strip() for item in sequence):
        return ["sequence must contain non-empty prompt strings"]
    return []


def _check_errors(entry: dict) -> list[str]:
    """Return errors for the deterministic checks.

    Parameters
    ----------
    entry : dict
        Regression entry.

    Returns
    -------
    list of str
        One error per malformed check.
    """
    errors = []
    for index, check in enumerate(entry.get("checks") or []):
        error = _check_error(index, check)
        if error:
            errors.append(error)
    return errors


def _check_error(index: int, check) -> str:
    """Return the error for one check, or an empty string.

    Parameters
    ----------
    index : int
        Check position.
    check : object
        Check entry.

    Returns
    -------
    str
        Error text, or an empty string when valid.
    """
    if not isinstance(check, dict):
        return f"check {index} must be an object"
    kind = check.get("type")
    if kind not in _CHECK_TYPES:
        return f"check {index} has an unknown type"
    if kind == "status_in":
        return _values_error(index, check)
    return _value_error(index, check)


def _value_error(index: int, check: dict) -> str:
    """Return the missing-value error for one check.

    Parameters
    ----------
    index : int
        Check position.
    check : dict
        Check entry.

    Returns
    -------
    str
        Error text, or an empty string when valid.
    """
    if "value" not in check:
        return f"check {index} is missing value"
    return ""


def _values_error(index: int, check: dict) -> str:
    """Return the error for a status check.

    Parameters
    ----------
    index : int
        Check position.
    check : dict
        Check entry.

    Returns
    -------
    str
        Error text, or an empty string when valid.
    """
    values = check.get("values")
    if isinstance(values, list) and values:
        return ""
    return f"check {index} must list status values"


def prompt_hash(sequence: list[str]) -> str:
    """Return a stable hash of the prompt sequence.

    Parameters
    ----------
    sequence : list of str
        Input messages in order.

    Returns
    -------
    str
        SHA-256 hex digest.
    """
    text = "\n\x00\n".join(sequence)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evaluate_checks(
    checks: list[dict], answer: str, root: Path | str
) -> list[dict]:
    """Evaluate every deterministic check against a run.

    Parameters
    ----------
    checks : list of dict
        Check entries.
    answer : str
        Final answer text.
    root : pathlib.Path or str
        Run workspace.

    Returns
    -------
    list of dict
        One result per check.
    """
    return [_check_result(check, answer, Path(root)) for check in checks]


def _check_result(check: dict, answer: str, root: Path) -> dict:
    """Return the result of one check.

    Parameters
    ----------
    check : dict
        Check entry.
    answer : str
        Final answer text.
    root : pathlib.Path
        Run workspace.

    Returns
    -------
    dict
        Check type, value, and pass state.
    """
    passed = _check_passes(check, answer, root)
    return {
        "type": check.get("type"),
        "value": check.get("value") or check.get("values"),
        "passed": passed,
    }


def _check_passes(check: dict, answer: str, root: Path) -> bool:
    """Return whether one check passes.

    Parameters
    ----------
    check : dict
        Check entry.
    answer : str
        Final answer text.
    root : pathlib.Path
        Run workspace.

    Returns
    -------
    bool
        ``True`` when the check passes.
    """
    kind = check.get("type")
    if kind == "contains":
        return _contains(check, answer)
    if kind == "not_contains":
        return not _contains(check, answer)
    if kind == "regex":
        return re.search(str(check["value"]), answer) is not None
    return _path_check(kind, check, answer, root)


def _contains(check: dict, answer: str) -> bool:
    """Return whether the answer contains the check value.

    Parameters
    ----------
    check : dict
        Check entry.
    answer : str
        Final answer text.

    Returns
    -------
    bool
        ``True`` when the value is present.
    """
    return str(check["value"]) in answer


def _path_check(kind: str, check: dict, answer: str, root: Path) -> bool:
    """Return the result of a file or status check.

    Parameters
    ----------
    kind : str
        Check type.
    check : dict
        Check entry.
    answer : str
        Final answer text.
    root : pathlib.Path
        Run workspace.

    Returns
    -------
    bool
        ``True`` when the check passes.
    """
    if kind == "file_exists":
        return (root / str(check["value"])).exists()
    if kind == "status_in":
        return _status_passes(check, answer)
    return False


def _status_passes(check: dict, answer: str) -> bool:
    """Return whether an answer states an allowed status.

    Parameters
    ----------
    check : dict
        Status check.
    answer : str
        Final answer text.

    Returns
    -------
    bool
        ``True`` when one allowed status appears.
    """
    text = answer.lower()
    return any(str(value) in text for value in check.get("values") or [])


def check_score(results: list[dict]) -> float:
    """Return the fraction of checks that passed.

    Parameters
    ----------
    results : list of dict
        Check results.

    Returns
    -------
    float
        Fraction in ``[0.0, 1.0]``; zero for an empty list.
    """
    if not results:
        return 0.0
    passed = sum(1 for result in results if result.get("passed"))
    return passed / len(results)


def passed(results: list[dict], threshold: float = 1.0) -> bool:
    """Return whether the check score meets a threshold.

    Parameters
    ----------
    results : list of dict
        Check results.
    threshold : float
        Minimum passing fraction.

    Returns
    -------
    bool
        ``True`` when the score meets the threshold.
    """
    return check_score(results) >= threshold
