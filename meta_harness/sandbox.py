"""Constrained Docker execution for project test verification."""

import subprocess
from pathlib import Path

from .docker_gate import DOCKER_LIMITS

DEFAULT_TEST_IMAGE = "savrenai-test:latest"


class TestSandbox:
    """Run project tests inside a network-disabled container."""

    def __init__(self, image: str = DEFAULT_TEST_IMAGE) -> None:
        """Choose the container image.

        Parameters
        ----------
        image : str
            Image containing the test runner.

        Returns
        -------
        None
            This initializer mutates the sandbox instance.
        """
        self.image = image

    def run(
        self, root: Path | str, command: list[str], timeout: int = 120
    ) -> tuple[bool, str]:
        """Run one test command against a workspace.

        Parameters
        ----------
        root : pathlib.Path or str
            Workspace root.
        command : list[str]
            Container command and arguments.
        timeout : int
            Timeout in seconds.

        Returns
        -------
        tuple[bool, str]
            Whether tests passed, and combined output.
        """
        if not self._available():
            return False, "Docker is unavailable"
        result = self._execute(Path(root), command, timeout)
        output = f"{result.stdout}\n{result.stderr}".strip()
        return result.returncode == 0, output

    def _execute(
        self, root: Path, command: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        """Run one sandbox command.

        Parameters
        ----------
        root : pathlib.Path
            Workspace root.
        command : list[str]
            Container command.
        timeout : int
            Timeout in seconds.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed process.
        """
        return subprocess.run(
            self._command(root, command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _available(self) -> bool:
        """Return whether Docker is reachable.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            Whether ``docker info`` succeeds.
        """
        return (
            subprocess.run(["docker", "info"], capture_output=True).returncode
            == 0
        )

    def _command(self, root: Path, command: list[str]) -> list[str]:
        """Build the constrained Docker command.

        Parameters
        ----------
        root : pathlib.Path
            Workspace root.
        command : list[str]
            Container command.

        Returns
        -------
        list[str]
            Docker argument vector.
        """
        return ["docker", "run", *self._flags(root), self.image, *command]

    def _flags(self, root: Path) -> list[str]:
        """Return the isolation and mount flags.

        Parameters
        ----------
        root : pathlib.Path
            Workspace root.

        Returns
        -------
        list[str]
            Docker flags.
        """
        return [*DOCKER_LIMITS, *self._mount_flags(root)]

    def _mount_flags(self, root: Path) -> list[str]:
        """Return the writable workspace mount flags.

        Parameters
        ----------
        root : pathlib.Path
            Workspace root.

        Returns
        -------
        list[str]
            Docker mount flags.
        """
        mount = f"{root.resolve()}:/workspace:rw"
        return ["--tmpfs", "/tmp", "-v", mount, "-w", "/workspace"]
