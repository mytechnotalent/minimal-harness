"""Tests for OS-level answer-mode shell confinement."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.bash_sandbox import SandboxUnavailable
from meta_harness.bash_sandbox import sandbox_argv
from meta_harness.tools import ToolError
from meta_harness.tools import ToolRegistry


class SandboxModeTests(unittest.TestCase):
    """Verify sandbox mode selection and missing-tool failures."""

    def test_host_mode_returns_none(self) -> None:
        """An explicit host mode skips confinement.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The result is ``None``.
        """
        with patch.dict(os.environ, {"HARNESS_BASH_SANDBOX": "host"}):
            self.assertIsNone(sandbox_argv(Path("/workspace"), "ls"))

    def test_unknown_mode_raises(self) -> None:
        """An unknown mode is rejected instead of silently running.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ``SandboxUnavailable`` is raised.
        """
        with patch.dict(os.environ, {"HARNESS_BASH_SANDBOX": "bogus"}):
            with self.assertRaises(SandboxUnavailable):
                sandbox_argv(Path("/workspace"), "ls")

    def test_missing_sandbox_raises(self) -> None:
        """A missing sandbox tool fails closed.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ``SandboxUnavailable`` is raised.
        """
        with patch.dict(os.environ, {"HARNESS_BASH_SANDBOX": "auto"}):
            with patch(
                "meta_harness.bash_sandbox.shutil.which",
                return_value=None,
            ):
                with self.assertRaises(SandboxUnavailable):
                    sandbox_argv(Path("/workspace"), "ls")

    def test_root_bind_is_refused(self) -> None:
        """The sandbox refuses to bind the filesystem root.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ``SandboxUnavailable`` is raised.
        """
        with patch.dict(os.environ, {"HARNESS_BASH_SANDBOX": "auto"}):
            with self.assertRaises(SandboxUnavailable):
                sandbox_argv(Path("/"), "ls")


class LinuxSandboxTests(unittest.TestCase):
    """Verify the bubblewrap argument vector."""

    def test_linux_argv_uses_bwrap(self) -> None:
        """The Linux command is wrapped and network is isolated.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Required flags are present.
        """
        with patch.dict(os.environ, {"HARNESS_BASH_SANDBOX": "auto"}):
            argv = _linux_argv()
        self.assertEqual(Path(argv[0]).name, "bwrap")
        self.assertIn("--unshare-net", argv)
        self.assertIn("--ro-bind-try", argv)
        self.assertEqual(argv[-3:], ["/bin/sh", "-c", "ls"])

    def test_network_flag_removes_isolation(self) -> None:
        """An opt-in network mode omits the network namespace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ``--unshare-net`` is absent.
        """
        env = {"HARNESS_BASH_SANDBOX": "auto", "HARNESS_BASH_NETWORK": "1"}
        with patch.dict(os.environ, env):
            argv = _linux_argv()
        self.assertNotIn("--unshare-net", argv)


class MacSandboxTests(unittest.TestCase):
    """Verify the sandbox-exec profile."""

    def test_macos_argv_uses_sandbox_exec(self) -> None:
        """The macOS command carries a write-confining profile.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The profile denies network and host writes.
        """
        with patch.dict(os.environ, {"HARNESS_BASH_SANDBOX": "auto"}):
            argv = _macos_argv()
        self.assertEqual(argv[0], "/usr/bin/sandbox-exec")
        self.assertIn("(deny network*)", argv[2])
        self.assertIn("(deny file-write*)", argv[2])


class BashTimeoutTests(unittest.TestCase):
    """Verify a hung command cannot crash the agent."""

    def test_timeout_is_reported(self) -> None:
        """A timeout becomes exit code 124 with a message.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The result carries the timeout exit code.
        """
        registry = ToolRegistry(".")
        with patch("meta_harness.tools.sandbox_argv", return_value=None):
            with patch("meta_harness.tools.subprocess.run") as run:
                run.side_effect = subprocess.TimeoutExpired("cmd", 1)
                result = registry.bash("sleep 1", timeout=1)
        self.assertEqual(result["returncode"], 124)
        self.assertIn("timed out", result["stderr"])

    def test_sandbox_unavailable_becomes_tool_error(self) -> None:
        """An unavailable sandbox is reported as a tool error.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ``ToolError`` is raised.
        """
        registry = ToolRegistry(".")
        with patch(
            "meta_harness.tools.sandbox_argv",
            side_effect=SandboxUnavailable("no sandbox"),
        ):
            with self.assertRaises(ToolError):
                registry.bash("echo hi")

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap not installed")
    def test_real_linux_sandbox_runs_command(self) -> None:
        """A real bubblewrap run writes inside the workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The command output and file are present.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.dict(os.environ, {"HARNESS_BASH_SANDBOX": "os"}):
                result = ToolRegistry(root).bash("echo hello > out.txt")
            self.assertEqual(result["returncode"], 0)
            self.assertEqual((root / "out.txt").read_text(), "hello\n")


def _linux_argv() -> list[str]:
    """Build a Linux argument vector with a fake bwrap path.

    Parameters
    ----------
    None

    Returns
    -------
    list of str
        Sandboxed argument vector.
    """
    with patch(
        "meta_harness.bash_sandbox.shutil.which",
        return_value="/usr/bin/bwrap",
    ):
        with patch("meta_harness.bash_sandbox.sys.platform", "linux"):
            return sandbox_argv(Path("/workspace"), "ls")


def _macos_argv() -> list[str]:
    """Build a macOS argument vector with a fake sandbox path.

    Parameters
    ----------
    None

    Returns
    -------
    list of str
        Sandboxed argument vector.
    """
    with patch("meta_harness.bash_sandbox.sys.platform", "darwin"):
        with patch(
            "meta_harness.bash_sandbox.shutil.which",
            return_value="/usr/bin/sandbox-exec",
        ):
            return sandbox_argv(Path("/workspace"), "ls")
