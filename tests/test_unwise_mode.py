"""Offline tests for the 50 percent opacity Unwise Mode toggle."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from gui.app import MainWindow
    from gui.settings import Settings
    from gui.store import SessionStore
except Exception:
    QApplication = None
    MainWindow = None


def _assert_wayland_effect(case, window):
    """Toggle Unwise Mode and assert the Wayland fallback.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    window : MainWindow
        Window under test.

    Returns
    -------
    None
        Effect assertions pass.
    """
    case.assertTrue(window.testAttribute(Qt.WA_TranslucentBackground))
    window._unwise_button.click()
    effect = window.graphicsEffect()
    case.assertIsNotNone(effect)
    case.assertAlmostEqual(effect.opacity(), 0.5)
    window._unwise_button.click()
    case.assertIsNone(window.graphicsEffect())


@unittest.skipIf(MainWindow is None, "PySide6 is not installed")
class UnwiseModeTests(unittest.TestCase):
    """Verify Unwise Mode opacity, persistence, and coexistence."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create the shared Qt application.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The application is stored on the class.
        """
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        """Build a temporary window with one session.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The window is ready for a test.
        """
        self._folder = tempfile.TemporaryDirectory()
        base = Path(self._folder.name)
        self._start_env(base)
        self._base = base
        self._store = SessionStore(base / "sessions")
        self._store.create()
        self.addCleanup(self._close)

    def _start_env(self, base) -> None:
        """Point research storage at the temporary folder.

        Parameters
        ----------
        base : pathlib.Path
            Temporary base directory.

        Returns
        -------
        None
            The environment override is active.
        """
        env = {"HARNESS_RESEARCH_DIR": str(base / "research")}
        self._env = patch.dict(os.environ, env)
        self._env.start()
        self.addCleanup(self._env.stop)

    def _window(self, unwise=False, dark=True):
        """Build a window with chosen Unwise Mode and dark mode settings.

        Parameters
        ----------
        unwise : bool
            Initial Unwise Mode value.
        dark : bool
            Initial dark mode value.

        Returns
        -------
        MainWindow
            Window under test.
        """
        settings = Settings(self._base / "settings.json")
        settings.set("unwise_mode", unwise)
        settings.set("dark_mode", dark)
        window = MainWindow(self._store, self._base / "project", settings)
        self.addCleanup(window._stop_panels)
        return window

    def _close(self) -> None:
        """Remove the temporary folder.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Resources are released.
        """
        self._folder.cleanup()

    def test_unwise_toggle_applies_half_opacity_and_persists(self) -> None:
        """Toggle Unwise Mode on and off with immediate persistence.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Opacity and the stored setting change immediately.
        """
        window = self._window()
        self.assertEqual(window.windowOpacity(), 1.0)
        window._unwise_button.click()
        self.assertAlmostEqual(window.windowOpacity(), 0.5, places=2)
        self.assertTrue(window._settings.get("unwise_mode"))
        window._unwise_button.click()
        self.assertEqual(window.windowOpacity(), 1.0)
        self.assertFalse(window._settings.get("unwise_mode"))

    def test_unwise_mode_is_restored_from_settings(self) -> None:
        """Apply Unwise Mode on startup when persisted.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The window starts at 50 percent opacity.
        """
        window = self._window(unwise=True)
        self.assertTrue(window._unwise_button.isChecked())
        self.assertAlmostEqual(window.windowOpacity(), 0.5, places=2)

    def test_wayland_uses_graphics_opacity_effect(self) -> None:
        """Use a graphics effect where window opacity is unsupported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The effect is applied and removed on Wayland.
        """
        with patch("gui.app._window_platform", return_value="wayland"):
            window = self._window()
            _assert_wayland_effect(self, window)

    def test_dark_psycho_toggle_still_works_with_unwise(self) -> None:
        """Keep the existing dark and psycho toggle behavior.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Dark mode and Unwise Mode remain independent.
        """
        window = self._window(dark=False)
        window._dark_button.click()
        self.assertTrue(window._settings.get("dark_mode"))
        self.assertEqual(window.windowOpacity(), 1.0)
        window._unwise_button.click()
        window._dark_button.click()
        self.assertFalse(window._settings.get("dark_mode"))
        self.assertAlmostEqual(window.windowOpacity(), 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
