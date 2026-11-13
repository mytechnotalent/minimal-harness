import io
import re
from collections.abc import Mapping
from typing import Final
from typing import NamedTuple

from .exceptions import ParseError

COMMENTCHARS = "#;"
UTF8_BOM: Final = "\N{BYTE ORDER MARK}"
# characters str.splitlines() treats as line breaks besides \n, \r\n and \r
_OTHER_LINE_SEPARATORS: Final = re.compile(
    "[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]"
)


class ParsedLine(NamedTuple):
    lineno: int
    section: str | None
    name: str | None
    value: list[str] | None


def parse_ini_data(
    path: str,
    data: str,
    *,
    strip_inline_comments: bool,
    strip_section_whitespace: bool = False,
) -> tuple[
    Mapping[str, Mapping[str, str]], Mapping[tuple[str, str | None], int]
]:
    """Parse INI data and return sections and sources mappings.

    Args:
        path: Path for error messages
        data: INI content as string
        strip_inline_comments: Whether to strip inline comments from values
        strip_section_whitespace: Strip whitespace from section and key
            names (default: False). Addresses issue #4 by stripping
            Unicode whitespace.

    Returns:
        Tuple of (sections_data, sources) where:
        - sections_data: mapping of section -> {name -> value}
        - sources: mapping of (section, name) -> line number
    """
    data = data.removeprefix(UTF8_BOM)

    tokens = parse_lines(
        path,
        split_lines(path, data),
        strip_inline_comments=strip_inline_comments,
        strip_section_whitespace=strip_section_whitespace,
    )

    sources: dict[tuple[str, str | None], int] = {}
    sections_data: dict[str, dict[str, str]] = {}

    for lineno, section, name, value in tokens:
        if section is None:
            raise ParseError(path, lineno, "no section header defined")
        sources[section, name] = lineno
        if name is None:
            if section in sections_data:
                raise ParseError(
                    path, lineno, f"duplicate section {section!r}"
                )
            sections_data[section] = {}
        else:
            if name in sections_data[section]:
                raise ParseError(path, lineno, f"duplicate name {name!r}")
            assert value is not None
            sections_data[section][name] = "\n".join(value)

    return sections_data, sources


def split_lines(path: str, data: str) -> list[str]:
    """Split ``data`` into lines on ``\\n``, ``\\r\\n`` and ``\\r`` only.

    A line holding only form feeds (a page break) counts as blank.
    Any other line separator ``str.splitlines()`` knows of raises
    ``ParseError``, as its meaning in an INI file is ambiguous.
    """
    lines = io.StringIO(data, newline=None).readlines()
    for lineno, line in enumerate(lines):
        if line.rstrip("\n").strip("\x0c") == "":
            continue
        if match := _OTHER_LINE_SEPARATORS.search(line):
            raise ParseError(
                path,
                lineno,
                f"unexpected line separator U+{ord(match[0]):04X}",
            )
    return lines


def parse_lines(
    path: str,
    line_iter: list[str],
    *,
    strip_inline_comments: bool = False,
    strip_section_whitespace: bool = False,
) -> list[ParsedLine]:
    result: list[ParsedLine] = []
    section = None
    for lineno, line in enumerate(line_iter):
        name, data = _parseline(
            path, line, lineno, strip_inline_comments, strip_section_whitespace
        )
        # new value
        if name is not None and data is not None:
            result.append(
                ParsedLine(lineno, section, name, [data] if data else [])
            )
        # new section
        elif name is not None and data is None:
            if not name:
                raise ParseError(path, lineno, "empty section name")
            section = name
            result.append(ParsedLine(lineno, section, None, None))
        # continuation
        elif name is None and data is not None:
            value = result[-1].value if result else None
            if value is None:
                raise ParseError(path, lineno, "unexpected value continuation")
            value.append(data)
    return result


