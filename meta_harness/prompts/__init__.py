"""Load adversarial stage prompts from disk."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load(name: str) -> str:
    """Return the raw prompt text for a stage.

    Parameters
    ----------
    name : str
        Stage identifier such as ``proposer``, ``reviewer``, or
        ``adjudicator``.

    Returns
    -------
    str
        Prompt body with trailing whitespace stripped.
    """
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
