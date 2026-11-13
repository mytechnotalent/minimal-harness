"""Search harness configurations on a task manifest."""

import argparse
import json
import os
import shlex
import shutil
import sys
import tempfile
import time
from pathlib import Path

from meta_harness.task_evaluator import load_manifest
from meta_harness.task_evaluator import score_candidate
from meta_harness.task_evaluator import score_workspace
from scripts.ab_pi import extract_code
from scripts.ab_pi import run_once

_CODE_SUFFIX = (
    " Return the complete solution in a single ```python code block."
    " Do not create or modify files."
)
_REPO_SUFFIX = (
    " Modify the files in the current workspace to satisfy this request."
    " Do not print the full solution; write the changes to disk."
)


def parse_args(argv):
    """Parse command-line arguments.

    Parameters
    ----------
    argv : list[str]
        Command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--configs", required=True)
    parser.add_argument("--harness-cmd", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out")
    return parser.parse_args(argv)


def load_configs(path):
    """Load the configuration list.

    Parameters
    ----------
    path : str
        Configuration JSON path.

    Returns
    -------
    list
        Configuration records.
    """
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("configs must be a JSON list")
    return value


def search(manifest_path, configs, command, timeout, repeats=1):
    """Evaluate every config on every task.

    Parameters
    ----------
    manifest_path : str
        Manifest path.

    configs : list
        Configuration records.

    command : list[str]
        Harness command prefix.

    timeout : int
        Per-run timeout in seconds.

    repeats : int
        Runs per task and config.

    Returns
    -------
    dict
        Ranked configuration reports.
    """
    path = Path(manifest_path)
    tasks = load_manifest(path)
    reports = [
        _config_rows(path.parent, tasks, command, config, timeout, repeats)
        for config in configs
    ]
    return _archive(reports)


def _config_rows(root, tasks, command, config, timeout, repeats):
    """Evaluate one config across tasks and repeats.

    Parameters
    ----------
    root : pathlib.Path
        Manifest root directory.

    tasks : list[dict]
        Task records.

    command : list[str]
        Harness command prefix.

    config : dict
        Configuration record.

    timeout : int
        Per-run timeout in seconds.

    repeats : int
        Runs per task.

    Returns
    -------
    dict
        Configuration report.
    """
    rows = []
    for task in tasks:
        runs = [
            _task_score(task, root, command, config, timeout)
            for _ in range(max(1, repeats))
        ]
        rows.append(_average_task(task.get("id"), runs))
    return _config_report(config.get("name", "config"), rows)


def _average_task(task_id, runs):
    """Average repeated runs for one task.

    Parameters
    ----------
    task_id : str
        Task identifier.

    runs : list[dict]
        Per-run rows.

    Returns
    -------
    dict
        Averaged task row.
    """
    return {
        "id": task_id,
        "passed": _average(row["passed"] for row in runs),
        "seconds": _average(row["seconds"] for row in runs),
        "repeats": len(runs),
    }


def _config_report(name, rows):
    """Build one configuration report.

    Parameters
    ----------
    name : str
        Configuration name.

    rows : list[dict]
        Per-task rows.

    Returns
    -------
    dict
        Configuration report.
    """
    return {
        "name": name,
        "score": _average(row["passed"] for row in rows),
        "seconds": _average(row["seconds"] for row in rows),
        "tasks": rows,
    }


def _task_score(task, root, command, config, timeout):
    """Score one config on one task.

    Parameters
    ----------
    task : dict
        Task record.

    root : pathlib.Path
        Manifest root directory.

    command : list[str]
        Harness command prefix.

    config : dict
        Configuration record.

    timeout : int
        Per-run timeout in seconds.

    Returns
    -------
    dict
        One config/task row.
    """
    prompt = task.get("prompt", "")
    if task.get("workspace"):
        return _workspace_score(task, root, command, config, prompt, timeout)
    return _code_score(task, root, command, config, prompt, timeout)


def _workspace_score(task, root, command, config, prompt, timeout):
    """Run and score one workspace task.

    Parameters
    ----------
    task : dict
        Task record.

    root : pathlib.Path
        Manifest root directory.

    command : list[str]
        Harness command prefix.

    config : dict
        Configuration record.

    prompt : str
        Task prompt.

    timeout : int
        Per-run timeout in seconds.

    Returns
    -------
    dict
        One config/task row.
    """
    with tempfile.TemporaryDirectory() as workspace:
        _copy_template(root, task, workspace)
        answer, elapsed = _run(
            config, command, prompt + _REPO_SUFFIX, timeout, workspace
        )
        passed = _workspace_pass(root, task, workspace, timeout)
    return _row(task, passed, elapsed, answer)


def _copy_template(root, task, workspace) -> None:
    """Copy a task workspace into a scratch directory.

    Parameters
    ----------
    root : pathlib.Path
        Manifest root directory.

    task : dict
        Task record.

    workspace : str
        Destination directory.

    Returns
    -------
    None
        The workspace is populated.
    """
    source = root / task["workspace"]
    shutil.copytree(source, workspace, dirs_exist_ok=True)


def _workspace_pass(root, task, workspace, timeout) -> bool:
    """Run a task's hidden test in a workspace.

    Parameters
    ----------
    root : pathlib.Path
        Manifest root directory.

    task : dict
        Task record.

    workspace : str
        Workspace directory.

    timeout : int
        Timeout in seconds.

    Returns
    -------
    bool
        Whether the hidden test passed.
    """
    test = root / task["test"]
    runner = task.get("runner", "unittest")
    return score_workspace(Path(workspace), test, runner, timeout)[0]


def _code_score(task, root, command, config, prompt, timeout):
    """Run and score one single-file code task.

    Parameters
    ----------
    task : dict
        Task record.

    root : pathlib.Path
        Manifest root directory.

    command : list[str]
        Harness command prefix.

    config : dict
        Configuration record.

    prompt : str
        Task prompt.

    timeout : int
        Per-run timeout in seconds.

    Returns
    -------
    dict
        One config/task row.
    """
    with tempfile.TemporaryDirectory() as workspace:
        answer, elapsed = _run(
            config, command, prompt + _CODE_SUFFIX, timeout, workspace
        )
    rate = _code_rate(answer, root, task)
    return _row(task, rate > 0, elapsed, answer)


def _run(config, command, prompt, timeout, cwd):
    """Run the harness under one configuration.

    Parameters
    ----------
    config : dict
        Configuration record.

    command : list[str]
        Harness command prefix.

    prompt : str
        Task prompt.

    timeout : int
        Timeout in seconds.

    cwd : str
        Working directory.

    Returns
    -------
    tuple
        Answer text and elapsed seconds.
    """
    env = {**os.environ, **config.get("env", {})}
    args = [*command, *config.get("args", [])]
    started = time.monotonic()
    answer = run_once(args, prompt, timeout, cwd, env=env)
    return answer, round(time.monotonic() - started, 2)


def _code_rate(answer, root, task):
    """Score one extracted code answer.

    Parameters
    ----------
    answer : str
        Agent output.

    root : pathlib.Path
        Manifest root directory.

    task : dict
        Task record.

    Returns
    -------
    float
        Pass rate in the unit interval.
    """
    return score_candidate(extract_code(answer), root, [task])[0]


def _row(task, passed, elapsed, answer):
    """Build one config/task row.

    Parameters
    ----------
    task : dict
        Task record.

    passed : bool
        Whether the task passed.

    elapsed : float
        Elapsed seconds.

    answer : str
        Agent output.

    Returns
    -------
    dict
        Row with pass flag, timing, and output size.
    """
    return {
        "id": task.get("id"),
        "passed": 1.0 if passed else 0.0,
        "seconds": elapsed,
        "answer_chars": len(answer),
    }


def _archive(reports):
    """Rank reports and mark the Pareto front.

    Parameters
    ----------
    reports : list[dict]
        Configuration reports.

    Returns
    -------
    dict
        Ranked reports with Pareto flags.
    """
    ranked = sorted(
        reports, key=lambda item: (-item["score"], item["seconds"])
    )
    for report in ranked:
        report["pareto"] = not any(
            _dominates(other, report) for other in ranked
        )
    return {"configs": ranked}


def _dominates(first, second):
    """Report whether one config dominates another.

    Parameters
    ----------
    first : dict
        Candidate dominator.

    second : dict
        Candidate compared against.

    Returns
    -------
    bool
        Whether the first is at least as good and strictly better once.
    """
    better = first["score"] > second["score"] or (
        first["score"] == second["score"]
        and first["seconds"] < second["seconds"]
    )
    return better and first["seconds"] <= second["seconds"]


def _average(values):
    """Return the mean of a sequence.

    Parameters
    ----------
    values : iterable of float
        Values to average.

    Returns
    -------
    float
        Mean value, or zero when empty.
    """
    items = list(values)
    return 0.0 if not items else sum(items) / len(items)


def _emit(report, out):
    """Print and optionally write the report.

    Parameters
    ----------
    report : dict
        Search report.

    out : str or None
        Optional output path.

    Returns
    -------
    int
        Process exit code.
    """
    text = json.dumps(report, indent=2)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv=None):
    """Run the configuration search.

    Parameters
    ----------
    argv : list[str] or None
        Command-line arguments.

    Returns
    -------
    int
        Process exit code.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    configs = load_configs(args.configs)
    command = shlex.split(args.harness_cmd)
    report = search(
        args.manifest, configs, command, args.timeout, args.repeats
    )
    return _emit(report, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
