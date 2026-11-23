"""Parse one log line."""


def parse_line(line):
    """Parse one timestamped log line.

    Parameters
    ----------
    line : str
        Line in ``TIMESTAMP LEVEL message`` form.

    Returns
    -------
    dict or None
        Parsed fields, or None for a malformed line.
    """
    raise NotImplementedError("parse_line is not implemented")
