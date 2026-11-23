"""Comparative baseline-vs-harness evaluation CLI."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from meta_harness.env import load_env
from meta_harness.evalbench.baseline import BaselineRunner
from meta_harness.evalbench.cases import load_cases
from meta_harness.evalbench.harness_run import HarnessRunner
from meta_harness.evalbench.report import compare
from meta_harness.evalbench.report import markdown_report
from meta_harness.evalbench.report import repeat_stats
from meta_harness.openrouter import OpenRouterClient

ENV_FLAGS = (
    "HARNESS_PROVIDER",
    "OPENROUTER_MODEL",
    "OPENCODE_MODEL",
    "HARNESS_ANSWER_REVIEW",
    "HARNESS_ANSWER_LEDGER",
    "HARNESS_ANSWER_INVARIANTS",
    "HARNESS_REQUIREMENT_CHECK",
    "HARNESS_ADVERSARIAL_DRAFTS",
    "HARNESS_ANSWER_TESTS",
    "HARNESS_AUTO_VERIFY",
    "HARNESS_CODING_STANDARDS",
)


def main(argv=None) -> int:
    """Run the evaluation CLI and emit reports.

    Parameters
    ----------
    argv : list of str or None
        Command line arguments.

    Returns
    -------
    int
        Exit status, zero on success.
    """
    args = parse_args(argv)
    try:
        return run_evaluation(args)
    except Exception as exc:
        print(f"evaluation failed: {exc}")
        return 1


def parse_args(argv):
    """Parse evaluation CLI arguments.

    Parameters
    ----------
    argv : list of str or None
        Command line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Compare baseline and harness configurations"
    )
    _add_arguments(parser)
    return parser.parse_args(argv)


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register CLI options.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Parser being configured.

    Returns
    -------
    None
        Options are registered.
    """
    parser.add_argument("--cases", required=True, help="json/jsonl case file")
    parser.add_argument("--repeats", type=int, default=1, help="runs/config")
    parser.add_argument("--out", default="", help="output directory")
    parser.add_argument("--model", default="", help="model override")
    parser.add_argument("--web", action="store_true", help="web tools")
    parser.add_argument("--max-turns", type=int, default=8, help="tool turns")


def run_evaluation(args, client=None) -> int:
    """Execute baseline and harness runs and write reports.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    client : Any or None
        Optional model client override for tests.

    Returns
    -------
    int
        Exit status, zero on success.
    """
    cases = load_cases(args.cases)
    client = _live_client(args) if client is None else client
    out = Path(args.out or _default_out())
    baseline = _repeat_runs(cases, client, args, True)
    harness = _repeat_runs(cases, client, args, False)
    _write_reports(out, cases, args, client, baseline, harness)
    print(f"reports written to {out}")
    return 0


def _live_client(args):
    """Build a live client after loading the environment file.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    OpenRouterClient
        Configured model client.
    """
    load_env()
    return OpenRouterClient(model=args.model or None)


def _repeat_runs(
    cases, client, args, baseline: bool
) -> list[list[dict[str, Any]]]:
    """Run every case once per repeat for one configuration.

    Parameters
    ----------
    cases : list
        Benchmark cases.
    client : Any
        Model client.
    args : argparse.Namespace
        Parsed arguments.
    baseline : bool
        Use the baseline runner when true.

    Returns
    -------
    list[list[dict[str, Any]]]
        Scored run records per repeat.
    """
    runner = _runner(client, args, baseline)
    return [
        [runner.run_case(case) for case in cases] for _ in range(args.repeats)
    ]


def _runner(client, args, baseline: bool):
    """Build the baseline or harness runner.

    Parameters
    ----------
    client : Any
        Model client.
    args : argparse.Namespace
        Parsed arguments.
    baseline : bool
        Baseline runner when true.

    Returns
    -------
    Any
        Configured runner.
    """
    if baseline:
        return BaselineRunner(client, max_turns=args.max_turns)
    return HarnessRunner(
        client,
        max_turns=args.max_turns,
        web_enabled=args.web,
    )


def _write_reports(out, cases, args, client, baseline, harness) -> None:
    """Write config, records, and comparison reports.

    Parameters
    ----------
    out : pathlib.Path
        Output directory.
    cases : list
        Benchmark cases.
    args : argparse.Namespace
        Parsed arguments.
    client : Any
        Model client.
    baseline : list[list[dict[str, Any]]]
        Baseline records per repeat.
    harness : list[list[dict[str, Any]]]
        Harness records per repeat.

    Returns
    -------
    None
        Report files are written.
    """
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "config.json", _config(args, cases, client))
    _write_jsonl(out / "baseline.jsonl", _flatten(baseline))
    _write_jsonl(out / "harness.jsonl", _flatten(harness))
    _write_comparison(out, cases, args, client, baseline, harness)


def _write_comparison(out, cases, args, client, baseline, harness) -> None:
    """Write the comparison JSON and markdown report.

    Parameters
    ----------
    out : pathlib.Path
        Output directory.
    cases : list
        Benchmark cases.
    args : argparse.Namespace
        Parsed arguments.
    client : Any
        Model client.
    baseline : list[list[dict[str, Any]]]
        Baseline records per repeat.
    harness : list[list[dict[str, Any]]]
        Harness records per repeat.

    Returns
    -------
    None
        Comparison files are written.
    """
    result = compare(baseline[-1], harness[-1])
    result["repeat_stats"] = _repeat_payload(baseline, harness)
    _write_json(out / "comparison.json", result)
    report = _report_text(args, cases, client, result)
    _write_text(out / "report.md", report)


def _repeat_payload(baseline, harness) -> dict[str, Any]:
    """Compute repeat statistics for both configurations.

    Parameters
    ----------
    baseline : list[list[dict[str, Any]]]
        Baseline records per repeat.
    harness : list[list[dict[str, Any]]]
        Harness records per repeat.

    Returns
    -------
    dict[str, Any]
        Per-configuration repeat statistics.
    """
    return {
        "baseline": repeat_stats(baseline),
        "harness": repeat_stats(harness),
    }


def _report_text(args, cases, client, comparison) -> str:
    """Render the markdown report for a comparison.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    cases : list
        Benchmark cases.
    client : Any
        Model client.
    comparison : dict[str, Any]
        Comparison payload.

    Returns
    -------
    str
        Markdown report text.
    """
    return markdown_report(comparison, _config(args, cases, client))


def _flatten(runs: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Flatten per-repeat record lists into one list.

    Parameters
    ----------
    runs : list[list[dict[str, Any]]]
        Records per repeat.

    Returns
    -------
    list[dict[str, Any]]
        All records.
    """
    return [record for run in runs for record in run]


