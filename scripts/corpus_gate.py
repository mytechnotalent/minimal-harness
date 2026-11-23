"""Gate a corpus run against a fair Pi baseline."""

import argparse
import json
import shlex
from pathlib import Path

from scripts import ab_pi

FAIR_PI_COMMAND = (
    "pi --provider opencode-go-manual --model deepseek-v4.1-flash "
    "--print --mode text --no-session --tools read,write,edit"
)


def parse_args(argv=None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv : list[str] or None
        Command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    _add_baseline(parser)
    _add_commands(parser)
    return parser.parse_args(argv)


def _add_baseline(parser: argparse.ArgumentParser) -> None:
    """Add manifest, repeat, budget, and threshold options.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Target parser.

    Returns
    -------
    None
        Arguments are registered.
    """
    parser.add_argument(
        "--manifest", default="benchmarks/independent/manifest.json"
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--min-pass", type=float, default=0.52)
    parser.add_argument("--min-gain", type=float, default=0.0)
    parser.add_argument("--out", default="runs/corpus-gate.json")


def _add_commands(parser: argparse.ArgumentParser) -> None:
    """Add agent command options.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Target parser.

    Returns
    -------
    None
        Arguments are registered.
    """
    parser.add_argument(
        "--harness-cmd", default="python -m meta_harness.cli --no-web"
    )
    parser.add_argument("--pi-cmd", default=FAIR_PI_COMMAND)


def gate_passed(
    harness: float, pi: float, min_pass: float, min_gain: float
) -> bool:
    """Return whether a harness result clears the corpus gate.

    Parameters
    ----------
    harness : float
        Harness pass rate.
    pi : float
        Pi pass rate.
    min_pass : float
        Minimum absolute pass rate.
    min_gain : float
        Minimum gain over Pi.

    Returns
    -------
    bool
        ``True`` when both conditions hold.
    """
    return harness >= min_pass and harness >= pi + min_gain


def main(argv=None) -> int:
    """Run the comparison, write the report, and apply the gate.

    Parameters
    ----------
    argv : list[str] or None
        Command-line arguments.

    Returns
    -------
    int
        Zero when the gate passes, otherwise one.
    """
    args = parse_args(argv)
    report = _compare(args)
    ok = _gate(report, args)
    _write_report(args.out, report)
    _print_summary(report, ok)
    return 0 if ok else 1


def _gate(report: dict, args: argparse.Namespace) -> bool:
    """Apply the configured gate to a report.

    Parameters
    ----------
    report : dict
        Comparison report.
    args : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    bool
        ``True`` when the gate passes.
    """
    return gate_passed(
        report["harness"], report["pi"], args.min_pass, args.min_gain
    )


def _print_summary(report: dict, ok: bool) -> None:
    """Print the one-line gate summary.

    Parameters
    ----------
    report : dict
        Comparison report.
    ok : bool
        Gate result.

    Returns
    -------
    None
        The summary is printed.
    """
    state = "pass" if ok else "fail"
    print(
        f"harness={report['harness']:.3f} pi={report['pi']:.3f} gate={state}"
    )


def _compare(args: argparse.Namespace) -> dict:
    """Run the configured comparison.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    dict
        Comparison report.
    """
    harness, pi = _commands(args)
    return ab_pi.compare(
        args.manifest, harness, pi, args.timeout, args.repeats
    )


def _commands(args: argparse.Namespace) -> tuple:
    """Split harness and baseline command strings.

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


def _write_report(path: str, report: dict) -> None:
    """Write a JSON report.

    Parameters
    ----------
    path : str
        Destination path.
    report : dict
        Comparison report.

    Returns
    -------
    None
        The report is written.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
