"""Tests for session-scoped research thread storage."""

import tempfile
import unittest
from pathlib import Path

from gui.research.threads import ThreadStore


def _store(folder):
    """Create a thread store for a temporary session.

    Parameters
    ----------
    folder : str
        Temporary parent directory.

    Returns
    -------
    ThreadStore
        Thread store for the session.
    """
    return ThreadStore(Path(folder) / "session")


class ThreadStoreTests(unittest.TestCase):
    """Verify creation, default selection, listing, and status changes."""

    def test_create_writes_metadata_and_transcript(self) -> None:
        """Create a thread folder with both files.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Metadata and transcript exist.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _store(folder)
            thread = store.create("Topic")
            self.assertTrue(store.transcript_path(thread["id"]).exists())
            self.assertEqual(store.get(thread["id"])["title"], "Topic")

    def test_default_creates_and_returns_thread(self) -> None:
        """Create a default thread when none exists.

        Parameters
        ----------
        None

        Returns
        -------
        None
            One active thread is returned.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _store(folder)
            thread = store.default()
            self.assertEqual(len(store.list()), 1)
            self.assertEqual(store.default()["id"], thread["id"])

    def test_list_filters_archived_threads(self) -> None:
        """Hide archived threads from the active list.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Active and archived lists differ.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _store(folder)
            thread = store.create("Topic")
            store.archive(thread["id"])
            self.assertEqual(store.list(), [])
            self.assertEqual(len(store.list(status="archived")), 1)

    def test_restore_returns_thread_to_active_list(self) -> None:
        """Restore an archived thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The thread appears again.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _store(folder)
            thread = store.create("Topic")
            store.archive(thread["id"])
            store.restore(thread["id"])
            self.assertEqual(
                [item["id"] for item in store.list()], [thread["id"]]
            )

    def test_update_changes_snapshot_setting(self) -> None:
        """Persist the per-thread snapshot toggle.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The stored setting changes.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _store(folder)
            thread = store.create("Topic")
            updated = store.update(thread["id"], snapshot_enabled=True)
            self.assertTrue(updated["snapshot_enabled"])

    def test_invalid_thread_identifier_is_rejected(self) -> None:
        """Reject a path-like thread identifier.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ValueError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _store(folder)
            with self.assertRaises(ValueError):
                store.get("../thread")


if __name__ == "__main__":
    unittest.main()
