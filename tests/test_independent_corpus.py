"""Validate the independent repository corpus."""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from meta_harness.task_evaluator import score_workspace

ROOT = Path(__file__).resolve().parent.parent / "benchmarks" / "independent"


def _pytest_available() -> bool:
    """Return whether pytest is installed.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        Whether pytest can be imported.
    """
    return importlib.util.find_spec("pytest") is not None


@unittest.skipUnless(_pytest_available(), "pytest is not installed")
class IndependentCorpusTests(unittest.TestCase):
    """Verify every task fails stubbed and passes its reference."""

    def test_tasks_discriminate(self) -> None:
        """Stubs fail while reference solutions pass.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        tasks = json.loads(
            (ROOT / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(tasks), 5)
        for task in tasks:
            self.assertFalse(self._run(task, False), task["id"])
            self.assertTrue(self._run(task, True), task["id"])

    def _run(self, task, reference) -> bool:
        """Run one task's hidden test.

        Parameters
        ----------
        task : dict
            Task record.

        reference : bool
            Whether to overlay the reference solution.

        Returns
        -------
        bool
            Whether the hidden test passed.
        """
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            shutil.copytree(ROOT / task["workspace"], root, dirs_exist_ok=True)
            if reference:
                shutil.copytree(
                    ROOT / task["reference"], root, dirs_exist_ok=True
                )
            return _passes(ROOT, root, task)


def _passes(source_root, workspace, task) -> bool:
    """Run a task's hidden test in a workspace.

    Parameters
    ----------
    source_root : pathlib.Path
        Corpus root.

    workspace : pathlib.Path
        Workspace copy.

    task : dict
        Task record.

    Returns
    -------
    bool
        Whether the hidden test passed.
    """
    test = source_root / task["test"]
    return score_workspace(workspace, test, task["runner"])[0]


if __name__ == "__main__":
    unittest.main()