def _config(args, cases, client) -> dict[str, Any]:
    """Capture the run configuration for reproducibility.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    cases : list
        Benchmark cases.
    client : Any
        Model client.

    Returns
    -------
    dict[str, Any]
        Configuration payload.
    """
    base = {
        "created_utc": _now(),
        "cases_file": str(args.cases),
        "case_ids": [case.id for case in cases],
        "case_count": len(cases),
    }
    return {**base, **_run_config(args, client)}


def _run_config(args, client) -> dict[str, Any]:
    """Capture run settings and environment flags.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    client : Any
        Model client.

    Returns
    -------
    dict[str, Any]
        Run settings.
    """
    values = {"repeats": args.repeats, "model": client.model}
    values["provider"] = getattr(client, "provider", "")
    values["max_turns"] = args.max_turns
    values["web"] = args.web
    values["env"] = _env_flags()
    return values


def _env_flags() -> dict[str, str]:
    """Collect configured harness environment flags.

    Parameters
    ----------
    None

    Returns
    -------
    dict[str, str]
        Flag name to value, empty when unset.
    """
    return {name: os.environ.get(name, "") for name in ENV_FLAGS}


def _now() -> str:
    """Return the current UTC timestamp string.

    Parameters
    ----------
    None

    Returns
    -------
    str
        ISO timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def _default_out() -> str:
    """Return a timestamped default output directory.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Directory path.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"runs/eval-{stamp}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON file.

    Parameters
    ----------
    path : pathlib.Path
        Destination path.
    payload : dict[str, Any]
        Payload.

    Returns
    -------
    None
        The file is written.
    """
    path.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write one JSONL file.

    Parameters
    ----------
    path : pathlib.Path
        Destination path.
    records : list[dict[str, Any]]
        Records.

    Returns
    -------
    None
        The file is written.
    """
    lines = [json.dumps(record, default=str) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    """Write one text file.

    Parameters
    ----------
    path : pathlib.Path
        Destination path.
    text : str
        Content.

    Returns
    -------
    None
        The file is written.
    """
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
