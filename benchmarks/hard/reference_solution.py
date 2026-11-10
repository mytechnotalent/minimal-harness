"""Reference solution for the hard benchmark."""

import re

_DURATION = re.compile(r"(\d+)(ms|h|m|s)")
_UNIT_MS = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000}
_ROMAN = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}
_BRACKETS = {")": "(", "]": "[", "}": "{"}


def parse_duration(text):
    """Return milliseconds for a duration string.

    Parameters
    ----------
    text : str
        Duration such as ``1h30m`` or ``500ms``.

    Returns
    -------
    int
        Total duration in milliseconds.

    Raises
    ------
    ValueError
        If the text is empty or contains invalid parts.
    """
    value = text.strip()
    if not value:
        raise ValueError("empty duration")
    return _duration_total(value)


def _duration_total(value):
    """Sum the millisecond amounts in a trimmed duration string.

    Parameters
    ----------
    value : str
        Non-empty duration text.

    Returns
    -------
    int
        Total duration in milliseconds.

    Raises
    ------
    ValueError
        If any text is not a recognized duration part.
    """
    total = 0
    position = 0
    for match in _DURATION.finditer(value):
        position = _duration_end(match, position)
        total += _milliseconds(match)
    if position != len(value):
        raise ValueError("invalid duration")
    return total


def _duration_end(match, position):
    """Return the end offset after validating one duration match.

    Parameters
    ----------
    match : re.Match
        Matched amount and unit.

    position : int
        Expected start offset of the match.

    Returns
    -------
    int
        End offset of the match.

    Raises
    ------
    ValueError
        If the match does not start at the expected offset.
    """
    if match.start() != position:
        raise ValueError("invalid duration")
    return match.end()


def _milliseconds(match):
    """Convert one duration match to milliseconds.

    Parameters
    ----------
    match : re.Match
        Matched amount and unit.

    Returns
    -------
    int
        Millisecond value of the match.
    """
    return int(match.group(1)) * _UNIT_MS[match.group(2)]


def merge_intervals(intervals):
    """Merge overlapping or touching closed intervals.

    Parameters
    ----------
    intervals : list of list of int
        Closed ``[start, end]`` intervals in any order.

    Returns
    -------
    list of list of int
        Sorted intervals with overlaps merged.
    """
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        _merge_one(merged, start, end)
    return merged


def _merge_one(merged, start, end):
    """Merge one interval into the accumulated result.

    Parameters
    ----------
    merged : list of list of int
        Accumulated merged intervals.

    start : int
        Start of the next interval.

    end : int
        End of the next interval.

    Returns
    -------
    None
        The merged list is updated in place.
    """
    if start <= merged[-1][1]:
        merged[-1][1] = max(merged[-1][1], end)
    else:
        merged.append([start, end])


def normalize_path(path):
    """Collapse dot segments and duplicate slashes.

    Parameters
    ----------
    path : str
        Path to normalize.

    Returns
    -------
    str
        Normalized path with ``.`` for an empty relative path.
    """
    absolute = path.startswith("/")
    stack = _path_stack(path, absolute)
    joined = "/".join(stack)
    if absolute:
        return "/" + joined
    return joined or "."


def _path_stack(path, absolute):
    """Resolve the path into its component stack.

    Parameters
    ----------
    path : str
        Path to split on slashes.

    absolute : bool
        Whether the path starts at the root.

    Returns
    -------
    list of str
        Resolved path components.
    """
    stack = []
    for part in path.split("/"):
        _push_part(stack, part, absolute)
    return stack


def _push_part(stack, part, absolute):
    """Apply one path component to the component stack.

    Parameters
    ----------
    stack : list of str
        Accumulated path components.

    part : str
        Next path component.

    absolute : bool
        Whether the path starts at the root.

    Returns
    -------
    None
        The stack is updated in place.
    """
    if part in ("", "."):
        return
    if part == "..":
        _pop_parent(stack, absolute)
    else:
        stack.append(part)


def _pop_parent(stack, absolute):
    """Apply one parent-directory component.

    Parameters
    ----------
    stack : list of str
        Accumulated path components.

    absolute : bool
        Whether the path starts at the root.

    Returns
    -------
    None
        The stack is updated in place.
    """
    if stack and stack[-1] != "..":
        stack.pop()
    elif not absolute:
        stack.append("..")


def roman_to_int(s):
    """Convert a valid Roman numeral to an integer.

    Parameters
    ----------
    s : str
        Numeral using ``I``, ``V``, ``X``, ``L``, ``C``, ``D``, and ``M``.

    Returns
    -------
    int
        Integer value of the numeral.

    Raises
    ------
    ValueError
        If the numeral is empty or contains invalid characters.
    """
    if not s:
        raise ValueError("empty numeral")
    total = 0
    for index, char in enumerate(s):
        total += _roman_step(s, index, char)
    return total


def _roman_step(s, index, char):
    """Return the signed contribution of one numeral character.

    Parameters
    ----------
    s : str
        Whole numeral.

    index : int
        Position of the character.

    char : str
        Character being converted.

    Returns
    -------
    int
        Signed value to add to the running total.

    Raises
    ------
    ValueError
        If the character is not a Roman digit.
    """
    if char not in _ROMAN:
        raise ValueError("invalid numeral")
    value = _ROMAN[char]
    following = _ROMAN[s[index + 1]] if index + 1 < len(s) else 0
    if following > value:
        return -value
    return value


def chunk(items, size):
    """Split a list into consecutive chunks.

    Parameters
    ----------
    items : list
        Items to split.

    size : int
        Maximum chunk length.

    Returns
    -------
    list of list
        Consecutive chunks, empty when ``items`` is empty.

    Raises
    ------
    ValueError
        If ``size`` is not positive.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    return [
        list(items[index : index + size])
        for index in range(0, len(items), size)
    ]


def balanced_brackets(s):
    """Return whether brackets are balanced and properly nested.

    Parameters
    ----------
    s : str
        Text containing bracket characters.

    Returns
    -------
    bool
        True when every bracket is closed in the right order.
    """
    stack = []
    for char in s:
        if char in "([{":
            stack.append(char)
        elif char in _BRACKETS:
            if not stack or stack.pop() != _BRACKETS[char]:
                return False
    return not stack


def word_wrap(text, width):
    """Wrap text into lines of at most width characters.

    Parameters
    ----------
    text : str
        Text to wrap.

    width : int
        Maximum line length.

    Returns
    -------
    list of str
        Wrapped lines, empty when the text has no words.
    """
    words = text.split()
    if not words:
        return []
    return _wrap_words(words, width)


def _wrap_words(words, width):
    """Greedily wrap a non-empty list of words.

    Parameters
    ----------
    words : list of str
        Words to wrap.

    width : int
        Maximum line length.

    Returns
    -------
    list of str
        Wrapped lines.
    """
    lines = []
    current = words[0]
    for word in words[1:]:
        current = _wrap_word(lines, current, word, width)
    lines.append(current)
    return lines


def _wrap_word(lines, current, word, width):
    """Append one word to the current line or start a new line.

    Parameters
    ----------
    lines : list of str
        Completed lines.

    current : str
        Line being built.

    word : str
        Next word.

    width : int
        Maximum line length.

    Returns
    -------
    str
        The line that should continue.
    """
    if len(current) + 1 + len(word) <= width:
        return current + " " + word
    lines.append(current)
    return word