def _parseline(
    path: str,
    line: str,
    lineno: int,
    strip_inline_comments: bool,
    strip_section_whitespace: bool,
) -> tuple[str | None, str | None]:
    """Split one physical line into an optional name and value.

    Args:
        path: Path used in error messages.
        line: The physical line, possibly including its line ending.
        lineno: Zero based line number of ``line``.
        strip_inline_comments: Remove trailing ``#`` or ``;`` comments.
        strip_section_whitespace: Strip section names of whitespace.

    Returns:
        A ``(name, value)`` pair. Blank lines and comments yield
        ``(None, None)``, a section header yields ``(name, None)`` and a
        continuation value yields ``(None, value)``.

    Raises:
        ParseError: If the line cannot be interpreted.
    """
    if not line.strip() or iscommentline(line):
        return None, None
    if line.startswith("["):
        return (
            _parse_section(path, line, lineno, strip_section_whitespace),
            None,
        )
    if line[0].isspace():
        return None, _parse_value(path, line, lineno, strip_inline_comments)
    return _parse_name_value(path, line, lineno, strip_inline_comments)


def _parse_section(
    path: str, line: str, lineno: int, strip_section_whitespace: bool
) -> str:
    """Extract the name from a section header line.

    Args:
        path: Path used in error messages.
        line: The physical line starting with ``[``.
        lineno: Zero based line number of ``line``.
        strip_section_whitespace: Strip the extracted name of whitespace.

    Returns:
        The section name as written between the brackets.

    Raises:
        ParseError: If the header has no closing bracket.
    """
    end = line.find("]")
    if end < 0:
        raise ParseError(path, lineno, f"invalid line {line.strip()!r}")
    name = line[1:end]
    return name.strip() if strip_section_whitespace else name


def _parse_value(
    path: str, text: str, lineno: int, strip_inline_comments: bool
) -> str:
    """Turn the raw text of a value into its parsed form.

    Args:
        path: Path used in error messages.
        text: The raw value text, possibly with surrounding whitespace.
        lineno: Zero based line number the text came from.
        strip_inline_comments: Remove a trailing ``#`` or ``;`` comment.

    Returns:
        The whitespace stripped value, unchanged when comment stripping
        is disabled.
    """
    del path, lineno
    value = text.strip()
    return _strip_comment(value) if strip_inline_comments else value


def _strip_comment(value: str) -> str:
    """Remove an inline comment from a value.

    Args:
        value: The already whitespace stripped value.

    Returns:
        The value up to the first comment character, without trailing
        whitespace.
    """
    for index, char in enumerate(value):
        if char in COMMENTCHARS:
            return value[:index].rstrip()
    return value


def _parse_name_value(
    path: str, line: str, lineno: int, strip_inline_comments: bool
) -> tuple[str, str]:
    """Split a ``name = value`` or ``name: value`` line.

    Args:
        path: Path used in error messages.
        line: The physical line holding the assignment.
        lineno: Zero based line number of ``line``.
        strip_inline_comments: Remove a trailing ``#`` or ``;`` comment.

    Returns:
        The stripped name and the parsed value, which may be empty.

    Raises:
        ParseError: If the line holds no delimiter or an empty name.
    """
    index = _find_delimiter(line)
    name = line[:index].strip() if index >= 0 else ""
    if not name:
        raise ParseError(path, lineno, f"invalid line {line.strip()!r}")
    return name, _parse_value(
        path, line[index + 1 :], lineno, strip_inline_comments
    )


def _find_delimiter(line: str) -> int:
    """Find the earliest name/value delimiter in a line.

    Args:
        line: The physical line to inspect.

    Returns:
        The index of the first ``=`` or ``:``, or ``-1`` when absent.
    """
    found = [index for index in map(line.find, ("=", ":")) if index >= 0]
    return min(found, default=-1)


def iscommentline(line: str) -> bool:
    """Report whether a line is a whole line comment.

    Args:
        line: The line to inspect, with or without its line ending.

    Returns:
        True when the stripped line starts with ``#`` or ``;``.
    """
    return line.strip().startswith(("#", ";"))
