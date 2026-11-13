"""Parse and compare semantic versions."""


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
    raise NotImplementedError("parse is not implemented")


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
    raise NotImplementedError("compare is not implemented")
