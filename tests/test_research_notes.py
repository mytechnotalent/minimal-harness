"""Tests for the global note store and revision history."""

import tempfile
import unittest

from gui.research.notes import NoteStore

NOTE_ID = "nt_" + "0" * 32


def _scope(session="session", thread=None):
    """Build a note scope mapping.

    Parameters
    ----------
    session : str
        Session identifier.
    thread : str or None
        Thread identifier.

    Returns
    -------
    dict
        Scope mapping.
    """
    thread_id = thread or "th_" + "0" * 32
    return {
        "session_id": session,
        "thread_id": thread_id,
        "thread_title_snapshot": "Thread",
        "thread_deleted": False,
    }


def _origin():
    """Build an immutable note origin mapping.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Origin mapping.
    """
    return {"message_seq": 1, "message_hash": "hash", "role": "assistant"}


def _new(store, scope, body="first"):
    """Create one note for a test.

    Parameters
    ----------
    store : NoteStore
        Note store.
    scope : dict
        Note scope.
    body : str
        Markdown body.

    Returns
    -------
    dict
        Created note.
    """
    return store.create(scope, "Title", body, _origin())


def _assert_restore(case, restored, revisions):
    """Assert that a restored revision kept its history.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    restored : dict
        Restored note.
    revisions : list
        Stored revisions.

    Returns
    -------
    None
        Assertions pass when history is intact.
    """
    case.assertEqual(restored["body_md"], "first")
    case.assertEqual(restored["restored_from_revision"], 1)
    case.assertEqual(len(revisions), 2)


class NoteStoreTests(unittest.TestCase):
    """Verify note creation, filtering, revisions, and deletion."""

    def test_create_and_get(self) -> None:
        """Persist and reload a note.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The stored fields match.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = NoteStore(folder)
            note = _new(store, _scope())
            loaded = store.get(note["id"])
        self.assertEqual(loaded["title"], "Title")
        self.assertEqual(loaded["revision"], 1)

    def test_list_filters_by_session(self) -> None:
        """Return only notes in the requested session.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only the first session note is returned.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = NoteStore(folder)
            scope = _scope("session-one")
            first = _new(store, scope)
            _new(store, _scope("session-two"))
            notes = store.list("session-one")
        self.assertEqual([note["id"] for note in notes], [first["id"]])

    def test_update_writes_revision(self) -> None:
        """Store the old body before applying an edit.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The revision holds the previous body.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = NoteStore(folder)
            note = _new(store, _scope())
            updated = store.update(note["id"], body_md="second")
            revisions = store.revisions(note["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(revisions[0]["body_md"], "first")

    def test_all_revisions_are_retained(self) -> None:
        """Keep every superseded version.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Two revisions exist after two edits.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = NoteStore(folder)
            note = _new(store, _scope())
            store.update(note["id"], body_md="second")
            store.update(note["id"], body_md="third")
            revisions = store.revisions(note["id"])
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[1]["body_md"], "second")

    def test_restore_revision_creates_new_revision(self) -> None:
        """Restore an earlier body without rewriting history.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The body returns and the revision count grows.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = NoteStore(folder)
            note = _new(store, _scope())
            store.update(note["id"], body_md="second")
            restored = store.restore_revision(note["id"], 1)
            revisions = store.revisions(note["id"])
        _assert_restore(self, restored, revisions)

    def test_delete_removes_note_and_revisions(self) -> None:
        """Delete a note and its revision folder.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The note cannot be loaded afterward.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = NoteStore(folder)
            note = _new(store, _scope())
            store.update(note["id"], body_md="second")
            store.delete(note["id"])
            self.assertFalse((store.notes / f"{note['id']}.json").exists())
            self.assertFalse((store.revision_root / note["id"]).exists())

    def test_invalid_identifier_is_rejected(self) -> None:
        """Reject a path-like note identifier.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ValueError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = NoteStore(folder)
            with self.assertRaises(ValueError):
                store.get("../note")


if __name__ == "__main__":
    unittest.main()
