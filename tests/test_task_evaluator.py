"""Offline tests for the task-manifest evaluator."""

import unittest
from pathlib import Path

from meta_harness.task_evaluator import load_manifest, score_candidate

STARTER = Path(__file__).parent.parent / "benchmarks" / "starter"


class TaskEvaluatorTests(unittest.TestCase):
    """Verify pass-rate scoring against the starter manifest."""

    def test_reference_solution_scores_full(self) -> None:
        """The reference solution passes every starter task.

        Returns
        -------
        None
            Assertions pass when the rate is 1.0.
        """
        rate, results = self._score("reference_solution.py")
        self.assertEqual(rate, 1.0)
        self.assertTrue(all(item.passed for item in results))

    def test_broken_solution_scores_zero(self) -> None:
        """The broken solution fails every starter task.

        Returns
        -------
        None
            Assertions pass when the rate is 0.0.
        """
        rate, results = self._score("broken_solution.py")
        self.assertEqual(rate, 0.0)
        self.assertFalse(any(item.passed for item in results))

    def _score(self, filename: str):
        """Score a fixture solution against the starter manifest.

        Parameters
        ----------
        filename : str
            Solution filename inside ``benchmarks/starter``.

        Returns
        -------
        tuple[float, list[TaskResult]]
            Pass rate and per-task results.
        """
        code = (STARTER / filename).read_text(encoding="utf-8")
        manifest = load_manifest(STARTER / "manifest.json")
        return score_candidate(code, STARTER, manifest, timeout=10)


if __name__ == "__main__":
    unittest.main()
