"""Offline tests for HAL eye-state recovery."""

import unittest

try:
    from gui.hal import HalWindow
except Exception:
    HalWindow = None


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
        """Unrecognized speech releases the question and returns to idle."""
        fake = _FakeHal(pending=object())
        HalWindow._handle_empty_heard(fake)
        self.assertEqual(fake.resolved, 1)
        self.assertEqual(fake.state, "idle")

    def test_ask_timeout_ignores_stale_question(self) -> None:
        """A timeout for an old question leaves the current one alone."""
        fake = _FakeHal(pending=object())
        HalWindow._ask_timeout(fake, object())
        self.assertEqual(fake.resolved, 0)
        self.assertIsNone(fake.state)

    def test_ask_timeout_releases_active_question(self) -> None:
        """A timeout releases the active question and returns to idle."""
        bridge = object()
        fake = _FakeHal(pending=bridge)
        HalWindow._ask_timeout(fake, bridge)
        self.assertEqual(fake.resolved, 1)
        self.assertEqual(fake.state, "idle")
