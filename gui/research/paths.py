"""Resolve the research data root with a workspace safety guard."""

import os
from pathlib import Path


class ResearchPathError(RuntimeError):
    """Report a research root that overlaps the active workspace."""


def research_root(app_data=None, workspace=None, env=None):
    """Return the resolved research root, creating it when needed.

    Parameters
    ----------
    app_data : pathlib.Path or str or None
        Base application data directory. Defaults to the app default.
    workspace : pathlib.Path or str or None
        Active project workspace to stay outside of.
    env : collections.abc.Mapping or None
        Environment mapping. Defaults to ``os.environ``.

    Returns
    -------
    pathlib.Path
        Created research root directory.
    """
    source = os.environ if env is None else env
    root = _configured_root(source, app_data)
    resolved = root.expanduser().resolve()
    _check_workspace(resolved, workspace)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _configured_root(env, app_data):
    """Return the configured or default research root.

    Parameters
    ----------
    env : collections.abc.Mapping
        Environment mapping.
    app_data : pathlib.Path or str or None
        Base application data directory.

    Returns
    -------
    pathlib.Path
        Research root before resolution.
    """
    configured = env.get("HARNESS_RESEARCH_DIR")
    if configured:
        return Path(configured)
    base = default_app_data() if app_data is None else Path(app_data)
    return base / "research"


def default_app_data():
    """Return the default base data directory.

    Parameters
    ----------
    None

    Returns
    -------
    pathlib.Path
        Source checkout data directory or platform data directory.
    """
    if Path("pyproject.toml").exists():
        return Path("runs")
    return Path(_xdg_base()) / "minimal-harness"


def _xdg_base():
    """Return the XDG data home or a portable fallback.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Base user data directory.
    """
    fallback = Path.home() / ".local" / "share"
    return os.environ.get("XDG_DATA_HOME", str(fallback))


def _check_workspace(root, workspace):
    """Reject a research root inside the active workspace.

    Parameters
    ----------
    root : pathlib.Path
        Resolved research root.
    workspace : pathlib.Path or str or None
        Active workspace, when known.

    Returns
    -------
    None
        The root is accepted.
    """
    if workspace is None:
        return
    active = Path(workspace).expanduser().resolve()
    if root == active or active in root.parents:
        raise ResearchPathError("research root is inside the active workspace")
