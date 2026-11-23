"""PySide6 desktop shell with command and ideas panels."""

import importlib
import json
import math
import os
import plistlib
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtCore import QSize
from PySide6.QtCore import Qt
from PySide6.QtCore import QThread
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtGui import QPainter
from PySide6.QtGui import QPen
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QTextBlockFormat
from PySide6.QtGui import QTextCursor
from PySide6.QtGui import QTextDocument
from PySide6.QtGui import QTextDocumentFragment
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QInputDialog
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QListWidget
from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QMenu
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QSplitter
from PySide6.QtWidgets import QTextEdit
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget

from meta_harness.agent import Agent
from meta_harness.app_mode import ui_mode
from meta_harness.app_mode import voice_enabled
from meta_harness.env import load_env
from meta_harness.markdown_text import readable_markdown
from meta_harness.openrouter import OpenRouterClient
from meta_harness.profiles import effective_turns
from meta_harness.prompts import load as load_prompt
from meta_harness.session import Session
from meta_harness.tools import RESEARCH_TOOL_NAMES
from meta_harness.tools import ToolRegistry
from meta_harness.voice import VoiceEngine
from meta_harness.voice import missing_dependencies
from meta_harness.voice_text import match_option
from meta_harness.voice_text import speech_text

from .cyber_style import AGENT_BUBBLE
from .cyber_style import TOOL_BUBBLE
from .cyber_style import USER_BUBBLE
from .store import SessionRecord
from .store import SessionStore
from .research.archive import ArchiveError
from .research.archive import ArchiveService
from .research.evidence import EvidenceStore
from .research.notes import NoteStore
from .research.paths import ResearchPathError
from .research.paths import research_root
from .research.restored import RestoredHistoryStore
from .research.services import ResearchServices
from .research.sources import SourceStore
from .research.threads import ThreadStore
from .research.tombstones import write_thread_tombstone
from .research.transfers import TransferStore
from .research_context import research_context
from .research_welcome import ResearchWelcomeDialog
from .research_workspace import ResearchWorkspace
from .restored_history import RestoredHistoryDialog
from .settings import Settings
from .style import apply_palette
from .worker import AgentWorker
from .worker import QuestionBridge
from .workspace import workspace_root

_BUBBLES = {
    ("cyber", False, False): AGENT_BUBBLE,
    ("cyber", True, False): USER_BUBBLE,
    ("cyber", False, True): TOOL_BUBBLE,
    ("cyber", True, True): TOOL_BUBBLE,
    ("dark", False, False): "#1A2A33",
    ("dark", True, False): "#1E3A4A",
    ("dark", False, True): "#22303A",
    ("dark", True, True): "#22303A",
    ("light", False, False): "#D6E0E6",
    ("light", True, False): "#D2DBD6",
    ("light", False, True): "#EFEFEF",
    ("light", True, True): "#EFEFEF",
}


class Bridge(QObject):
    """Forward agent worker signals to a chat panel."""

    def __init__(self, worker: AgentWorker, panel: "ChatPanel") -> None:
        """Connect worker signals to panel slots.

        Parameters
        ----------
        worker : AgentWorker
            Background agent executor.
        panel : ChatPanel
            Panel receiving the output.

        Returns
        -------
        None
            Signals are wired.
        """
        super().__init__()
        worker.prompt_started.connect(panel.on_prompt_started)
        worker.started.connect(panel.on_started)
        worker.tool.connect(panel.on_tool)
        worker.answered.connect(panel.on_answered)
        worker.error.connect(panel.on_error)
        worker.asked.connect(panel.on_asked)


