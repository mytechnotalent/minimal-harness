"""Tests for reading restored primary history from a session."""

import json
import tempfile
import unittest
from pathlib import Path

from gui.research.atomic import write_json_atomic
from gui.research.restored import RestoredHistoryStore

HISTORY_ID = "rh_" + "0" * 32


def _history(folder):
    """Create one restored history fixture.

    Parameters
    ----------
    folder : str
        Temporary parent directory.

    Returns
    -------
    RestoredHistoryStore
        Store containing one history.
    """
    session = Path(folder) / "session"
    store = RestoredHistoryStore(session)
    history = store.root / HISTORY_ID
    history.mkdir(parents=True)
    write_json_atomic(history / "meta.json", _meta())
    _write_transcript(history)
    return store


def _meta():
    """Build restored history metadata for the fixture.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Metadata mapping.
    """
    meta = _meta_ids()
    meta.update(_meta_origin())
    meta.update(_meta_state())
    return meta


def _meta_ids():
    """Build identifier fields for the fixture.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Identifier fields.
    """
    return {
        "id": HISTORY_ID,
        "target_session_id": "session",
        "archive_id": "ar_" + "0" * 32,
        "restore_id": "rs_" + "0" * 32,
    }


def _meta_origin():
    """Build origin fields for the fixture.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Origin fields.
    """
    return {
        "original_session_id": "old",
        "original_title": "Old session",
        "archived_at": 0,
        "restored_at": 1,
    }


def _meta_state():
    """Build state fields for the fixture.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        State fields.
    """
    return {
        "message_count": 1,
        "sha256": "hash",
        "read_only": True,
        "searchable": True,
    }


def _write_transcript(history):
    """Write one transcript line for the fixture.

    Parameters
    ----------
    history : pathlib.Path
        Restored history folder.

    Returns
    -------
    None
        The transcript file is written.
    """
    line = json.dumps({"role": "user", "content": "hello"})
    (history / "transcript.jsonl").write_text(line + "\n")


class RestoredHistoryTests(unittest.TestCase):
    """Verify restored history listing and transcripts."""

    def test_list_returns_metadata(self) -> None:
        """List restored histories newest first.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The fixture is returned.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _history(folder)
            histories = store.list()
        self.assertEqual(histories[0]["id"], HISTORY_ID)

    def test_transcript_returns_messages(self) -> None:
        """Read and parse a restored transcript.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The stored message is returned.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = _history(folder)
            messages = store.transcript(HISTORY_ID)
        self.assertEqual(messages[0]["content"], "hello")

    def test_invalid_identifier_is_rejected(self) -> None:
        """Reject a path-like history identifier.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ValueError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = RestoredHistoryStore(Path(folder) / "session")
            with self.assertRaises(ValueError):
                store.get("../../x")


if __name__ == "__main__":
    unittest.main()
