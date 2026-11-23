"""Build distributable SavrenAI release archives."""

import os
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
    if sys.platform == "darwin":
        return _build_darwin(root)
    if sys.platform == "win32":
        return _build_windows(root)
    print("Release builds run on macOS or Windows only.")
    return 1


def _build_darwin(root: Path) -> int:
    """Build, ad-hoc sign, and zip the macOS bundle.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    int
        Process exit code.
    """
    env = dict(os.environ)
    env["SAVRENAI_RELEASE"] = "1"
    _run([sys.executable, "setup_app.py", "py2app"], root, env)
    bundle = root / "dist" / f"{APP_NAME}.app"
    _run(_codesign_command(bundle), root, None)
    _zip(bundle, root / f"{APP_NAME}-macos")
    return 0


def _codesign_command(bundle: Path) -> list[str]:
    """Build the ad-hoc codesign command for one bundle.

    Parameters
    ----------
    bundle : pathlib.Path
        Built application bundle.

    Returns
    -------
    list[str]
        Command and arguments.
    """
    return ["codesign", "--force", "--deep", "-s", "-", str(bundle)]


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
    """Archive a bundle or folder with ditto.

    Parameters
    ----------
    source : pathlib.Path
        Bundle or folder to archive.
    destination : pathlib.Path
        Output path without extension.

    Returns
    -------
    None
        The archive is written next to the source.
    """
    if sys.platform != "darwin":
        shutil.make_archive(
            str(destination), "zip", source.parent, source.name
        )
        return
    _run(_ditto_command(source, destination), source.parent, None)


def _ditto_command(source: Path, destination: Path) -> list[str]:
    """Build the ditto zip command.

    Parameters
    ----------
    source : pathlib.Path
        Bundle or folder to archive.
    destination : pathlib.Path
        Output path without extension.

    Returns
    -------
    list[str]
        Command and arguments.
    """
    target = f"{destination}.zip"
    return ["ditto", "-c", "-k", "--keepParent", str(source), target]


if __name__ == "__main__":
    raise SystemExit(main())
