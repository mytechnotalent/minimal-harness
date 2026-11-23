"""Offline tests for the dark mode palette and setting."""

import tempfile
import unittest
from pathlib import Path

from gui.settings import Settings
from gui.style import DARK_STYLESHEET
from gui.style import STYLESHEET


class DarkModeTest(unittest.TestCase):
    """Verify the dark mode default and stylesheet."""

    def test_dark_mode_defaults_on(self) -> None:
        """Fresh settings enable dark mode.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The default value is asserted.
        """
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder) / "settings.json")
            self.assertTrue(settings.get("dark_mode"))

    def test_dark_stylesheet_uses_dark_background(self) -> None:
        """The dark sheet differs and uses a dark surface.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The palette contents are asserted.
        """
        self.assertIn("background-color: #12181D", DARK_STYLESHEET)
        self.assertNotEqual(DARK_STYLESHEET, STYLESHEET)
