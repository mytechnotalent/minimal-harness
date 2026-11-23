"""Build distributable SavrenAI release archives."""

import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "SavrenAI"


def main() -> int:
    """Build the platform release archive.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Process exit code.
    """
    root = Path(__file__).resolve().parent.parent
    if sys.platform == "win32":
        return _build_windows(root)
    print("Release builds run on Windows only.")
    return 1


def _build_windows(root: Path) -> int:
    """Build and zip the Windows executable folder.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    int
        Process exit code.
    """
    entry = str(root / "scripts" / "run_desktop.py")
    _run(_windows_command(entry), root, None)
    _zip(root / "dist" / APP_NAME, root / f"{APP_NAME}-windows")
    return 0


def _windows_command(entry: str) -> list[str]:
    """Build the PyInstaller one-directory command.

    Parameters
    ----------
    entry : str
        Desktop entry point path.

    Returns
    -------
    list[str]
        Command and arguments.
    """
    prefix = [sys.executable, "-m", "PyInstaller", "--windowed"]
    return [*prefix, "--name", APP_NAME, entry]


def _run(command: list[str], cwd: Path, env: dict | None) -> None:
    """Run one build subprocess.

    Parameters
    ----------
    command : list[str]
        Command and arguments.
    cwd : pathlib.Path
        Working directory.
    env : dict or None
        Environment overrides.

    Returns
    -------
    None
        The command must succeed.
    """
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _zip(source: Path, destination: Path) -> None:
    """Archive a built folder as a zip file.

    Parameters
    ----------
    source : pathlib.Path
        Folder to archive.
    destination : pathlib.Path
        Output path without extension.

    Returns
    -------
    None
        The archive is written next to the source.
    """
    shutil.make_archive(str(destination), "zip", source.parent, source.name)


if __name__ == "__main__":
    raise SystemExit(main())
