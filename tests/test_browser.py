"""Tests for optional Playwright browser error reporting."""

import unittest

from meta_harness.browser import _launch_hint


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
