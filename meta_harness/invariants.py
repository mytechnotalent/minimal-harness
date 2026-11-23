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
            "Effective database privileges include those inherited through "
            "role membership, default privileges, and object ownership; "
            "review them explicitly.",
            "An application pre-insert SELECT alone does not prevent "
            "duplicates; only a database constraint or lock does.",
        ),
    },
    {
        "category": "retries",
        "keywords": (
            "retry",
            "retries",
            "idempot",
            "request id",
            "duplicate",
            "upsert",
            "concurrent",
            "concurrency",
            "payment",
            "queue",
            "webhook",
            "replay",
            "exactly once",
            "at least once",
        ),
        "rules": (
            "A request ID identifies one HTTP request for tracing; it is not "
            "an idempotency key.",
            "An idempotency key identifies the same logical operation across "
            "retries; the server stores the outcome.",
            "Frontend debounce and IP rate limits are not "
            "duplicate-prevention guarantees.",
            "An idempotency design must define key scope, key uniqueness, "
            "and the request payload fingerprint.",
            "An idempotency record must track in-progress, completed, and "
            "failed states, and store the result for replay.",
            "A repeated request with the same idempotency key must return "
            "the stored result instead of creating a new operation.",
            "Concurrent requests with the same key must be serialized or "
            "rejected by a database unique constraint, not only by an "
            "application check.",
            "A retry of a completed operation must not repeat the business "
            "effect.",
            "Expired idempotency keys must be handled explicitly so a late "
            "retry cannot double-process.",
            "Application validation is not a substitute for a database "
            "constraint on critical uniqueness.",
            "Reusing one idempotency key for different payloads is an error, "
            "and generating a new key for every retry defeats idempotency.",
            "An upsert requires a database unique constraint on the key it "
            "matches.",
            "Retries must distinguish transient failures from permanent "
            "failures.",
            "Duplicate HTTP requests, duplicate logical operations, duplicate "
            "database rows, and duplicate external side effects are separate "
            "problems that need separate controls.",
            "A repeated key must not re-send notifications or payments; the "
            "stored result must be replayed instead.",
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
            "privilege",
            "grant",
            "inherit",
            "rate limit",
            "security",
            "log",
        ),
        "rules": (
            "Frontend controls are not a security boundary.",
            "Least privilege applies to service roles and database "
            "permissions, including inherited roles, default privileges, "
            "and object ownership.",
            "A role must not be able to grant privileges it does not hold "
            "or escalate its own privileges.",
            "Secrets must not be logged or embedded in client code.",
            "Logs and error messages must not contain secrets, tokens, or "
            "sensitive request bodies.",
            "Collect, store, and log only the fields the task requires; "
            "minimize sensitive data.",
            "Resource-level authorization must be checked server-side for "
            "every object access, not only at the route or UI layer.",
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
            "recovery",
            "failover",
        ),
        "rules": (
            "A rollback plan must name the data and schema state it restores.",
            "Production logging must avoid sensitive payloads and unbounded "
            "volume.",
            "A backup is not verified until a restore has been tested.",
            "Recovery behavior must be tested under partial failure, not "
            "only described.",
        ),
    },
    {
        "category": "architecture",
        "keywords": (
            "architecture",
            "outbox",
            "worker",
            "replication",
            "audit event",
            "ocr",
            "inference",
            "cost estimate",
            "per page",
            "per-document",
            "document processing",
        ),
        "rules": (
            "A business write and its audit event must be committed in one "
            "transaction or coordinated through a transactional outbox; "
            "writing to two stores is not atomic.",
            "Outbox delivery must be retried, monitored, and reconciled; a "
            "failed delivery must not be dropped silently.",
            "A queue message or storage prefix does not enforce "
            "document-level authorization; the worker must verify access "
            "for every document it processes.",
            "A cost estimate must state cost per unit, volume, input and "
            "output usage, storage, logging, compute, retry overhead, and "
            "peak usage.",
            "A cost estimate must distinguish verified prices from "
            "assumptions and projections.",
            "A recommended cloud service must be checked against its actual "
            "API, permission model, runtime, and processing limits.",
            "Audit history is immutable unless a separate, explicitly "
            "authorized workflow allows a change.",
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
