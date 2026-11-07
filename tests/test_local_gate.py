"""Offline tests for the opt-in local gate fallback."""

import sys
import tempfile
import unittest
from pathlib import Path

from meta_harness.docker_gate import LocalGate


class LocalGateTests(unittest.TestCase):
    """Verify non-isolated host command execution."""

    def test_passing_command(self) -> None:
        """A zero exit status passes and is marked non-isolated."""
        with tempfile.TemporaryDirectory() as directory:
            result = LocalGate().run(Path(directory), "echo ok")
        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 1.0)
        self.assertFalse(result["isolated"])

    def test_failing_command(self) -> None:
        """A nonzero exit status fails and preserves the code."""
        command = f'"{sys.executable}" -c "import sys; sys.exit(3)"'
        with tempfile.TemporaryDirectory() as directory:
            result = LocalGate().run(Path(directory), command)
        self.assertFalse(result["passed"])
        self.assertEqual(result["returncode"], 3)
        self.assertFalse(result["isolated"])

    def test_missing_command(self) -> None:
        """A command that cannot start fails closed."""
        with tempfile.TemporaryDirectory() as directory:
            result = LocalGate().run(
                Path(directory), "definitely-not-a-command-xyz"
            )
        self.assertFalse(result["passed"])
        self.assertTrue(result.get("returncode") or result.get("error"))


if __name__ == "__main__":
    unittest.main()
