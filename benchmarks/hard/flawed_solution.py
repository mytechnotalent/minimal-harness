"""Flawed hard-benchmark solution used to exercise gate 2."""

import re

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
    """Return milliseconds for a duration string."""
    total = 0
    for amount, unit in re.findall(r"(\d+)([hms])", text):
        total += int(amount) * {"h": 3600000, "m": 60000, "s": 1000}[unit]
    return total


def merge_intervals(intervals):
    """Merge overlapping or touching closed intervals."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def normalize_path(path):
    """Collapse dot segments and duplicate slashes."""
    absolute = path.startswith("/")
    stack = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
        else:
            stack.append(part)
    joined = "/".join(stack)
    if absolute:
        return "/" + joined
    return joined or "."


def roman_to_int(s):
    """Convert a valid Roman numeral to an integer."""
    if not s:
        raise ValueError("empty numeral")
    total = 0
    for index, char in enumerate(s):
        if char not in _ROMAN:
            raise ValueError("invalid numeral")
        value = _ROMAN[char]
        if index + 1 < len(s) and _ROMAN[s[index + 1]] > value:
            total -= value
        else:
            total += value
    return total


def chunk(items, size):
    """Split a list into consecutive chunks."""
    if size <= 0:
        raise ValueError("size must be positive")
    return [
        list(items[index : index + size])
        for index in range(0, len(items), size)
    ]


def balanced_brackets(s):
    """Return whether brackets are balanced and properly nested."""
    stack = []
    for char in s:
        if char in "([{":
            stack.append(char)
        elif char in _BRACKETS:
            if not stack or stack.pop() != _BRACKETS[char]:
                return False
    return not stack


def word_wrap(text, width):
    """Wrap text into lines of at most width characters."""
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
