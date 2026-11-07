"""Load local environment assignments without overriding the shell."""

import os
from pathlib import Path


def load_env(path: Path | str = ".env") -> None:
    """Load ``KEY=VALUE`` lines from an environment file.

    Parameters
    ----------
    path : pathlib.Path or str
        Environment file path.

    Returns
    -------
    None
        The environment is updated without overriding existing values.
    """
    file = Path(path)
    if file.exists():
        for line in file.read_text().splitlines():
            _load_line(line)


def _load_line(line: str) -> None:
    """Load one environment assignment.

    Parameters
    ----------
    line : str
        Environment file line.

    Returns
    -------
    None
        A valid assignment is loaded.
    """
    text = line.strip()
    if "=" in text and not text.startswith("#"):
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
