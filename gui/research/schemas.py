"""Required fields and validation for research records."""

from .ids import require_id

SCOPE_FIELDS = frozenset(
    {
        "session_id",
        "thread_id",
        "thread_title_snapshot",
        "thread_deleted",
    }
)

RECORD_FIELDS = {
    "note": frozenset(
        {
            "id",
            "kind",
            "scope",
            "title",
            "body_md",
            "tags",
            "origin",
            "source_ids",
            "evidence_ids",
            "status",
            "revision",
            "created",
            "updated",
            "restored",
        }
    ),
    "revision": frozenset(
        {
            "note_id",
            "revision",
            "title",
            "body_md",
            "saved_at",
            "editor",
            "restored_from_revision",
            "created",
        }
    ),
    "source": frozenset(
        {
            "id",
            "scope",
            "origin",
            "url",
            "title",
            "retrieved_at",
            "excerpt",
            "content_hash",
            "evidence_label",
            "occurrences",
            "status",
            "restored",
        }
    ),
    "evidence": frozenset(
        {
            "id",
            "scope",
            "source_id",
            "url",
            "captured_at",
            "tool_call_id",
            "sha256",
            "bytes",
            "width",
            "height",
            "caption",
            "status",
            "orphan",
            "restored",
        }
    ),
    "thread": frozenset(
        {
            "id",
            "session_id",
            "title",
            "tags",
            "status",
            "snapshot_enabled",
            "created",
            "updated",
            "archived_at",
            "message_count",
        }
    ),
    "tombstone": frozenset(
        {
            "thread_id",
            "session_id",
            "title",
            "created",
            "deleted",
            "message_count",
            "note_ids",
            "source_ids",
            "evidence_ids",
            "transfer_ids",
        }
    ),
    "transfer": frozenset(
        {
            "id",
            "session_id",
            "direction",
            "source",
            "target",
            "kind",
            "user_confirmed",
            "created_at",
            "restored",
        }
    ),
    "restored_history": frozenset(
        {
            "id",
            "target_session_id",
            "archive_id",
            "restore_id",
            "original_session_id",
            "original_title",
            "archived_at",
            "restored_at",
            "message_count",
            "sha256",
            "read_only",
            "searchable",
        }
    ),
    "archive": frozenset(
        {
            "archive_id",
            "format_version",
            "original_session_id",
            "original_session_meta",
            "created_at",
            "completed_at",
            "status",
            "verification",
            "counts",
            "files",
            "id_index",
        }
    ),
}

_STATUSES = frozenset({"active", "archived"})


class RecordError(ValueError):
    """Report an invalid research record."""


def validate_record(kind, record):
    """Require all fields for one record kind.

    Parameters
    ----------
    kind : str
        Record kind.
    record : dict
        Record to validate.

    Returns
    -------
    None
        The record is accepted.
    """
    required = RECORD_FIELDS.get(kind)
    if required is None:
        raise RecordError(f"unknown record kind: {kind}")
    missing = required - set(record)
    if missing:
        raise RecordError(f"missing {kind} fields: {sorted(missing)}")


def validate_scope(scope):
    """Require the fields of a record scope.

    Parameters
    ----------
    scope : dict
        Scope mapping.

    Returns
    -------
    None
        The scope is accepted.
    """
    missing = SCOPE_FIELDS - set(scope)
    if missing:
        raise RecordError(f"missing scope fields: {sorted(missing)}")


def validate_note(record):
    """Validate one note record.

    Parameters
    ----------
    record : dict
        Note to validate.

    Returns
    -------
    None
        The note is accepted.
    """
    validate_record("note", record)
    validate_scope(record["scope"])
    require_id(record["id"], "nt")
    _validate_status(record["status"])


def validate_revision(record):
    """Validate one note revision record.

    Parameters
    ----------
    record : dict
        Revision to validate.

    Returns
    -------
    None
        The revision is accepted.
    """
    validate_record("revision", record)
    require_id(record["note_id"], "nt")
    if not isinstance(record["revision"], int) or record["revision"] < 1:
        raise RecordError("revision must be a positive integer")


def validate_source(record):
    """Validate one source record.

    Parameters
    ----------
    record : dict
        Source to validate.

    Returns
    -------
    None
        The source is accepted.
    """
    validate_record("source", record)
    validate_scope(record["scope"])
    require_id(record["id"], "src")
    _validate_status(record["status"])


def validate_evidence(record):
    """Validate one evidence record.

    Parameters
    ----------
    record : dict
        Evidence to validate.

    Returns
    -------
    None
        The evidence is accepted.
    """
    validate_record("evidence", record)
    validate_scope(record["scope"])
    require_id(record["id"], "ev")
    _validate_status(record["status"])


def _validate_status(status):
    """Require a supported record status.

    Parameters
    ----------
    status : str
        Candidate status.

    Returns
    -------
    None
        The status is accepted.
    """
    if status not in _STATUSES:
        raise RecordError(f"unsupported status: {status}")
