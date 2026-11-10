"""Pure text helpers shared by voice input and speech output."""

import re

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE = re.compile(r"`([^`]*)`")
_MARKUP = re.compile(r"[*_#>~|]")
_NUMBER_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)


def speech_text(answer: str) -> str:
    """Convert assistant markdown into speakable plain text.

    Parameters
    ----------
    answer : str
        Assistant response, possibly containing markdown.

    Returns
    -------
    str
        Plain text suitable for a speech synthesizer.
    """
    text = _FENCE.sub(" Code block omitted. ", answer)
    text = _INLINE.sub(r"\1", text)
    text = _MARKUP.sub("", text)
    return " ".join(text.split())


def match_option(transcript: str, options: list[str]) -> str:
    """Resolve a spoken reply into an option or free text.

    Parameters
    ----------
    transcript : str
        Recognized speech.
    options : list[str]
        Suggested answers.

    Returns
    -------
    str
        Matched option, or the spoken text when nothing matches.
    """
    said = " ".join(transcript.split())
    if not said:
        return "no answer"
    return _resolve(said, options)


def _resolve(said: str, options: list[str]) -> str:
    """Resolve normalized speech to one suggested option.

    Parameters
    ----------
    said : str
        Normalized spoken text.

    options : list of str
        Suggested answers.

    Returns
    -------
    str
        Matching option, or the spoken text when nothing matches.
    """
    exact = _exact_option(said, options)
    if exact:
        return exact
    return _spoken_choice(said, options) or said


def _exact_option(said: str, options: list[str]) -> str:
    """Find an option matched by text.

    Parameters
    ----------
    said : str
        Normalized spoken text.

    options : list of str
        Suggested answers.

    Returns
    -------
    str
        Matching option text, or an empty string.
    """
    lowered = said.lower()
    for option in options:
        if lowered == option.strip().lower():
            return option
    for option in options:
        if option.strip().lower() in lowered:
            return option
    return ""


def _spoken_choice(said: str, options: list[str]) -> str:
    """Find an option selected by number or number word.

    Parameters
    ----------
    said : str
        Normalized spoken text.

    options : list of str
        Suggested answers.

    Returns
    -------
    str
        Selected option text, or an empty string.
    """
    index = _word_number(said.lower().strip(" ."))
    if 1 <= index <= len(options):
        return options[index - 1]
    return ""


def _word_number(said: str) -> int:
    """Convert a spoken number or number word to an index.

    Parameters
    ----------
    said : str
        Lowercase text that may hold a number.

    Returns
    -------
    int
        One-based index, or zero when no number is present.
    """
    if said.isdigit():
        return int(said)
    if said in _NUMBER_WORDS:
        return _NUMBER_WORDS.index(said) + 1
    return 0
