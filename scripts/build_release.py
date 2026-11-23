"""Build distributable SavrenAI release archives."""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "SavrenAI"
_ENV_TEMPLATE = ".env.example"


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
    _run(_installer_command(root), root, None)
    _add_env_template(root)
    _archive(_payload(root), root / f"{APP_NAME}-{_platform_tag()}")
    return 0


def _installer_command(root: Path) -> list[str]:
    """Build the PyInstaller command for this platform.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    list[str]
        Command and arguments.
    """
    flags = ["--noconfirm", "--clean", *_data_flags(root)]
    if sys.platform in ("darwin", "win32"):
        flags.append("--windowed")
    entry = str(root / "scripts" / "run_desktop.py")
    prefix = [sys.executable, "-m", "PyInstaller", *flags]
    return [*prefix, "--name", APP_NAME, entry]


def _data_flags(root: Path) -> list[str]:
    """Build PyInstaller data flags for prompts and assets.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    list[str]
        Add-data argument pairs.
    """
    prompts = root / "meta_harness" / "prompts"
    assets = root / "gui" / "assets"
    return [
        "--add-data",
        _data_pair(prompts, "meta_harness/prompts"),
        "--add-data",
        _data_pair(assets, "gui/assets"),
    ]


def _data_pair(directory: Path, target: str) -> str:
    """Format one PyInstaller data mapping.

    Parameters
    ----------
    directory : pathlib.Path
        Source directory.
    target : str
        Bundle-relative target directory.

    Returns
    -------
    str
        Source-target pair.
    """
    return f"{directory}{os.pathsep}{target}"


def _payload(root: Path) -> Path:
    """Return the built artifact directory for this platform.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    pathlib.Path
        Artifact directory.
    """
    if sys.platform == "darwin":
        return root / "dist" / f"{APP_NAME}.app"
    return root / "dist" / APP_NAME


def _add_env_template(root: Path) -> None:
    """Copy the environment template next to the built artifact.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    None
        The template is copied into the payload.
    """
    payload = _payload(root)
    if sys.platform == "darwin":
        target = payload / "Contents" / "MacOS" / _ENV_TEMPLATE
    else:
        target = payload / _ENV_TEMPLATE
    shutil.copy(root / _ENV_TEMPLATE, target)


def _archive(source: Path, destination: Path) -> None:
    """Zip the built artifact directory.

    Parameters
    ----------
    source : pathlib.Path
        Artifact directory.
    destination : pathlib.Path
        Output path without extension.

    Returns
    -------
    None
        The archive is written.
    """
    if sys.platform == "darwin":
        _run(_ditto_command(source, destination), source.parent, None)
        return
    shutil.make_archive(str(destination), "zip", source.parent, source.name)


def _ditto_command(source: Path, destination: Path) -> list[str]:
    """Build the ditto zip command.

    Parameters
    ----------
    source : pathlib.Path
        Artifact directory.
    destination : pathlib.Path
        Output path without extension.

    Returns
    -------
    list[str]
        Command and arguments.
    """
    target = f"{destination}.zip"
    return ["ditto", "-c", "-k", "--keepParent", str(source), target]


def _platform_tag() -> str:
    """Return the platform label for the archive name.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Platform tag.
    """
    if sys.platform == "darwin":
        return f"macos-{platform.machine()}"
    if sys.platform == "win32":
        return "windows"
    return "linux"


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


if __name__ == "__main__":
    raise SystemExit(main())
