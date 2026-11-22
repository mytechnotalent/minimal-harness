"""Tests for the research evidence store."""

import tempfile
import unittest
from pathlib import Path

from gui.research.evidence import EvidenceStore

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _png(width=2, height=3):
    """Build a minimal PNG header with dimensions.

    Parameters
    ----------
    width : int
        Image width.
    height : int
        Image height.

    Returns
    -------
    bytes
        Header bytes sufficient for dimension parsing.
    """
    size = width.to_bytes(4, "big") + height.to_bytes(4, "big")
    return PNG_HEADER + b"\x00\x00\x00\rIHDR" + size


def _scope(session="session", thread=None):
    """Build an evidence scope mapping.

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


def _assert_orphan(case, orphaned, record):
    """Assert that orphan metadata retained its thread origin.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    orphaned : dict
        Orphaned evidence record.
    record : dict
        Original evidence record.

    Returns
    -------
    None
        Assertions pass when origin metadata remains.
    """
    orphan = orphaned["orphan"]
    case.assertEqual(orphan["reason"], "thread_deleted")
    case.assertEqual(
        orphan["original_thread_id"], record["scope"]["thread_id"]
    )


class EvidenceStoreTests(unittest.TestCase):
    """Verify screenshot capture, dimensions, orphaning, and deletion."""

    def test_capture_writes_png_and_metadata(self) -> None:
        """Write a PNG pair with parsed dimensions.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both files exist and dimensions are stored.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = EvidenceStore(folder)
            record = store.capture(_scope(), "https://example.com", _png(4, 5))
            png = store.evidence / "session" / record["scope"]["thread_id"]
            png = png / f"{record['id']}.png"
            self.assertTrue(png.exists())
            self.assertEqual(record["width"], 4)
            self.assertEqual(record["height"], 5)

    def test_capture_stays_outside_a_project(self) -> None:
        """Write evidence only under the research root.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The project directory is untouched.
        """
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "project"
            project.mkdir()
            marker = project / "keep.txt"
            marker.write_text("keep")
            store = EvidenceStore(Path(folder) / "research")
            store.capture(_scope(), "https://example.com", _png())
            self.assertEqual(list(project.iterdir()), [marker])

    def test_list_filters_by_session(self) -> None:
        """Return evidence from one session only.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The other session is excluded.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = EvidenceStore(folder)
            store.capture(_scope("one"), "https://example.com", _png())
            store.capture(_scope("two"), "https://example.com", _png())
            records = store.list("one")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["scope"]["session_id"], "one")

    def test_orphan_keeps_original_association(self) -> None:
        """Mark evidence orphaned without losing its thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Origin metadata remains.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = EvidenceStore(folder)
            record = store.capture(_scope(), "https://example.com", _png())
            orphaned = store.mark_orphaned(record["id"])
        _assert_orphan(self, orphaned, record)

    def test_delete_removes_pair(self) -> None:
        """Delete both PNG and metadata.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The metadata no longer loads.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = EvidenceStore(folder)
            record = store.capture(_scope(), "https://example.com", _png())
            store.delete(record["id"])
            with self.assertRaises(FileNotFoundError):
                store.get(record["id"])

    def test_traversal_segment_is_rejected(self) -> None:
        """Reject a session identifier that looks like a path.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ValueError is raised.
        """
        with tempfile.TemporaryDirectory() as folder:
            store = EvidenceStore(folder)
            with self.assertRaises(ValueError):
                store.capture(_scope(".."), "https://example.com", _png())


if __name__ == "__main__":
    unittest.main()
