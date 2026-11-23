"""Tests for optional Playwright browser error reporting."""

import os
import threading
import unittest
from unittest.mock import patch

from meta_harness.browser import BrowserClient
from meta_harness.browser import BrowserError
from meta_harness.browser import _launch_hint


def _slow_worker(*args: object) -> None:
    """Block long enough to trip the join timeout.

    Parameters
    ----------
    *args : object
        Ignored worker arguments.

    Returns
    -------
    None
        The helper returns after one second.
    """
    threading.Event().wait(1)


class LaunchHintTests(unittest.TestCase):
    """Verify browser launch failures are actionable."""

    def test_missing_executable_mentions_install_command(self) -> None:
        """A missing browser tells the user how to install it.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when the hint names the install command.
        """
        hint = _launch_hint(RuntimeError("Executable doesn't exist at /x"))
        self.assertIn("playwright install chromium", hint)

    def test_other_failures_keep_the_original_message(self) -> None:
        """Unrelated launch failures keep their original detail.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when the original message is preserved.
        """
        hint = _launch_hint(RuntimeError("boom"))
        self.assertIn("boom", hint)


class JoinTimeoutTests(unittest.TestCase):
    """Verify a hung browser thread cannot block the agent."""

    def test_hung_worker_raises_browser_error(self) -> None:
        """A stuck worker is abandoned after the configured timeout.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when BrowserError is raised.
        """
        client = BrowserClient()
        with patch.dict(os.environ, {"HARNESS_BROWSER_TIMEOUT": "0.05"}):
            with patch.object(BrowserClient, "_worker", _slow_worker):
                with self.assertRaises(BrowserError):
                    client.open("https://example.com")
