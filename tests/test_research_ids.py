"""Tests for research identifiers, message hashes, and restore maps."""

import tempfile
import unittest
from pathlib import Path

from gui.research.ids import IdMap
from gui.research.ids import is_valid_id
from gui.research.ids import message_identity
from gui.research.ids import new_id
from gui.research.ids import require_id


class IdentifierTests(unittest.TestCase):
    """Verify identifier creation and validation."""

    def test_new_ids_are_prefixed_and_unique(self) -> None:
        """Create distinct identifiers with the requested prefix.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both identifiers are valid and different.
        """
        first = new_id("nt")
        second = new_id("nt")
        self.assertNotEqual(first, second)
        self.assertTrue(is_valid_id(first, "nt"))

    def test_traversal_is_rejected(self) -> None:
        """Reject identifiers that look like paths.

        Parameters
        ----------
        None

        Returns
        -------
        None
            ValueError is raised.
        """
        for value in ("../../etc/passwd", "nt_short", "nt_" + "z" * 32):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    require_id(value, "nt")

    def test_message_identity_is_content_sensitive(self) -> None:
        """Change the hash when content changes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Sequence is kept and hashes differ.
        """
        first = message_identity(0, {"role": "user", "content": "a"})
        second = message_identity(0, {"role": "user", "content": "b"})
        self.assertEqual(first["seq"], second["seq"])
        self.assertNotEqual(first["hash"], second["hash"])


class IdMapTests(unittest.TestCase):
    """Verify restore mapping storage and remapping."""

    def test_mapping_round_trip(self) -> None:
        """Persist and reload original-to-restored identifiers.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The mapping survives a round trip.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.json"
            mapping = IdMap("rs_" + "0" * 32)
            new_source = mapping.new("sources", "src", "src_old")
            mapping.save(path)
            loaded = IdMap.load(path)
            self.assertEqual(loaded.require("sources", "src_old"), new_source)

    def test_missing_mapping_raises(self) -> None:
        """Reject a reference without a mapping.

        Parameters
        ----------
        None

        Returns
        -------
        None
            KeyError is raised.
        """
        mapping = IdMap("rs_" + "0" * 32)
        with self.assertRaises(KeyError):
            mapping.require("notes", "nt_missing")


if __name__ == "__main__":
    unittest.main()
