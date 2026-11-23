"""Score recorded eval runs with the official BFCL evaluator."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any


def serialize_calls(calls: list[dict[str, Any]]) -> str:
    """Render recorded tool calls as Python call text.

    Parameters
    ----------
    calls : list[dict[str, Any]]
        Recorded tool-call records with name and arguments.

    Returns
    -------
    str
        Comma-separated Python call syntax.
    """
    parts = []
    for call in calls:
        name = call.get("name", "")
        arguments = call.get("arguments") or {}
        rendered = _argument_text(arguments)
        parts.append(f"{name}({rendered})")
    return ", ".join(parts)


def _argument_text(arguments: dict[str, Any]) -> str:
    """Render one argument mapping as Python call text.

    Parameters
    ----------
    arguments : dict[str, Any]
        Argument values.

    Returns
    -------
    str
        Comma-separated keyword assignments.
    """
    return ", ".join(f"{key}={value!r}" for key, value in arguments.items())


def build_model_result(path: Path) -> list[dict[str, str]]:
    """Build official-format model result entries from run records.

    Parameters
    ----------
    path : pathlib.Path
        JSONL run records.

    Returns
    -------
    list[dict[str, str]]
        Entries with id and serialized result text.
    """
    entries = []
    for line in path.read_text().splitlines():
        record = json.loads(line)
        text = serialize_calls(record.get("tool_calls") or [])
        entries.append({"id": record["case_id"], "result": text})
    return entries


def official_score(
    records: list[dict[str, str]], label: str, out: Path
) -> float:
    """Score one configuration with the official checker.

    Parameters
    ----------
    records : list[dict[str, str]]
        Official-format model result entries.
    label : str
        Configuration label.
    out : pathlib.Path
        Score output directory.

    Returns
    -------
    float
        Official accuracy.
    """
    table = _run_official(records, label, out)
    return table["gorilla-openfunctions-v2"]["simple_python"]["accuracy"]


def _run_official(
    records: list[dict[str, str]], label: str, out: Path
) -> dict[str, Any]:
    """Run the official checker for one configuration.

    Parameters
    ----------
    records : list[dict[str, str]]
        Official-format model result entries.
    label : str
        Configuration label.
    out : pathlib.Path
        Score output directory.

    Returns
    -------
    dict[str, Any]
        Official leaderboard table.
    """
    evaluator, handler = _official_tools(label)
    table: dict[str, Any] = {}
    _evaluate(evaluator, records, out, handler, table)
    return table


def _official_tools(label: str):
    """Import the checker and build the Gorilla handler.

    Parameters
    ----------
    label : str
        Configuration label.

    Returns
    -------
    tuple
        Checker module and handler instance.
    """
    evaluator = importlib.import_module("bfcl_eval.eval_checker.eval_runner")
    module = importlib.import_module(
        "bfcl_eval.model_handler.api_inference.gorilla"
    )
    handler = module.GorillaHandler(
        "gorilla-openfunctions-v2", 0, label, False
    )
    return evaluator, handler


_DEFAULTS = {
    "test_category": "simple_python",
    "result_dir": Path("result_dir"),
    "model_name": "gorilla-openfunctions-v2",
}


def _evaluate(evaluator, records, out, handler, table) -> None:
    """Run one official scoring pass.

    Parameters
    ----------
    evaluator : module
        Imported BFCL evaluator module.
    records : list[dict[str, str]]
        Official-format model result entries.
    out : pathlib.Path
        Score output directory.
    handler : Any
        Gorilla handler instance.
    table : dict[str, Any]
        Leaderboard table mutated in place.

    Returns
    -------
    None
        The table is updated in place.
    """
    kwargs = dict(_DEFAULTS)
    kwargs["score_dir"] = out
    kwargs["model_result"] = records
    kwargs["handler"] = handler
    kwargs["leaderboard_table"] = table
    kwargs["allow_missing"] = True
    evaluator.evaluate_task(**kwargs)


def main(argv=None) -> int:
    """Score a run directory with the official BFCL evaluator.

    Parameters
    ----------
    argv : list of str or None
        Command line arguments.

    Returns
    -------
    int
        Exit status.
    """
    args = parse_args(argv)
    scores = {}
    for label in ("baseline", "harness"):
        records = build_model_result(Path(args.run_dir) / f"{label}.jsonl")
        scores[label] = official_score(records, label, Path(args.out))
    print(json.dumps(scores, indent=2))
    return 0


def parse_args(argv):
    """Parse command line arguments.

    Parameters
    ----------
    argv : list of str or None
        Command line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="eval run directory")
    parser.add_argument(
        "--out", default="runs/bfcl-official", help="score dir"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
