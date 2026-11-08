"""Entry point for the macOS app bundle."""

import os
import sys
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
    _prefer_repository(root)
    from gui.app import main as launch

    launch()


def _prefer_repository(root: Path) -> None:
    """Put the repository ahead of py2app's build copies.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    None
        ``sys.path`` is updated.
    """
    text = str(root)
    if text in sys.path:
        sys.path.remove(text)
    sys.path.insert(0, text)


if __name__ == "__main__":
    main()
