"""Entry point for the SavrenAI desktop app bundle."""

import os

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
    home = os.environ.get("HARNESS_HOME")
    if home:
        os.chdir(home)
    gui.app.main()


if __name__ == "__main__":
    main()
