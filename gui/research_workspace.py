"""Tabbed research panel that keeps chat, threads, notes, and sources."""

from PySide6.QtCore import QSignalBlocker
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
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
    thread_archive_requested = Signal(str)
    thread_restore_requested = Signal(str)
    thread_delete_requested = Signal(str)
    archived_toggled = Signal(bool)
    edit_note_requested = Signal(str)
    revisions_requested = Signal(str)
    proposal_save_requested = Signal(str)
    proposal_discard_requested = Signal(str)

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
        self._notes, self._all_notes = [], []
        self._sources, self._all_sources = [], []
        self._proposals = []
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
        box.addLayout(self._thread_actions(page))
        return page

    def _thread_actions(self, page):
        """Build thread control buttons and the archived toggle.

        Parameters
        ----------
        page : QWidget
            Owning thread page.

        Returns
        -------
        QHBoxLayout
            Thread action row.
        """
        row = QHBoxLayout()
        _thread_buttons(self, row, page)
        self._archived_box = QCheckBox("Show archived", page)
        self._archived_box.toggled.connect(self.archived_toggled.emit)
        row.addWidget(self._archived_box)
        return row

    def _build_notes(self):
        """Build the notes page with search, editing, and proposals.

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
        self._build_note_body(box, page)
        box.addLayout(self._note_actions(page))
        self._build_proposals(box, page)
        return page

    def _build_note_body(self, box, page):
        """Build note search, list, and viewer widgets.

        Parameters
        ----------
        box : QVBoxLayout
            Notes page layout.
        page : QWidget
            Owning notes page.

        Returns
        -------
        None
            Widgets are added.
        """
        self._note_search = _search_box(page, self._filter_notes)
        self._note_list, self._note_view = _note_widgets(page)
        self._note_list.itemClicked.connect(self._show_note)
        box.addWidget(self._note_search)
        box.addWidget(self._note_list)
        box.addWidget(self._note_view)

    def _note_actions(self, page):
        """Build note edit and revision buttons.

        Parameters
        ----------
        page : QWidget
            Owning notes page.

        Returns
        -------
        QHBoxLayout
            Note action row.
        """
        row = QHBoxLayout()
        row.addWidget(_action_button("Edit note", self._edit_note, page))
        row.addWidget(_action_button("Revisions", self._show_revisions, page))
        return row

    def _build_proposals(self, box, page):
        """Build the pending proposal list and actions.

        Parameters
        ----------
        box : QVBoxLayout
            Notes page layout.
        page : QWidget
            Owning notes page.

        Returns
        -------
        None
            Proposal widgets are added.
        """
        box.addWidget(QLabel("Pending note proposals", page))
        self._proposal_list = QListWidget(page)
        box.addWidget(self._proposal_list)
        box.addLayout(self._proposal_actions(page))

    def _proposal_actions(self, page):
        """Build proposal save and discard buttons.

        Parameters
        ----------
        page : QWidget
            Owning notes page.

        Returns
        -------
        QHBoxLayout
            Proposal action row.
        """
        row = QHBoxLayout()
        row.addWidget(
            _action_button("Save proposal", self._save_proposal, page)
        )
        row.addWidget(_action_button("Discard", self._discard_proposal, page))
        return row

    def _build_sources(self):
        """Build the source page with search and a viewer.

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
        self._build_source_body(box, page)
        return page

    def _build_source_body(self, box, page):
        """Build source search, list, and viewer widgets.

        Parameters
        ----------
        box : QVBoxLayout
            Sources page layout.
        page : QWidget
            Owning sources page.

        Returns
        -------
        None
            Widgets are added.
        """
        self._source_search = _search_box(page, self._filter_sources)
        self._source_list, self._source_view = _source_widgets(page)
        self._source_list.itemClicked.connect(self._show_source)
        box.addWidget(self._source_search)
        box.addWidget(self._source_list)
        box.addWidget(self._source_view)

    def show_notes(self):
        """Select the Notes tab.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The notes tab becomes visible.
        """
        self._tabs.setCurrentIndex(2)

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

    def _new_thread(self):
        """Request a new thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self.new_thread_requested.emit()

    def _archive_thread(self):
        """Request archival of the selected thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self._emit_selected(self.thread_archive_requested, self._thread_list)

    def _restore_thread(self):
        """Request restoration of the selected thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self._emit_selected(self.thread_restore_requested, self._thread_list)

    def _delete_thread(self):
        """Request deletion of the selected thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self._emit_selected(self.thread_delete_requested, self._thread_list)

    def set_notes(self, notes):
        """Populate the notes tab and apply the current search.

        Parameters
        ----------
        notes : list
            Note records for the active session.

        Returns
        -------
        None
            The notes list is refreshed.
        """
        self._all_notes = list(notes)
        self._filter_notes(self._note_search.text())

    def _filter_notes(self, text):
        """Filter notes by a case-insensitive query.

        Parameters
        ----------
        text : str
            Search text.

        Returns
        -------
        None
            The visible note list is rebuilt.
        """
        needle = text.strip().lower()
        self._notes = _matching(self._all_notes, _note_has, needle)
        self._refill_notes()
        self._select_first(self._note_list, self._note_view, _NO_NOTES)

    def _refill_notes(self):
        """Rebuild the visible note rows.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The note list reflects the filtered notes.
        """
        self._note_list.clear()
        for note in self._notes:
            self._add_note_item(note)

    def _add_note_item(self, note):
        """Add one note row.

        Parameters
        ----------
        note : dict
            Note record.

        Returns
        -------
        None
            The row is added.
        """
        item = QListWidgetItem(note.get("title") or note["id"])
        item.setData(Qt.UserRole, note["id"])
        self._note_list.addItem(item)

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

    def _edit_note(self):
        """Request an edit for the selected note.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self._emit_selected(self.edit_note_requested, self._note_list)

    def _show_revisions(self):
        """Request revisions for the selected note.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self._emit_selected(self.revisions_requested, self._note_list)

    def set_sources(self, sources):
        """Populate the sources tab and apply the current search.

        Parameters
        ----------
        sources : list
            Source records for the active session.

        Returns
        -------
        None
            The sources list is refreshed.
        """
        self._all_sources = list(sources)
        self._filter_sources(self._source_search.text())

    def _filter_sources(self, text):
        """Filter sources by a case-insensitive query.

        Parameters
        ----------
        text : str
            Search text.

        Returns
        -------
        None
            The visible source list is rebuilt.
        """
        needle = text.strip().lower()
        self._sources = _matching(self._all_sources, _source_has, needle)
        self._refill_sources()
        self._select_first(self._source_list, self._source_view, _NO_SOURCES)

    def _refill_sources(self):
        """Rebuild the visible source rows.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The source list reflects the filtered sources.
        """
        self._source_list.clear()
        for source in self._sources:
            self._add_source_item(source)

    def _add_source_item(self, source):
        """Add one source row.

        Parameters
        ----------
        source : dict
            Source record.

        Returns
        -------
        None
            The row is added.
        """
        item = QListWidgetItem(source.get("title") or source["id"])
        item.setData(Qt.UserRole, source["id"])
        self._source_list.addItem(item)

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

    def set_proposals(self, proposals):
        """Populate pending note proposals.

        Parameters
        ----------
        proposals : list
            Pending proposal records.

        Returns
        -------
        None
            The proposal list is refreshed.
        """
        self._proposals = list(proposals)
        self._proposal_list.clear()
        for proposal in self._proposals:
            item = QListWidgetItem(proposal.get("title") or proposal["id"])
            item.setData(Qt.UserRole, proposal["id"])
            self._proposal_list.addItem(item)
        if self._proposal_list.count():
            self._proposal_list.setCurrentRow(0)

    def _save_proposal(self):
        """Request saving the selected proposal.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self._emit_selected(self.proposal_save_requested, self._proposal_list)

    def _discard_proposal(self):
        """Request discarding the selected proposal.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The request signal is emitted.
        """
        self._emit_selected(
            self.proposal_discard_requested, self._proposal_list
        )

    def _emit_selected(self, signal, listing):
        """Emit the identifier of the selected row.

        Parameters
        ----------
        signal : Signal
            Signal to emit.
        listing : QListWidget
            Source list.

        Returns
        -------
        None
            The signal is emitted when a row is selected.
        """
        item = listing.currentItem()
        if item is not None:
            signal.emit(item.data(Qt.UserRole))

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
        self.set_notes(self._all_notes)
        self.set_sources(self._all_sources)

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


def _thread_buttons(workspace, row, page):
    """Add thread lifecycle buttons to a row.

    Parameters
    ----------
    workspace : ResearchWorkspace
        Owning workspace.
    row : QHBoxLayout
        Action row.
    page : QWidget
        Owning thread page.

    Returns
    -------
    None
        Buttons are added.
    """
    row.addWidget(_action_button("New", workspace._new_thread, page))
    row.addWidget(_action_button("Archive", workspace._archive_thread, page))
    row.addWidget(_action_button("Restore", workspace._restore_thread, page))
    row.addWidget(_action_button("Delete", workspace._delete_thread, page))


def _action_button(label, callback, parent):
    """Build one action button.

    Parameters
    ----------
    label : str
        Button text.
    callback : collections.abc.Callable
        Click handler.
    parent : QWidget
        Owning widget.

    Returns
    -------
    QPushButton
        Configured button.
    """
    button = QPushButton(label, parent)
    button.clicked.connect(callback)
    return button


def _search_box(page, callback):
    """Build a search field connected to a filter callback.

    Parameters
    ----------
    page : QWidget
        Owning tab page.
    callback : collections.abc.Callable
        Text change handler.

    Returns
    -------
    QLineEdit
        Configured search field.
    """
    field = QLineEdit(page)
    field.setPlaceholderText("Search")
    field.textChanged.connect(callback)
    return field


def _matching(items, matcher, needle):
    """Return items accepted by a matcher.

    Parameters
    ----------
    items : list
        Candidate records.
    matcher : collections.abc.Callable
        Record and needle predicate.
    needle : str
        Lowercase query.

    Returns
    -------
    list
        Matching records.
    """
    return [item for item in items if matcher(item, needle)]


def _note_has(note, needle):
    """Return whether a note matches a search query.

    Parameters
    ----------
    note : dict
        Note record.
    needle : str
        Lowercase query.

    Returns
    -------
    bool
        ``True`` when the note matches.
    """
    tags = " ".join(str(tag) for tag in note.get("tags", []))
    text = " ".join([note.get("title", ""), note.get("body_md", ""), tags])
    return needle in text.lower()


def _source_has(source, needle):
    """Return whether a source matches a search query.

    Parameters
    ----------
    source : dict
        Source record.
    needle : str
        Lowercase query.

    Returns
    -------
    bool
        ``True`` when the source matches.
    """
    text = " ".join(
        [
            source.get("title", ""),
            source.get("url", ""),
            source.get("excerpt", ""),
        ]
    )
    return needle in text.lower()


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
