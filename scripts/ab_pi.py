"""Compare this harness against Pi on a task manifest."""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from meta_harness.task_evaluator import load_manifest
from meta_harness.task_evaluator import score_candidate
from meta_harness.task_evaluator import score_workspace

_CODE_BLOCK = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)
_PROMPT_SUFFIX = (
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
    parser.add_argument("--harness-cmd", default=_harness_cmd())
    parser.add_argument("--pi-cmd", default="pi")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out")
    return parser.parse_args(argv)


def _harness_cmd() -> str:
    """Return the default harness command.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Shell-quoted command prefix.
    """
    return shlex.join([sys.executable, "-m", "meta_harness.cli", "--no-web"])


def run_once(command, prompt, timeout, cwd=None):
    """Run one agent command and return its answer text.

    Parameters
    ----------
    command : list[str]
        Command prefix.

    prompt : str
        Task prompt.

    timeout : int
        Timeout in seconds.

    cwd : str or None
        Working directory for the agent.

    Returns
    -------
    str
        Standard output, or an empty string on failure.
    """
    return _run_status(command, prompt, timeout, cwd)[0]


def _run_status(command, prompt, timeout, cwd=None) -> tuple:
    """Run one agent and classify its outcome.

    Parameters
    ----------
    command : list[str]
        Command prefix.

    prompt : str
        Task prompt.

    timeout : int
        Timeout in seconds.

    cwd : str or None
        Working directory for the agent.

    Returns
    -------
    tuple
        Answer text, elapsed seconds, and status string.
    """
    started = time.monotonic()
    try:
        completed = _invoke(command, prompt, timeout, cwd)
    except subprocess.TimeoutExpired:
        return "", _elapsed(started), "timeout"
    except OSError:
        return "", _elapsed(started), "error"
    return _completed_status(completed, started)


def _completed_status(completed, started) -> tuple:
    """Return the outcome of a completed agent process.

    Parameters
    ----------
    completed : subprocess.CompletedProcess
        Completed agent process.

    started : float
        Start time from ``time.monotonic``.

    Returns
    -------
    tuple
        Output text, elapsed seconds, and status string.
    """
    status = "ok" if completed.returncode == 0 else "error"
    return completed.stdout, _elapsed(started), status


def _elapsed(started: float) -> float:
    """Return rounded elapsed seconds.

    Parameters
    ----------
    started : float
        Start time from ``time.monotonic``.

    Returns
    -------
    float
        Elapsed seconds rounded to two decimals.
    """
    return round(time.monotonic() - started, 2)


def _invoke(command, prompt, timeout, cwd):
    """Run one agent subprocess.

    Parameters
    ----------
    command : list[str]
        Command prefix.

    prompt : str
        Task prompt.

    timeout : int
        Timeout in seconds.

    cwd : str or None
        Working directory.

    Returns
    -------
    subprocess.CompletedProcess
        Completed agent process.
    """
    return subprocess.run(
        [*command, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


def extract_code(answer):
    """Extract Python source from an answer.

    Parameters
    ----------
    answer : str
        Agent output.

    Returns
    -------
    str
        Fenced code when present, otherwise the whole answer.
    """
    blocks = _CODE_BLOCK.findall(answer)
    return "\n\n".join(block.strip() for block in blocks) if blocks else answer


def score_answer(answer, manifest_dir, manifest):
    """Score one answer against a task manifest.

    Parameters
    ----------
    answer : str
        Agent output.

    manifest_dir : pathlib.Path
        Manifest root directory.

    manifest : list[dict]
        Tasks to score.

    Returns
    -------
    float
        Pass rate in the unit interval.
    """
    rate, _ = score_candidate(extract_code(answer), manifest_dir, manifest)
    return rate


def compare(manifest_path, harness_cmd, pi_cmd, timeout, repeats=1):
    """Score both agents on every manifest task.

    Parameters
    ----------
    manifest_path : str
        Manifest path.

    harness_cmd : list[str]
        This harness command prefix.

    pi_cmd : list[str]
        Pi command prefix.

    timeout : int
        Per-task timeout in seconds.

    repeats : int
        Number of runs per task.

    Returns
    -------
    dict
        Per-agent and per-task comparison data.
    """
    path = Path(manifest_path)
    manifest = load_manifest(path)
    rows = [
        _repeat_row(task, path.parent, harness_cmd, pi_cmd, timeout, repeats)
        for task in manifest
    ]
    return _report(rows)


def _repeat_row(task, root, harness_cmd, pi_cmd, timeout, repeats):
    """Average repeated runs for one task.

    Parameters
    ----------
    task : dict
        Task record.

    root : pathlib.Path
        Manifest root directory.

    harness_cmd : list[str]
        This harness command prefix.

    pi_cmd : list[str]
        Pi command prefix.

    timeout : int
        Per-task timeout in seconds.

    repeats : int
        Number of runs per task.

    Returns
    -------
    dict
        Averaged task row.
    """
    runs = [
        _task_row(task, root, harness_cmd, pi_cmd, timeout)
        for _ in range(max(1, repeats))
    ]
    return _average_row(task.get("id"), runs)


def _average_row(task_id, runs) -> dict:
    """Average per-run rows for one task.

    Parameters
    ----------
    task_id : str
        Task identifier.

    runs : list[dict]
        Per-run task rows.

    Returns
    -------
    dict
        Averaged row with per-run values and timeout counts.
    """
    row = _average_fields(task_id, runs)
    row["harness_runs"] = [item["harness"] for item in runs]
    row["pi_runs"] = [item["pi"] for item in runs]
    row["harness_timeouts"] = _count(runs, "harness_status")
    row["pi_timeouts"] = _count(runs, "pi_status")
    return row


def _average_fields(task_id, runs) -> dict:
    """Average pass rates and timings across runs.

    Parameters
    ----------
    task_id : str
        Task identifier.

    runs : list[dict]
        Per-run task rows.

    Returns
    -------
    dict
        Averaged fields.
    """
    return {
        "id": task_id,
        "repeats": len(runs),
        "harness": _average(item["harness"] for item in runs),
        "pi": _average(item["pi"] for item in runs),
        "harness_s": _average(item["harness_s"] for item in runs),
        "pi_s": _average(item["pi_s"] for item in runs),
    }


def _count(runs, key) -> int:
    """Count timeout statuses in task rows.

    Parameters
    ----------
    runs : list[dict]
        Per-run task rows.

    key : str
        Status key.

    Returns
    -------
    int
        Number of timeout statuses.
    """
    return sum(1 for item in runs if item[key] == "timeout")


def _task_row(task, root, harness_cmd, pi_cmd, timeout):
    """Score both agents on one task.

    Parameters
    ----------
    task : dict
        Task record.

    root : pathlib.Path
        Manifest root directory.

    harness_cmd : list[str]
        This harness command prefix.

    pi_cmd : list[str]
        Pi command prefix.

    timeout : int
        Per-task timeout in seconds.

    Returns
    -------
    dict
        Task identifier, both pass rates, and elapsed seconds.
    """
    if task.get("workspace"):
        return _workspace_row(task, root, harness_cmd, pi_cmd, timeout)
    return _code_row(task, root, harness_cmd, pi_cmd, timeout)


def _code_row(task, root, harness_cmd, pi_cmd, timeout):
    """Score both agents on one single-file code task.

    Parameters
    ----------
    task : dict
        Task record.

    root : pathlib.Path
        Manifest root directory.

    harness_cmd : list[str]
        This harness command prefix.

    pi_cmd : list[str]
        Pi command prefix.

    timeout : int
        Per-task timeout in seconds.

    Returns
    -------
    dict
        Task identifier, both pass rates, and elapsed seconds.
    """
    prompt = task.get("prompt", "") + _PROMPT_SUFFIX
    mine = _agent_answer(harness_cmd, prompt, timeout)
    other = _agent_answer(pi_cmd, prompt, timeout)
    row = _row_fields(task.get("id"), mine, other)
    row["harness"] = score_answer(mine[0], root, [task])
    row["pi"] = score_answer(other[0], root, [task])
    return row


def _row_fields(task_id, mine, other) -> dict:
    """Build timing and status fields for a task row.

    Parameters
    ----------
    task_id : str
        Task identifier.

    mine : tuple
        Harness answer, elapsed seconds, and status.

    other : tuple
        Pi answer, elapsed seconds, and status.

    Returns
    -------
    dict
        Partial task row.
    """
    return {
        "id": task_id,
        "harness_s": mine[1],
        "pi_s": other[1],
        "harness_status": mine[2],
        "pi_status": other[2],
    }


def _agent_answer(command, prompt, timeout):
    """Run one agent in a fresh workspace.

    Parameters
    ----------
    command : list[str]
        Command prefix.

    prompt : str
        Task prompt.

    timeout : int
        Timeout in seconds.

    Returns
    -------
    tuple
        Answer text, elapsed seconds, and status string.
    """
    with tempfile.TemporaryDirectory() as workspace:
        return _run_status(command, prompt, timeout, workspace)


def _workspace_row(task, root, harness_cmd, pi_cmd, timeout):
    """Score both agents on one workspace task.

    Parameters
    ----------
    task : dict
        Task record with ``workspace`` and ``test`` paths.

    root : pathlib.Path
        Manifest root directory.

    harness_cmd : list[str]
        This harness command prefix.

    pi_cmd : list[str]
        Pi command prefix.

    timeout : int
        Per-task timeout in seconds.

    Returns
    -------
    dict
        Task identifier, both pass rates, and elapsed seconds.
    """
    prompt = task.get("prompt", "") + _REPO_SUFFIX
    template = root / task["workspace"]
    test = root / task["test"]
    runner = task.get("runner", "unittest")
    return _run_pair(
        task, prompt, timeout, template, test, runner, harness_cmd, pi_cmd
    )


def _run_pair(
    task, prompt, timeout, template, test, runner, harness_cmd, pi_cmd
):
    """Run both agents and build a workspace row.

    Parameters
    ----------
    task : dict
        Task record.

    prompt : str
        Task prompt.

    timeout : int
        Per-task timeout in seconds.

    template : pathlib.Path
        Workspace template.

    test : pathlib.Path
        Hidden test module.

    runner : str
        ``unittest`` or ``pytest``.

    harness_cmd : list[str]
        This harness command prefix.

    pi_cmd : list[str]
        Pi command prefix.

    Returns
    -------
    dict
        Task row.
    """
    mine = _agent_workspace(
        harness_cmd, prompt, timeout, template, test, runner
    )
    other = _agent_workspace(pi_cmd, prompt, timeout, template, test, runner)
    return _workspace_result(task, mine, other)


def _agent_workspace(command, prompt, timeout, template, test, runner):
    """Run one agent in a fresh workspace copy and score it.

    Parameters
    ----------
    command : list[str]
        Command prefix.

    prompt : str
        Task prompt.

    timeout : int
        Timeout in seconds.

    template : pathlib.Path
        Workspace template to copy.

    test : pathlib.Path
        Hidden test module.

    runner : str
        ``unittest`` or ``pytest``.

    Returns
    -------
    tuple
        Passed flag, elapsed seconds, and status string.
    """
    with tempfile.TemporaryDirectory() as workspace:
        shutil.copytree(template, workspace, dirs_exist_ok=True)
        _, elapsed, status = _run_status(command, prompt, timeout, workspace)
        passed = score_workspace(Path(workspace), test, runner, timeout)[0]
    return passed, elapsed, status


def _workspace_result(task, mine, other):
    """Build a task row from workspace outcomes.

    Parameters
    ----------
    task : dict
        Task record.

    mine : tuple
        Harness passed flag, elapsed seconds, and status.

    other : tuple
        Pi passed flag, elapsed seconds, and status.

    Returns
    -------
    dict
        Task row.
    """
    row = {"id": task.get("id"), "harness": 1.0 if mine[0] else 0.0}
    row["pi"] = 1.0 if other[0] else 0.0
    row["harness_s"], row["pi_s"] = mine[1], other[1]
    row["harness_status"], row["pi_status"] = mine[2], other[2]
    return row


def _report(rows):
    """Build the comparison summary.

    Parameters
    ----------
    rows : list[dict]
        Per-task results.

    Returns
    -------
    dict
        Per-task rows, pass rates, elapsed times, and timeout counts.
    """
    return _timing_summary(_score_summary(rows), rows)


def _score_summary(rows) -> dict:
    """Compute pass-rate aggregates.

    Parameters
    ----------
    rows : list[dict]
        Per-task results.

    Returns
    -------
    dict
        Task rows and pass-rate aggregates.
    """
    summary = {"tasks": rows}
    summary["harness"] = _average(row["harness"] for row in rows)
    summary["pi"] = _average(row["pi"] for row in rows)
    summary["delta"] = summary["harness"] - summary["pi"]
    summary["harness_spread"] = _spread(row["harness"] for row in rows)
    summary["pi_spread"] = _spread(row["pi"] for row in rows)
    return summary


def _timing_summary(summary, rows) -> dict:
    """Add average elapsed times and timeout counts to a summary.

    Parameters
    ----------
    summary : dict
        Pass-rate summary.

    rows : list[dict]
        Per-task results.

    Returns
    -------
    dict
        Summary with elapsed times and timeout counts.
    """
    summary["harness_timeouts"] = _sum_timeouts(rows, "harness_timeouts")
    summary["pi_timeouts"] = _sum_timeouts(rows, "pi_timeouts")
    return _time_averages(summary, rows)


def _time_averages(summary, rows) -> dict:
    """Add average elapsed times to a summary.

    Parameters
    ----------
    summary : dict
        Pass-rate summary.

    rows : list[dict]
        Per-task results.

    Returns
    -------
    dict
        Summary with average elapsed seconds.
    """
    summary["harness_seconds"] = _average(
        _seconds(row, "harness_s") for row in rows
    )
    summary["pi_seconds"] = _average(_seconds(row, "pi_s") for row in rows)
    return summary


def _seconds(row, key) -> float:
    """Return a task row's elapsed seconds.

    Parameters
    ----------
    row : dict
        Per-task result.

    key : str
        Timing key.

    Returns
    -------
    float
        Elapsed seconds, or zero when missing.
    """
    return float(row.get(key, 0.0))


def _sum_timeouts(rows, key) -> int:
    """Sum per-task timeout counts.

    Parameters
    ----------
    rows : list[dict]
        Per-task results.

    key : str
        Timeout key.

    Returns
    -------
    int
        Total timeout count.
    """
    return sum(int(row.get(key, 0)) for row in rows)


def _spread(values) -> float:
    """Return the range of a sequence.

    Parameters
    ----------
    values : iterable of float
        Values to inspect.

    Returns
    -------
    float
        Maximum minus minimum, or zero when empty.
    """
    items = list(values)
    return 0.0 if not items else max(items) - min(items)


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


def main(argv=None) -> int:
    """Run the comparison and print JSON.

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
    harness_cmd, pi_cmd = _commands(args)
    report = compare(
        args.manifest, harness_cmd, pi_cmd, args.timeout, args.repeats
    )
    return _emit_report(report, args.out)


def _commands(args):
    """Split the configured agent command strings.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    tuple
        Harness and Pi command prefixes.
    """
    return shlex.split(args.harness_cmd), shlex.split(args.pi_cmd)


def _emit_report(report, out) -> int:
    """Write and print the comparison report.

    Parameters
    ----------
    report : dict
        Comparison report.

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


if __name__ == "__main__":
    raise SystemExit(main())
