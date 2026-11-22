"""Offline tests for the Research Desk welcome dialog and header."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWidgets import QCheckBox
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtWidgets import QTextBrowser

    from gui.app import MainWindow
    from gui.research_welcome import ResearchWelcomeDialog
    from gui.research_welcome import WELCOME_MARKDOWN
    from gui.settings import Settings
    from gui.store import SessionStore
except Exception:
    QApplication = None
    MainWindow = None
    ResearchWelcomeDialog = None


@unittest.skipIf(ResearchWelcomeDialog is None, "PySide6 is not installed")
class WelcomeDialogTests(unittest.TestCase):
    """Verify the introduction text, checkbox, and button."""

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

    def test_welcome_dialog_shows_required_content(self) -> None:
        """Show the introduction, suppression box, and accept button.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The required widgets and text are present.
        """
        dialog = ResearchWelcomeDialog()
        body = dialog.findChild(QTextBrowser).toPlainText()
        self.assertIn("Welcome to Research Desk", body)
        self.assertIn("What You Can Do", WELCOME_MARKDOWN)
        _assert_dialog_widgets(self, dialog)


def _assert_dialog_widgets(case, dialog):
    """Assert the suppression checkbox and accept button.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    dialog : ResearchWelcomeDialog
        Dialog under test.

    Returns
    -------
    None
        Widget assertions pass.
    """
    checkbox = dialog.findChild(QCheckBox)
    button = dialog.findChild(QPushButton)
    case.assertEqual(checkbox.text(), "Do not show this again")
    case.assertEqual(button.text(), "Got it - Let's Explore")
    case.assertFalse(dialog.dont_show_again())


def _open_twice(window):
    """Toggle Research Desk open twice with a patched dialog.

    Parameters
    ----------
    window : MainWindow
        Window under test.

    Returns
    -------
    unittest.mock.Mock
        Dialog class mock.
    """
    with patch("gui.app.ResearchWelcomeDialog") as dialog:
        window.toggle_research()
        window.toggle_research()
    return dialog


@unittest.skipIf(MainWindow is None, "PySide6 is not installed")
class WelcomeWindowTests(unittest.TestCase):
    """Verify first-use suppression and the persistent header."""

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
        self._build_window(base)
        self.addCleanup(self._close)

    def _build_window(self, base) -> None:
        """Create the temporary session store and window.

        Parameters
        ----------
        base : pathlib.Path
            Temporary base directory.

        Returns
        -------
        None
            The window is stored on the test.
        """
        self._settings_path = base / "settings.json"
        self._store = SessionStore(base / "sessions")
        self._store.create()
        settings = Settings(self._settings_path)
        self.window = MainWindow(self._store, base / "project", settings)

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

    def _close(self) -> None:
        """Stop worker threads and remove the temporary folder.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Resources are released.
        """
        self.window._stop_panels()
        self._folder.cleanup()

    def test_first_open_shows_welcome_once(self) -> None:
        """Show the welcome dialog only on the first open.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Later opens stay silent.
        """
        window = self.window
        dialog = _open_twice(window)
        self.assertEqual(dialog.call_count, 1)
        self.assertTrue(window._settings.get("research_desk_welcome_seen"))
        saved = Settings(self._settings_path)
        self.assertTrue(saved.get("research_desk_welcome_seen"))

    def test_help_icon_reopens_welcome(self) -> None:
        """Reopen the introduction from the header help icon.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dialog is shown again despite suppression.
        """
        window = self.window
        window._settings.set("research_desk_welcome_seen", True)
        with patch("gui.app.ResearchWelcomeDialog") as dialog:
            window._research_workspace._help_button.click()
        self.assertEqual(dialog.call_count, 1)

    def test_header_shows_current_project_name(self) -> None:
        """Show the project name beside the Research Desk title.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The header text is correct.
        """
        label = self.window._research_workspace._title_label
        self.assertEqual(label.text(), "Research Desk \u00b7 project")


if __name__ == "__main__":
    unittest.main()
