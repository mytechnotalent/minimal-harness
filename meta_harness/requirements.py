"""Structured requirement states and contradiction checks."""

STATES = (
    "confirmed",
    "proposed",
    "assumed",
    "rejected",
    "deferred",
    "superseded",
    "unknown",
    "contradicted",
)
_SPEC_WORDS = (
    "requirement",
    "requirements",
    "spec",
    "specification",
    "prototype",
    "production",
    "phase 1",
    "phase 2",
    "permission",
    "administrator",
    "audit",
    "deferred",
    "superseded",
)
_UNCONFIRMED = (
    "proposed",
    "assumed",
    "rejected",
    "deferred",
    "superseded",
    "unknown",
)


def needs_requirements(prompt: str, prior: list[str]) -> bool:
    """Return whether evolving requirements need extraction.

    Parameters
    ----------
    prompt : str
        Current user question.
    prior : list of str
        Earlier user requests.

    Returns
    -------
    bool
        ``True`` when a prior turn and a spec word are present.
    """
    if not prior:
        return False
    text = f"{prompt}\n" + "\n".join(prior)
    return any(word in text.lower() for word in _SPEC_WORDS)


def requirement_issues(ledger: dict) -> list[str]:
    """Return contradiction and state issues from an extraction.

    Parameters
    ----------
    ledger : dict
        Extracted requirement ledger.

    Returns
    -------
    list of str
        Human-readable issue strings.
    """
    issues: list[str] = []
    for item in ledger.get("requirements") or []:
        issues.extend(_requirement_issue(item))
    return issues


def _requirement_issue(item) -> list[str]:
    """Return issues for one extracted requirement.

    Parameters
    ----------
    item : object
        Requirement entry.

    Returns
    -------
    list of str
        Empty when the state is used correctly.
    """
    if not isinstance(item, dict):
        return []
    name = str(item.get("requirement") or "requirement")
    state = str(item.get("state") or "unknown")
    if state == "contradicted":
        return [_contradiction(name, item)]
    return _state_issue(name, state, item)


def _state_issue(name: str, state: str, item: dict) -> list[str]:
    """Return the issue for a misuse of a requirement state.

    Parameters
    ----------
    name : str
        Requirement name.
    state : str
        Requirement state.
    item : dict
        Requirement entry.

    Returns
    -------
    list of str
        Empty when the state is used correctly.
    """
    if item.get("used_as_confirmed") and state in _UNCONFIRMED:
        return [f"{name}: {state} but presented as confirmed"]
    return []


def _contradiction(name: str, item: dict) -> str:
    """Return the contradiction issue text.

    Parameters
    ----------
    name : str
        Requirement name.
    item : dict
        Requirement entry.

    Returns
    -------
    str
        Issue text with the conflicting detail.
    """
    reason = str(item.get("evidence") or "conflicting requirements")
    return f"{name}: contradicted ({reason})"
