"""Constrained Docker execution for candidate checks."""

import json
import subprocess
from pathlib import Path
from typing import Any

DOCKER_LIMITS = [
    "--rm",
    "--network=none",
    "--cpus=1",
    "--memory=512m",
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges:true",
    "--pids-limit=128",
]


class DockerGate:
    """Run candidate commands in a resource-limited container."""

    def __init__(self, image: str = "python:3.12-slim") -> None:
        """Choose the container image.

        Parameters
        ----------
        image : str
            Docker image used for checks.

        Returns
        -------
        None
            This initializer mutates the gate instance.
        """
        self.image = image

    def run(self, candidate_dir: Path, command: list[str]) -> dict[str, Any]:
        """Execute a command against a read-only directory.

        Parameters
        ----------
        candidate_dir : pathlib.Path
            Candidate directory to mount.
        command : list[str]
            Container command and arguments.

        Returns
        -------
        dict[str, Any]
            Gate status, score, and output.
        """
        if not self._available():
            return {
                "passed": False,
                "score": 0.0,
                "error": "Docker is unavailable",
            }
        return self._result(self._run(candidate_dir, command))

    def _available(self) -> bool:
        """Check whether Docker is reachable.

        Returns
        -------
        bool
            Whether Docker reports healthy information.
        """
        return (
            subprocess.run(["docker", "info"], capture_output=True).returncode
            == 0
        )

    def _run(
        self, candidate_dir: Path, command: list[str]
    ) -> subprocess.CompletedProcess[str]:
        """Run a constrained Docker process.

        Parameters
        ----------
        candidate_dir : pathlib.Path
            Candidate directory to mount.
        command : list[str]
            Container command and arguments.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed process result.
        """
        return subprocess.run(
            self._docker_command(candidate_dir, command),
            capture_output=True,
            text=True,
            timeout=180,
        )

    def _docker_command(
        self, candidate_dir: Path, command: list[str]
    ) -> list[str]:
        """Build a constrained Docker command.

        Parameters
        ----------
        candidate_dir : pathlib.Path
            Candidate directory to mount.
        command : list[str]
            Container command and arguments.

        Returns
        -------
        list[str]
            Docker CLI argument vector.
        """
        return [
            "docker",
            "run",
            *self._limits(),
            *self._mount(candidate_dir),
            self.image,
            *command,
        ]

    def _limits(self) -> list[str]:
        """Return Docker isolation flags.

        Returns
        -------
        list[str]
            Docker flags.
        """
        return DOCKER_LIMITS[:]

    def _mount(self, candidate_dir: Path) -> list[str]:
        """Return the candidate mount.

        Parameters
        ----------
        candidate_dir : pathlib.Path
            Candidate directory.

        Returns
        -------
        list[str]
            Docker mount arguments.
        """
        return ["-v", f"{candidate_dir.resolve()}:/candidate:ro"]

    def _result(
        self, result: subprocess.CompletedProcess[str]
    ) -> dict[str, Any]:
        """Convert process output into a gate result.

        Parameters
        ----------
        result : subprocess.CompletedProcess[str]
            Completed Docker process.

        Returns
        -------
        dict[str, Any]
            Normalized pass/fail result.
        """
        passed = result.returncode == 0
        return {
            "passed": passed,
            "score": float(passed),
            "returncode": result.returncode,
            "stdout": result.stdout[-10000:],
            "stderr": result.stderr[-10000:],
        }


def load_gate_result(path: Path) -> dict[str, Any]:
    """Load a JSON gate result.

    Parameters
    ----------
    path : pathlib.Path
        JSON file containing a gate result.

    Returns
    -------
    dict[str, Any]
        Decoded gate result.
    """
    return json.loads(path.read_text())
