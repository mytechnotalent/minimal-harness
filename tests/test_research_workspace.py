"""Offline tests for the tabbed research workspace."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWidgets import QWidget

    from gui.research_workspace import ResearchWorkspace
except Exception:
    QApplication = None
    ResearchWorkspace = None
    QWidget = None


def _source():
    """Build one source record for the fixture.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Source record.
    """
    source = {"id": "src_" + "0" * 32, "title": "S"}
    source.update({"url": "https://example.com", "excerpt": "text"})
    return source


@unittest.skipIf(ResearchWorkspace is None, "PySide6 is not installed")
class ResearchWorkspaceTests(unittest.TestCase):
    """Verify tabs, thread selection, notes, and sources."""

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

    def _workspace(self, error=None):
        """Build a workspace around a plain chat widget.

        Parameters
        ----------
        error : str or None
            Optional storage error.

        Returns
        -------
        ResearchWorkspace
            Workspace under test.
        """
        return ResearchWorkspace(QWidget(), error)

    def test_chat_is_the_default_tab(self) -> None:
        """Show four tabs with chat first.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The tab order is asserted.
        """
        workspace = self._workspace()
        self.assertEqual(workspace._tabs.count(), 4)
        self.assertEqual(workspace._tabs.tabText(0), "Chat")

    def test_thread_selection_emits_identifier(self) -> None:
        """Emit the selected thread through the workspace signal.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The selected identifier matches.
        """
        workspace = self._workspace()
        first = {"id": "th_" + "0" * 32, "title": "One"}
        second = {"id": "th_" + "1" * 32, "title": "Two"}
        selected = []
        workspace.thread_selected.connect(selected.append)
        workspace.set_threads([first, second], first["id"])
        workspace._thread_clicked(workspace._thread_list.item(1))
        self.assertEqual(selected, [second["id"]])

    def test_notes_render_in_the_notes_tab(self) -> None:
        """Render a selected note body.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The note text appears in the viewer.
        """
        workspace = self._workspace()
        note = {"id": "nt_" + "0" * 32, "title": "N", "body_md": "body text"}
        workspace.set_notes([note])
        workspace._show_note(workspace._note_list.item(0))
        self.assertIn("body text", workspace._note_view.toPlainText())

    def test_sources_render_in_the_sources_tab(self) -> None:
        """Render a selected source URL.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The URL appears in the viewer.
        """
        workspace = self._workspace()
        workspace.set_sources([_source()])
        workspace._show_source(workspace._source_list.item(0))
        self.assertIn("example.com", workspace._source_view.toPlainText())

    def test_storage_error_is_visible(self) -> None:
        """Show a storage error in the research tabs.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The error text is displayed.
        """
        workspace = self._workspace("storage unavailable")
        self.assertIn(
            "storage unavailable", workspace._note_view.toPlainText()
        )


if __name__ == "__main__":
    unittest.main()
