"""Headless tests for the full-screen TUI event handling."""

import unittest
from unittest.mock import Mock

from meta_harness.tui import TUI


class TUITests(unittest.TestCase):
    """Verify TUI keyboard actions without opening a terminal."""

    def test_submit_runs_agent_and_quit_stops(self) -> None:
        """Submit a prompt and then exit the interface.

        Returns
        -------
        None
            Assertions pass when input events work.
        """
        agent = Mock()
        agent.run.return_value = "done"
        tui = TUI(agent)
        for key in "hello":
            tui._handle(key)
        self.assertTrue(tui._handle("\n"))
        tui.prompt = "/quit"
        self.assertFalse(tui._submit())


if __name__ == "__main__":
    unittest.main()
