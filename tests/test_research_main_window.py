"""Offline tests for primary and research isolation in the main window."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


def _assert_survived(case, window, note, tombstone, thread_id):
    """Assert that a deleted thread kept its note and tombstone.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    window : MainWindow
        Window under test.
    note : dict
        Saved note.
    tombstone : pathlib.Path
        Tombstone folder.
    thread_id : str
        Deleted thread identifier.

    Returns
    -------
    None
        Assertions pass.
    """
    saved = window._note_store.get(note["id"])
    case.assertEqual(saved["title"], "A finding")
    case.assertTrue((tombstone / f"{thread_id}.json").exists())


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
        self._start_env(base)
        store = SessionStore(base / "sessions")
        store.create()
        settings = Settings(base / "settings.json")
        self.window = MainWindow(store, base / "project", settings)
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

    def test_thread_delete_keeps_saved_note(self) -> None:
        """Keep a saved note and tombstone after thread deletion.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The note survives and provenance is written.
        """
        window = self.window
        window._save_research_note("A finding")
        note = window._note_store.list(window._record.session_id)[0]
        thread_id = window._research_thread["id"]
        with patch.object(window, "_confirm_thread_delete", return_value=True):
            window._delete_research_thread(thread_id)
        tombstone = window._research_root / "tombstones" / "threads"
        _assert_survived(self, window, note, tombstone, thread_id)

    def test_transfer_prefills_target_composer(self) -> None:
        """Prefill the destination composer and record provenance.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The draft and transfer record are present.
        """
        window = self.window
        window._transfer_to_primary("research text", "selection")
        records = window._transfer_store.list()
        self.assertEqual(
            window._command_panel._input.toPlainText(), "research text"
        )
        self.assertEqual(records[0]["direction"], "research_to_primary")

    def test_web_search_results_are_captured_as_sources(self) -> None:
        """Store search results in the source store.

        Parameters
        ----------
        None

        Returns
        -------
        None
            One source is captured.
        """
        window = self.window
        content = '[{"url": "https://example.com", "title": "E"}]'
        window._capture_source("web_search", {}, content)
        self.assertEqual(
            len(window._source_store.list(window._record.session_id)), 1
        )

    def test_snapshot_toggle_is_persisted_per_thread(self) -> None:
        """Store the snapshot toggle on the active thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Thread metadata reflects the setting.
        """
        window = self.window
        window._on_snapshot_toggled(True)
        thread_id = window._research_thread["id"]
        self.assertTrue(
            window._thread_store.get(thread_id)["snapshot_enabled"]
        )

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
