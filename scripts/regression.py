"""Run one benchmark regression entry and record evidence."""

import argparse
import copy
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from meta_harness.agent import Agent
from meta_harness.env import load_env
from meta_harness.openrouter import OpenRouterClient
from meta_harness.regression import check_score
from meta_harness.regression import evaluate_checks
from meta_harness.regression import load_entry
from meta_harness.regression import passed
from meta_harness.regression import prompt_hash
from meta_harness.regression import validate_entry
from meta_harness.session import Session


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv : list of str
        Command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--out")
    parser.add_argument("--model")
    return parser.parse_args(argv)


def main() -> None:
    """Run the requested entry and write its evidence.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The result is written and reported.
    """
    args = parse_args(sys.argv[1:])
    load_env(".env")
    entry = _validated_entry(args.entry)
    result = run_entry(entry, args.model)
    path = _write_result(result, args.out)
    _report(result, path)


def _validated_entry(path: str) -> dict:
    """Load an entry and stop when it is invalid.

    Parameters
    ----------
    path : str
        Entry file.

    Returns
    -------
    dict
        Validated entry.
    """
    entry = load_entry(path)
    errors = validate_entry(entry)
    if errors:
        sys.exit("\n".join(errors))
    return entry


def run_entry(entry: dict, model_override: str | None) -> dict:
    """Execute one regression entry and collect evidence.

    Parameters
    ----------
    entry : dict
        Regression entry.
    model_override : str or None
        Optional model override.

    Returns
    -------
    dict
        Structured run result.
    """
    run_dir = _run_dir(entry)
    root = _seed_workspace(entry, run_dir)
    client = _client(entry, model_override)
    agent = _agent(entry, root, run_dir, client)
    turns = _run_messages(agent, entry["sequence"])
    checks = evaluate_checks(entry["checks"], turns[-1]["answer"], root)
    return _result(entry, client, checks, run_dir, root, turns)


