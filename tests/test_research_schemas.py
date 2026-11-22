"""Tests for research record schema validation."""

import unittest

from gui.research.schemas import RecordError
from gui.research.schemas import validate_note
from gui.research.schemas import validate_record
from gui.research.schemas import validate_scope

NOTE_ID = "nt_" + "0" * 32


def _note(**changes):
    """Build a minimal valid note record.

    Parameters
    ----------
    changes : dict
        Fields to override.

    Returns
    -------
    dict
        Note record.
    """
    record = {"id": NOTE_ID, "kind": "note", "scope": _scope()}
    record.update(_note_text())
    record.update(_note_links())
    record.update(_note_state())
    record.update(changes)
    return record


def _note_text():
    """Return note text fields.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Text fields.
    """
    return {"title": "Title", "body_md": "Body", "tags": [], "origin": {}}


def _note_links():
    """Return note reference fields.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Reference fields.
    """
    return {"source_ids": [], "evidence_ids": [], "restored": None}


def _note_state():
    """Return note state and timestamp fields.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        State fields.
    """
    return {"status": "active", "revision": 1, "created": 0, "updated": 0}


def _scope(**changes):
    """Build a valid scope mapping.

    Parameters
    ----------
    changes : dict
        Fields to override.

    Returns
    -------
    dict
        Scope mapping.
    """
    scope = {
        "session_id": "session",
        "thread_id": "thread",
        "thread_title_snapshot": "Title",
        "thread_deleted": False,
    }
    scope.update(changes)
    return scope


class SchemaTests(unittest.TestCase):
    """Verify required fields, statuses, and identifier checks."""

    def test_valid_note_is_accepted(self) -> None:
        """Accept a complete note record.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No exception is raised.
        """
        validate_note(_note())

    def test_missing_field_is_rejected(self) -> None:
        """Reject a note without a required field.

        Parameters
        ----------
        None

        Returns
        -------
        None
            RecordError is raised.
        """
        record = _note()
        record.pop("body_md")
        with self.assertRaises(RecordError):
            validate_note(record)

    def test_unknown_kind_is_rejected(self) -> None:
        """Reject an unknown record kind.

        Parameters
        ----------
        None

        Returns
        -------
        None
            RecordError is raised.
        """
        with self.assertRaises(RecordError):
            validate_record("unknown", {})

    def test_bad_status_is_rejected(self) -> None:
        """Reject an unsupported status.

        Parameters
        ----------
        None

        Returns
        -------
        None
            RecordError is raised.
        """
        with self.assertRaises(RecordError):
            validate_note(_note(status="draft"))

    def test_bad_identifier_is_rejected(self) -> None:
        """Reject a note identifier with the wrong shape.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ValueError is raised.
        """
        with self.assertRaises(ValueError):
            validate_note(_note(id="../note"))

    def test_scope_missing_field_is_rejected(self) -> None:
        """Reject a scope without every required field.

        Parameters
        ----------
        None

        Returns
        -------
        None
            RecordError is raised.
        """
        scope = _scope()
        scope.pop("thread_id")
        with self.assertRaises(RecordError):
            validate_scope(scope)


if __name__ == "__main__":
    unittest.main()
