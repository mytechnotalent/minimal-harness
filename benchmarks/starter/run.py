"""Score a Python solution string against the starter manifest.

Usage:
    python benchmarks/starter/run.py path/to/solution.py
"""

import sys
from pathlib import Path

from meta_harness.task_evaluator import TaskResult
from meta_harness.task_evaluator import load_manifest
from meta_harness.task_evaluator import score_candidate


def main() -> int:
    """Score the solution passed on the command line.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Process exit code.
    """
    if len(sys.argv) != 2:
        print("usage: run.py PATH_TO_SOLUTION.py", file=sys.stderr)
        return 2
    _score(Path(sys.argv[1]))
    return 0


def _score(solution: Path) -> None:
    """Score one solution file against the starter manifest.

    Parameters
    ----------
    solution : pathlib.Path
        Path to the candidate solution.

    Returns
    -------
    None
        Per-task marks and the pass rate are printed.
    """
    root = Path(__file__).parent
    manifest = load_manifest(root / "manifest.json")
    code = solution.read_text(encoding="utf-8")
    rate, results = score_candidate(code, root, manifest)
    _report(rate, results)


def _report(rate: float, results: list[TaskResult]) -> None:
    """Print per-task marks and the pass rate.

    Parameters
    ----------
    rate : float
        Overall pass rate.

    results : list[TaskResult]
        Per-task results.

    Returns
    -------
    None
        One line per task plus a summary line is printed.
    """
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"  {mark}  {result.task_id}")
    print(f"pass rate: {rate * 100:.0f}%")


if __name__ == "__main__":
    sys.exit(main())