def _run_dir(entry: dict) -> Path:
    """Create a timestamped run directory.

    Parameters
    ----------
    entry : dict
        Regression entry.

    Returns
    -------
    pathlib.Path
        New run directory.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path("runs") / "regression" / entry["id"] / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _seed_workspace(entry: dict, run_dir: Path) -> Path:
    """Copy an optional workspace fixture into the run directory.

    Parameters
    ----------
    entry : dict
        Regression entry.
    run_dir : pathlib.Path
        Run directory.

    Returns
    -------
    pathlib.Path
        Workspace root.
    """
    root = run_dir / "workspace"
    source = entry.get("workspace")
    if source:
        shutil.copytree(Path(source), root)
    else:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _client(entry: dict, model_override: str | None) -> OpenRouterClient:
    """Build the model client for one entry.

    Parameters
    ----------
    entry : dict
        Regression entry.
    model_override : str or None
        Optional model override.

    Returns
    -------
    OpenRouterClient
        Configured client.
    """
    config = entry.get("config") or {}
    return OpenRouterClient(model_override or config.get("model"))


def _agent(
    entry: dict, root: Path, run_dir: Path, client: OpenRouterClient
) -> Agent:
    """Build the agent for one entry.

    Parameters
    ----------
    entry : dict
        Regression entry.
    root : pathlib.Path
        Workspace root.
    run_dir : pathlib.Path
        Run directory.
    client : OpenRouterClient
        Model client.

    Returns
    -------
    Agent
        Configured agent.
    """
    config = entry.get("config") or {}
    return Agent(
        root=root,
        client=client,
        max_turns=int(config.get("max_turns", 24)),
        session=Session(run_dir / "transcript.jsonl"),
    )


def _run_messages(agent: Agent, sequence: list[str]) -> list[dict]:
    """Run each prompt and capture its answer and trace.

    Parameters
    ----------
    agent : Agent
        Configured agent.
    sequence : list of str
        Input messages in order.

    Returns
    -------
    list of dict
        One record per turn.
    """
    turns = []
    for prompt in sequence:
        answer = agent.run(prompt)
        trace = copy.deepcopy(agent._trace)
        turns.append({"prompt": prompt, "answer": answer, "trace": trace})
    return turns


def _result(
    entry: dict,
    client: OpenRouterClient,
    checks: list[dict],
    run_dir: Path,
    root: Path,
    turns: list[dict],
) -> dict:
    """Build the result document for one run.

    Parameters
    ----------
    entry : dict
        Regression entry.
    client : OpenRouterClient
        Model client.
    checks : list of dict
        Check results.
    run_dir : pathlib.Path
        Run directory.
    root : pathlib.Path
        Workspace root.
    turns : list of dict
        Captured turns.

    Returns
    -------
    dict
        Result document.
    """
    result = _result_identity(entry, client, checks)
    result.update(_result_scoring(entry, checks))
    result["run_dir"] = str(run_dir)
    result["workspace"] = str(root)
    result["turns"] = turns
    result["previous"] = _previous(entry["id"], run_dir)
    result["delta"] = _delta(result)
    return result


def _result_identity(
    entry: dict, client: OpenRouterClient, checks: list[dict]
) -> dict:
    """Return the identity and configuration fields.

    Parameters
    ----------
    entry : dict
        Regression entry.
    client : OpenRouterClient
        Model client.
    checks : list of dict
        Check results.

    Returns
    -------
    dict
        Partial result.
    """
    result = {"id": entry["id"]}
    result["prompt_version"] = entry.get("prompt_version")
    result["prompt_sha256"] = prompt_hash(entry["sequence"])
    result["config"] = _config(client, entry)
    result["checks"] = checks
    return result


def _result_scoring(entry: dict, checks: list[dict]) -> dict:
    """Return the scoring and rubric fields.

    Parameters
    ----------
    entry : dict
        Regression entry.
    checks : list of dict
        Check results.

    Returns
    -------
    dict
        Partial result.
    """
    score = check_score(checks)
    result = {"score": score, "passed": passed(checks, _threshold(entry))}
    result["expected_behaviors"] = entry.get("expected_behaviors") or []
    result["known_failures"] = entry.get("known_failures") or []
    result["rubric"] = entry.get("rubric") or {}
    return result


def _config(client: OpenRouterClient, entry: dict) -> dict:
    """Return the pinned configuration for one run.

    Parameters
    ----------
    client : OpenRouterClient
        Model client.
    entry : dict
        Regression entry.

    Returns
    -------
    dict
        Model, provider, limits, and commit.
    """
    config = entry.get("config") or {}
    pinned = _pinned(client, config)
    pinned["commit"] = _commit()
    return pinned


def _pinned(client: OpenRouterClient, config: dict) -> dict:
    """Return the pinned model and limit fields.

    Parameters
    ----------
    client : OpenRouterClient
        Model client.
    config : dict
        Entry configuration.

    Returns
    -------
    dict
        Model, provider, and limits.
    """
    return {
        "model": client.model,
        "provider": client.provider,
        "max_turns": int(config.get("max_turns", 24)),
        "temperature": config.get("temperature", 0.2),
        "timeout": config.get("timeout"),
    }


def _commit() -> str:
    """Return the current git commit, or an empty string.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Commit hash when available.
    """
    cmd = ["git", "rev-parse", "HEAD"]
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def _threshold(entry: dict) -> float:
    """Return the pass threshold for one entry.

    Parameters
    ----------
    entry : dict
        Regression entry.

    Returns
    -------
    float
        Minimum passing fraction.
    """
    rubric = entry.get("rubric") or {}
    return float(rubric.get("pass_threshold", 1.0))


def _previous(test_id: str, current: Path) -> dict | None:
    """Return the most recent earlier result for one test.

    Parameters
    ----------
    test_id : str
        Test identifier.
    current : pathlib.Path
        Current run directory.

    Returns
    -------
    dict or None
        Earlier score and pass state.
    """
    base = Path("runs") / "regression" / test_id
    paths = _earlier_results(base, current)
    if not paths:
        return None
    data = json.loads(paths[-1].read_text(encoding="utf-8"))
    return _previous_summary(data)


def _earlier_results(base: Path, current: Path) -> list[Path]:
    """Return earlier result files for one test.

    Parameters
    ----------
    base : pathlib.Path
        Test result directory.
    current : pathlib.Path
        Current run directory.

    Returns
    -------
    list of pathlib.Path
        Sorted result files excluding the current run.
    """
    found = base.glob("*/result.json")
    return sorted(path for path in found if path.parent != current)


def _previous_summary(data: dict) -> dict:
    """Return the previous score and pass state.

    Parameters
    ----------
    data : dict
        Earlier result document.

    Returns
    -------
    dict
        Score, pass state, and run directory.
    """
    summary = {"score": data.get("score"), "passed": data.get("passed")}
    summary["run_dir"] = data.get("run_dir")
    return summary


def _delta(result: dict) -> float | None:
    """Return the score change from the previous run.

    Parameters
    ----------
    result : dict
        Current result.

    Returns
    -------
    float or None
        Score delta, or ``None`` when no earlier run exists.
    """
    previous = result.get("previous") or {}
    if "score" not in previous:
        return None
    return round(result["score"] - previous["score"], 4)


def _write_result(result: dict, out: str | None) -> Path:
    """Write a result document to disk.

    Parameters
    ----------
    result : dict
        Result document.
    out : str or None
        Optional explicit path.

    Returns
    -------
    pathlib.Path
        Written path.
    """
    path = Path(out) if out else Path(result["run_dir"]) / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return path


def _report(result: dict, path: Path) -> None:
    """Print one run summary.

    Parameters
    ----------
    result : dict
        Result document.
    path : pathlib.Path
        Written result path.

    Returns
    -------
    None
        The summary is printed.
    """
    status = "PASS" if result["passed"] else "FAIL"
    print(f"{result['id']}: {status} score={result['score']:.2f}")
    print(f"result: {path}")


if __name__ == "__main__":
    main()
