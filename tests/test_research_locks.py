"""Tests for research operation locks and journal persistence."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gui.research.journal import Journal
from gui.research.locks import LockError
from gui.research.locks import OperationLock


class OperationLockTests(unittest.TestCase):
    """Verify acquisition, contention, release, and stale cleanup."""

    def test_lock_acquisition_and_release(self) -> None:
        """Hold a lock and remove it on exit.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The lock file appears and disappears.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lock"
            with OperationLock(path):
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())

    def test_second_acquisition_is_rejected(self) -> None:
        """Reject a concurrent lock owner.

        Parameters
        ----------
        None

        Returns
        -------
        None
            LockError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lock"
            with OperationLock(path):
                with self.assertRaises(LockError):
                    OperationLock(path).acquire()

    def test_stale_owner_is_removed(self) -> None:
        """Reclaim a lock left by a missing process.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A new lock can be acquired.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lock"
            path.write_text(json.dumps({"pid": 999999, "operation": "old"}))
            with OperationLock(path):
                self.assertTrue(path.exists())

    def test_invalid_process_error_is_stale(self) -> None:
        """Reclaim a lock when the platform rejects the PID check.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A new lock can be acquired.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lock"
            path.write_text(json.dumps({"pid": 1234, "operation": "old"}))
            with patch("gui.research.locks.os.kill", side_effect=OSError):
                with OperationLock(path):
                    self.assertTrue(path.exists())

    def test_malformed_lock_is_removed(self) -> None:
        """Reclaim a lock file that cannot be decoded.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A new lock can be acquired.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lock"
            path.write_text("not json")
            with OperationLock(path):
                self.assertTrue(path.exists())


class JournalTests(unittest.TestCase):
    """Verify journal merging and removal."""

    def test_journal_round_trip(self) -> None:
        """Merge fields and read them back.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The latest state and fields are present.
        """
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(Path(folder) / "journal.json")
            journal.write("prepared", total=2)
            data = journal.write("staged", total=3)
            self.assertEqual(journal.read()["state"], "staged")
            self.assertEqual(data["total"], 3)

    def test_journal_remove(self) -> None:
        """Delete a journal file.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The file no longer exists.
        """
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(Path(folder) / "journal.json")
            journal.write("complete")
            journal.remove()
            self.assertFalse(journal.path.exists())


if __name__ == "__main__":
    unittest.main()
