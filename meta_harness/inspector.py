"""Pretty-print trajectory.jsonl files written by SearchPipeline."""

import json
from pathlib import Path

_TRUNCATE = 200


def print_run(root: Path) -> int:
    """Print every trajectory.jsonl found under a workspace root.

    Parameters
    ----------
    root : pathlib.Path
        Workspace directory holding one or more ``iteration-*/`` folders.

    Returns
    -------
    int
        Process exit code. ``0`` when at least one iteration was printed,
        ``1`` when no trajectory files were found.
    """
    files = sorted(root.glob("iteration-*/trajectory.jsonl"))
    if not files:
        print(f"no trajectory files under {root}")
        return 1
    for path in files:
        _print_file(path)
    return 0


def _print_file(path: Path) -> None:
    """Print one iteration's trajectory jsonl.

    Parameters
    ----------
    path : pathlib.Path
        Path to a ``trajectory.jsonl`` file.

    Returns
    -------
    None
        Entries written to stdout.
    """
    label = path.parent.name
    print(f"=== {label} ===")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            _print_entry(json.loads(line))
    print()


def _print_entry(entry: dict) -> None:
    """Print one trajectory entry in a readable, truncated form.

    Parameters
    ----------
    entry : dict
        Decoded trajectory entry.

    Returns
    -------
    None
        Entry written to stdout.
    """
    header = _header(entry)
    print()
    print(header)
    print(f"  system:   {_short(entry.get('prompt_system'))}")
    print(f"  user:     {_short(entry.get('prompt_user'))}")
    print(f"  response: {_short(entry.get('response'))}")


def _header(entry: dict) -> str:
    """Return the one-line header for a trajectory entry.

    Parameters
    ----------
    entry : dict
        Decoded trajectory entry.

    Returns
    -------
    str
        Formatted header line.
    """
    stage = entry.get("stage", "?")
    ts = entry.get("ts", "?")
    tag = (
        f" (candidate={entry['candidate_id']})"
        if entry.get("candidate_id")
        else ""
    )
    return f"[{ts}] {stage}{tag}"


def _short(value: object) -> str:
    """Return a truncated string form of a trajectory field.

    Parameters
    ----------
    value : object
        Field value.

    Returns
    -------
    str
        Truncated string with an ellipsis when longer than the limit.
    """
    text = "" if value is None else str(value).replace("\n", " ")
    return text if len(text) <= _TRUNCATE else text[:_TRUNCATE] + "..."
