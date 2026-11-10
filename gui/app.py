"""PySide6 desktop shell with command and ideas panels."""

import importlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtCore import QSize
from PySide6.QtCore import Qt
from PySide6.QtCore import QThread
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
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
from meta_harness.session import Session
from meta_harness.voice import VoiceEngine
from meta_harness.voice import missing_dependencies
from meta_harness.voice_text import match_option
from meta_harness.voice_text import speech_text

from .cyber_style import AGENT_BUBBLE
from .cyber_style import TOOL_BUBBLE
from .cyber_style import USER_BUBBLE
from .store import SessionRecord
from .store import SessionStore
from .context import snapshot
from .settings import Settings
from .worker import AgentWorker
from .worker import QuestionBridge
from .workspace import workspace_root


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


class ChatPanel(QWidget):
    """One agent chat panel with header, log, and input."""

    posted = Signal()
    heard = Signal(str)

    def __init__(
        self,
        agent: Agent,
        title: str = "Minimal Harness",
        context=None,
        show_notes_toggle: bool = False,
        show_tools: bool = False,
        settings=None,
        voice_on: bool = False,
        theme: str = "classic",
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
        show_notes_toggle : bool
            Whether to show the notes context checkbox.
        show_tools : bool
            Whether to render tool activity in the log.
        settings : Settings or None
            Optional persisted interface settings.
        voice_on : bool
            Whether to build voice controls.
        theme : str
            Active theme name (``classic`` or ``cyber``).

        Returns
        -------
        None
            The panel is ready to show.
        """
        super().__init__()
        self._agent = agent
        self._context = context
        self._show_tools = show_tools
        self._settings = settings
        self._configure_state(voice_on)
        self._theme = theme
        self._start_worker(agent, title, show_notes_toggle)

    def _configure_state(self, voice_on: bool) -> None:
        """Initialize per-panel mutable state.

        Parameters
        ----------
        voice_on : bool
            Whether to build voice controls.

        Returns
        -------
        None
            State fields are initialized.
        """
        self._voice_on = voice_on
        self._notes_included = False
        self._outgoing: list[str] = []
        self._queued = 0
        self._voice_missing = missing_dependencies() if voice_on else []
        self._voice = _make_voice(self._voice_missing)

    def _start_worker(self, agent, title, show_notes_toggle) -> None:
        """Start the animation timer and background worker.

        Parameters
        ----------
        agent : Agent
            Backend agent for this panel.

        title : str
            Panel header title.

        show_notes_toggle : bool
            Whether to show the notes context checkbox.

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
        self._build_ui(title, show_notes_toggle)
        self._thread.start()

    def _build_ui(self, title: str, show_notes_toggle: bool) -> None:
        """Compose the panel layout.

        Parameters
        ----------
        title : str
            Panel header title.
        show_notes_toggle : bool
            Whether to show the notes context checkbox.

        Returns
        -------
        None
            Widgets are arranged in place.
        """
        self._layout = QVBoxLayout(self)
        self._layout.addLayout(self._build_header(title))
        self._build_status()
        self._build_voice_status()
        self._build_composer(show_notes_toggle)
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
        self._tick = 0
        self._layout.addWidget(self._status)

    def _build_composer(self, show_notes_toggle: bool) -> None:
        """Build the log, input row, and question card.

        Parameters
        ----------
        show_notes_toggle : bool
            Whether to show the notes context checkbox.

        Returns
        -------
        None
            Widgets are added to the layout.
        """
        self._build_log()
        self._build_input_row()
        self._notes = self._build_notes(show_notes_toggle)
        self._build_question_card()
        if self._notes is not None:
            self._layout.addWidget(self._notes)
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
        self._layout.addWidget(self._log)

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

    def _build_notes(self, show_notes_toggle: bool):
        """Create the optional notes checkbox.

        Parameters
        ----------
        show_notes_toggle : bool
            Whether to show the notes context checkbox.

        Returns
        -------
        QCheckBox or None
            The checkbox when enabled, otherwise None.
        """
        if not show_notes_toggle:
            return None
        notes = QCheckBox("Include saved notes", self)
        notes.setChecked(self._notes_included)
        notes.stateChanged.connect(self._on_notes)
        return notes

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

    def _on_notes(self, state: int) -> None:
        """Toggle whether notes join the context.

        Parameters
        ----------
        state : int
            Checkbox check state.

        Returns
        -------
        None
            The note flag is updated.
        """
        self._notes_included = state == Qt.CheckState.Checked.value

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
        if self._context is not None:
            prompt = self._context() + "\n\n" + prompt
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
        doc.setMarkdown(text)
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
        if self._theme != "cyber":
            if tool:
                return "#EFEFEF"
            return "#D2DBD6" if user else "#D6E0E6"
        if tool:
            return TOOL_BUBBLE
        return USER_BUBBLE if user else AGENT_BUBBLE

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
        """Begin the moving thinking indicator.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The status animates while the worker runs.
        """
        self._tick = 0
        self._status.setText("thinking")
        self._timer.start()

    def _animate(self) -> None:
        """Advance the thinking indicator dots.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The status label cycles through dot counts and queue size.
        """
        self._tick = (self._tick + 1) % 4
        text = "thinking" + "." * self._tick
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
            The status label empties.
        """
        self._timer.stop()
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

    def _build_panels(self) -> None:
        """Create the command and ideas chat panels.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Panels and their cards are created.
        """
        self._command_panel = self._make_command_panel()
        self._command_panel.posted.connect(self._on_posted)
        self._ideas_panel = self._make_ideas_panel()
        self._ideas_panel.posted.connect(self._on_posted)
        self._ideas_card = self._card(self._ideas_panel)
        self._ideas_card.hide()

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
        return ChatPanel(self._make_agent(), **self._panel_options())

    def _make_ideas_panel(self):
        """Create the ideas chat panel.

        Parameters
        ----------
        None

        Returns
        -------
        ChatPanel
            Panel for speculative ideas.
        """
        return ChatPanel(
            self._make_agent(),
            title="Ideas",
            context=self._make_ideas_context,
            show_notes_toggle=True,
            **self._panel_options(),
        )

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
        self.setWindowTitle("Minimal Harness")
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
        main.addWidget(self._ideas_card)
        return main

    def _make_agent(self) -> Agent:
        """Build an agent for one panel.

        Parameters
        ----------
        None

        Returns
        -------
        Agent
            Agent bound to the working session.
        """
        agent = Agent(
            root=self._root,
            session=Session(self._active_path()),
        )
        agent.tools.require_project_folder = True
        return agent

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

    def _make_ideas_context(self) -> str:
        """Build the ideas panel live context.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Workspace snapshot, command tail, and notes.
        """
        first = snapshot(self._root)
        tail = self._command_tail()
        notes = self._notes_text() if self._ideas_panel._notes_included else ""
        return "\n\n".join(part for part in [first, tail, notes] if part)

    def _command_tail(self) -> str:
        """Summarize the recent command conversation.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Recent user and assistant messages.
        """
        if self._record is None or not self._record.transcript.exists():
            return ""
        return "Recent commands conversation:\n" + self._read_session(
            self._record.transcript
        )

    def _notes_text(self) -> str:
        """Return the current session notes.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Saved notes for the session.
        """
        if self._record is None or not self._record.notes.exists():
            return ""
        return "Saved notes:\n" + self._read_session(self._record.notes)

    def _read_session(self, path: Path) -> str:
        """Format a session transcript as readable text.

        Parameters
        ----------
        path : pathlib.Path
            JSONL session file.

        Returns
        -------
        str
            Joined speaker lines.
        """
        lines = []
        for line in path.read_text().splitlines()[-8:]:
            entry = _session_line(line)
            if entry:
                lines.append(entry)
        return "\n".join(lines)

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
        """Delete a session folder after confirming.

        Parameters
        ----------
        record : SessionRecord
            Session to delete.

        Returns
        -------
        None
            The folder is removed and lists refresh.
        """
        answer = QMessageBox.question(
            self,
            "Delete",
            "Delete '%s' permanently?" % record.title,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._remove(record)

    def _remove(self, record: SessionRecord) -> None:
        """Remove a session folder and refresh lists.

        Parameters
        ----------
        record : SessionRecord
            Session to delete.

        Returns
        -------
        None
            The folder is removed and lists refresh.
        """
        shutil.rmtree(record.folder, ignore_errors=True)
        self._refresh_sidebar()

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
        """Switch both panels to a session.

        Parameters
        ----------
        record : SessionRecord
            Session to make active.

        Returns
        -------
        None
            Both panels load the session.
        """
        self._record = record
        self._touch_active()
        transcripts = Session(record.transcript)
        notes = Session(record.notes)
        self._command_panel.switch_session(transcripts)
        self._ideas_panel.switch_session(notes)
        self._mark_active(record)

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
        bar.addWidget(self._ideas_button())
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
        self._show_commands = _toggle_box(
            self, "Show commands", "show_commands", self._on_show_commands
        )
        bar.addWidget(self._show_commands)
        self._show_tools = _toggle_box(
            self, "Show tool activity", "show_tools", self._on_show_tools
        )
        bar.addWidget(self._show_tools)

    def _ideas_button(self) -> QPushButton:
        """Create the ideas toggle button.

        Parameters
        ----------
        None

        Returns
        -------
        QPushButton
            Button that opens or closes the ideas panel.
        """
        self._toggle = QPushButton("Open Ideas", self)
        self._toggle.clicked.connect(self.toggle_ideas)
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
        self._command_panel._agent.tools.root = root
        self._ideas_panel._agent.tools.root = root
        self._update_workspace_label()

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
        self._ideas_panel._show_tools = checked

    def toggle_ideas(self) -> None:
        """Toggle the ideas panel visibility.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The ideas card shows or hides.
        """
        if self._ideas_card.isVisible():
            self._ideas_card.hide()
            self._toggle.setText("Open Ideas")
        else:
            self._ideas_card.show()
            self._toggle.setText("Close Ideas")

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
        self._ideas_panel.stop()


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
    app = Path.home() / "Applications" / "Minimal Harness.app"
    executable = app / "Contents" / "MacOS" / "Minimal Harness"
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
    app.setApplicationName("Minimal Harness")
    app.setApplicationDisplayName("Minimal Harness")
    app.setWindowIcon(icon)
    _set_process_name("Minimal Harness")


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
    """Apply the classic or cyber stylesheet.

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
        from .cyber_style import apply_palette
    else:
        from .style import apply_palette
    apply_palette(app)


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


def _session_line(line: str) -> str:
    """Format one JSONL session line as speaker text.

    Parameters
    ----------
    line : str
        Raw JSONL line.

    Returns
    -------
    str
        Formatted speaker line, or an empty string.
    """
    try:
        body = json.loads(line)
    except json.JSONDecodeError:
        return ""
    role, content = body.get("role"), body.get("content")
    if role in ("user", "assistant") and isinstance(content, str):
        return role + ": " + content
    return ""


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
