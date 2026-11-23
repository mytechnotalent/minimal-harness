"""Summarize parsed log lines."""


def summarize(lines):
    """Summarize a sequence of log lines.

    Parameters
    ----------
    lines : iterable of str
        Log lines to summarize.

    Returns
    -------
    dict
        Counts, invalid count, and first and last timestamps.
    """
    raise NotImplementedError("summarize is not implemented")


def filter_level(lines, level):
    """Return messages at one level.

    Parameters
    ----------
    lines : iterable of str
        Log lines to filter.

    level : str
        Level to keep.

    Returns
    -------
    list of str
        Matching messages in order.
    """
    raise NotImplementedError("filter_level is not implemented")
