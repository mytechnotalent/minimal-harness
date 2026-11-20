"""Curated technical invariants selected by task keywords."""

INVARIANTS = (
    {
        "category": "database",
        "keywords": (
            "sql",
            "postgres",
            "database",
            "unique",
            "transaction",
            "query",
        ),
        "rules": (
            "A database UNIQUE constraint prevents two conflicting rows from "
            "both committing, including under concurrent inserts.",
            "A pre-insert SELECT is race-prone without a constraint or "
            "transaction.",
            "Parameterized queries are the primary defense against SQL "
            "injection.",
        ),
    },
    {
        "category": "retries",
        "keywords": ("retry", "retries", "idempot", "request id", "duplicate"),
        "rules": (
            "A request ID identifies one HTTP request for tracing; it is not "
            "an idempotency key.",
            "An idempotency key identifies the same logical operation across "
            "retries; the server stores the outcome.",
            "Frontend debounce and IP rate limits are not "
            "duplicate-prevention guarantees.",
        ),
    },
    {
        "category": "security",
        "keywords": (
            "auth",
            "password",
            "token",
            "secret",
            "permission",
            "rate limit",
            "security",
        ),
        "rules": (
            "Frontend controls are not a security boundary.",
            "Least privilege applies to service roles and database "
            "permissions.",
            "Secrets must not be logged or embedded in client code.",
        ),
    },
    {
        "category": "operations",
        "keywords": (
            "deploy",
            "rollback",
            "monitor",
            "production",
            "backup",
            "restore",
        ),
        "rules": (
            "A rollback plan must name the data and schema state it restores.",
            "Production logging must avoid sensitive payloads and unbounded "
            "volume.",
            "A backup is not verified until a restore has been tested.",
        ),
    },
)


def relevant_invariants(prompt: str, answer: str) -> list[str]:
    """Return invariants matching the task keywords.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.

    Returns
    -------
    list of str
        Matching invariant statements.
    """
    text = f"{prompt}\n{answer}".lower()
    rules: list[str] = []
    for entry in INVARIANTS:
        if any(word in text for word in entry["keywords"]):
            rules.extend(entry["rules"])
    return rules


def needs_invariants(prompt: str, answer: str) -> bool:
    """Return whether any curated invariant applies.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.

    Returns
    -------
    bool
        ``True`` when at least one invariant matches.
    """
    return bool(relevant_invariants(prompt, answer))
