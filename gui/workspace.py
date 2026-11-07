"""Resolve the project workspace used by the desktop frontends."""

import os
from pathlib import Path


def workspace_root(settings) -> Path:
    """Return the configured project workspace root.

    Parameters
    ----------
    settings : Settings
        Persisted interface settings.

    Returns
    -------
    pathlib.Path
        Existing project workspace directory.
    """
    configured = os.getenv("HARNESS_WORKSPACE") or settings.get("workspace")
    root = Path(str(configured)).expanduser() if configured else default_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_root() -> Path:
    """Return the default project workspace directory.

    Returns
    -------
    pathlib.Path
        User projects directory outside the repository.
    """
    return Path.home() / "HarnessProjects"
