"""Offline tests for the task-manifest evaluator."""

import unittest
from pathlib import Path

from meta_harness.task_evaluator import load_manifest
from meta_harness.task_evaluator import score_candidate

STARTER = Path(__file__).parent.parent / "benchmarks" / "starter"
VALIDATION = Path(__file__).parent.parent / "benchmarks" / "validation"
HELDOUT = Path(__file__).parent.parent / "benchmarks" / "heldout"
HARD = Path(__file__).parent.parent / "benchmarks" / "hard"


class TaskEvaluatorTests(unittest.TestCase):
    """Verify pass-rate scoring against the starter manifest."""

    def test_reference_solution_scores_full(self) -> None:
        """The reference solution passes every starter task.

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when the rate is 0.0.
        """
        rate, results = self._score("broken_solution.py")
        self.assertEqual(rate, 0.0)
        self.assertFalse(any(item.passed for item in results))

    def test_validation_reference_solution_scores_full(self) -> None:
        """The reference solution passes every validation task.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        rate, results = self._score_reference(VALIDATION)
        self.assertEqual(rate, 1.0)
        self.assertTrue(all(item.passed for item in results))

    def test_heldout_reference_solution_scores_full(self) -> None:
        """The reference solution passes every held-out task.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        rate, results = self._score_reference(HELDOUT)
        self.assertEqual(rate, 1.0)
        self.assertTrue(all(item.passed for item in results))

    def test_hard_reference_solution_scores_full(self) -> None:
        """The hard reference solution passes every hard split.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        code = (HARD / "reference_solution.py").read_text(encoding="utf-8")
        for split in ("search", "validation", "heldout"):
            manifest = load_manifest(HARD / split / "manifest.json")
            rate, _ = score_candidate(code, HARD / split, manifest, timeout=10)
            self.assertEqual(rate, 1.0)

    def test_heldout_missing_functions_score_zero(self) -> None:
        """A solution without held-out functions fails.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        code = "def unused():\n    return 0\n"
        manifest = load_manifest(HELDOUT / "manifest.json")
        rate, _ = score_candidate(code, HELDOUT, manifest, timeout=10)
        self.assertEqual(rate, 0.0)

    def _score_reference(self, root: Path):
        """Score the starter reference solution on a split.

        Parameters
        ----------
        root : pathlib.Path
            Benchmark directory.

        Returns
        -------
        tuple[float, list[TaskResult]]
            Pass rate and per-task results.
        """
        code = (STARTER / "reference_solution.py").read_text(encoding="utf-8")
        manifest = load_manifest(root / "manifest.json")
        return score_candidate(code, root, manifest, timeout=10)

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
