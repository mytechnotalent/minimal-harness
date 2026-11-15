"""Offline tests for constrained project-test execution."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.sandbox import TestSandbox


class SandboxTests(unittest.TestCase):
    """Verify the test sandbox command and result handling."""

    def test_command_includes_isolation(self) -> None:
        """The Docker command disables networking and mounts the workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        command = TestSandbox()._command(
            Path("/tmp/ws"), ["python", "-m", "pytest"]
        )
        self.assertIn("--network=none", command)
        self.assertTrue(
            any(part.endswith(":/workspace:rw") for part in command)
        )
        self.assertEqual(command[-3:], ["python", "-m", "pytest"])

    def test_run_parses_result(self) -> None:
        """A successful container run reports a pass and its output.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        result = subprocess.CompletedProcess([], 0, "ok", "")
        with patch.object(TestSandbox, "_available", return_value=True):
            with patch(
                "meta_harness.sandbox.subprocess.run", return_value=result
            ):
                passed, output = TestSandbox().run("/tmp/ws", ["python"])
        self.assertTrue(passed)
        self.assertIn("ok", output)

    def test_run_reports_missing_docker(self) -> None:
        """A missing Docker daemon fails closed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.object(TestSandbox, "_available", return_value=False):
            passed, output = TestSandbox().run("/tmp/ws", ["python"])
        self.assertFalse(passed)
        self.assertIn("Docker", output)
