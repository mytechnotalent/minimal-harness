"""Parse one log line."""

import re

_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


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
    parts = line.strip().split(maxsplit=2)
    if len(parts) != 3:
        return None
    stamp, level, message = parts
    if level not in _LEVELS or not _TIME.fullmatch(stamp):
        return None
    return {"time": stamp, "level": level, "message": message.strip()}
