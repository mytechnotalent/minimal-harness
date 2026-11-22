"""Tabbed research panel that keeps chat, threads, notes, and sources."""

from PySide6.QtCore import QSignalBlocker
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget
from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QTabWidget
from PySide6.QtWidgets import QTextBrowser
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget

_NO_NOTES = "No saved notes yet."
_NO_SOURCES = "No sources captured yet."


class ResearchWorkspace(QWidget):
    """Organize the research panel without replacing its chat."""

    thread_selected = Signal(str)
    new_thread_requested = Signal()

    def __init__(self, chat, storage_error=None):
        """Build the four research tabs around an existing chat panel.

        Parameters
        ----------
        chat : QWidget
            Research chat panel.
        storage_error : str or None
            Optional research storage error.

        Returns
        -------
        None
            The workspace is ready to show.
        """
        super().__init__()
        self.chat = chat
        self._notes, self._sources = [], []
        self._build_layout()
        self.set_storage_error(storage_error)

    def _build_layout(self):
        """Create the tab container.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The tab widget is installed.
        """
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._tabs = QTabWidget(self)
        self._add_tabs()
        self._layout.addWidget(self._tabs)

    def _add_tabs(self):
        """Add the four research tabs in display order.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The chat tab is first and selected by default.
        """
        self._tabs.addTab(self.chat, "Chat")
        self._tabs.addTab(self._build_threads(), "Threads")
        self._tabs.addTab(self._build_notes(), "Notes")
        self._tabs.addTab(self._build_sources(), "Sources")

    def _build_threads(self):
        """Build the thread selection page.

        Parameters
        ----------
        None

        Returns
        -------
        QWidget
            Thread page.
        """
        page = QWidget(self)
        box = QVBoxLayout(page)
        self._thread_list = QListWidget(page)
        self._thread_list.itemClicked.connect(self._thread_clicked)
        box.addWidget(self._thread_list)
        box.addWidget(self._new_thread_button(page))
        return page

    def _new_thread_button(self, page):
        """Build the new-thread button.

        Parameters
        ----------
        page : QWidget
            Owning thread page.

        Returns
        -------
        QPushButton
            Button that requests a new thread.
        """
        button = QPushButton("New research thread", page)
        button.clicked.connect(self.new_thread_requested.emit)
        return button

    def _build_notes(self):
        """Build the notes list and read-only viewer.

        Parameters
        ----------
        None

        Returns
        -------
        QWidget
            Notes page.
        """
        page = QWidget(self)
        box = QVBoxLayout(page)
        self._note_list, self._note_view = _note_widgets(page)
        self._note_list.itemClicked.connect(self._show_note)
        box.addWidget(self._note_list)
        box.addWidget(self._note_view)
        return page

    def _build_sources(self):
        """Build the source list and read-only viewer.

        Parameters
        ----------
        None

        Returns
        -------
        QWidget
            Sources page.
        """
        page = QWidget(self)
        box = QVBoxLayout(page)
        self._source_list, self._source_view = _source_widgets(page)
        self._source_list.itemClicked.connect(self._show_source)
        box.addWidget(self._source_list)
        box.addWidget(self._source_view)
        return page

    def set_threads(self, threads, active_id):
        """Populate the thread list without emitting selection signals.

        Parameters
        ----------
        threads : list
            Thread metadata records.
        active_id : str or None
            Currently active thread identifier.

        Returns
        -------
        None
            The thread list is refreshed.
        """
        blocker = QSignalBlocker(self._thread_list)
        self._thread_list.clear()
        for thread in threads:
            self._add_thread(thread, active_id)
        del blocker

    def _add_thread(self, thread, active_id):
        """Add one thread row and select it when active.

        Parameters
        ----------
        thread : dict
            Thread metadata.
        active_id : str or None
            Currently active thread identifier.

        Returns
        -------
        None
            The row is added.
        """
        item = QListWidgetItem(thread.get("title") or thread["id"])
        item.setData(Qt.UserRole, thread["id"])
        self._thread_list.addItem(item)
        if thread["id"] == active_id:
            self._thread_list.setCurrentItem(item)

    def _thread_clicked(self, item):
        """Emit the identifier of a clicked thread.

        Parameters
        ----------
        item : QListWidgetItem
            Clicked thread row.

        Returns
        -------
        None
            The selection signal is emitted.
        """
        thread_id = item.data(Qt.UserRole)
        if thread_id:
            self.thread_selected.emit(thread_id)

    def set_notes(self, notes):
        """Populate the notes tab.

        Parameters
        ----------
        notes : list
            Note records for the active session.

        Returns
        -------
        None
            The notes list is refreshed.
        """
        self._notes = list(notes)
        self._note_list.clear()
        for note in self._notes:
            self._note_list.addItem(note.get("title") or note["id"])
        self._select_first(
            self._note_list, self._note_view, "No saved notes yet."
        )

    def _show_note(self, item):
        """Render the selected note as markdown.

        Parameters
        ----------
        item : QListWidgetItem
            Selected note row.

        Returns
        -------
        None
            The note viewer is updated.
        """
        row = self._note_list.row(item)
        if 0 <= row < len(self._notes):
            self._note_view.setMarkdown(self._notes[row].get("body_md", ""))

    def set_sources(self, sources):
        """Populate the sources tab.

        Parameters
        ----------
        sources : list
            Source records for the active session.

        Returns
        -------
        None
            The sources list is refreshed.
        """
        self._sources = list(sources)
        self._source_list.clear()
        for source in self._sources:
            self._source_list.addItem(source.get("title") or source["id"])
        self._select_first(self._source_list, self._source_view, _NO_SOURCES)

    def _show_source(self, item):
        """Render the selected source metadata.

        Parameters
        ----------
        item : QListWidgetItem
            Selected source row.

        Returns
        -------
        None
            The source viewer is updated.
        """
        row = self._source_list.row(item)
        if 0 <= row < len(self._sources):
            self._source_view.setMarkdown(_source_text(self._sources[row]))

    def set_storage_error(self, message):
        """Show a storage error in the notes and source tabs.

        Parameters
        ----------
        message : str or None
            Error message, or ``None`` when storage works.

        Returns
        -------
        None
            The tabs show the current storage state.
        """
        if message:
            self._show_empty(self._note_view, message)
            self._show_empty(self._source_view, message)
            return
        self.set_notes(self._notes)
        self.set_sources(self._sources)

    def _select_first(self, listing, viewer, empty_text):
        """Select the first row or show an empty message.

        Parameters
        ----------
        listing : QListWidget
            List to select from.
        viewer : QTextBrowser
            Viewer to update.
        empty_text : str
            Text shown when the list is empty.

        Returns
        -------
        None
            Selection and empty state are updated.
        """
        if listing.count():
            listing.setCurrentRow(0)
            return
        self._show_empty(viewer, empty_text)

    def _show_empty(self, viewer, text):
        """Show an empty-state message in a viewer.

        Parameters
        ----------
        viewer : QTextBrowser
            Target viewer.
        text : str
            Message to display.

        Returns
        -------
        None
            The viewer is updated.
        """
        viewer.setPlainText(text)


def _note_widgets(page):
    """Build the notes list and viewer pair.

    Parameters
    ----------
    page : QWidget
        Owning tab page.

    Returns
    -------
    tuple
        List and viewer widgets.
    """
    listing = QListWidget(page)
    viewer = QTextBrowser(page)
    viewer.setOpenExternalLinks(False)
    return listing, viewer


def _source_widgets(page):
    """Build the sources list and viewer pair.

    Parameters
    ----------
    page : QWidget
        Owning tab page.

    Returns
    -------
    tuple
        List and viewer widgets.
    """
    listing = QListWidget(page)
    viewer = QTextBrowser(page)
    viewer.setOpenExternalLinks(False)
    return listing, viewer


def _source_text(source):
    """Format one source as markdown.

    Parameters
    ----------
    source : dict
        Source record.

    Returns
    -------
    str
        Markdown for the source viewer.
    """
    title = source.get("title") or source.get("url", "")
    parts = [f"**{title}**", source.get("url", ""), source.get("excerpt", "")]
    return "\n\n".join(part for part in parts if part)
