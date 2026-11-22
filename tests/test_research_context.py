"""Tests that research context never includes the primary conversation."""

import tempfile
import unittest
from pathlib import Path

from gui.research_context import research_context


class ResearchContextTests(unittest.TestCase):
    """Verify the snapshot toggle and primary-conversation isolation."""

    def test_disabled_toggle_returns_empty_context(self) -> None:
        """Return no context when the snapshot is off.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The context string is empty.
        """
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(research_context(folder, False), "")

    def test_enabled_toggle_returns_workspace_only(self) -> None:
        """Include workspace state but never a primary transcript.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The snapshot is returned without primary conversation text.
        """
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "notes.txt").write_text("x")
            text = research_context(folder, True)
        self.assertIn("notes.txt", text)
        self.assertNotIn("Recent commands conversation", text)


if __name__ == "__main__":
    unittest.main()
