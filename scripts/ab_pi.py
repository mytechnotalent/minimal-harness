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
    try:
        completed = _invoke(command, prompt, timeout, cwd)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return completed.stdout if completed.returncode == 0 else ""


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


def compare(manifest_path, harness_cmd, pi_cmd, timeout):
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

    Returns
    -------
    dict
        Per-agent and per-task comparison data.
    """
    path = Path(manifest_path)
    manifest = load_manifest(path)
    rows = [
        _task_row(task, path.parent, harness_cmd, pi_cmd, timeout)
        for task in manifest
    ]
    return _report(rows)


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
        Task identifier and both pass rates.
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
    mine, other, mine_s, pi_s = _answers(prompt, harness_cmd, pi_cmd, timeout)
    row = {"id": task.get("id"), "harness_s": mine_s, "pi_s": pi_s}
    row["harness"] = score_answer(mine, root, [task])
    row["pi"] = score_answer(other, root, [task])
    return row


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
    mine = _agent_workspace(harness_cmd, prompt, timeout, template, test)
    other = _agent_workspace(pi_cmd, prompt, timeout, template, test)
    return _workspace_result(task, mine, other)


def _agent_workspace(command, prompt, timeout, template, test):
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

    Returns
    -------
    tuple
        Passed flag and elapsed seconds.
    """
    with tempfile.TemporaryDirectory() as workspace:
        shutil.copytree(template, workspace, dirs_exist_ok=True)
        _, elapsed = _timed(command, prompt, timeout, workspace)
        passed = score_workspace(Path(workspace), test, timeout)[0]
    return passed, elapsed


def _workspace_result(task, mine, other):
    """Build a task row from workspace outcomes.

    Parameters
    ----------
    task : dict
        Task record.

    mine : tuple
        Harness passed flag and elapsed seconds.

    other : tuple
        Pi passed flag and elapsed seconds.

    Returns
    -------
    dict
        Task row.
    """
    return {
        "id": task.get("id"),
        "harness": 1.0 if mine[0] else 0.0,
        "pi": 1.0 if other[0] else 0.0,
        "harness_s": mine[1],
        "pi_s": other[1],
    }


def _answers(prompt, harness_cmd, pi_cmd, timeout):
    """Run both agents in isolated workspaces.

    Parameters
    ----------
    prompt : str
        Task prompt including the answer-format suffix.

    harness_cmd : list[str]
        This harness command prefix.

    pi_cmd : list[str]
        Pi command prefix.

    timeout : int
        Per-task timeout in seconds.

    Returns
    -------
    tuple
        Harness answer and Pi answer.
    """
    with tempfile.TemporaryDirectory() as ours:
        mine, mine_s = _timed(harness_cmd, prompt, timeout, ours)
    with tempfile.TemporaryDirectory() as theirs:
        other, pi_s = _timed(pi_cmd, prompt, timeout, theirs)
    return mine, other, mine_s, pi_s


def _timed(command, prompt, timeout, cwd):
    """Run one agent and measure elapsed time.

    Parameters
    ----------
    command : list[str]
        Command prefix.

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
    started = time.monotonic()
    answer = run_once(command, prompt, timeout, cwd)
    return answer, round(time.monotonic() - started, 2)


def _report(rows):
    """Build the comparison summary.

    Parameters
    ----------
    rows : list[dict]
        Per-task results.

    Returns
    -------
    dict
        Per-task rows, pass rates, and average elapsed times.
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
    ours = _average(row["harness"] for row in rows)
    theirs = _average(row["pi"] for row in rows)
    return {
        "tasks": rows,
        "harness": ours,
        "pi": theirs,
        "delta": ours - theirs,
    }


def _timing_summary(summary, rows) -> dict:
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
    report = compare(args.manifest, harness_cmd, pi_cmd, args.timeout)
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
