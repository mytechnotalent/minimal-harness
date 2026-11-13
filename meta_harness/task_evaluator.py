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


def score_review_tests(
    code: str,
    test_sources: list[str],
    timeout: int = 5,
) -> tuple[bool, str]:
    """Run reviewer-generated tests against a candidate solution.

    Parameters
    ----------
    code : str
        Candidate solution source.

    test_sources : list[str]
        Reviewer-generated unittest sources.

    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    tuple[bool, str]
        Whether every reviewer test passed, and combined output.
    """
    if not test_sources:
        return True, ""
    with tempfile.TemporaryDirectory() as work:
        return _run_review_tests(Path(work), code, test_sources, timeout)


def _run_review_tests(wd, code, test_sources, timeout):
    """Stage and run reviewer tests in a scratch directory.

    Parameters
    ----------
    wd : pathlib.Path
        Working directory (temporary).

    code : str
        Candidate solution source.

    test_sources : list[str]
        Reviewer-generated unittest sources.

    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    tuple[bool, str]
        Whether every reviewer test passed, and combined output.
    """
    (wd / "solution.py").write_text(code, encoding="utf-8")
    (wd / "reviewer_test.py").write_text(
        "\n\n".join(test_sources), encoding="utf-8"
    )
    proc = _unittest_proc(wd, "reviewer_test", timeout)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def _unittest_proc(wd, module, timeout):
    """Run one unittest module in a working directory.

    Parameters
    ----------
    wd : pathlib.Path
        Working directory containing the test module.

    module : str
        Test module name.

    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    subprocess.CompletedProcess
        Completed test process with captured text output.
    """
    return subprocess.run(
        [sys.executable, "-m", "unittest", module],
        cwd=wd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def score_workspace(
    workspace: Path,
    test_path: Path,
    timeout: int = 60,
) -> tuple[bool, str]:
    """Run a hidden test against an agent workspace.

    Parameters
    ----------
    workspace : pathlib.Path
        Workspace root modified by the agent.

    test_path : pathlib.Path
        Hidden test module to run.

    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    tuple[bool, str]
        Whether the hidden test passed, and combined output.
    """
    text = test_path.read_text(encoding="utf-8")
    return _staged_workspace_result(
        workspace, "_hidden_test.py", text, timeout
    )


def run_workspace_tests(
    workspace: Path,
    test_sources: list[str],
    timeout: int = 60,
) -> tuple[bool, str]:
    """Run reviewer-generated tests against an agent workspace.

    Parameters
    ----------
    workspace : pathlib.Path
        Workspace containing the agent's changes.

    test_sources : list[str]
        Reviewer-generated unittest sources.

    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    tuple[bool, str]
        Whether every test passed, and combined output.
    """
    if not test_sources:
        return True, ""
    return _staged_workspace_result(
        workspace, "_reviewer_test.py", "\n\n".join(test_sources), timeout
    )


def _stage_test(workspace: Path, name: str, text: str) -> Path:
    """Write a staged test module into a workspace.

    Parameters
    ----------
    workspace : pathlib.Path
        Workspace root.

    name : str
        Test module filename.

    text : str
        Test source.

    Returns
    -------
    pathlib.Path
        Staged test path.
    """
    path = workspace / name
    path.write_text(text, encoding="utf-8")
    return path


def _staged_workspace_result(workspace, name, text, timeout):
    """Run one staged test module and remove it afterwards.

    Parameters
    ----------
    workspace : pathlib.Path
        Workspace root.

    name : str
        Test module filename.

    text : str
        Test source.

    timeout : int
        Subprocess timeout in seconds.

    Returns
    -------
    tuple[bool, str]
        Whether the test passed, and combined output.
    """
    staged = _stage_test(workspace, name, text)
    try:
        proc = _unittest_proc(workspace, Path(name).stem, timeout)
    finally:
        staged.unlink(missing_ok=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
