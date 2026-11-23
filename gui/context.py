"""Live workspace snapshot for the ideas window."""

import subprocess
from datetime import datetime
from datetime import timezone
from pathlib import Path


def snapshot(root: Path | str) -> str:
    """Build a short description of the current workspace state.

    Parameters
    ----------
    root : pathlib.Path or str
        Workspace directory to inspect.

    Returns
    -------
    str
        Snapshot text with git status, diffs, and file tree.
    """
    path = Path(root)
    header = _header(path)
    status = _git("status --porcelain", path)
    diff = _git("diff --stat", path)
    tree = _tree(path)
    return header + "\n\n" + _compose(status, diff, tree)


def _header(root):
    """Build snapshot time, branch, and commit metadata.

    Parameters
    ----------
    root : pathlib.Path
        Workspace directory.

    Returns
    -------
    str
        Snapshot header.
    """
    branch = _git("rev-parse --abbrev-ref HEAD", root) or "unknown"
    head = _git("rev-parse --short HEAD", root) or "unknown"
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"Snapshot taken at {stamp}\nbranch: {branch}\nHEAD: {head}"


def _empty(status, diff, tree):
    """Return whether all snapshot sections are empty.

    Parameters
    ----------
    status : str
        Git status output.
    diff : str
        Git diff stat output.
    tree : str
        File tree output.

    Returns
    -------
    bool
        ``True`` when no content exists.
    """
    return not status and not diff and not tree


def _parts(status, diff, tree):
    """Build non-empty snapshot sections.

    Parameters
    ----------
    status : str
        Git status output.
    diff : str
        Git diff stat output.
    tree : str
        File tree output.

    Returns
    -------
    list
        Section strings.
    """
    parts = []
    if status:
        parts.append("git status:\n" + status)
    if diff:
        parts.append("git diff (stat):\n" + diff)
    if tree:
        parts.append("files:\n" + tree)
    return parts


def _git(args: str, root: Path) -> str:
    """Run one git command in the workspace.

    Parameters
    ----------
    args : str
        Git arguments.
    root : pathlib.Path
        Workspace directory.

    Returns
    -------
    str
        Trimmed command output or blank.
    """
    try:
        return _run_git(args, root).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def _run_git(args: str, root: Path):
    """Run one git command in the workspace.

    Parameters
    ----------
    args : str
        Git arguments.

    root : pathlib.Path
        Workspace directory.

    Returns
    -------
    subprocess.CompletedProcess
        Completed process with captured text output.
    """
    return subprocess.run(
        ["git", "-C", str(root)] + args.split(),
        capture_output=True,
        text=True,
        timeout=5,
    )


def _tree(root: Path) -> str:
    """List the top-level workspace entries.

    Parameters
    ----------
    root : pathlib.Path
        Workspace directory.

    Returns
    -------
    str
        Sorted top-level entry names.
    """
    try:
        entries = sorted(
            p.name for p in root.iterdir() if not p.name.startswith(".")
        )
        return "\n".join(entries[:25])
    except OSError:
        return ""


def _compose(status: str, diff: str, tree: str) -> str:
    """Join snapshot sections with headers.

    Parameters
    ----------
    status : str
        Git status output.
    diff : str
        Git diff stat output.
    tree : str
        File tree output.

    Returns
    -------
    str
        Combined snapshot text.
    """
    if _empty(status, diff, tree):
        return "Workspace is empty."
    return "\n\n".join(_parts(status, diff, tree))
