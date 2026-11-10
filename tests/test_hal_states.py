"""Offline tests for HAL eye-state recovery."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from gui.hal import HalWindow
    from gui.hal import _log_error
except Exception:
    HalWindow = None
    _log_error = None


class _FakeHal:
    """Record state and question-resolution calls."""

    def __init__(self, pending=None) -> None:
        """Store the fake pending question.

        Parameters
        ----------
        pending : object or None
            Value returned as ``_pending``.

        Returns
        -------
        None
            The fake is ready.
        """
        self._pending = pending
        self.resolved = 0
        self.state = None

    def _resolve_pending(self) -> None:
        """Record one pending-question resolution.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The counter is incremented.
        """
        self.resolved += 1

    def _set_state(self, state: str) -> None:
        """Record the latest eye state.

        Parameters
        ----------
        state : str
            Eye state name.

        Returns
        -------
        None
            The state is stored.
        """
        self.state = state


@unittest.skipUnless(HalWindow is not None, "PySide6 is not installed")
class HalStateTests(unittest.TestCase):
    """Verify the eye never stays stuck waiting for a spoken answer."""

    def test_empty_heard_resolves_and_idles(self) -> None:
        """Unrecognized speech releases the question and returns to idle.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        fake = _FakeHal(pending=object())
        HalWindow._handle_empty_heard(fake)
        self.assertEqual(fake.resolved, 1)
        self.assertEqual(fake.state, "idle")

    def test_ask_timeout_ignores_stale_question(self) -> None:
        """A timeout for an old question leaves the current one alone.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        fake = _FakeHal(pending=object())
        HalWindow._ask_timeout(fake, object())
        self.assertEqual(fake.resolved, 0)
        self.assertIsNone(fake.state)

    def test_ask_timeout_releases_active_question(self) -> None:
        """A timeout releases the active question and returns to idle.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        bridge = object()
        fake = _FakeHal(pending=bridge)
        HalWindow._ask_timeout(fake, bridge)
        self.assertEqual(fake.resolved, 1)
        self.assertEqual(fake.state, "idle")

    def test_log_error_appends_message(self) -> None:
        """Diagnostics are written where the app can read them later.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hal.log"
            with patch.dict(os.environ, {"HARNESS_HAL_LOG": str(path)}):
                _log_error("boom")
            self.assertIn("boom", path.read_text())
