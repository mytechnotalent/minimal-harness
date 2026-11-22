"""Read-only viewer for restored primary history."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QListWidget
from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtWidgets import QTextBrowser
from PySide6.QtWidgets import QVBoxLayout


class RestoredHistoryDialog(QDialog):
    """Show archived primary transcripts without merging them."""

    def __init__(self, histories, loader, parent=None):
        """Build the restored history viewer.

        Parameters
        ----------
        histories : list
            Restored history metadata records.
        loader : collections.abc.Callable
            Callable returning transcript messages for one history.
        parent : QWidget or None
            Optional parent widget.

        Returns
        -------
        None
            The dialog is ready to show.
        """
        super().__init__(parent)
        self._histories = list(histories)
        self._loader = loader
        self._build_window()
        self._populate()

    def _build_window(self):
        """Compose the dialog layout.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The layout and widgets are created.
        """
        self.setWindowTitle("Restored history")
        self.resize(780, 520)
        self._layout = QVBoxLayout(self)
        self._layout.addWidget(self._notice())
        self._layout.addWidget(self._list_widget())
        self._layout.addWidget(self._view_widget())

    def _list_widget(self):
        """Build the history selector.

        Parameters
        ----------
        None

        Returns
        -------
        QListWidget
            History list.
        """
        self._list = QListWidget(self)
        self._list.itemClicked.connect(self._show)
        return self._list

    def _view_widget(self):
        """Build the read-only transcript viewer.

        Parameters
        ----------
        None

        Returns
        -------
        QTextBrowser
            Transcript viewer.
        """
        self._view = QTextBrowser(self)
        self._view.setOpenExternalLinks(False)
        return self._view

    def _notice(self):
        """Build the read-only notice label.

        Parameters
        ----------
        None

        Returns
        -------
        QLabel
            Notice label.
        """
        text = "Read-only restored history. This is never merged into chat."
        label = QLabel(text, self)
        label.setWordWrap(True)
        return label

    def _populate(self):
        """Fill the history list and open the first entry.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The list reflects all restored histories.
        """
        for history in self._histories:
            title = history.get("original_title") or history["id"]
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, history["id"])
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
            self._show(self._list.item(0))

    def _show(self, item):
        """Render the selected restored transcript.

        Parameters
        ----------
        item : QListWidgetItem
            Selected history row.

        Returns
        -------
        None
            The viewer shows the transcript.
        """
        messages = self._loader(item.data(Qt.UserRole))
        self._view.setMarkdown(_format_messages(messages))


def _format_messages(messages):
    """Format transcript messages as markdown.

    Parameters
    ----------
    messages : list
        Transcript messages.

    Returns
    -------
    str
        Markdown transcript.
    """
    lines = []
    for message in messages:
        content = message.get("content")
        if not content:
            continue
        role = message.get("role", "unknown")
        lines.append(f"**{role}:** {content}")
    return "\n\n".join(lines) or "No messages in this restored history."
