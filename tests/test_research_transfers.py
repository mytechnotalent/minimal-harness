"""Tests for cross-window transfer provenance."""

import tempfile
import unittest
from pathlib import Path

from gui.research.transfers import TransferStore


def _transfer(store):
    """Create one transfer with a target thread.

    Parameters
    ----------
    store : TransferStore
        Transfer store.

    Returns
    -------
    dict
        Transfer record.
    """
    return store.append(
        "primary_to_research",
        "selection",
        "text",
        target_thread_id="th_" + "0" * 32,
    )


class TransferStoreTests(unittest.TestCase):
    """Verify transfer records and ordering."""

    def test_append_and_list(self) -> None:
        """Persist two transfers and read them back.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both records are returned in order.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = TransferStore(Path(folder) / "session")
            store.append("primary_to_research", "message", "first")
            store.append("research_to_primary", "selection", "second")
            records = store.list()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["excerpt"], "first")

    def test_transfer_carries_provenance(self) -> None:
        """Store session, direction, thread, and confirmation.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Provenance fields are present.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = TransferStore(Path(folder) / "session")
            record = _transfer(store)
        self.assertEqual(record["session_id"], "session")
        self.assertTrue(record["user_confirmed"])
        self.assertEqual(record["target_thread_id"], "th_" + "0" * 32)


if __name__ == "__main__":
    unittest.main()
