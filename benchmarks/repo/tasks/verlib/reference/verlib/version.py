"""Parse and compare semantic versions."""

import re

_VERSION = re.compile(
    r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?"
)


def parse(text):
    """Parse a semantic version string.

    Parameters
    ----------
    text : str
        Version such as ``1.2.3-alpha.1+build``.

    Returns
    -------
    tuple
        Major, minor, patch, and prerelease identifiers.
    """
    match = _VERSION.fullmatch(text)
    if match is None:
        raise ValueError("invalid version: {!r}".format(text))
    major, minor, patch, pre, _ = match.groups()
    return int(major), int(minor), int(patch), _prerelease(pre)


def _prerelease(text):
    """Return parsed prerelease identifiers.

    Parameters
    ----------
    text : str or None
        Prerelease text without the leading dash.

    Returns
    -------
    tuple
        Integer or string identifiers.
    """
    if not text:
        return ()
    return tuple(
        int(part) if part.isdigit() else part for part in text.split(".")
    )


def compare(left, right):
    """Compare two semantic version strings.

    Parameters
    ----------
    left : str
        First version.

    right : str
        Second version.

    Returns
    -------
    int
        Negative, zero, or positive comparison result.
    """
    first = parse(left)
    second = parse(right)
    if first[:3] != second[:3]:
        return 1 if first[:3] > second[:3] else -1
    return _compare_pre(first[3], second[3])


def _compare_pre(left, right):
    """Compare prerelease identifier tuples.

    Parameters
    ----------
    left : tuple
        Left prerelease identifiers.

    right : tuple
        Right prerelease identifiers.

    Returns
    -------
    int
        Negative, zero, or positive comparison result.
    """
    if not left or not right:
        return _compare_empty(left, right)
    for first, second in zip(left, right):
        result = _compare_identifier(first, second)
        if result:
            return result
    return (len(left) > len(right)) - (len(left) < len(right))


def _compare_empty(left, right):
    """Compare when one side has no prerelease.

    Parameters
    ----------
    left : tuple
        Left prerelease identifiers.

    right : tuple
        Right prerelease identifiers.

    Returns
    -------
    int
        Negative, zero, or positive comparison result.
    """
    if not left and not right:
        return 0
    return 1 if not left else -1


def _compare_identifier(first, second):
    """Compare two prerelease identifiers.

    Parameters
    ----------
    first : int or str
        Left identifier.

    second : int or str
        Right identifier.

    Returns
    -------
    int
        Negative, zero, or positive comparison result.
    """
    if isinstance(first, int) and isinstance(second, int):
        return (first > second) - (first < second)
    if isinstance(first, int):
        return -1
    if isinstance(second, int):
        return 1
    return (first > second) - (first < second)
