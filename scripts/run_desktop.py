"""Entry point for the macOS app bundle."""

import os
from pathlib import Path


def main() -> None:
    """Switch to the repository and launch the desktop app.

    Returns
    -------
    None
        The app runs.
    """
    home = os.environ.get("HARNESS_HOME")
    root = Path(home) if home else Path(__file__).resolve().parent.parent
    os.chdir(root)
    from gui.app import main as launch

    launch()


if __name__ == "__main__":
    main()
