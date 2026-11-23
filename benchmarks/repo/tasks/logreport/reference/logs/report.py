"""Summarize parsed log lines."""

from logs.parser import parse_line


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
    counts: dict[str, int] = {}
    stamps = []
    invalid = _collect(lines, counts, stamps)
    return _summary(counts, invalid, stamps)


def _collect(lines, counts, stamps):
    """Collect counts and timestamps from log lines.

    Parameters
    ----------
    lines : iterable of str
        Log lines.

    counts : dict
        Mutable per-level counters.

    stamps : list
        Mutable timestamp list.

    Returns
    -------
    int
        Number of invalid lines.
    """
    invalid = 0
    for item in map(parse_line, lines):
        if item is None:
            invalid += 1
            continue
        counts[item["level"]] = counts.get(item["level"], 0) + 1
        stamps.append(item["time"])
    return invalid


def _summary(counts, invalid, stamps):
    """Build the summary mapping.

    Parameters
    ----------
    counts : dict
        Per-level counters.

    invalid : int
        Number of invalid lines.

    stamps : list
        Valid timestamps in order.

    Returns
    -------
    dict
        Summary with counts and timestamp bounds.
    """
    return {
        "counts": counts,
        "invalid": invalid,
        "first": stamps[0] if stamps else None,
        "last": stamps[-1] if stamps else None,
    }


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
    return [
        item["message"]
        for item in map(parse_line, lines)
        if item is not None and item["level"] == level
    ]
