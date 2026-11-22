"""Offline tests for primary and research isolation in the main window."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from gui.app import MainWindow
    from gui.settings import Settings
    from gui.store import SessionStore
except Exception:
    QApplication = None
    MainWindow = None


def _assert_isolation(case, window):
    """Assert that research state is independent of primary state.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    window : MainWindow
        Window under test.

    Returns
    -------
    None
        Isolation assertions pass.
    """
    research = window._research_panel
    case.assertEqual(window._research_workspace._tabs.count(), 4)
    case.assertIn("research", research._agent.system_prompt.lower())
    case.assertNotEqual(
        research._agent.session.path, window._record.transcript
    )
    _assert_read_only(case, research)
    case.assertEqual(window._make_research_context(), "")


def _assert_read_only(case, research):
    """Assert that the research agent is read-only.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    research : ChatPanel
        Research panel.

    Returns
    -------
    None
        Security assertions pass.
    """
    case.assertTrue(research._agent.tools.read_only)
    case.assertNotIn("write", research._agent.tools.tools)


@unittest.skipIf(MainWindow is None, "PySide6 is not installed")
class MainWindowResearchTests(unittest.TestCase):
    """Verify the research panel stays separate from the primary chat."""

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
        store = SessionStore(base / "sessions")
        store.create()
        settings = Settings(base / "settings.json")
        self.window = MainWindow(store, base / "project", settings)
        self.addCleanup(self._close)

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

    def test_research_is_independent_from_primary(self) -> None:
        """Keep transcripts, prompts, and thread selection separate.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Isolation guarantees are asserted.
        """
        window = self.window
        _assert_isolation(self, window)
        record = window._record
        window._new_research_thread()
        self.assertIs(window._record, record)


if __name__ == "__main__":
    unittest.main()
