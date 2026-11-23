"""Offline integration tests for archive, delete, and restore actions."""

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


def _archive_choice(window):
    """Archive the active session through the delete dialog choice.

    Parameters
    ----------
    window : MainWindow
        Window under test.

    Returns
    -------
    dict
        Archive manifest.
    """
    with patch.object(window, "_delete_choice", return_value="archive"):
        window._delete(window._record)
    return window._archive_service.list()[0]


def _delete_choice(window):
    """Delete the active session through the delete dialog choice.

    Parameters
    ----------
    window : MainWindow
        Window under test.

    Returns
    -------
    None
        The session is deleted.
    """
    with patch.object(window, "_delete_choice", return_value="delete"):
        window._delete(window._record)


def _restore_choice(window, manifest):
    """Restore one manifest through the sidebar action.

    Parameters
    ----------
    window : MainWindow
        Window under test.
    manifest : dict
        Archive manifest.

    Returns
    -------
    None
        The restore runs.
    """
    with patch.object(window, "_archive_choice", return_value=manifest):
        window._restore_archive()


def _tamper(root, manifest):
    """Corrupt one archived file.

    Parameters
    ----------
    root : pathlib.Path
        Research root.
    manifest : dict
        Archive manifest.

    Returns
    -------
    None
        The archive no longer verifies.
    """
    folder = root / "archives" / manifest["archive_id"]
    (folder / manifest["files"][0]["path"]).write_bytes(b"tampered")


def _restored_notes(case, window, before):
    """Archive, restore, and assert the new session records.

    Parameters
    ----------
    case : unittest.TestCase
        Owning test case.
    window : MainWindow
        Window under test.
    before : int
        Session count before the restore.

    Returns
    -------
    None
        Restore assertions pass.
    """
    manifest = _archive_choice(window)
    _restore_choice(window, manifest)
    notes = window._note_store.list(window._record.session_id, status=None)
    case.assertEqual(len(window._store.list()), before + 1)
    case.assertEqual(notes[0]["title"], "A finding")


def _corrupt_restore_attempt(window):
    """Attempt to restore a corrupt archive.

    Parameters
    ----------
    window : MainWindow
        Window under test.

    Returns
    -------
    tuple
        Warning mock and session count before the attempt.
    """
    manifest = _archive_choice(window)
    _tamper(window._research_root, manifest)
    before = len(window._store.list())
    with patch("gui.app.QMessageBox.warning") as warning:
        _restore_choice(window, manifest)
    return warning, before


@unittest.skipIf(MainWindow is None, "PySide6 is not installed")
class ArchiveUiTests(unittest.TestCase):
    """Verify the session archive, delete, and restore UI flows."""

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
        self._store = SessionStore(base / "sessions")
        self._store.create()
        settings = Settings(base / "settings.json")
        self.window = MainWindow(self._store, base / "project", settings)
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

    def test_sidebar_has_restore_archive_button(self) -> None:
        """Expose a restore archive button in the sidebar.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The button label is correct.
        """
        self.assertEqual(self.window._restore_button.text(), "Restore archive")

    def test_archive_choice_archives_and_replaces_session(self) -> None:
        """Archive the active session and activate another one.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The archive exists and the old live note is gone.
        """
        window = self.window
        window._save_research_note("A finding")
        session_id = window._record.session_id
        manifest = _archive_choice(window)
        self.assertEqual(manifest["original_session_id"], session_id)
        self.assertEqual(window._note_store.list(session_id, status=None), [])
        self.assertNotEqual(window._record.session_id, session_id)

    def test_delete_all_removes_scoped_records(self) -> None:
        """Delete the session folder and every scoped global record.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Live data is gone.
        """
        window = self.window
        window._save_research_note("A finding")
        record = window._record
        _delete_choice(window)
        self.assertFalse(record.folder.exists())
        self.assertEqual(
            window._note_store.list(record.session_id, status=None), []
        )

    def test_restore_archive_restores_into_new_session(self) -> None:
        """Restore an archive into a new active session.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The restored note is present.
        """
        window = self.window
        window._save_research_note("A finding")
        before = len(self._store.list())
        _restored_notes(self, window, before)

    def test_corrupt_archive_is_not_restored(self) -> None:
        """Show a verification warning and leave sessions unchanged.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The restore is refused.
        """
        window = self.window
        window._save_research_note("A finding")
        warning, before = _corrupt_restore_attempt(window)
        self.assertTrue(warning.called)
        self.assertEqual(len(self._store.list()), before)


if __name__ == "__main__":
    unittest.main()
