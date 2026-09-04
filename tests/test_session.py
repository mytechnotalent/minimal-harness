"""Tests for persistent JSONL agent sessions."""

import tempfile
import unittest
from pathlib import Path

from meta_harness.session import Session


class SessionTests(unittest.TestCase):
    """Verify transcript persistence and reload behavior."""

    def test_session_round_trips_messages(self) -> None:
        """Persist messages and reload them in a new session.

        Returns
        -------
        None
            Assertions pass when JSONL persistence works.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            Session(path).append({"role": "user", "content": "hello"})
            restored = Session(path)
        self.assertEqual(restored.messages[0]["content"], "hello")


if __name__ == "__main__":
    unittest.main()
