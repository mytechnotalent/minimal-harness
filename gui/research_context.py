"""Assemble optional research context without primary conversation leakage."""

from .context import snapshot


def research_context(workspace, include_snapshot):
    """Return workspace context only when the user opts in.

    Parameters
    ----------
    workspace : pathlib.Path or str
        Active project workspace.
    include_snapshot : bool
        Whether the snapshot toggle is enabled.

    Returns
    -------
    str
        Snapshot text or an empty string.
    """
    if not include_snapshot:
        return ""
    return snapshot(workspace)
