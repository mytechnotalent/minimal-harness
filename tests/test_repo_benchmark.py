"""Validate the multi-file repository benchmark corpus."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from meta_harness.task_evaluator import run_workspace_tests
from meta_harness.task_evaluator import score_workspace

ROOT = Path(__file__).resolve().parent.parent / "benchmarks" / "repo"


def _tasks() -> list[dict]:
    """Return the repository benchmark tasks.

    Parameters
    ----------
    None

    Returns
    -------
    list[dict]
        Task records.
    """
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


class RepoBenchmarkTests(unittest.TestCase):
    """Verify every task fails unmodified and passes its reference."""

    def test_tasks_discriminate(self) -> None:
        """Stubs fail while reference solutions pass.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        tasks = _tasks()
        self.assertEqual(len(tasks), 4)
        for task in tasks:
            self.assertFalse(self._stub_passes(task), task["id"])
            self.assertTrue(self._reference_passes(task), task["id"])

    def _stub_passes(self, task) -> bool:
        """Run a task's hidden test against the stub workspace.

        Parameters
        ----------
        task : dict
            Task record.

        Returns
        -------
        bool
            Whether the stub passed.
        """
        with tempfile.TemporaryDirectory() as workspace:
            shutil.copytree(
                ROOT / task["workspace"], workspace, dirs_exist_ok=True
            )
            return score_workspace(Path(workspace), ROOT / task["test"])[0]

    def _reference_passes(self, task) -> bool:
        """Run a task's hidden test against its reference solution.

        Parameters
        ----------
        task : dict
            Task record.

        Returns
        -------
        bool
            Whether the reference passed.
        """
        with tempfile.TemporaryDirectory() as workspace:
            shutil.copytree(
                ROOT / task["workspace"], workspace, dirs_exist_ok=True
            )
            shutil.copytree(
                ROOT / task["reference"], workspace, dirs_exist_ok=True
            )
            return score_workspace(Path(workspace), ROOT / task["test"])[0]


_REVIEW_TEST = (
    "import unittest\n"
    "from mod import value\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_value(self):\n"
    "        self.assertEqual(value(), 7)\n"
)


class WorkspaceTestRunnerTests(unittest.TestCase):
    """Verify reviewer tests execute inside a workspace."""

    def test_reviewer_tests_run_in_workspace(self) -> None:
        """A reviewer test sees the workspace modules.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            (root / "mod.py").write_text("def value():\n    return 7\n")
            passed, _ = run_workspace_tests(root, [_REVIEW_TEST])
        self.assertTrue(passed)


if __name__ == "__main__":
    unittest.main()
