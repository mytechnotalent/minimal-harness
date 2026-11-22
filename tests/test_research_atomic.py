"""Tests for atomic research file writes and hashing helpers."""

import tempfile
import unittest
from pathlib import Path

from gui.research.atomic import read_json
from gui.research.atomic import rename_atomic
from gui.research.atomic import write_bytes_atomic
from gui.research.atomic import write_json_atomic
from gui.research.hashing import hash_json
from gui.research.hashing import sha256_file
from gui.research.hashing import sha256_text


class AtomicWriteTests(unittest.TestCase):
    """Verify atomic writes, JSON round trips, and renames."""

    def test_bytes_round_trip_and_overwrite(self) -> None:
        """Replace a file with new bytes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The last write wins.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.bin"
            write_bytes_atomic(path, b"one")
            write_bytes_atomic(path, b"two")
            self.assertEqual(path.read_bytes(), b"two")

    def test_json_round_trip(self) -> None:
        """Persist and reload a JSON document.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The value is unchanged.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "record.json"
            write_json_atomic(path, {"b": 2, "a": 1})
            self.assertEqual(read_json(path), {"a": 1, "b": 2})

    def test_no_temporary_files_remain(self) -> None:
        """Leave no temporary file beside the destination.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only the destination exists.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "record.json"
            write_json_atomic(path, {"a": 1})
            self.assertEqual(list(Path(folder).glob(".tmp-*")), [])

    def test_rename_moves_file(self) -> None:
        """Move a file with an atomic rename.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The source is gone and the target exists.
        """
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "a.txt"
            target = Path(folder) / "b.txt"
            source.write_text("value")
            rename_atomic(source, target)
            self.assertFalse(source.exists())
            self.assertEqual(target.read_text(), "value")

    def test_hash_helpers_are_stable(self) -> None:
        """Return stable file and text hashes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Digests match equivalent content.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.txt"
            path.write_text("abc")
            self.assertEqual(sha256_file(path), sha256_text("abc"))
            self.assertEqual(hash_json({"a": 1}), hash_json({"a": 1}))


if __name__ == "__main__":
    unittest.main()
