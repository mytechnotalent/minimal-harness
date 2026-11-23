"""Deterministic checks for requested files and completion claims."""

import re
from pathlib import Path

STATUSES = (
    "completed and verified",
    "completed but not fully verified",
    "partially completed",
    "blocked",
    "failed",
)
_ACTION = (
    r"(?:create|created|write|wrote|written|save|saved|generate|generated"
    r"|produce|produced|make|made|add|added|update|updated)"
)
_PATH = r"[`\"']?([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)"
_CLAIM_ACTION = (
    r"(?:created|wrote|written|saved|generated|produced|made|added|updated)"
)
_REQUEST = re.compile(
    _ACTION
    + r"\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:file\s+)?"
    + r"(?:named\s+|called\s+)?"
    + _PATH,
    re.I,
)
_CLAIM = re.compile(
    _CLAIM_ACTION
    + r"\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:file\s+)?"
    + r"(?:named\s+|called\s+)?"
    + _PATH,
    re.I,
)
_FILENAME = re.compile(
    r"(?:file|script|report)\s+(?:named\s+|called\s+)" + _PATH,
    re.I,
)
_TEST_CLAIM = re.compile(
    r"\b(?:tests?|test suite)\b[^.\n]{0,40}\b(?:pass|passed|passing|green)\b",
    re.I,
)
_STATUS_HINT = (
    "completion status not stated; use completed and verified, "
    "completed but not fully verified, partially completed, blocked, "
    "or failed"
)


def needs_deliverables(prompt: str, changed: list[str]) -> bool:
    """Return whether a task produces files or artifacts.

    Parameters
    ----------
    prompt : str
        User question.
    changed : list of str
        Files changed during the current task.

    Returns
    -------
    bool
        ``True`` when files changed or the prompt requests one.
    """
    if changed:
        return True
    return bool(_requested_paths(prompt))


def deliverable_issues(
    prompt: str, answer: str, changed: list[str], trace: list[dict]
) -> list[str]:
    """Return deterministic deliverable issues for one answer.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.
    changed : list of str
        Files changed during the current task.
    trace : list of dict
        Execution records.

    Returns
    -------
    list of str
        Issue strings; empty when every claim is supported.
    """
    if not needs_deliverables(prompt, changed):
        return []
    issues = _missing_files(prompt, changed)
    issues.extend(_false_file_claims(answer, changed))
    issues.extend(_test_claim_issues(answer, trace))
    issues.extend(_status_issues(prompt, answer, changed))
    return issues


def _requested_paths(text: str) -> list[str]:
    """Return file paths named in action phrases.

    Parameters
    ----------
    text : str
        Prompt or answer.

    Returns
    -------
    list of str
        Unique paths in first-seen order.
    """
    paths = [match.group(1) for match in _REQUEST.finditer(text)]
    paths.extend(match.group(1) for match in _FILENAME.finditer(text))
    return list(dict.fromkeys(paths))


def _claimed_paths(text: str) -> list[str]:
    """Return file paths named in completed-action phrases.

    Parameters
    ----------
    text : str
        Answer text.

    Returns
    -------
    list of str
        Unique paths in first-seen order.
    """
    paths = [match.group(1) for match in _CLAIM.finditer(text)]
    paths.extend(match.group(1) for match in _FILENAME.finditer(text))
    return list(dict.fromkeys(paths))


def _missing_files(prompt: str, changed: list[str]) -> list[str]:
    """Return requested files absent from the changed list.

    Parameters
    ----------
    prompt : str
        User question.
    changed : list of str
        Files changed during the current task.

    Returns
    -------
    list of str
        One issue per missing requested file.
    """
    issues = []
    for path in _requested_paths(prompt):
        if not _matches(path, changed):
            issues.append(f"requested file {path} was not created or modified")
    return issues


def _false_file_claims(answer: str, changed: list[str]) -> list[str]:
    """Return files the answer claims but did not change.

    Parameters
    ----------
    answer : str
        Draft answer.
    changed : list of str
        Files changed during the current task.

    Returns
    -------
    list of str
        One issue per unsupported file claim.
    """
    issues = []
    for path in _claimed_paths(answer):
        if not _matches(path, changed):
            issues.append(f"answer names {path} but it was not changed")
    return issues


def _matches(path: str, changed: list[str]) -> bool:
    """Return whether a path was changed in this task.

    Parameters
    ----------
    path : str
        Requested or claimed path.
    changed : list of str
        Files changed during the current task.

    Returns
    -------
    bool
        ``True`` when the file name or directory suffix matches.
    """
    target = path.lstrip("./")
    if "/" not in target:
        return any(Path(item).name == target for item in changed)
    return any(
        item == target or item.endswith("/" + target) for item in changed
    )


def _test_claim_issues(answer: str, trace: list[dict]) -> list[str]:
    """Return an issue when passing tests are claimed without a run.

    Parameters
    ----------
    answer : str
        Draft answer.
    trace : list of dict
        Execution records.

    Returns
    -------
    list of str
        One issue when the claim is unsupported.
    """
    if not _TEST_CLAIM.search(answer):
        return []
    if _test_trace(trace):
        return []
    return ["answer claims tests passed without a successful test command"]


def _test_trace(trace: list[dict]) -> bool:
    """Return whether a successful test command was recorded.

    Parameters
    ----------
    trace : list of dict
        Execution records.

    Returns
    -------
    bool
        ``True`` when a successful bash call ran a test command.
    """
    for entry in trace:
        if entry.get("status") != "ok" or entry.get("tool") != "bash":
            continue
        if _is_test_command(_command(entry)):
            return True
    return False


def _command(entry: dict) -> str:
    """Return the redacted bash command of one record.

    Parameters
    ----------
    entry : dict
        Execution record.

    Returns
    -------
    str
        Lowercase command text.
    """
    arguments = entry.get("arguments") or {}
    return str(arguments.get("command") or "").lower()


def _is_test_command(command: str) -> bool:
    """Return whether a command runs tests.

    Parameters
    ----------
    command : str
        Lowercase command text.

    Returns
    -------
    bool
        ``True`` for test runners or test-named commands.
    """
    return "test" in command or "pytest" in command


def _status_issues(prompt: str, answer: str, changed: list[str]) -> list[str]:
    """Return an issue when the completion status is missing.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.
    changed : list of str
        Files changed during the current task.

    Returns
    -------
    list of str
        One issue when no explicit status appears.
    """
    if not needs_deliverables(prompt, changed):
        return []
    if _has_status(answer):
        return []
    return [_STATUS_HINT]


def _has_status(answer: str) -> bool:
    """Return whether the answer states a completion status.

    Parameters
    ----------
    answer : str
        Draft answer.

    Returns
    -------
    bool
        ``True`` when one of the status labels appears.
    """
    text = answer.lower()
    return any(status in text for status in STATUSES)
