"""Entry point for the SavrenAI desktop app bundle."""

import os
import sys
from pathlib import Path

import gui.app


def main() -> None:
    """Switch to the harness home and launch the desktop app.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The app runs.
    """
    _chdir_home()
    gui.app.main()


def _chdir_home() -> None:
    """Move to the harness home or the frozen bundle directory.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The working directory is updated.
    """
    home = os.environ.get("HARNESS_HOME")
    if home:
        os.chdir(home)
        return
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)


if __name__ == "__main__":
    main()
