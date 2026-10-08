"""Deterministic per-task evaluator for candidate proposals."""

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskResult:
    """One task's evaluation outcome."""

    task_id: str
    passed: bool
    stdout: str
    stderr: str


def load_manifest(path: Path) -> list[dict]:
    """Return the parsed task manifest as a list of dicts.

    Parameters
    ----------
    path : pathlib.Path
        Manifest JSON path.

    Returns
    -------
    list[dict]
        Parsed tasks.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score_candidate(
    code: str,
    manifest_dir: Path,
    manifest: list[dict],
    timeout: int = 5,
) -> tuple[float, list[TaskResult]]:
    """Return (pass rate, per-task results) for candidate source.

    Parameters
    ----------
    code : str
        Candidate solution source code.
    manifest_dir : pathlib.Path
        Directory the manifest paths are relative to.
    manifest : list[dict]
        Tasks to run.
    timeout : int
        Per-task subprocess timeout in seconds.

    Returns
    -------
    tuple[float, list[TaskResult]]
        Pass rate in ``[0.0, 1.0]`` and one result per task.
    """
    results = [
        evaluate_task(code, manifest_dir, task, timeout) for task in manifest
    ]
    return _rate(results), results


def _rate(results: list[TaskResult]) -> float:
    """Return the pass rate across per-task results.

    Parameters
    ----------
    results : list[TaskResult]
        Per-task results.

    Returns
    -------
    float
        Pass rate in ``[0.0, 1.0]``.
    """
    return (
        0.0
        if not results
        else sum(1 for r in results if r.passed) / len(results)
    )


def evaluate_task(
    code: str, root: Path, task: dict, timeout: int
) -> TaskResult:
    """Run one task's pytest against the candidate code.

    Parameters
    ----------
    code : str
        Candidate solution source code.
    root : pathlib.Path
        Directory the manifest paths are relative to.
    task : dict
        Task record with ``id`` and ``test`` fields.
    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    TaskResult
        Outcome of the pytest invocation.
    """
    with tempfile.TemporaryDirectory() as work:
        return _run_task(Path(work), code, root, task, timeout)


def _run_task(
    wd: Path, code: str, root: Path, task: dict, timeout: int
) -> TaskResult:
    """Stage the task and run pytest inside a scratch directory.

    Parameters
    ----------
    wd : pathlib.Path
        Working directory (temporary).
    code : str
        Candidate solution source code.
    root : pathlib.Path
        Manifest root directory.
    task : dict
        Task record.
    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    TaskResult
        Outcome of the pytest invocation.
    """
    (wd / "solution.py").write_text(code, encoding="utf-8")
    (wd / "test.py").write_text(
        (root / task["test"]).read_text(encoding="utf-8"), encoding="utf-8"
    )
    return _pytest(wd, task["id"], timeout)


def _pytest(wd: Path, task_id: str, timeout: int) -> TaskResult:
    """Invoke pytest in ``wd`` and wrap the result.

    Parameters
    ----------
    wd : pathlib.Path
        Working directory containing ``solution.py`` and ``test.py``.
    task_id : str
        Task identifier.
    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    TaskResult
        Outcome of the pytest invocation.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "test"],
        cwd=wd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return TaskResult(task_id, proc.returncode == 0, proc.stdout, proc.stderr)
