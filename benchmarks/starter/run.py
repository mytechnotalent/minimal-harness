"""Score a Python solution string against the starter manifest.

Usage:
    python benchmarks/starter/run.py path/to/solution.py
"""

import sys
from pathlib import Path

from meta_harness.task_evaluator import (
    TaskResult,
    load_manifest,
    score_candidate,
)


def main() -> int:
    """Score the solution passed on the command line.

    Returns
    -------
    int
        Process exit code.
    """
    if len(sys.argv) != 2:
        print("usage: run.py PATH_TO_SOLUTION.py", file=sys.stderr)
        return 2
    root = Path(__file__).parent
    manifest = load_manifest(root / "manifest.json")
    code = Path(sys.argv[1]).read_text(encoding="utf-8")
    rate, results = score_candidate(code, root, manifest)
    _report(rate, results)
    return 0


def _report(rate: float, results: list[TaskResult]) -> None:
    """Print per-task marks and the pass rate.

    Parameters
    ----------
    rate : float
        Overall pass rate.
    results : list[TaskResult]
        Per-task results.
    """
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"  {mark}  {result.task_id}")
    print(f"pass rate: {rate * 100:.0f}%")


if __name__ == "__main__":
    sys.exit(main())
