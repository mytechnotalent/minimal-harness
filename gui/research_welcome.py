"""Research Desk welcome dialog and its introduction text."""

from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QTextBrowser
from PySide6.QtWidgets import QVBoxLayout

WELCOME_MARKDOWN = """# Welcome to Research Desk

Your dedicated research space for this project.

Every project has its own Research Desk. Your research conversations,
notes, sources, and findings stay associated with the project they belong
to. When you switch projects, you'll see that project's separate Research
Desk.

### What You Can Do

**Threads**
Create separate research conversations to explore different questions,
topics, and problems.

**Chat**
Work with your research AI to investigate ideas, analyze information, and
explore possibilities.

**Notes**
Save, edit, organize, and revisit important findings. Your notes retain
their history so you can review earlier versions.

**Sources**
Collect and manage websites, references, and supporting evidence gathered
during research.

### Work Between Your Two Spaces

Research Desk is separate from Primary Chat. Nothing is automatically
shared between them.

You can deliberately send entire messages or selected passages between
Primary Chat and Research Desk whenever you want to transfer information.

### Your Research, Your Control

Research Desk can examine project materials and approved research sources,
but it cannot modify your project files.

You control what gets researched, saved, archived, and shared.
"""


class ResearchWelcomeDialog(QDialog):
    """Introduce Research Desk on first use and from the help icon."""

    def __init__(self, parent=None):
        """Build the welcome dialog.

        Parameters
        ----------
        parent : QWidget or None
            Optional parent widget.

        Returns
        -------
        None
            The dialog is ready to show.
        """
        super().__init__(parent)
        self._build_window()

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
        self.setWindowTitle("Research Desk")
        self.resize(760, 680)
        layout = QVBoxLayout(self)
        layout.addWidget(self._body())
        layout.addWidget(self._checkbox())
        layout.addLayout(self._actions())

    def _body(self):
        """Build the scrollable introduction text.

        Parameters
        ----------
        None

        Returns
        -------
        QTextBrowser
            Read-only introduction viewer.
        """
        view = QTextBrowser(self)
        view.setOpenExternalLinks(False)
        view.setMarkdown(WELCOME_MARKDOWN)
        return view

    def _checkbox(self):
        """Build the do-not-show-again checkbox.

        Parameters
        ----------
        None

        Returns
        -------
        QCheckBox
            Suppression checkbox.
        """
        self._dont_show = QCheckBox("Do not show this again", self)
        return self._dont_show

    def _actions(self):
        """Build the dialog action row.

        Parameters
        ----------
        None

        Returns
        -------
        QHBoxLayout
            Action row with the accept button.
        """
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._accept_button())
        return row

    def _accept_button(self):
        """Build the acceptance button.

        Parameters
        ----------
        None

        Returns
        -------
        QPushButton
            Button that closes the dialog.
        """
        button = QPushButton("Got it - Let's Explore", self)
        button.clicked.connect(self.accept)
        return button

    def dont_show_again(self):
        """Return whether suppression was requested.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            Checkbox state.
        """
        return self._dont_show.isChecked()