class PromptInput(QPlainTextEdit):
    """Multi-line prompt editor that grows to fit its content."""

    submitted = Signal(str)
    max_height = 220

    def __init__(self, parent: QWidget | None = None) -> None:
        """Prepare a growing prompt editor.

        Parameters
        ----------
        parent : QWidget or None
            Optional parent widget.

        Returns
        -------
        None
            The editor starts at single-line height.
        """
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.document().contentsChanged.connect(self._resize_to_content)
        self.setFixedHeight(self._measure_height())

    def sizeHint(self) -> QSize:  # noqa: N802
        """Report the content-sized height.

        Parameters
        ----------
        None

        Returns
        -------
        QSize
            Preferred widget size.
        """
        size = super().sizeHint()
        size.setHeight(self._measure_height())
        return size

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Submit on Enter and insert a newline on Shift-Enter.

        Parameters
        ----------
        event : QKeyEvent
            Incoming key event.

        Returns
        -------
        None
            Matching keys submit or insert a line break.
        """
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            self._submit_enter()
            event.accept()
            return
        super().keyPressEvent(event)

    def _submit_enter(self) -> None:
        """Emit the current text and clear the editor.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The submitted signal is emitted.
        """
        self.submitted.emit(self.toPlainText())
        self.clear()

    def _resize_to_content(self) -> None:
        """Fit the editor height to its wrapped lines.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Height matches content up to the cap.
        """
        height = self._measure_height()
        if height != self.height():
            self.setFixedHeight(height)

    def _measure_height(self) -> int:
        """Compute the height for the current wrapped text.

        Parameters
        ----------
        None

        Returns
        -------
        int
            Capped pixel height.
        """
        width = self.viewport().width()
        metrics = self.fontMetrics()
        lines = 1
        for text_line in self.toPlainText().splitlines():
            lines += max(1, metrics.horizontalAdvance(text_line) // width)
        height = lines * metrics.lineSpacing() + self.frameWidth() * 2
        return min(self.max_height, height)


class PulseDot(QWidget):
    """Blue dot that pulses while the agent is thinking."""

    COLOR = QColor("#6FDBFF")
    OUTLINE = QColor("#0B3A52")

    def __init__(self, parent=None) -> None:
        """Create the idle pulsing dot.

        Parameters
        ----------
        parent : QWidget or None
            Optional parent widget.

        Returns
        -------
        None
            The dot starts hidden at a fixed size.
        """
        super().__init__(parent)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(20, 20)
        self.hide()

    def start(self) -> None:
        """Show the dot and begin pulsing.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dot animates until stopped.
        """
        self._phase = 0.0
        self.show()
        self._timer.start()

    def stop(self) -> None:
        """Stop pulsing and hide the dot.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dot is hidden.
        """
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        """Step the pulse phase forward.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The widget repaints at the new phase.
        """
        self._phase = (self._phase + 0.013) % 1.0
        self.update()

    def _radius(self) -> float:
        """Compute the current dot radius.

        Parameters
        ----------
        None

        Returns
        -------
        float
            Radius in pixels between two and seven.
        """
        wave = 0.5 + 0.5 * math.sin(self._phase * 2 * math.pi)
        return 2.0 + 5.0 * wave

    def paintEvent(self, event) -> None:  # noqa: N802
        """Paint the dot with a soft halo.

        Parameters
        ----------
        event : QPaintEvent
            Paint event supplied by Qt.

        Returns
        -------
        None
            The dot is drawn on the widget.
        """
        radius = self._radius()
        center = self.rect().center()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        self._paint_halo(painter, center, radius)
        self._paint_core(painter, center, radius)

    def _paint_halo(self, painter, center, radius) -> None:
        """Paint the translucent outer glow.

        Parameters
        ----------
        painter : QPainter
            Active painter for the widget.
        center : QPoint
            Center of the dot.
        radius : float
            Radius of the solid core.

        Returns
        -------
        None
            The halo is drawn behind the core.
        """
        painter.setBrush(QColor(111, 219, 255, 90))
        painter.drawEllipse(center, int(radius + 3), int(radius + 3))

    def _paint_core(self, painter, center, radius) -> None:
        """Paint the solid blue core.

        Parameters
        ----------
        painter : QPainter
            Active painter for the widget.
        center : QPoint
            Center of the dot.
        radius : float
            Radius of the solid core.

        Returns
        -------
        None
            The core is drawn over the halo.
        """
        painter.setBrush(self.COLOR)
        painter.setPen(QPen(self.OUTLINE, 2))
        painter.drawEllipse(center, int(radius), int(radius))


class ChatPanel(QWidget):
    """One agent chat panel with header, log, and input."""

    posted = Signal()
    heard = Signal(str)
    note_requested = Signal(str)
    transfer_requested = Signal(str, str)
    snapshot_toggled = Signal(bool)
    tool_observed = Signal(str, dict, str)

    def __init__(
        self,
        agent: Agent,
        title: str = "SavrenAI",
        context=None,
        show_snapshot_toggle: bool = False,
        show_tools: bool = False,
        settings=None,
        voice_on: bool = False,
        theme: str = "classic",
        dark: bool = False,
        transfer_label: str | None = None,
    ) -> None:
        """Build the panel and start its background worker.

        Parameters
        ----------
        agent : Agent
            Backend agent for this panel.
        title : str
            Panel header title.
        context : callable or None
            Optional live-workspace snapshot builder.
        show_snapshot_toggle : bool
            Whether to show the snapshot context checkbox.
        show_tools : bool
            Whether to render tool activity in the log.
        settings : Settings or None
            Optional persisted interface settings.
        voice_on : bool
            Whether to build voice controls.
        theme : str
            Active theme name (``classic`` or ``cyber``).
        dark : bool
            Whether the dark palette is active.
        transfer_label : str or None
            Optional label for the cross-window transfer action.

        Returns
        -------
        None
            The panel is ready to show.
        """
        super().__init__()
        self._agent, self._transfer_label = agent, transfer_label
        self._context = context
        self._show_tools = show_tools
        self._settings = settings
        self._configure_state(voice_on, dark)
        self._theme = theme
        self._start_worker(agent, title, show_snapshot_toggle)

    def _configure_state(self, voice_on: bool, dark: bool) -> None:
        """Initialize per-panel mutable state.

        Parameters
        ----------
        voice_on : bool
            Whether to build voice controls.
        dark : bool
            Whether the dark palette is active.

        Returns
        -------
        None
            State fields are initialized.
        """
        self._voice_on = voice_on
        self._dark = dark
        self._snapshot_included = False
        self._outgoing: list[str] = []
        self._queued = 0
        self._hearing = False
        self._voice_missing = missing_dependencies() if voice_on else []
        self._voice = _make_voice(self._voice_missing)

    def _start_worker(self, agent, title, show_snapshot_toggle) -> None:
        """Start the animation timer and background worker.

        Parameters
        ----------
        agent : Agent
            Backend agent for this panel.

        title : str
            Panel header title.

        show_snapshot_toggle : bool
            Whether to show the snapshot context checkbox.

        Returns
        -------
        None
            The worker thread starts.
        """
        self._timer = _animation_timer(self)
        self._worker = AgentWorker(agent)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        Bridge(self._worker, self)
        self._build_ui(title, show_snapshot_toggle)
        self._thread.start()

    def _build_ui(self, title: str, show_snapshot_toggle: bool) -> None:
        """Compose the panel layout.

        Parameters
        ----------
        title : str
            Panel header title.
        show_snapshot_toggle : bool
            Whether to show the snapshot context checkbox.

        Returns
        -------
        None
            Widgets are arranged in place.
        """
        self._layout = QVBoxLayout(self)
        self._layout.addLayout(self._build_header(title))
        self._build_status()
        self._build_voice_status()
        self._build_composer(show_snapshot_toggle)
        self._pending: QuestionBridge | None = None

    def _build_status(self) -> None:
        """Create the animated status label.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The label is added to the layout.
        """
        self._status = QLabel("", self)
        self._status.setObjectName("statusLabel")
        self._dot = PulseDot(self)
        self._layout.addLayout(self._status_row())

    def _status_row(self) -> QHBoxLayout:
        """Build the thinking dot and status label row.

        Parameters
        ----------
        None

        Returns
        -------
        QHBoxLayout
            Row containing the pulse dot and status text.
        """
        row = QHBoxLayout()
        row.addWidget(self._dot)
        row.addWidget(self._status)
        row.addStretch(1)
        return row

    def _build_composer(self, show_snapshot_toggle: bool) -> None:
        """Build the log, input row, and question card.

        Parameters
        ----------
        show_snapshot_toggle : bool
            Whether to show the snapshot context checkbox.

        Returns
        -------
        None
            Widgets are added to the layout.
        """
        self._build_log()
        self._build_input_row()
        self._snapshot_toggle = self._build_snapshot(show_snapshot_toggle)
        self._build_question_card()
        if self._snapshot_toggle is not None:
            self._layout.addWidget(self._snapshot_toggle)
        self._add_speak_toggle()
        self._finish_composer()

    def _build_log(self) -> None:
        """Create the read-only transcript log.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The log is configured and added.
        """
        self._log = QTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QTextEdit.WidgetWidth)
        self._log.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._log.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._log.setContextMenuPolicy(Qt.CustomContextMenu)
        self._log.customContextMenuRequested.connect(self._log_menu)
        self._layout.addWidget(self._log)

    def _log_menu(self, pos):
        """Offer actions for selected transcript text.

        Parameters
        ----------
        pos : QPoint
            Menu request position.

        Returns
        -------
        None
            The menu runs until dismissed.
        """
        menu = self._log.createStandardContextMenu()
        self._add_note_action(menu)
        self._add_transfer_action(menu)
        menu.exec(self._log.mapToGlobal(pos))

    def _add_note_action(self, menu):
        """Add a save-selection note action when text is selected.

        Parameters
        ----------
        menu : QMenu
            Transcript context menu.

        Returns
        -------
        None
            The action is added when text is selected.
        """
        cursor = self._log.textCursor()
        if not cursor.hasSelection():
            return
        action = menu.addAction("Save selection as note")
        action.triggered.connect(
            lambda: self.note_requested.emit(cursor.selectedText())
        )

    def _add_transfer_action(self, menu):
        """Add a cross-window transfer action.

        Parameters
        ----------
        menu : QMenu
            Transcript context menu.

        Returns
        -------
        None
            The action is added when a label and text exist.
        """
        if not self._transfer_label:
            return
        cursor = self._log.textCursor()
        text, kind = _cursor_text(cursor)
        if not text:
            return
        action = menu.addAction(f"Send to {self._transfer_label}")
        action.triggered.connect(lambda: self._transfer_text(text, kind))

    def _transfer_text(self, text, kind):
        """Emit a cross-window transfer request.

        Parameters
        ----------
        text : str
            Transferred text.
        kind : str
            Message or selection.

        Returns
        -------
        None
            The request signal is emitted.
        """
        self.transfer_requested.emit(text, kind)

    def prefill(self, text):
        """Place text in the composer without sending it.

        Parameters
        ----------
        text : str
            Draft text.

        Returns
        -------
        None
            The composer is updated.
        """
        self._input.setPlainText(text)
        self._input.setFocus()

    def set_snapshot_included(self, enabled):
        """Set the snapshot toggle without emitting a change.

        Parameters
        ----------
        enabled : bool
            Whether the snapshot should be included.

        Returns
        -------
        None
            The toggle state is updated.
        """
        self._snapshot_included = bool(enabled)
        if self._snapshot_toggle is None:
            return
        self._snapshot_toggle.blockSignals(True)
        self._snapshot_toggle.setChecked(self._snapshot_included)
        self._snapshot_toggle.blockSignals(False)

    def _build_input_row(self) -> None:
        """Create the input, talk, and send row.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The row widgets are created.
        """
        self._input = PromptInput(self)
        self._send = QPushButton("Ask", self)
        self._build_voice_widgets()
        self._row = QHBoxLayout()
        self._row.addWidget(self._input)
        self._add_talk(self._row)
        self._row.addWidget(self._send)

    def _build_snapshot(self, show_snapshot_toggle: bool):
        """Create the optional workspace snapshot checkbox.

        Parameters
        ----------
        show_snapshot_toggle : bool
            Whether to show the snapshot context checkbox.

        Returns
        -------
        QCheckBox or None
            The checkbox when enabled, otherwise None.
        """
        if not show_snapshot_toggle:
            return None
        box = QCheckBox("Include workspace snapshot", self)
        box.setChecked(self._snapshot_included)
        box.stateChanged.connect(self._on_snapshot)
        return box

    def _finish_composer(self) -> None:
        """Wire composer signals and add the input row.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Signals are connected and the row is added.
        """
        self._layout.addLayout(self._row)
        self._send.clicked.connect(self._submit)
        self._input.submitted.connect(self._submit)
        self._connect_voice()

    def _build_voice_status(self) -> None:
        """Add the voice status label only in voice mode.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The label is created when voice is enabled.
        """
        self._voice_status = None
        if not self._voice_on:
            return
        self._voice_status = QLabel("", self)
        self._voice_status.setObjectName("voiceStatus")
        self._layout.addWidget(self._voice_status)

    def _build_voice_widgets(self) -> None:
        """Create voice widgets only in voice mode.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Widgets are created when voice is enabled.
        """
        self._talk = None
        self._speak_toggle = None
        if not self._voice_on:
            return
        self._talk = QPushButton("Hold to Talk", self)
        self._speak_toggle = QCheckBox("Speak replies", self)
        self._build_voice()

    def _add_talk(self, row: QHBoxLayout) -> None:
        """Place the talk button in the input row.

        Parameters
        ----------
        row : QHBoxLayout
            Input row layout.

        Returns
        -------
        None
            The button is added when present.
        """
        if self._talk is not None:
            row.addWidget(self._talk)

    def _add_speak_toggle(self) -> None:
        """Place the speak toggle above the input row.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The toggle is added when present.
        """
        if self._speak_toggle is not None:
            self._layout.addWidget(self._speak_toggle)

    def _connect_voice(self) -> None:
        """Connect voice signals only in voice mode.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The recognition signal is connected when enabled.
        """
        if self._voice_on:
            self.heard.connect(self._on_heard)

    def _build_question_card(self) -> None:
        """Build the inline agent-question panel.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The hidden card is added to the layout.
        """
        self._question_card = _question_widget(self)
        self._question_label = _wrapped_label(self._question_card)
        self._question_options = QHBoxLayout()
        self._question_input = QLineEdit(self._question_card)
        self._question_send = QPushButton("Answer", self._question_card)
        self._compose_question_card()
        self._wire_question_card()

    def _compose_question_card(self) -> None:
        """Arrange the question card widgets.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The card is hidden and added to the layout.
        """
        box = QVBoxLayout(self._question_card)
        box.setContentsMargins(6, 6, 6, 6)
        box.addWidget(self._question_label)
        box.addLayout(self._question_options)
        box.addLayout(self._question_row())
        self._question_card.hide()
        self._layout.addWidget(self._question_card)

    def _wire_question_card(self) -> None:
        """Connect the question card answer controls.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Signals are connected.
        """
        self._question_send.clicked.connect(self._answer_typed)
        self._question_input.returnPressed.connect(self._answer_typed)

    def _question_row(self) -> QHBoxLayout:
        """Build the free-text answer row.

        Parameters
        ----------
        None

        Returns
        -------
        QHBoxLayout
            Input and answer button row.
        """
        row = QHBoxLayout()
        row.addWidget(self._question_input)
        row.addWidget(self._question_send)
        return row

    def _show_question(self, question: str, options: list[str]) -> None:
        """Render a non-modal question with option buttons.

        Parameters
        ----------
        question : str
            Question text.
        options : list[str]
            Suggested answers.

        Returns
        -------
        None
            The question card is shown.
        """
        self._question_label.setText(question)
        self._clear_options()
        self._option_buttons(options)
        self._question_input.clear()
        self._question_card.show()

    def _option_buttons(self, options: list[str]) -> None:
        """Create one button per suggested answer.

        Parameters
        ----------
        options : list[str]
            Suggested answers.

        Returns
        -------
        None
            Buttons are added to the options row.
        """
        for option in options:
            button = QPushButton(option, self._question_card)
            button.clicked.connect(
                lambda _checked=False, text=option: self._answer_question(text)
            )
            self._question_options.addWidget(button)

    def _clear_options(self) -> None:
        """Remove option buttons from the previous question.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The options row is emptied.
        """
        while self._question_options.count():
            widget = self._question_options.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _answer_typed(self) -> None:
        """Submit the free-text answer field.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The typed answer resolves the pending question.
        """
        text = self._question_input.text().strip()
        if text:
            self._answer_question(text)

    def _answer_question(self, answer: str) -> None:
        """Resolve the pending agent question.

        Parameters
        ----------
        answer : str
            Selected or typed answer.

        Returns
        -------
        None
            The bridge is resolved and the card is hidden.
        """
        if self._pending is None:
            return
        bridge = self._pending
        self._pending = None
        text = answer.strip() or "no answer"
        self._append_log("you", text)
        self._hide_question()
        self._worker.resolve(bridge, text)

    def _cancel_question(self) -> None:
        """Resolve a pending question with no answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The pending bridge is released.
        """
        if self._pending is None:
            return
        bridge = self._pending
        self._pending = None
        self._hide_question()
        self._worker.resolve(bridge, "no answer")

    def _hide_question(self) -> None:
        """Hide and clear the inline question card.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The card is hidden and options are removed.
        """
        self._clear_options()
        self._question_input.clear()
        self._question_card.hide()

    def _on_snapshot(self, state: int) -> None:
        """Toggle whether the workspace snapshot joins the context.

        Parameters
        ----------
        state : int
            Checkbox check state.

        Returns
        -------
        None
            The note flag is updated.
        """
        self._snapshot_included = state == Qt.CheckState.Checked.value
        self.snapshot_toggled.emit(self._snapshot_included)

    def _build_voice(self) -> None:
        """Configure the voice controls for this environment.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Controls are enabled or annotated in place.
        """
        enabled = self._voice is not None
        self._voice_controls(enabled)
        self._voice_hints(enabled)
        self._wire_voice()

    def _voice_controls(self, enabled: bool) -> None:
        """Enable or disable the voice widgets.

        Parameters
        ----------
        enabled : bool
            Whether voice dependencies are available.

        Returns
        -------
        None
            Widget state is updated.
        """
        self._talk.setEnabled(enabled)
        self._speak_toggle.setEnabled(enabled)
        self._speak_toggle.setChecked(enabled and self._speak_default())

    def _voice_hints(self, enabled: bool) -> None:
        """Attach install hints when voice is unavailable.

        Parameters
        ----------
        enabled : bool
            Whether voice dependencies are available.

        Returns
        -------
        None
            Tooltips are set when needed.
        """
        if enabled:
            return
        missing = ", ".join(self._voice_missing)
        self._talk.setToolTip("Missing voice modules: " + missing)
        self._speak_toggle.setToolTip("pip install -e '.[voice]'")

    def _speak_default(self) -> bool:
        """Return whether replies should be spoken by default.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            Stored setting, or ``True`` without settings.
        """
        if self._settings is None:
            return True
        return self._settings.get("speak_replies")

    def _wire_voice(self) -> None:
        """Connect voice button and toggle signals.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Signals are connected.
        """
        self._talk.pressed.connect(self._start_talk)
        self._talk.released.connect(self._stop_talk)
        self._speak_toggle.toggled.connect(self._on_speak)

    def _on_speak(self, checked: bool) -> None:
        """Persist the speak toggle and cancel active speech.

        Parameters
        ----------
        checked : bool
            New checkbox state.

        Returns
        -------
        None
            The setting is stored and playback may stop.
        """
        if self._settings is not None:
            self._settings.set("speak_replies", checked)
        if not checked and self._voice is not None:
            self._voice.stop_speaking()

    def _start_talk(self) -> None:
        """Begin push-to-talk microphone capture.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Recording starts or an error is shown.
        """
        if self._voice is None:
            self._voice_status.setText("voice unavailable")
            return
        if self._hearing:
            return
        if self._begin_capture():
            return
        self._voice_status.setText("listening...")

    def _begin_capture(self) -> bool:
        """Start recording, reporting any microphone error.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            True when an error was already displayed.
        """
        try:
            self._voice.stop_speaking()
            self._voice.start_recording()
        except Exception as exc:
            self._voice_status.setText(f"mic error: {exc}")
            return True
        return False

    def _stop_talk(self) -> None:
        """Stop capture and transcribe on a background thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Transcription is queued.
        """
        if self._voice is None or not self._voice.recording:
            return
        if self._hearing:
            return
        self._hearing = True
        self._voice_status.setText("transcribing...")
        threading.Thread(target=self._hear, daemon=True).start()

    def _hear(self) -> None:
        """Transcribe the captured utterance and report it.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Recognized text is emitted, even when empty.
        """
        try:
            text = self._voice.stop_recording()
        except Exception:
            text = ""
        finally:
            self._hearing = False
        self.heard.emit(text)

    def _on_heard(self, text: str) -> None:
        """Submit a recognized utterance.

        Parameters
        ----------
        text : str
            Recognized speech.

        Returns
        -------
        None
            The prompt is submitted when text was heard.
        """
        if not text.strip():
            self._voice_status.setText("didn't catch that")
            return
        self._voice_status.setText("")
        self._dispatch_heard(text)

    def _dispatch_heard(self, text: str) -> None:
        """Submit heard text as an answer or a new prompt.

        Parameters
        ----------
        text : str
            Recognized speech.

        Returns
        -------
        None
            The text is submitted to the pending question or composer.
        """
        if self._pending is not None:
            self._answer_voice(text)
            return
        self._input.setPlainText(text)
        self._submit()

    def _answer_voice(self, text: str) -> None:
        """Resolve a pending question from spoken input.

        Parameters
        ----------
        text : str
            Recognized speech.

        Returns
        -------
        None
            The matched option or spoken text is submitted.
        """
        options = self._pending.options if self._pending else []
        self._answer_question(match_option(text, options))

    def _speak_answer(self, text: str) -> None:
        """Speak text when the toggle is on and voice is available.

        Parameters
        ----------
        text : str
            Assistant or question text.

        Returns
        -------
        None
            Speech is queued when enabled.
        """
        if self._voice is None or not self._speak_toggle.isChecked():
            return
        self._voice.speak(speech_text(text))

    def _build_header(self, title: str) -> QHBoxLayout:
        """Compose the top information bar.

        Parameters
        ----------
        title : str
            Header name.

        Returns
        -------
        QHBoxLayout
            Header layout with name and model labels.
        """
        header = QHBoxLayout()
        header.addWidget(self._header_label("<b>" + title + "</b>"))
        header.addStretch(1)
        header.addWidget(
            self._header_label("Model: " + self._agent.client.model)
        )
        return header

    def _header_label(self, text: str) -> QLabel:
        """Build one header label.

        Parameters
        ----------
        text : str
            Text to display.

        Returns
        -------
        QLabel
            Styled header label.
        """
        label = QLabel(text, self)
        return label

    def _submit(self, prompt: str = "") -> None:
        """Dispatch the typed prompt to the worker thread.

        Parameters
        ----------
        prompt : str
            Prompt text, or empty to read the input box.

        Returns
        -------
        None
            The prompt is queued for the worker.
        """
        prompt = (prompt or self._input.toPlainText()).strip()
        if not prompt:
            return
        if self._pending is not None:
            self._input.clear()
            self._answer_question(prompt)
            return
        self._start_prompt(prompt)

    def _start_prompt(self, prompt: str) -> None:
        """Queue a prompt for the worker.

        Parameters
        ----------
        prompt : str
            Trimmed prompt text.

        Returns
        -------
        None
            The prompt is queued for the worker.
        """
        self._outgoing.append(prompt)
        self._queued = len(self._outgoing)
        self._input.clear()
        prompt = _with_context(self._context, prompt)
        self._worker.prompt_ready.emit(prompt)
        self.posted.emit()

    def switch_session(self, session: Session) -> None:
        """Point the panel agent at a new session.

        Parameters
        ----------
        session : Session
            Session to make active.

        Returns
        -------
        None
            The session is bound and the log reloaded.
        """
        self._cancel_question()
        self._agent.session = session
        self._agent.messages = self._agent._initial_messages(session)
        self._log.clear()
        for message in session.messages:
            self._render_message(message)

    def set_dark(self, dark: bool) -> None:
        """Switch the panel between light and dark bubbles.

        Parameters
        ----------
        dark : bool
            Whether the dark palette is active.

        Returns
        -------
        None
            The transcript is redrawn with the new bubble colors.
        """
        self._dark = dark
        self._reload_log()

    def _reload_log(self) -> None:
        """Redraw stored messages with the current theme.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The log is cleared and repopulated.
        """
        self._log.clear()
        for message in self._agent.session.messages:
            self._render_message(message)

    def _render_message(self, message: dict) -> None:
        """Render one stored session message as a bubble.

        Parameters
        ----------
        message : dict
            Persisted message dictionary.

        Returns
        -------
        None
            The message is appended to the log.
        """
        role = message.get("role")
        content = message.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            self._append_log("you" if role == "user" else "agent", content)
        elif role == "tool" and self._show_tools and isinstance(content, str):
            self._append_log("tool", content)

    def _append_log(self, label: str, text: str) -> None:
        """Append a chat bubble and scroll to the newest.

        Parameters
        ----------
        label : str
            Speaker label ("you" or "agent").
        text : str
            Markdown message content to display.

        Returns
        -------
        None
            The bubble is shown and the view follows it.
        """
        user, tool = label == "you", label == "tool"
        cursor = self._log_cursor()
        start = cursor.position()
        end = self._insert_markdown(cursor, text)
        self._apply_bubble(start, end, user, tool)
        self._follow(cursor)

    def _log_cursor(self):
        """Return a log cursor positioned at the end.

        Parameters
        ----------
        None

        Returns
        -------
        QTextCursor
            Cursor at the end of the transcript.
        """
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self._log.document().isEmpty():
            cursor.insertBlock()
        return cursor

    def _insert_markdown(self, cursor, text: str) -> int:
        """Insert markdown text and return the end position.

        Parameters
        ----------
        cursor : QTextCursor
            Log cursor positioned at the insert point.

        text : str
            Markdown message content.

        Returns
        -------
        int
            Position after the inserted content.
        """
        doc = QTextDocument()
        doc.setMarkdown(readable_markdown(text))
        cursor.insertFragment(QTextDocumentFragment(doc))
        return cursor.position()

    def _follow(self, cursor) -> None:
        """Scroll the log to the newest content.

        Parameters
        ----------
        cursor : QTextCursor
            Cursor to restore.

        Returns
        -------
        None
            The view scrolls to the end.
        """
        self._log.setTextCursor(cursor)
        bar = self._log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _apply_bubble(
        self, start: int, end: int, user: bool, tool: bool = False
    ) -> None:
        """Style inserted blocks as an aligned bubble.

        Parameters
        ----------
        start : int
            First inserted block position.
        end : int
            Position after the last inserted block.
        user : bool
            Whether the bubble is the user's.
        tool : bool
            Whether the bubble is a tool step.

        Returns
        -------
        None
            Block formats are applied in place.
        """
        fmt = self._bubble_format(user, tool)
        first = QTextBlockFormat(fmt)
        first.setTopMargin(6)
        self._apply_blocks(start, end, first, fmt)

    def _bubble_format(self, user: bool, tool: bool) -> QTextBlockFormat:
        """Build the block format for one bubble.

        Parameters
        ----------
        user : bool
            Whether the bubble is the user's.

        tool : bool
            Whether the bubble is a tool step.

        Returns
        -------
        QTextBlockFormat
            Background and alignment for the bubble.
        """
        fmt = QTextBlockFormat()
        fmt.setBackground(QColor(self._bubble_color(user, tool)))
        if tool:
            return _left_bubble(fmt, self._bubble_margin())
        fmt.setAlignment(Qt.AlignRight if user else Qt.AlignLeft)
        self._set_side_margin(fmt, user)
        return fmt

    def _set_side_margin(self, fmt, user: bool) -> None:
        """Set the margin on the inner side of a bubble.

        Parameters
        ----------
        fmt : QTextBlockFormat
            Block format being updated.

        user : bool
            Whether the bubble is the user's.

        Returns
        -------
        None
            A left or right margin is applied.
        """
        if user:
            fmt.setLeftMargin(self._bubble_margin())
        else:
            fmt.setRightMargin(self._bubble_margin())

    def _apply_blocks(self, start, end, first, fmt) -> None:
        """Apply block formats to the inserted range.

        Parameters
        ----------
        start : int
            First inserted block position.

        end : int
            Position after the last inserted block.

        first : QTextBlockFormat
            Format for the first block.

        fmt : QTextBlockFormat
            Format for the remaining blocks.

        Returns
        -------
        None
            Block formats are applied in place.
        """
        block = self._log.document().findBlock(start)
        count = 0
        while block.isValid() and block.position() < end:
            cursor = QTextCursor(block)
            cursor.setBlockFormat(first if count == 0 else fmt)
            block = block.next()
            count += 1

    def _bubble_color(self, user: bool, tool: bool) -> str:
        """Return the bubble background for the active theme.

        Parameters
        ----------
        user : bool
            Whether the bubble is the user's.
        tool : bool
            Whether the bubble is a tool step.

        Returns
        -------
        str
            Hex color string.
        """
        theme = self._bubble_theme()
        return _BUBBLES[(theme, bool(user), bool(tool))]

    def _bubble_theme(self) -> str:
        """Return the bubble palette name for the active theme.

        Parameters
        ----------
        None

        Returns
        -------
        str
            One of ``cyber``, ``dark``, or ``light``.
        """
        if self._theme == "cyber":
            return "cyber"
        return "dark" if self._dark else "light"

    def _bubble_margin(self) -> int:
        """Compute the inward bubble offset.

        Parameters
        ----------
        None

        Returns
        -------
        int
            Pull-in margin in pixels.
        """
        return max(30, int(self._log.viewport().width() * 0.4))

    def on_prompt_started(self, prompt: str) -> None:
        """Show the user prompt when the worker actually begins it.

        Parameters
        ----------
        prompt : str
            Prompt delivered to the worker.

        Returns
        -------
        None
            The user bubble appears in processing order.
        """
        display = self._outgoing.pop(0) if self._outgoing else prompt
        self._queued = len(self._outgoing)
        self._append_log("you", display)

    def on_started(self) -> None:
        """Begin the pulsing thinking indicator.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dot pulses while the worker runs.
        """
        self._status.setText("thinking")
        self._dot.start()

    def _animate(self) -> None:
        """Refresh the queue size beside the thinking label.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The status label reflects the queued prompt count.
        """
        text = "thinking"
        if self._queued:
            text += f"  ({self._queued} queued)"
        self._status.setText(text)

    def _stop_thinking(self) -> None:
        """Clear the thinking indicator.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dot stops and the status label empties.
        """
        self._timer.stop()
        self._dot.stop()
        self._status.setText("")

    def on_answered(self, answer: str) -> None:
        """Show the agent's final reply.

        Parameters
        ----------
        answer : str
            Final assistant text.

        Returns
        -------
        None
            The reply is appended to the log.
        """
        self._stop_thinking()
        self._append_log("agent", answer)
        self._speak_answer(answer)

    def on_tool(self, name: str, arguments: dict, content: str) -> None:
        """Show tool activity when enabled.

        Parameters
        ----------
        name : str
            Tool name.
        arguments : dict
            Tool arguments.
        content : str
            Tool result content.

        Returns
        -------
        None
            Activity renders only when the toggle is on.
        """
        self.tool_observed.emit(name, arguments, content)
        if not self._show_tools:
            return
        self._append_tool(name, arguments, content)

    def _append_tool(self, name: str, arguments: dict, content: str) -> None:
        """Render one tool step as a compact log line.

        Parameters
        ----------
        name : str
            Tool name.
        arguments : dict
            Tool arguments.
        content : str
            Tool result content.

        Returns
        -------
        None
            The tool step is appended to the log.
        """
        label = f"tool> {name} {json.dumps(arguments)[:120]}"
        label += "\n" + str(content)[:300]
        self._append_log("tool", label)

    def on_error(self, message: str) -> None:
        """Show a backend failure dialog.

        Parameters
        ----------
        message : str
            Human-readable error text.

        Returns
        -------
        None
            An error dialog is displayed.
        """
        self._stop_thinking()
        self._append_log("agent", f"Error: {message}")
        self._status.setText("error")

    def on_asked(
        self, question: str, options: list[str], bridge: QuestionBridge
    ) -> None:
        """Present an agent question inline without a modal dialog.

        Parameters
        ----------
        question : str
            Question text for the user.
        options : list[str]
            Suggested answers.
        bridge : QuestionBridge
            Pending prompt awaiting the answer.

        Returns
        -------
        None
            The question card is shown and the worker stays blocked.
        """
        self._pending = bridge
        self._speak_answer(question)
        self._show_question(question, options)

    def stop(self) -> None:
        """Stop the panel worker thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The thread stops.
        """
        self._cancel_question()
        self._thread.quit()
        self._thread.wait(2000)
        if self._voice is not None:
            self._voice.stop_speaking()


class MainWindow(QMainWindow):
    """Window hosting a session sidebar and two chat panels."""

    def __init__(self, store: SessionStore, root: Path, settings=None) -> None:
        """Build the split window with a session sidebar.

        Parameters
        ----------
        store : SessionStore
            Session backend for listing and switching.
        root : pathlib.Path
            Workspace root used by both agents.
        settings : Settings or None
            Optional persisted interface settings.

        Returns
        -------
        None
            The window is ready to show.
        """
        super().__init__()
        self._configure(store, root, settings)
        self._build_panels()
        self._build_window()

    def _configure(self, store, root, settings) -> None:
        """Initialize the window state.

        Parameters
        ----------
        store : SessionStore
            Session backend for listing and switching.

        root : pathlib.Path
            Workspace root used by both agents.

        settings : Settings or None
            Optional persisted interface settings.

        Returns
        -------
        None
            State fields are initialized.
        """
        self._settings = settings or Settings()
        self._store = store
        self._root = root
        self._voice_on = voice_enabled()
        self._theme = ui_mode()
        self._record: SessionRecord | None = None
        self._enable_wayland_transparency()
        self._configure_research(root)

    def _enable_wayland_transparency(self) -> None:
        """Allow opacity effects on a Wayland window surface.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The translucent attribute is enabled on Wayland.
        """
        if _window_platform() == "wayland":
            self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _configure_research(self, root) -> None:
        """Prepare session-local and global research stores.

        Parameters
        ----------
        root : pathlib.Path
            Active project workspace.

        Returns
        -------
        None
            Research stores are configured or disabled.
        """
        self._thread_store = self._research_thread = None
        self._restored_store = self._transfer_store = None
        self._show_archived_threads = False
        self._reset_research_stores(root)
        self._services = ResearchServices(
            self._note_store, self._source_store, self._evidence_store
        )

    def _reset_research_stores(self, root) -> None:
        """Resolve global stores while keeping session stores intact.

        Parameters
        ----------
        root : pathlib.Path
            Active project workspace.

        Returns
        -------
        None
            Note and source stores are replaced.
        """
        self._research_root, self._research_error = _resolve_research(root)
        self._init_global_stores()
        self._archive_service = _make_archive_service(
            self._research_root, self._store.root
        )
        self._use_research_services()
        self._show_storage_error()
        self._recover_archives()

    def _init_global_stores(self) -> None:
        """Create the global research stores.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Store attributes are replaced.
        """
        self._note_store = _init_store(NoteStore, self._research_root)
        self._source_store = _init_store(SourceStore, self._research_root)
        self._evidence_store = _init_store(EvidenceStore, self._research_root)

    def _recover_archives(self) -> None:
        """Resume or roll back interrupted archive operations.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The startup reconciliation entry point runs.
        """
        if self._archive_service is None:
            return
        try:
            self._archive_service.recover()
        except (KeyError, OSError, RuntimeError, ValueError):
            return

    def _use_research_services(self) -> None:
        """Point session services at the current global stores.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Store references are updated when services exist.
        """
        if hasattr(self, "_services"):
            self._services.use_stores(
                self._note_store, self._source_store, self._evidence_store
            )

    def _show_storage_error(self) -> None:
        """Mirror the research storage error into the visible tabs.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The workspace error state is updated when built.
        """
        if hasattr(self, "_research_workspace"):
            self._research_workspace.set_storage_error(self._research_error)

    def _build_panels(self) -> None:
        """Create the command and research panels.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Panels, tabs, and their cards are created.
        """
        self._build_command_panel()
        self._build_research_panel()
        self._research_card = self._card(self._research_workspace)
        self._research_card.hide()

    def _build_command_panel(self) -> None:
        """Create and connect the primary chat panel.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The command panel is ready.
        """
        self._command_panel = self._make_command_panel()
        self._command_panel.posted.connect(self._on_posted)
        self._command_panel.transfer_requested.connect(
            self._transfer_to_research
        )

    def _build_research_panel(self) -> None:
        """Create the research tab workspace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The research workspace is ready.
        """
        self._research_panel = self._make_research_panel()
        self._wire_research_panel()
        self._research_workspace = ResearchWorkspace(
            self._research_panel, self._research_error
        )
        self._research_workspace.set_project_name(_project_name(self._root))
        self._wire_research_workspace()

    def _wire_research_panel(self) -> None:
        """Connect research chat actions to window handlers.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Chat signals are connected.
        """
        panel = self._research_panel
        panel.posted.connect(self._on_research_posted)
        panel.note_requested.connect(self._save_research_note)
        panel.transfer_requested.connect(self._transfer_to_primary)
        panel.snapshot_toggled.connect(self._on_snapshot_toggled)
        panel.tool_observed.connect(self._capture_source)

    def _wire_research_workspace(self) -> None:
        """Connect research tab actions to window handlers.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Signals are connected.
        """
        self._wire_thread_workspace()
        self._wire_note_workspace()
        self._research_workspace.help_requested.connect(
            self._show_research_welcome
        )

    def _wire_thread_workspace(self) -> None:
        """Connect thread selection and lifecycle actions.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Thread signals are connected.
        """
        for signal, slot in _thread_signals(self):
            signal.connect(slot)

    def _wire_note_workspace(self) -> None:
        """Connect note, revision, and proposal actions.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Note signals are connected.
        """
        workspace = self._research_workspace
        workspace.edit_note_requested.connect(self._edit_note)
        workspace.revisions_requested.connect(self._show_note_revisions)
        workspace.proposal_save_requested.connect(self._save_proposal)
        workspace.proposal_discard_requested.connect(self._discard_proposal)

    def _panel_options(self) -> dict:
        """Return shared chat-panel keyword options.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Shared ``ChatPanel`` options.
        """
        return {
            "show_tools": self._settings.get("show_tools"),
            "settings": self._settings,
            "voice_on": self._voice_on,
            "theme": self._theme,
            "dark": bool(self._settings.get("dark_mode")),
        }

    def _make_command_panel(self):
        """Create the command chat panel.

        Parameters
        ----------
        None

        Returns
        -------
        ChatPanel
            Panel for direct commands.
        """
        options = self._panel_options()
        options["transfer_label"] = "Research"
        return ChatPanel(self._make_agent(self._active_path()), **options)

    def _make_research_panel(self):
        """Create the research chat panel.

        Parameters
        ----------
        None

        Returns
        -------
        ChatPanel
            Panel for research conversations.
        """
        agent = self._make_research_agent()
        options = self._research_panel_options()
        return _new_research_panel(agent, options, self._make_research_context)

    def _research_panel_options(self) -> dict:
        """Return research chat options including transfer label.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Shared and research-specific panel options.
        """
        options = self._panel_options()
        options["transfer_label"] = "Primary chat"
        return options

    def _build_window(self) -> None:
        """Compose the window chrome and activate the first session.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The window is ready to show.
        """
        self.setCentralWidget(_window_central(self))
        self.setWindowTitle("SavrenAI")
        self.resize(1440, 640)
        self._refresh_sidebar()
        self._activate(self._store.list()[0])

    def _build_body(self, central) -> QSplitter:
        """Build the splitter body with sidebar and panels.

        Parameters
        ----------
        central : QWidget
            Central widget.

        Returns
        -------
        QSplitter
            Body splitter holding the sidebar and chat panels.
        """
        body = QSplitter(Qt.Horizontal, central)
        body.setHandleWidth(6)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_panel_splitter(central))
        return body

    def _build_panel_splitter(self, central) -> QSplitter:
        """Build the splitter holding both chat panels.

        Parameters
        ----------
        central : QWidget
            Central widget.

        Returns
        -------
        QSplitter
            Horizontal splitter with command and ideas cards.
        """
        main = QSplitter(Qt.Horizontal, central)
        main.setHandleWidth(6)
        main.addWidget(self._card(self._command_panel))
        main.addWidget(self._research_card)
        return main

    def _make_agent(self, path, prompt=None, tools=None) -> Agent:
        """Build an agent for one panel.

        Parameters
        ----------
        path : pathlib.Path
            Transcript path.
        prompt : str or None
            Optional full system prompt override.
        tools : ToolRegistry or None
            Optional restricted tool registry.

        Returns
        -------
        Agent
            Agent bound to the working session.
        """
        options = _agent_options(self._root, path, prompt, tools)
        options["max_turns"] = self._turns()
        agent = Agent(**options)
        agent.tools.require_project_folder = True
        return agent

    def _make_research_agent(self) -> Agent:
        """Build the read-only research agent with its own prompt.

        Parameters
        ----------
        None

        Returns
        -------
        Agent
            Agent bound to a research transcript.
        """
        path = Path("runs/gui-research.jsonl")
        tools = _research_tools(self._root, self._services)
        return self._make_agent(path, load_prompt("research"), tools)

    def _turns(self) -> int:
        """Return the effective turn budget for the active model.

        Parameters
        ----------
        None

        Returns
        -------
        int
            Profile or default turn count.
        """
        client = OpenRouterClient()
        return effective_turns(client.model, None)

    def _active_path(self) -> Path:
        """Return the active session transcript path.

        Parameters
        ----------
        None

        Returns
        -------
        pathlib.Path
            Transcript path for the current session.
        """
        if self._record is None:
            return Path("runs/gui-session.jsonl")
        return self._record.transcript

    def _make_research_context(self) -> str:
        """Build optional research context without primary leakage.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Workspace snapshot when enabled, otherwise empty.
        """
        include = self._research_panel._snapshot_included
        return research_context(self._root, include)

    def _session_notes(self) -> list:
        """Return notes scoped to the active session.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Note records, or an empty list.
        """
        if self._record is None or self._note_store is None:
            return []
        return self._note_store.list(self._record.session_id)

    def _session_sources(self) -> list:
        """Return sources scoped to the active session.

        Parameters
        ----------
        None

        Returns
        -------
        list
            Source records, or an empty list.
        """
        if self._record is None or self._source_store is None:
            return []
        return self._source_store.list(self._record.session_id)

    def _build_sidebar(self) -> QWidget:
        """Build the sessions and builds sidebar.

        Parameters
        ----------
        None

        Returns
        -------
        QWidget
            Sidebar with two sections and new buttons.
        """
        sidebar = _sidebar_widget(self)
        box = QVBoxLayout(sidebar)
        self._add_sessions(box, sidebar)
        box.addSpacing(12)
        self._add_builds(box, sidebar)
        _add_restore_button(self, box, sidebar)
        return sidebar

    def _add_sessions(self, box, sidebar) -> None:
        """Add the sessions list and new-session button.

        Parameters
        ----------
        box : QVBoxLayout
            Sidebar layout.

        sidebar : QWidget
            Sidebar widget.

        Returns
        -------
        None
            The section is added.
        """
        box.addWidget(QLabel("<b>Sessions</b>", sidebar))
        self._session_list = _item_list(
            sidebar, self._select, self._menu_session
        )
        box.addWidget(self._session_list)
        box.addWidget(_new_button(sidebar, "+ New Session", self._new_session))

    def _add_builds(self, box, sidebar) -> None:
        """Add the builds list and new-build button.

        Parameters
        ----------
        box : QVBoxLayout
            Sidebar layout.

        sidebar : QWidget
            Sidebar widget.

        Returns
        -------
        None
            The section is added.
        """
        box.addWidget(QLabel("<b>Builds</b>", sidebar))
        self._build_list = _item_list(sidebar, self._select, self._menu_build)
        box.addWidget(self._build_list)
        box.addWidget(_new_button(sidebar, "+ New Build", self._new_build))

    def _refresh_sidebar(self) -> None:
        """Repopulate the session and build lists.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both lists reflect the store.
        """
        self._session_list.clear()
        for record in self._store.list(kind="session"):
            self._session_list.addItem(self._item(record))
        self._build_list.clear()
        for record in self._store.list(kind="build"):
            self._build_list.addItem(self._item(record))

    def _menu_session(self, pos) -> None:
        """Open the context menu for a session row.

        Parameters
        ----------
        pos : QPoint
            Menu request position.

        Returns
        -------
        None
            The menu is shown for the row.
        """
        self._item_menu(self._session_list, pos)

    def _menu_build(self, pos) -> None:
        """Open the context menu for a build row.

        Parameters
        ----------
        pos : QPoint
            Menu request position.

        Returns
        -------
        None
            The menu is shown for the row.
        """
        self._item_menu(self._build_list, pos)

    def _item_menu(self, listing: QListWidget, pos) -> None:
        """Show rename and delete actions for an item.

        Parameters
        ----------
        listing : QListWidget
            List containing the row.
        pos : QPoint
            Menu request position.

        Returns
        -------
        None
            Actions run when chosen.
        """
        item = listing.itemAt(pos)
        if item is None:
            return
        record = self._store.load(item.data(Qt.UserRole))
        self._run_menu(record, listing.mapToGlobal(pos))

    def _run_menu(self, record, global_pos) -> None:
        """Show and dispatch the rename/delete menu.

        Parameters
        ----------
        record : SessionRecord
            Session for the row.

        global_pos : QPoint
            Menu position in global coordinates.

        Returns
        -------
        None
            The chosen action runs.
        """
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        chosen = menu.exec(global_pos)
        if chosen is delete:
            self._delete(record)
        elif chosen is rename:
            self._rename(record)

    def _rename(self, record: SessionRecord) -> None:
        """Prompt for and apply a new session title.

        Parameters
        ----------
        record : SessionRecord
            Session to rename.

        Returns
        -------
        None
            The title is updated and lists refresh.
        """
        title, ok = QInputDialog.getText(
            self, "Rename", "Title:", text=record.title
        )
        if not ok or not title.strip():
            return
        self._store.rename(record, title.strip())
        self._refresh_sidebar()
        self._mark_renamed(record)

    def _mark_renamed(self, record) -> None:
        """Highlight the renamed row when it is active.

        Parameters
        ----------
        record : SessionRecord
            Session that was renamed.

        Returns
        -------
        None
            The active row is highlighted.
        """
        if self._record.session_id == record.session_id:
            self._mark_active(record)

    def _delete(self, record: SessionRecord) -> None:
        """Archive, delete, or cancel a session removal.

        Parameters
        ----------
        record : SessionRecord
            Session to remove.

        Returns
        -------
        None
            The chosen action runs.
        """
        choice = self._delete_choice(record)
        if choice == "archive":
            self._archive_record(record)
        elif choice == "delete":
            self._delete_all(record)

    def _delete_choice(self, record):
        """Ask whether to archive or delete a session.

        Parameters
        ----------
        record : SessionRecord
            Session to remove.

        Returns
        -------
        str or None
            ``archive``, ``delete``, or ``None`` when cancelled.
        """
        box, archive, delete = _delete_options(self, record)
        box.exec()
        if box.clickedButton() is archive:
            return "archive"
        if box.clickedButton() is delete:
            return "delete"
        return None

    def _archive_record(self, record):
        """Archive one session and forget it locally.

        Parameters
        ----------
        record : SessionRecord
            Session to archive.

        Returns
        -------
        None
            The archive is written and the session is forgotten.
        """
        if self._archive_service is None:
            return
        if not self._try_archive(record):
            return
        self._forget(record)

    def _try_archive(self, record):
        """Write an archive, reporting failures.

        Parameters
        ----------
        record : SessionRecord
            Session to archive.

        Returns
        -------
        bool
            ``True`` when the archive is written.
        """
        try:
            self._archive_call(record)
        except (ArchiveError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Archive", str(exc))
            return False
        return True

    def _archive_call(self, record):
        """Write the archive for one session.

        Parameters
        ----------
        record : SessionRecord
            Session to archive.

        Returns
        -------
        None
            The archive is written.
        """
        notes, sources, evidence = self._research_stores()
        self._archive_service.archive_session(record, notes, sources, evidence)

    def _research_stores(self):
        """Return the global note, source, and evidence stores.

        Parameters
        ----------
        None

        Returns
        -------
        tuple
            Note, source, and evidence stores.
        """
        return self._note_store, self._source_store, self._evidence_store

    def _delete_all(self, record):
        """Delete a session and every scoped global record.

        Parameters
        ----------
        record : SessionRecord
            Session to delete.

        Returns
        -------
        None
            Live data is removed and the session is forgotten.
        """
        self._remove(record)
        self._forget(record)

    def _remove(self, record: SessionRecord) -> None:
        """Remove live session and scoped global records.

        Parameters
        ----------
        record : SessionRecord
            Session to delete.

        Returns
        -------
        None
            Live data is removed and lists refresh.
        """
        self._delete_global_records(record)
        shutil.rmtree(record.folder, ignore_errors=True)
        self._refresh_sidebar()

    def _delete_global_records(self, record):
        """Delete scoped global records for a session.

        Parameters
        ----------
        record : SessionRecord
            Session owning the records.

        Returns
        -------
        None
            Scoped notes, sources, evidence, and tombstones are removed.
        """
        if self._archive_service is not None:
            self._archive_service.delete_session_data(
                record, *self._research_stores()
            )

    def _forget(self, record):
        """Refresh lists and activate a replacement session.

        Parameters
        ----------
        record : SessionRecord
            Session that was removed.

        Returns
        -------
        None
            Another session becomes active when needed.
        """
        if (
            self._record is not None
            and self._record.session_id == record.session_id
        ):
            self._record = None
        self._refresh_sidebar()
        if self._record is None:
            self._activate_default(record.kind)

    def _activate_default(self, kind):
        """Activate the newest session of a kind or create one.

        Parameters
        ----------
        kind : str
            Session kind.

        Returns
        -------
        None
            A session becomes active.
        """
        records = self._store.list(kind=kind)
        self._activate(
            records[0] if records else self._store.create(kind=kind)
        )

    def _item(self, record: SessionRecord) -> QListWidgetItem:
        """Build a list row for a session.

        Parameters
        ----------
        record : SessionRecord
            Session to display.

        Returns
        -------
        QListWidgetItem
            Row carrying the session id.
        """
        item = QListWidgetItem(record.title)
        item.setData(Qt.UserRole, record.session_id)
        return item

    def _new_session(self) -> None:
        """Create and activate a new session.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A new session becomes active.
        """
        self._activate(self._store.create())

    def _new_build(self) -> None:
        """Create and activate a new build.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A new build becomes active.
        """
        self._activate(self._store.create(kind="build"))

    def _select(self, item: QListWidgetItem) -> None:
        """Activate the clicked session.

        Parameters
        ----------
        item : QListWidgetItem
            Clicked session row.

        Returns
        -------
        None
            The session becomes active.
        """
        session_id = item.data(Qt.UserRole)
        self._activate(self._store.load(session_id))

    def _activate(self, record: SessionRecord) -> None:
        """Switch the primary panel and the session's research threads.

        Parameters
        ----------
        record : SessionRecord
            Session to make active.

        Returns
        -------
        None
            Both panels load independent histories.
        """
        self._record = record
        self._touch_active()
        self._command_panel.switch_session(Session(record.transcript))
        self._activate_research(record)
        self._mark_active(record)

    def _activate_research(self, record):
        """Load the newest research thread for a session.

        Parameters
        ----------
        record : SessionRecord
            Active session.

        Returns
        -------
        None
            The research panel and tabs are refreshed.
        """
        self._thread_store = ThreadStore(record.folder)
        self._restored_store = RestoredHistoryStore(record.folder)
        self._transfer_store = TransferStore(record.folder)
        self._open_research_thread(self._thread_store.default())
        self._refresh_restored_button()

    def _open_research_thread(self, thread):
        """Bind the research panel to one thread.

        Parameters
        ----------
        thread : dict
            Thread metadata.

        Returns
        -------
        None
            The research transcript and tabs are updated.
        """
        self._research_thread = thread
        self._services.bind(self._record, thread)
        self._research_panel.set_snapshot_included(
            thread.get("snapshot_enabled", False)
        )
        path = self._thread_store.transcript_path(thread["id"])
        self._research_panel.switch_session(Session(path))
        self._refresh_research_workspace()

    def _refresh_research_workspace(self) -> None:
        """Refresh thread, note, and source tabs.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The research workspace reflects active state.
        """
        if self._thread_store is None:
            return
        self._research_workspace.set_project_name(_project_name(self._root))
        active = self._research_thread["id"]
        self._refresh_thread_list(active)
        self._research_workspace.set_notes(self._session_notes())
        self._research_workspace.set_sources(self._session_sources())
        self._research_workspace.set_proposals(self._services.proposals())

    def _refresh_thread_list(self, active):
        """Refresh the thread list for the archived visibility setting.

        Parameters
        ----------
        active : str
            Active thread identifier.

        Returns
        -------
        None
            The thread list is updated.
        """
        status = None if self._show_archived_threads else "active"
        threads = self._thread_store.list(status=status)
        self._research_workspace.set_threads(threads, active)

    def _select_research_thread(self, thread_id) -> None:
        """Switch the research panel without touching the primary panel.

        Parameters
        ----------
        thread_id : str
            Selected thread identifier.

        Returns
        -------
        None
            The research panel loads the thread.
        """
        if self._thread_store is None:
            return
        self._open_research_thread(self._thread_store.get(thread_id))

    def _new_research_thread(self) -> None:
        """Create and open an empty research thread.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The new thread becomes active.
        """
        if self._thread_store is None:
            return
        self._open_research_thread(self._thread_store.create())

    def _archive_research_thread(self, thread_id) -> None:
        """Archive one research thread.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        None
            The thread leaves the active list.
        """
        if self._thread_store is None:
            return
        self._thread_store.archive(thread_id)
        self._refresh_research_workspace()

    def _restore_research_thread(self, thread_id) -> None:
        """Restore one archived research thread.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        None
            The thread returns to the active list.
        """
        if self._thread_store is None:
            return
        self._thread_store.restore(thread_id)
        self._refresh_research_workspace()

    def _delete_research_thread(self, thread_id) -> None:
        """Delete a thread transcript while keeping notes and sources.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        None
            The thread is removed or deletion is cancelled.
        """
        if self._thread_store is None:
            return
        if not self._confirm_thread_delete(thread_id):
            return
        self._remove_thread(self._thread_store.get(thread_id))

    def _remove_thread(self, thread) -> None:
        """Remove one thread and keep its surviving records.

        Parameters
        ----------
        thread : dict
            Thread metadata.

        Returns
        -------
        None
            The thread is deleted and the list refreshed.
        """
        thread_id = thread["id"]
        self._write_thread_tombstone(thread)
        self._thread_store.delete(thread_id)
        if self._research_thread["id"] == thread_id:
            self._open_research_thread(self._thread_store.default())
        self._refresh_research_workspace()

    def _confirm_thread_delete(self, thread_id) -> bool:
        """Ask whether to delete one thread transcript.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        bool
            ``True`` when the user confirms deletion.
        """
        thread = self._thread_store.get(thread_id)
        answer = QMessageBox.question(
            self,
            "Delete research thread",
            "Delete the transcript for '%s'? Notes and sources are kept."
            % thread.get("title", thread_id),
        )
        return answer == QMessageBox.StandardButton.Yes

    def _write_thread_tombstone(self, thread) -> None:
        """Persist provenance for a deleted thread.

        Parameters
        ----------
        thread : dict
            Thread metadata.

        Returns
        -------
        None
            A tombstone is written when storage is available.
        """
        if self._research_root is None:
            return
        note_ids = _record_ids(self._thread_notes(thread["id"]))
        source_ids = _record_ids(self._thread_sources(thread["id"]))
        write_thread_tombstone(
            self._research_root, thread, note_ids, source_ids
        )

    def _thread_notes(self, thread_id) -> list:
        """Return notes associated with one thread.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        list
            Matching notes.
        """
        if self._note_store is None or self._record is None:
            return []
        return self._note_store.list(self._record.session_id, thread_id)

    def _thread_sources(self, thread_id) -> list:
        """Return sources associated with one thread.

        Parameters
        ----------
        thread_id : str
            Thread identifier.

        Returns
        -------
        list
            Matching sources.
        """
        if self._source_store is None or self._record is None:
            return []
        return self._source_store.list(self._record.session_id, thread_id)

    def _toggle_archived_threads(self, checked) -> None:
        """Show or hide archived research threads.

        Parameters
        ----------
        checked : bool
            Whether archived threads should be visible.

        Returns
        -------
        None
            The thread list is refreshed.
        """
        self._show_archived_threads = checked
        self._refresh_research_workspace()

    def _save_research_note(self, text) -> None:
        """Save selected research text as a note immediately.

        Parameters
        ----------
        text : str
            Selected transcript text.

        Returns
        -------
        None
            The note is created when storage is available.
        """
        body = text.strip()
        if not self._can_save_note(body):
            return
        self._create_research_note(body)
        self._refresh_research_workspace()
        self._research_workspace.show_notes()

    def _can_save_note(self, body) -> bool:
        """Return whether a note can be saved.

        Parameters
        ----------
        body : str
            Selected text.

        Returns
        -------
        bool
            ``True`` when storage and scope are ready.
        """
        return (
            bool(body)
            and self._note_store is not None
            and self._services.scope
        )

    def _create_research_note(self, body) -> None:
        """Create one note from selected text.

        Parameters
        ----------
        body : str
            Selected text.

        Returns
        -------
        None
            The note is persisted.
        """
        scope = self._services.scope
        title = _note_title(body)
        origin = _selection_origin(body)
        self._note_store.create(scope, title, body, origin)

    def _edit_note(self, note_id) -> None:
        """Edit a note through a title and markdown dialog.

        Parameters
        ----------
        note_id : str
            Note identifier.

        Returns
        -------
        None
            The note is updated or the dialog is cancelled.
        """
        if self._note_store is None:
            return
        note = self._note_store.get(note_id)
        values = self._read_note_edit(note)
        if values is None:
            return
        self._apply_note_edit(note_id, values[0], values[1])

    def _read_note_edit(self, note):
        """Read a title and body edit from dialogs.

        Parameters
        ----------
        note : dict
            Note record.

        Returns
        -------
        tuple or None
            New title and body, or ``None`` when cancelled.
        """
        title = self._edit_title(note)
        if title is None:
            return None
        body = self._edit_body(note)
        if body is None:
            return None
        return title, body

    def _apply_note_edit(self, note_id, title, body) -> None:
        """Persist an edited note and refresh views.

        Parameters
        ----------
        note_id : str
            Note identifier.
        title : str
            New title.
        body : str
            New markdown body.

        Returns
        -------
        None
            The note and views are updated.
        """
        self._note_store.update(note_id, title=title, body_md=body)
        self._refresh_research_workspace()

    def _edit_title(self, note):
        """Ask for a note title.

        Parameters
        ----------
        note : dict
            Note record.

        Returns
        -------
        str or None
            New title, or ``None`` when cancelled.
        """
        title, ok = QInputDialog.getText(
            self, "Edit note", "Title:", text=note["title"]
        )
        return title if ok and title.strip() else None

    def _edit_body(self, note):
        """Ask for note markdown.

        Parameters
        ----------
        note : dict
            Note record.

        Returns
        -------
        str or None
            New body, or ``None`` when cancelled.
        """
        body, ok = QInputDialog.getMultiLineText(
            self, "Edit note", "Markdown:", note["body_md"]
        )
        return body if ok else None

    def _show_note_revisions(self, note_id) -> None:
        """Select and restore an earlier note revision.

        Parameters
        ----------
        note_id : str
            Note identifier.

        Returns
        -------
        None
            The note is restored or the dialog is cancelled.
        """
        if self._note_store is None:
            return
        revisions = self._note_store.revisions(note_id)
        number = self._revision_choice(revisions)
        if number is None:
            return
        self._restore_note_revision(note_id, number)

    def _revision_choice(self, revisions):
        """Ask for a revision number when revisions exist.

        Parameters
        ----------
        revisions : list
            Revision records.

        Returns
        -------
        int or None
            Chosen revision, or ``None``.
        """
        if not revisions:
            QMessageBox.information(self, "Revisions", "No earlier revisions.")
            return None
        return self._choose_revision(revisions)

    def _restore_note_revision(self, note_id, number) -> None:
        """Restore a note revision and refresh views.

        Parameters
        ----------
        note_id : str
            Note identifier.
        number : int
            Revision number.

        Returns
        -------
        None
            The note and views are updated.
        """
        self._note_store.restore_revision(note_id, number)
        self._refresh_research_workspace()

    def _choose_revision(self, revisions):
        """Ask which revision to restore.

        Parameters
        ----------
        revisions : list
            Revision records.

        Returns
        -------
        int or None
            Revision number, or ``None`` when cancelled.
        """
        labels = [f"Revision {item['revision']}" for item in revisions]
        label, ok = QInputDialog.getItem(
            self, "Revisions", "Restore:", labels, 0, False
        )
        if not ok:
            return None
        return int(label.split()[-1])

    def _save_proposal(self, proposal_id) -> None:
        """Approve and persist one pending note proposal.

        Parameters
        ----------
        proposal_id : str
            Proposal identifier.

        Returns
        -------
        None
            The note is saved and the proposal removed.
        """
        if self._services is None:
            return
        try:
            self._services.apply_proposal(proposal_id)
        except (RuntimeError, ValueError, KeyError):
            return
        self._refresh_research_workspace()

    def _discard_proposal(self, proposal_id) -> None:
        """Discard one pending note proposal.

        Parameters
        ----------
        proposal_id : str
            Proposal identifier.

        Returns
        -------
        None
            The proposal is removed.
        """
        if self._services is None:
            return
        self._services.discard_proposal(proposal_id)
        self._refresh_research_workspace()

    def _transfer_to_primary(self, text, kind) -> None:
        """Send selected research text to the primary composer.

        Parameters
        ----------
        text : str
            Transferred text.
        kind : str
            Message or selection.

        Returns
        -------
        None
            The primary composer is prefilled and provenance recorded.
        """
        if self._transfer_store is None:
            return
        thread_id = _active_thread_id(self._research_thread)
        self._transfer_store.append(
            "research_to_primary", kind, text, source_thread_id=thread_id
        )
        self._command_panel.prefill(text)

    def _transfer_to_research(self, text, kind) -> None:
        """Send selected primary text to a chosen research thread.

        Parameters
        ----------
        text : str
            Transferred text.
        kind : str
            Message or selection.

        Returns
        -------
        None
            The research composer is prefilled and provenance recorded.
        """
        thread = self._choose_research_target()
        if thread is None or self._transfer_store is None:
            return
        self._transfer_store.append(
            "primary_to_research", kind, text, target_thread_id=thread["id"]
        )
        self._open_research_thread(thread)
        self._research_panel.prefill(text)

    def _choose_research_target(self):
        """Choose or create a research thread for a transfer.

        Parameters
        ----------
        None

        Returns
        -------
        dict or None
            Chosen thread.
        """
        if self._thread_store is None:
            return None
        threads = self._thread_store.list()
        if not threads:
            return self._thread_store.create()
        if len(threads) == 1:
            return threads[0]
        return self._pick_thread(threads)

    def _pick_thread(self, threads):
        """Ask which research thread should receive a transfer.

        Parameters
        ----------
        threads : list
            Active thread metadata.

        Returns
        -------
        dict or None
            Chosen thread, or ``None`` when cancelled.
        """
        labels = [thread.get("title") or thread["id"] for thread in threads]
        label, ok = QInputDialog.getItem(
            self, "Send to research", "Thread:", labels, 0, False
        )
        if not ok:
            return None
        return threads[labels.index(label)]

    def _on_snapshot_toggled(self, enabled) -> None:
        """Persist the per-thread snapshot toggle.

        Parameters
        ----------
        enabled : bool
            Whether the workspace snapshot is included.

        Returns
        -------
        None
            Thread metadata is updated.
        """
        if self._thread_store is None or self._research_thread is None:
            return
        self._research_thread = self._thread_store.update(
            self._research_thread["id"], snapshot_enabled=enabled
        )

    def _capture_source(self, name, arguments, content) -> None:
        """Capture web tool results as structured sources.

        Parameters
        ----------
        name : str
            Tool name.
        arguments : dict
            Tool arguments.
        content : str
            Serialized tool result.

        Returns
        -------
        None
            New sources are stored when relevant.
        """
        if self._source_store is None or self._services.scope is None:
            return
        data = _parse_tool_json(content)
        if name == "web_search":
            _capture_search(self._source_store, self._services.scope, data)
        elif name in ("browser_open", "browser_assert", "evidence_capture"):
            _capture_page(self._source_store, self._services.scope, data)

    def _on_research_posted(self) -> None:
        """Touch the active research thread after a message.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Thread ordering and the sidebar refresh.
        """
        thread = self._active_research_thread()
        if thread is not None:
            self._research_thread = self._thread_store.update(thread["id"])
            self._refresh_research_workspace()
        self._on_posted()

    def _active_research_thread(self):
        """Return the active thread when research storage exists.

        Parameters
        ----------
        None

        Returns
        -------
        dict or None
            Active thread metadata.
        """
        if self._thread_store is None:
            return None
        return self._research_thread

    def _mark_active(self, record: SessionRecord) -> None:
        """Highlight the active row in its list.

        Parameters
        ----------
        record : SessionRecord
            Session now active.

        Returns
        -------
        None
            The matching row is selected.
        """
        target = self._list_for(record)
        for index in range(target.count()):
            item = target.item(index)
            if item.data(Qt.UserRole) == record.session_id:
                target.setCurrentItem(item)
                return

    def _list_for(self, record):
        """Return the list holding a session kind.

        Parameters
        ----------
        record : SessionRecord
            Session record.

        Returns
        -------
        QListWidget
            Session or build list.
        """
        if record.kind == "session":
            return self._session_list
        return self._build_list

    def _touch_active(self) -> None:
        """Bump the active session timestamp.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The session is marked recent.
        """
        if self._record is None:
            return
        self._store.touch(self._record)
        self._refresh_sidebar()

    def _on_posted(self) -> None:
        """Refresh the sidebar after a message posts.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The session list reflects the update.
        """
        self._touch_active()

    def _build_toggle_bar(self) -> QHBoxLayout:
        """Build the settings and ideas toggle row.

        Parameters
        ----------
        None

        Returns
        -------
        QHBoxLayout
            Bar with checkboxes and the ideas button.
        """
        bar = QHBoxLayout()
        self._add_workspace_controls(bar)
        bar.addStretch(1)
        self._add_toggles(bar)
        bar.addWidget(self._research_button())
        self._update_workspace_label()
        return bar

    def _add_workspace_controls(self, bar) -> None:
        """Add the workspace label and change-folder button.

        Parameters
        ----------
        bar : QHBoxLayout
            Toggle bar layout.

        Returns
        -------
        None
            Controls are added.
        """
        self._workspace_label = QLabel("", self)
        self._workspace_label.setObjectName("workspaceLabel")
        bar.addWidget(self._workspace_label)
        change = QPushButton("Change Folder", self)
        change.clicked.connect(self._choose_workspace)
        bar.addWidget(change)

    def _add_toggles(self, bar) -> None:
        """Add the command and tool-activity checkboxes.

        Parameters
        ----------
        bar : QHBoxLayout
            Toggle bar layout.

        Returns
        -------
        None
            Checkboxes are added.
        """
        for label, key, slot in _toggle_specs(self):
            bar.addWidget(_toggle_box(self, label, key, slot))
        bar.addWidget(self._dark_mode_button())
        bar.addWidget(self._unwise_button())
        bar.addWidget(self._restored_button())

    def _restored_button(self) -> QPushButton:
        """Create the restored-history viewer button.

        Parameters
        ----------
        None

        Returns
        -------
        QPushButton
            Button that opens read-only restored history.
        """
        self._history_button = QPushButton("Restored history", self)
        self._history_button.clicked.connect(self._show_restored_history)
        self._history_button.setEnabled(False)
        return self._history_button

    def _refresh_restored_button(self) -> None:
        """Enable the history button when records exist.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The button state and tooltip are updated.
        """
        histories = self._restored_store.list() if self._restored_store else []
        self._history_button.setEnabled(bool(histories))
        hint = f"{len(histories)} restored histories"
        self._history_button.setToolTip(hint if histories else "No history")

    def _show_restored_history(self) -> None:
        """Open the read-only restored history viewer.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dialog runs until closed.
        """
        if self._restored_store is None:
            return
        histories = self._restored_store.list()
        if not histories:
            return
        loader = self._restored_store.transcript
        dialog = RestoredHistoryDialog(histories, loader, self)
        dialog.exec()

    def _restore_archive(self) -> None:
        """Restore a verified archive from the sidebar.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The archive is restored or the action is cancelled.
        """
        if self._archive_service is None:
            return
        manifest = self._archive_choice(self._archive_service.list())
        if manifest is None or not self._verify_archive(manifest):
            return
        self._restore_archive_choice(manifest)

    def _archive_choice(self, archives):
        """Ask which archive to restore.

        Parameters
        ----------
        archives : list
            Archive manifests.

        Returns
        -------
        dict or None
            Chosen manifest, or ``None``.
        """
        if not archives:
            QMessageBox.information(
                self, "Restore archive", "No archives available."
            )
            return None
        return _choose_archive_dialog(self, archives)

    def _verify_archive(self, manifest):
        """Verify an archive before restoring it.

        Parameters
        ----------
        manifest : dict
            Archive manifest.

        Returns
        -------
        bool
            ``True`` when the archive verifies.
        """
        result = self._archive_service.verify(manifest["archive_id"])
        if result["ok"]:
            return True
        errors = "\n".join(result["errors"])
        QMessageBox.warning(
            self, "Restore archive", "Verification failed:\n" + errors
        )
        return False

    def _restore_archive_choice(self, manifest):
        """Restore one verified archive into a new session.

        Parameters
        ----------
        manifest : dict
            Archive manifest.

        Returns
        -------
        None
            The restored session becomes active.
        """
        result = self._perform_restore(manifest)
        if result is None:
            return
        self._refresh_sidebar()
        self._activate(self._store.load(result["target_session_id"]))

    def _perform_restore(self, manifest):
        """Restore one archive, reporting failures.

        Parameters
        ----------
        manifest : dict
            Archive manifest.

        Returns
        -------
        dict or None
            Restore result, or ``None`` on failure.
        """
        notes, sources, evidence = self._research_stores()
        try:
            return self._archive_service.restore(
                manifest["archive_id"], None, None, notes, sources, evidence
            )
        except (ArchiveError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Restore archive", str(exc))
            return None

    def _dark_mode_button(self) -> QPushButton:
        """Create the light and dark mode toggle button.

        Parameters
        ----------
        None

        Returns
        -------
        QPushButton
            Button that flips the palette and updates its label.
        """
        self._dark_button = QPushButton("", self)
        self._dark_button.clicked.connect(self._toggle_dark_mode)
        self._sync_dark_button()
        return self._dark_button

    def _unwise_button(self) -> QPushButton:
        """Create the 50 percent opacity Unwise Mode toggle.

        Parameters
        ----------
        None

        Returns
        -------
        QPushButton
            Checkable button that applies or removes 50 percent opacity.
        """
        self._unwise_button = QPushButton("Unwise", self)
        self._unwise_button.setCheckable(True)
        self._unwise_button.setChecked(bool(self._settings.get("unwise_mode")))
        self._unwise_button.toggled.connect(self._on_unwise_mode)
        self._apply_unwise(self._unwise_button.isChecked())
        return self._unwise_button

    def _on_unwise_mode(self, checked: bool) -> None:
        """Persist and apply Unwise Mode.

        Parameters
        ----------
        checked : bool
            Whether Unwise Mode is enabled.

        Returns
        -------
        None
            The window opacity and setting update.
        """
        self._settings.set("unwise_mode", checked)
        self._apply_unwise(checked)

    def _apply_unwise(self, enabled: bool) -> None:
        """Apply or remove the Unwise Mode window opacity.

        Parameters
        ----------
        enabled : bool
            Whether 50 percent opacity should be applied.

        Returns
        -------
        None
            The window opacity is updated.
        """
        if _window_platform() == "wayland":
            self._apply_unwise_effect(enabled)
        else:
            self.setWindowOpacity(0.5 if enabled else 1.0)
        self._unwise_button.setToolTip(_unwise_hint(enabled))

    def _apply_unwise_effect(self, enabled: bool) -> None:
        """Apply 50 percent opacity with a graphics effect on Wayland.

        Parameters
        ----------
        enabled : bool
            Whether 50 percent opacity should be applied.

        Returns
        -------
        None
            The graphics effect and translucent attribute update.
        """
        effect = QGraphicsOpacityEffect(self) if enabled else None
        if effect is not None:
            effect.setOpacity(0.5)
        self.setGraphicsEffect(effect)

    def _toggle_dark_mode(self) -> None:
        """Flip the palette between light and dark mode.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The setting, palette, and button label update.
        """
        dark = not bool(self._settings.get("dark_mode"))
        self._on_dark_mode(dark)
        self._sync_dark_button()

    def _sync_dark_button(self) -> None:
        """Set the dark mode button text for the active palette.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The label and tooltip match the current mode.
        """
        dark = bool(self._settings.get("dark_mode"))
        self._dark_button.setText("psycho mode" if dark else "\u263e")
        self._dark_button.setStyleSheet("" if dark else "color: #000000;")
        hint = "Switch to light mode" if dark else "Switch to dark mode"
        self._dark_button.setToolTip(hint)

    def _research_button(self) -> QPushButton:
        """Create the research panel toggle button.

        Parameters
        ----------
        None

        Returns
        -------
        QPushButton
            Button that opens or closes the research panel.
        """
        self._toggle = QPushButton("Research Desk", self)
        self._toggle.clicked.connect(self.toggle_research)
        return self._toggle

    def _update_workspace_label(self) -> None:
        """Show the active projects folder.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The label text and tooltip are updated.
        """
        self._workspace_label.setText("Projects: " + str(self._root))
        self._workspace_label.setToolTip(str(self._root))

    def _choose_workspace(self) -> None:
        """Ask for a new projects folder and apply it.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The selected folder becomes the workspace root.
        """
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose project folder", str(self._root)
        )
        if chosen:
            self._set_workspace(Path(chosen))

    def _set_workspace(self, root: Path) -> None:
        """Rebind tools to a new projects folder.

        Parameters
        ----------
        root : pathlib.Path
            New workspace root.

        Returns
        -------
        None
            Settings, tools, and the label are updated.
        """
        root = root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._root = root
        self._settings.set("workspace", str(root))
        self._bind_workspace_tools(root)
        self._reset_research_stores(root)
        self._refresh_research_workspace()
        self._update_workspace_label()

    def _bind_workspace_tools(self, root) -> None:
        """Rebind both agents to a workspace.

        Parameters
        ----------
        root : pathlib.Path
            New workspace root.

        Returns
        -------
        None
            Both tool registries are updated.
        """
        self._command_panel._agent.tools.root = root
        self._research_panel._agent.tools.root = root

    def _on_show_commands(self, checked: bool) -> None:
        """Persist and apply the commands toggle.

        Parameters
        ----------
        checked : bool
            New checkbox state.

        Returns
        -------
        None
            The setting is stored.
        """
        self._settings.set("show_commands", checked)

    def _on_show_tools(self, checked: bool) -> None:
        """Persist and apply the tool activity toggle.

        Parameters
        ----------
        checked : bool
            New checkbox state.

        Returns
        -------
        None
            The setting is stored and panels update.
        """
        self._settings.set("show_tools", checked)
        self._command_panel._show_tools = checked
        self._research_panel._show_tools = checked

    def _on_dark_mode(self, checked: bool) -> None:
        """Persist and apply the dark mode toggle.

        Parameters
        ----------
        checked : bool
            New checkbox state.

        Returns
        -------
        None
            The palette and panel bubbles update.
        """
        self._settings.set("dark_mode", checked)
        apply_palette(QApplication.instance(), checked)
        self._command_panel.set_dark(checked)
        self._research_panel.set_dark(checked)

    def toggle_research(self) -> None:
        """Toggle the research panel visibility.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The research card shows or hides.
        """
        if self._research_card.isVisible():
            self._research_card.hide()
            self._toggle.setText("Research Desk")
        else:
            self._research_card.show()
            self._toggle.setText("Close Research Desk")
            self._maybe_show_research_welcome()

    def _maybe_show_research_welcome(self):
        """Show the introduction once, before it has been dismissed.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dialog is shown only on first use.
        """
        if self._settings.get("research_desk_welcome_seen"):
            return
        self._show_research_welcome()

    def _show_research_welcome(self):
        """Open the Research Desk introduction and mark it seen.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The dialog runs until closed.
        """
        dialog = ResearchWelcomeDialog(self)
        dialog.exec()
        self._settings.set("research_desk_welcome_seen", True)

    def _card(self, panel: QWidget) -> QWidget:
        """Wrap a panel in a buffered card container.

        Parameters
        ----------
        panel : QWidget
            Panel to place inside the card.

        Returns
        -------
        QWidget
            Container with inset margins around the panel.
        """
        card = QWidget(self)
        card.setObjectName("PanelCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(8, 8, 8, 8)
        box.addWidget(panel)
        return card

    def _build_header(self) -> QWidget:
        """Build the fixed-height header region.

        Parameters
        ----------
        None

        Returns
        -------
        QWidget
            Header with logo and divider line.
        """
        header = QWidget(self)
        header.setFixedHeight(200)
        box = QVBoxLayout(header)
        box.setContentsMargins(5, 0, 5, 0)
        box.setSpacing(0)
        box.addWidget(self._brand_label(), 0, Qt.AlignBottom)
        box.addWidget(self._header_line())
        return header

    def _brand_label(self) -> QLabel:
        """Build the single top-left logo.

        Parameters
        ----------
        None

        Returns
        -------
        QLabel
            Logo showing the header image.
        """
        path = Path(__file__).parent / "assets" / "sage_logo.png"
        label = QLabel(self)
        pixmap = QPixmap(str(path)).scaledToHeight(
            180, Qt.SmoothTransformation
        )
        label.setPixmap(pixmap)
        label.setFixedSize(pixmap.size())
        return label

    def _header_line(self) -> QFrame:
        """Build the line under the header.

        Parameters
        ----------
        None

        Returns
        -------
        QFrame
            Horizontal separator frame.
        """
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def closeEvent(self, event) -> None:  # noqa: N802
        """Prompt to save and stop panel threads before closing.

        Parameters
        ----------
        event : QCloseEvent
            Close notification.

        Returns
        -------
        None
            The session is saved or removed, then threads stop.
        """
        choice = _close_choice(self)
        if choice == QMessageBox.Discard:
            self._remove(self._record)
        elif choice != QMessageBox.Save:
            event.ignore()
            return
        self._stop_panels()
        event.accept()

    def _stop_panels(self) -> None:
        """Stop both panel threads.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both panels stop their workers.
        """
        self._command_panel.stop()
        self._research_panel.stop()


def _launch_bundle() -> bool:
    """Start the macOS app bundle in the background when installed.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        ``True`` when a detached bundle process was started.
    """
    if not _is_bundle_launcher() or os.getenv("HARNESS_BUNDLE_LAUNCHED"):
        return False
    executable = _bundle_executable()
    if executable is None:
        return False
    _spawn_bundle(executable)
    return True


def _spawn_bundle(executable: Path) -> None:
    """Start the bundle executable detached from this terminal.

    Parameters
    ----------
    executable : pathlib.Path
        Bundle executable path.

    Returns
    -------
    None
        The child process starts.
    """
    root = Path(__file__).resolve().parent.parent
    env = _bundle_env(root)
    _popen_bundle(executable, env, root)


def _is_bundle_launcher() -> bool:
    """Return whether the current process is a console launcher script.

    Parameters
    ----------
    None

    Returns
    -------
    bool
        ``True`` for the ``harness-gui`` and ``harness-voice`` scripts.
    """
    name = Path(sys.argv[0]).name
    return name in ("harness-gui", "harness-voice")


def _bundle_executable() -> Path | None:
    """Return the installed app-bundle executable for this checkout.

    Parameters
    ----------
    None

    Returns
    -------
    pathlib.Path or None
        Bundle executable path when it exists and matches this repo.
    """
    if sys.platform != "darwin":
        return None
    app = Path.home() / "Applications" / "SavrenAI.app"
    executable = app / "Contents" / "MacOS" / "SavrenAI"
    if not executable.exists() or not _bundle_matches(app):
        return None
    return executable


def _bundle_matches(app: Path) -> bool:
    """Return whether a bundle was built from this repository.

    Parameters
    ----------
    app : pathlib.Path
        Application bundle path.

    Returns
    -------
    bool
        ``True`` when the bundle targets this checkout.
    """
    plist = app / "Contents" / "Info.plist"
    if not plist.exists():
        return False
    info = plistlib.loads(plist.read_bytes())
    home = info.get("LSEnvironment", {}).get("HARNESS_HOME")
    root = Path(__file__).resolve().parent.parent
    return not home or Path(home).resolve() == root


def main() -> None:
    """Launch the desktop application.

    Parameters
    ----------
    None

    Returns
    -------
    None
        The application runs until the window closes.
    """
    if _launch_bundle():
        return
    app = _build_app()
    store = _prepare_store()
    settings = Settings()
    window = _main_window(store, workspace_root(settings), settings)
    window.show()
    sys.exit(app.exec())


def _apply_hal_identity(app: QApplication) -> None:
    """Set the HAL application name and red-eye icon.

    Parameters
    ----------
    app : QApplication
        Running application.

    Returns
    -------
    None
        Name and icon are applied.
    """
    hal = importlib.import_module(".hal", __package__)
    icon = hal.hal_icon()
    app.setApplicationName("SavrenAI")
    app.setApplicationDisplayName("SavrenAI")
    app.setWindowIcon(icon)
    _set_process_name("SavrenAI")


def _set_process_name(name: str) -> None:
    """Set the macOS process and menu name.

    Parameters
    ----------
    name : str
        Display name.

    Returns
    -------
    None
        The name is applied when AppKit is available.
    """
    try:
        appkit = importlib.import_module("AppKit")
        foundation = importlib.import_module("Foundation")
    except Exception:
        return
    foundation.NSProcessInfo.processInfo().setProcessName_(name)
    _name_main_menu(appkit, name)


def _main_window(store: SessionStore, root: Path, settings):
    """Build the window for the configured interface mode.

    Parameters
    ----------
    store : SessionStore
        Session backend.
    root : pathlib.Path
        Project workspace root.
    settings : Settings
        Persisted interface settings.

    Returns
    -------
    QMainWindow
        Chat or HAL window.
    """
    if ui_mode() == "hal":
        hal = importlib.import_module(".hal", __package__)
        return hal.HalWindow(store, root, settings)
    return MainWindow(store, root, settings)


def _apply_theme(app: QApplication) -> None:
    """Apply the classic, dark, or cyber stylesheet.

    Parameters
    ----------
    app : QApplication
        Application receiving the stylesheet.

    Returns
    -------
    None
        The selected stylesheet is applied.
    """
    if ui_mode() in ("cyber", "hal"):
        from .cyber_style import apply_palette as apply_cyber

        apply_cyber(app)
        return
    apply_palette(app, bool(Settings().get("dark_mode")))


if __name__ == "__main__":
    main()


def _make_voice(missing: list[str]):
    """Create a voice engine when dependencies are available.

    Parameters
    ----------
    missing : list[str]
        Missing voice dependency names.

    Returns
    -------
    VoiceEngine or None
        Engine instance, or None when dependencies are missing.
    """
    if missing:
        return None
    return VoiceEngine()


def _thread_signals(window):
    """Return thread action signal and slot pairs.

    Parameters
    ----------
    window : MainWindow
        Owning window.

    Returns
    -------
    tuple
        Signal and slot pairs.
    """
    workspace = window._research_workspace
    return (
        (workspace.thread_selected, window._select_research_thread),
        (workspace.new_thread_requested, window._new_research_thread),
    ) + _thread_lifecycle_signals(window)


def _thread_lifecycle_signals(window):
    """Return thread lifecycle signal and slot pairs.

    Parameters
    ----------
    window : MainWindow
        Owning window.

    Returns
    -------
    tuple
        Signal and slot pairs.
    """
    workspace = window._research_workspace
    return (
        (workspace.thread_archive_requested, window._archive_research_thread),
        (workspace.thread_restore_requested, window._restore_research_thread),
        (workspace.thread_delete_requested, window._delete_research_thread),
        (workspace.archived_toggled, window._toggle_archived_threads),
    )


def _active_thread_id(thread):
    """Return the active research thread identifier.

    Parameters
    ----------
    thread : dict or None
        Active thread metadata.

    Returns
    -------
    str or None
        Thread identifier.
    """
    return thread["id"] if thread else None


def _parse_tool_json(content):
    """Parse serialized tool output without raising.

    Parameters
    ----------
    content : str
        Tool result text.

    Returns
    -------
    object
        Parsed value or ``None``.
    """
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None


def _capture_search(store, scope, data):
    """Store search result pages as sources.

    Parameters
    ----------
    store : SourceStore
        Source store.
    scope : dict
        Research scope.
    data : object
        Parsed search results.

    Returns
    -------
    None
        Valid results are stored.
    """
    if not isinstance(data, list):
        return
    for item in data:
        if isinstance(item, dict) and item.get("url"):
            _store_source(store, scope, item)


def _capture_page(store, scope, data):
    """Store one opened page as a source.

    Parameters
    ----------
    store : SourceStore
        Source store.
    scope : dict
        Research scope.
    data : object
        Parsed page result.

    Returns
    -------
    None
        The page is stored when it has a URL.
    """
    if isinstance(data, dict) and data.get("url"):
        _store_source(store, scope, data)


def _store_source(store, scope, item):
    """Store one tool result as a source, ignoring invalid URLs.

    Parameters
    ----------
    store : SourceStore
        Source store.
    scope : dict
        Research scope.
    item : dict
        Tool result mapping.

    Returns
    -------
    None
        The source is stored when the URL is valid.
    """
    excerpt = item.get("snippet") or str(item.get("text", ""))[:500]
    try:
        store.add(scope, item["url"], item.get("title", ""), excerpt)
    except (KeyError, ValueError):
        return


def _record_ids(records):
    """Return identifiers from a list of record mappings.

    Parameters
    ----------
    records : list
        Record mappings.

    Returns
    -------
    list
        Record identifiers.
    """
    return [record["id"] for record in records]


def _cursor_text(cursor):
    """Return selected text or the current block as message text.

    Parameters
    ----------
    cursor : QTextCursor
        Transcript cursor.

    Returns
    -------
    tuple
        Text and transfer kind.
    """
    if cursor.hasSelection():
        return cursor.selectedText().strip(), "selection"
    return cursor.block().text().strip(), "message"


def _note_title(body):
    """Return a short title from selected note text.

    Parameters
    ----------
    body : str
        Note body.

    Returns
    -------
    str
        First line, bounded to 80 characters.
    """
    first = body.splitlines()[0].strip()
    return (first or "Research note")[:80]


def _selection_origin(body):
    """Build an origin snapshot for a saved selection.

    Parameters
    ----------
    body : str
        Selected text.

    Returns
    -------
    dict
        Origin snapshot.
    """
    return {
        "message_seq": None,
        "message_hash": "",
        "role": "selection",
        "excerpt": body[:500],
        "captured_at": time.time(),
    }


def _new_research_panel(agent, options, context):
    """Build the research chat panel.

    Parameters
    ----------
    agent : Agent
        Research agent.
    options : dict
        Shared panel options.
    context : collections.abc.Callable
        Research context builder.

    Returns
    -------
    ChatPanel
        Configured research panel.
    """
    return ChatPanel(
        agent,
        title="Research",
        context=context,
        show_snapshot_toggle=True,
        **options,
    )


def _agent_options(root, path, prompt, tools):
    """Build optional agent keyword arguments.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    path : pathlib.Path
        Transcript path.
    prompt : str or None
        Optional system prompt.
    tools : ToolRegistry or None
        Optional restricted registry.

    Returns
    -------
    dict
        Agent keyword arguments.
    """
    return {
        "root": root,
        "session": Session(path),
        "system_prompt": prompt,
        "tools": tools,
    }


def _research_tools(root, services):
    """Build the default-deny research tool registry.

    Parameters
    ----------
    root : pathlib.Path
        Active project workspace.
    services : ResearchServices
        Session-bound note and evidence services.

    Returns
    -------
    ToolRegistry
        Read-only registry with private paths and unsafe URLs blocked.
    """
    options = _research_tool_options(services)
    options.update(_research_registry_options())
    return ToolRegistry(root, **options)


def _research_registry_options():
    """Return static research registry policy options.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Registry policy options.
    """
    return {
        "allowed_tools": RESEARCH_TOOL_NAMES,
        "read_only": True,
        "deny_private": True,
        "safe_urls": True,
    }


def _research_tool_options(services):
    """Build research service callback options.

    Parameters
    ----------
    services : ResearchServices
        Session-bound research services.

    Returns
    -------
    dict
        Tool registry callback options.
    """
    return {
        "note_sink": services.propose_note,
        "note_revision_sink": services.propose_revision,
        "evidence_sink": services.capture_evidence,
    }


def _window_platform():
    """Return the active Qt platform plugin name.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Platform name, or an empty string without an application.
    """
    app = QApplication.instance()
    return app.platformName() if app is not None else ""


def _unwise_hint(enabled):
    """Build the Unwise Mode tooltip.

    Parameters
    ----------
    enabled : bool
        Whether Unwise Mode is active.

    Returns
    -------
    str
        Tooltip text.
    """
    if enabled:
        return "Restore full opacity"
    return "Apply 50 percent opacity"


def _project_name(root):
    """Return the current project folder name.

    Parameters
    ----------
    root : pathlib.Path or str
        Workspace root.

    Returns
    -------
    str
        Project name.
    """
    name = Path(root).name
    return name or str(root)


def _make_archive_service(root, sessions_root):
    """Build an archive service when research storage exists.

    Parameters
    ----------
    root : pathlib.Path or None
        Research root.
    sessions_root : pathlib.Path
        Session folder parent.

    Returns
    -------
    ArchiveService or None
        Archive service or ``None``.
    """
    return ArchiveService(root, sessions_root) if root is not None else None


def _delete_options(window, record):
    """Build the archive, delete, and cancel dialog.

    Parameters
    ----------
    window : QWidget
        Owning window.
    record : SessionRecord
        Session to remove.

    Returns
    -------
    tuple
        Dialog, archive button, and delete button.
    """
    box = QMessageBox(window)
    box.setWindowTitle("Session")
    box.setText("Archive or delete '%s'?" % record.title)
    archive, delete = _add_delete_buttons(box)
    return box, archive, delete


def _add_delete_buttons(box):
    """Add archive, delete, and cancel buttons to a dialog.

    Parameters
    ----------
    box : QMessageBox
        Session removal dialog.

    Returns
    -------
    tuple
        Archive and delete buttons.
    """
    archive = box.addButton(
        "Archive research", QMessageBox.ButtonRole.AcceptRole
    )
    delete = box.addButton(
        "Delete all", QMessageBox.ButtonRole.DestructiveRole
    )
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    return archive, delete


def _add_restore_button(window, box, sidebar):
    """Add the sidebar restore-archive button.

    Parameters
    ----------
    window : MainWindow
        Owning window.
    box : QVBoxLayout
        Sidebar layout.
    sidebar : QWidget
        Sidebar widget.

    Returns
    -------
    None
        The button is added.
    """
    box.addSpacing(12)
    window._restore_button = _new_button(
        sidebar, "Restore archive", window._restore_archive
    )
    box.addWidget(window._restore_button)


def _choose_archive_dialog(window, archives):
    """Ask the user to choose one archive.

    Parameters
    ----------
    window : QWidget
        Owning window.
    archives : list
        Archive manifests.

    Returns
    -------
    dict or None
        Chosen manifest, or ``None`` when cancelled.
    """
    labels = [_archive_label(item) for item in archives]
    label, ok = QInputDialog.getItem(
        window, "Restore archive", "Archive:", labels, 0, False
    )
    if not ok:
        return None
    return archives[labels.index(label)]


def _archive_label(manifest):
    """Build a display label for one archive.

    Parameters
    ----------
    manifest : dict
        Archive manifest.

    Returns
    -------
    str
        Label with title and archive identifier.
    """
    title = manifest.get("original_session_meta", {}).get("title")
    return f"{title or 'Archive'} ({manifest['archive_id']})"


def _resolve_research(root):
    """Resolve the research root or return a storage error.

    Parameters
    ----------
    root : pathlib.Path
        Active project workspace.

    Returns
    -------
    tuple
        Research root or ``None`` and an error string or ``None``.
    """
    try:
        return research_root(workspace=root), None
    except ResearchPathError as exc:
        return None, str(exc)


def _init_store(factory, root):
    """Create a store when a research root exists.

    Parameters
    ----------
    factory : type
        Store class.
    root : pathlib.Path or None
        Research root.

    Returns
    -------
    object or None
        Store instance when storage is available.
    """
    return factory(root) if root is not None else None


def _window_central(window) -> QWidget:
    """Create the main window central widget and layout.

    Parameters
    ----------
    window : MainWindow
        Owning window.

    Returns
    -------
    QWidget
        Central widget with header, toggle bar, and body.
    """
    central = QWidget(window)
    layout = QVBoxLayout(central)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    layout.addWidget(window._build_header())
    layout.addLayout(window._build_toggle_bar())
    layout.addWidget(window._build_body(central))
    return central


def _sidebar_widget(parent) -> QWidget:
    """Create the fixed-width sidebar widget.

    Parameters
    ----------
    parent : QWidget
        Owning window.

    Returns
    -------
    QWidget
        Sidebar widget named ``Sidebar``.
    """
    sidebar = QWidget(parent)
    sidebar.setObjectName("Sidebar")
    sidebar.setFixedWidth(220)
    return sidebar


def _item_list(sidebar, click, menu) -> QListWidget:
    """Create a context-menu item list.

    Parameters
    ----------
    sidebar : QWidget
        Sidebar widget.

    click : callable
        Item-clicked slot.

    menu : callable
        Context-menu slot.

    Returns
    -------
    QListWidget
        Configured list widget.
    """
    widget = QListWidget(sidebar)
    widget.itemClicked.connect(click)
    widget.setContextMenuPolicy(Qt.CustomContextMenu)
    widget.customContextMenuRequested.connect(menu)
    return widget


def _new_button(sidebar, label: str, slot) -> QPushButton:
    """Create a new-item button wired to a slot.

    Parameters
    ----------
    sidebar : QWidget
        Sidebar widget.

    label : str
        Button text.

    slot : callable
        Clicked slot.

    Returns
    -------
    QPushButton
        Configured button.
    """
    button = QPushButton(label, sidebar)
    button.clicked.connect(slot)
    return button


def _with_context(builder, prompt):
    """Prepend optional context only when it is non-empty.

    Parameters
    ----------
    builder : collections.abc.Callable or None
        Optional context builder.
    prompt : str
        User prompt.

    Returns
    -------
    str
        Prompt with optional context.
    """
    context = builder() if builder is not None else ""
    return context + "\n\n" + prompt if context else prompt


def _toggle_specs(window):
    """Return the checkbox labels, settings keys, and slots.

    Parameters
    ----------
    window : QMainWindow
        Owning window.

    Returns
    -------
    tuple
        Checkbox specifications.
    """
    return (
        ("Show commands", "show_commands", window._on_show_commands),
        ("Show tool activity", "show_tools", window._on_show_tools),
    )


def _toggle_box(window, label: str, key: str, slot) -> QCheckBox:
    """Create a checkbox bound to a persisted setting.

    Parameters
    ----------
    window : QMainWindow
        Owning window.

    label : str
        Checkbox text.

    key : str
        Settings key.

    slot : callable
        Toggled slot.

    Returns
    -------
    QCheckBox
        Configured checkbox.
    """
    box = QCheckBox(label, window)
    box.setChecked(window._settings.get(key))
    box.toggled.connect(slot)
    return box


def _close_choice(window):
    """Ask whether to save the session before closing.

    Parameters
    ----------
    window : QMainWindow
        Owning window.

    Returns
    -------
    int
        Chosen standard button.
    """
    return QMessageBox.information(
        window,
        "Close",
        "Save this session?",
        buttons=QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        defaultButton=QMessageBox.Save,
    )


def _left_bubble(fmt, margin: int):
    """Apply left alignment and a right margin.

    Parameters
    ----------
    fmt : QTextBlockFormat
        Block format being updated.

    margin : int
        Right margin in pixels.

    Returns
    -------
    QTextBlockFormat
        The updated format.
    """
    fmt.setAlignment(Qt.AlignLeft)
    fmt.setRightMargin(margin)
    return fmt


def _bundle_env(root: Path) -> dict:
    """Build the detached launcher environment.

    Parameters
    ----------
    root : pathlib.Path
        Repository root.

    Returns
    -------
    dict
        Environment mapping for the child process.
    """
    env = dict(os.environ)
    env["HARNESS_BUNDLE_LAUNCHED"] = "1"
    env["HARNESS_HOME"] = str(root)
    return env


def _devnull_streams() -> dict:
    """Return DEVNULL stream options for a detached child.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Standard stream keyword arguments.
    """
    return {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }


def _popen_options(env: dict, root: Path) -> dict:
    """Build detached-process options.

    Parameters
    ----------
    env : dict
        Environment for the child process.

    root : pathlib.Path
        Working directory.

    Returns
    -------
    dict
        Keyword arguments for ``subprocess.Popen``.
    """
    return {
        "env": env,
        "cwd": str(root),
        **_devnull_streams(),
        "start_new_session": True,
        "close_fds": True,
    }


def _popen_bundle(executable: Path, env: dict, root: Path) -> None:
    """Start the bundle executable as a detached process.

    Parameters
    ----------
    executable : pathlib.Path
        Bundle executable path.

    env : dict
        Environment for the child process.

    root : pathlib.Path
        Repository root used as the working directory.

    Returns
    -------
    None
        The child process starts.
    """
    options = _popen_options(env, root)
    subprocess.Popen([str(executable), *sys.argv[1:]], **options)


def _build_app() -> QApplication:
    """Create and theme the QApplication.

    Parameters
    ----------
    None

    Returns
    -------
    QApplication
        Running application instance.
    """
    load_env()
    app = QApplication(sys.argv)
    _apply_theme(app)
    if ui_mode() == "hal":
        _apply_hal_identity(app)
    return app


def _prepare_store() -> SessionStore:
    """Create the session store with a first session.

    Parameters
    ----------
    None

    Returns
    -------
    SessionStore
        Session store rooted in ``runs/sessions``.
    """
    store = SessionStore(Path("runs/sessions"))
    if not any(store.root.iterdir()):
        store.create(kind="session")
    return store


def _name_main_menu(appkit, name: str) -> None:
    """Rename the first main-menu item.

    Parameters
    ----------
    appkit : module
        Imported AppKit module.

    name : str
        Display name.

    Returns
    -------
    None
        The menu title is updated when a menu exists.
    """
    menu = appkit.NSApplication.sharedApplication().mainMenu()
    if menu is not None and menu.numberOfItems() > 0:
        menu.itemAtIndex_(0).setTitle_(name)


def _animation_timer(panel) -> QTimer:
    """Create the panel animation timer.

    Parameters
    ----------
    panel : QWidget
        Owning panel.

    Returns
    -------
    QTimer
        Configured timer emitting ``_animate``.
    """
    timer = QTimer(panel)
    timer.setInterval(250)
    timer.timeout.connect(panel._animate)
    return timer


def _question_widget(panel) -> QWidget:
    """Create the hidden question card widget.

    Parameters
    ----------
    panel : QWidget
        Owning panel.

    Returns
    -------
    QWidget
        Question card widget named ``QuestionCard``.
    """
    card = QWidget(panel)
    card.setObjectName("QuestionCard")
    return card


def _wrapped_label(parent) -> QLabel:
    """Create a word-wrapped label.

    Parameters
    ----------
    parent : QWidget
        Owning widget.

    Returns
    -------
    QLabel
        Empty wrapped label.
    """
    label = QLabel("", parent)
    label.setWordWrap(True)
    return label
