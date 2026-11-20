"""Run a pre-registered harness campaign with confidence intervals."""

import argparse
import json
import math
import random
import shlex
import sys
from pathlib import Path

from meta_harness.env import load_env
from scripts.ab_pi import compare


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
    _add_options(parser)
    return parser.parse_args(argv)


def _add_options(parser):
    """Attach campaign options to a parser.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Parser to extend.

    Returns
    -------
    None
        Options are added in place.
    """
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--harness-cmd", default=_default_command())
    parser.add_argument("--baseline-cmd", default="pi")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out")


def _default_command() -> str:
    """Return the default harness command.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Shell-quoted harness command.
    """
    return shlex.join([sys.executable, "-m", "meta_harness.cli", "--no-web"])


def wilson(
    successes: float, total: int, z: float = 1.96
) -> tuple[float, float]:
    """Return a Wilson score interval.

    Parameters
    ----------
    successes : float
        Number of successful attempts.
    total : int
        Number of attempts.
    z : float
        Normal quantile.

    Returns
    -------
    tuple of float
        Lower and upper bounds.
    """
    if total == 0:
        return (0.0, 0.0)
    rate = successes / total
    denom = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denom
    margin = _wilson_margin(rate, total, z) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _wilson_margin(rate: float, total: int, z: float) -> float:
    """Return the Wilson half-width before normalization.

    Parameters
    ----------
    rate : float
        Observed rate.
    total : int
        Number of attempts.
    z : float
        Normal quantile.

    Returns
    -------
    float
        Half-width numerator.
    """
    variance = rate * (1 - rate) / total + z * z / (4 * total * total)
    return z * math.sqrt(variance)


def _mean(values) -> float:
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


def _flatten(report: dict, key: str) -> list[float]:
    """Collect per-run values for one agent.

    Parameters
    ----------
    report : dict
        Comparison report.
    key : str
        Agent key, ``harness`` or ``pi``.

    Returns
    -------
    list of float
        Per-run values.
    """
    values = []
    for row in report["tasks"]:
        values.extend(row.get(f"{key}_runs", []))
    return values


def _task_deltas(report: dict) -> list[float]:
    """Return per-task harness-minus-baseline deltas.

    Parameters
    ----------
    report : dict
        Comparison report.

    Returns
    -------
    list of float
        Per-task deltas.
    """
    deltas = []
    for row in report["tasks"]:
        mine = _mean(row.get("harness_runs", []))
        other = _mean(row.get("pi_runs", []))
        deltas.append(mine - other)
    return deltas


def _bootstrap(values: list[float], seed: int, rounds: int) -> tuple:
    """Return a bootstrap confidence interval for a mean.

    Parameters
    ----------
    values : list of float
        Observation values.
    seed : int
        Random seed.
    rounds : int
        Bootstrap rounds.

    Returns
    -------
    tuple of float
        Lower and upper bounds.
    """
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(_resample(values, rng) for _ in range(rounds))
    return (_percentile(means, 0.025), _percentile(means, 0.975))


def _resample(values: list[float], rng: random.Random) -> float:
    """Return one bootstrap mean.

    Parameters
    ----------
    values : list of float
        Observation values.
    rng : random.Random
        Random generator.

    Returns
    -------
    float
        Resampled mean.
    """
    sample = [rng.choice(values) for _ in values]
    return _mean(sample)


def _percentile(values: list[float], fraction: float) -> float:
    """Return one sorted-list percentile.

    Parameters
    ----------
    values : list of float
        Sorted values.
    fraction : float
        Fraction between zero and one.

    Returns
    -------
    float
        Selected value, or zero when empty.
    """
    if not values:
        return 0.0
    index = int(fraction * (len(values) - 1))
    return values[index]


def _agent_summary(report: dict) -> dict:
    """Summarize both agents with Wilson intervals.

    Parameters
    ----------
    report : dict
        Comparison report.

    Returns
    -------
    dict
        Rates and confidence intervals.
    """
    mine = _flatten(report, "harness")
    other = _flatten(report, "pi")
    return {
        "harness_rate": _mean(mine),
        "harness_ci": wilson(sum(mine), len(mine)),
        "baseline_rate": _mean(other),
        "baseline_ci": wilson(sum(other), len(other)),
    }


def summarize(report: dict) -> dict:
    """Add rates, a paired delta, and a bootstrap interval.

    Parameters
    ----------
    report : dict
        Comparison report.

    Returns
    -------
    dict
        Campaign summary.
    """
    deltas = _task_deltas(report)
    summary = _agent_summary(report)
    summary["delta"] = _mean(deltas)
    summary["delta_ci"] = _bootstrap(deltas, 0, 2000)
    return summary


def _emit(report: dict, out: str | None) -> int:
    """Write and print the campaign report.

    Parameters
    ----------
    report : dict
        Campaign report.
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


def _load_repo_env() -> None:
    """Load the repository .env without overriding exported values.

    Parameters
    ----------
    None

    Returns
    -------
    None
        Environment variables are populated.
    """
    load_env(Path(__file__).resolve().parent.parent / ".env")


def main(argv=None) -> int:
    """Run the campaign and emit a summary.

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
    _load_repo_env()
    mine = shlex.split(args.harness_cmd)
    other = shlex.split(args.baseline_cmd)
    report = compare(args.manifest, mine, other, args.timeout, args.repeats)
    report["summary"] = summarize(report)
    return _emit(report, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
