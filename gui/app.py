"""PySide6 desktop shell with command and ideas panels."""

import sys
import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QPixmap,
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
    QTextDocumentFragment,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from meta_harness.agent import Agent
from meta_harness.app_mode import ui_mode, voice_enabled
from meta_harness.env import load_env
from meta_harness.session import Session
from meta_harness.voice import VoiceEngine, missing_dependencies
from meta_harness.voice_text import match_option, speech_text

from .cyber_style import AGENT_BUBBLE, TOOL_BUBBLE, USER_BUBBLE
from .store import SessionRecord, SessionStore
from .context import snapshot
from .worker import AgentWorker, QuestionBridge
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
            self.submitted.emit(self.toPlainText())
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)

    def _resize_to_content(self) -> None:
        """Fit the editor height to its wrapped lines.

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
        self._theme = theme
        self._voice_on = voice_on
        self._notes_included = False
        self._outgoing: list[str] = []
        self._queued = 0
        self._voice_missing: list[str] = []
        self._voice = None
        if voice_on:
            self._voice_missing = missing_dependencies()
            if not self._voice_missing:
                self._voice = VoiceEngine()
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._animate)
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
        self._status = QLabel("", self)
        self._status.setObjectName("statusLabel")
        self._tick = 0
        self._layout.addWidget(self._status)
        self._build_voice_status()
        self._log = QTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QTextEdit.WidgetWidth)
        self._log.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._log.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._notes: QCheckBox | None = None
        if show_notes_toggle:
            self._notes = QCheckBox("Include saved notes", self)
            self._notes.setChecked(self._notes_included)
            self._notes.stateChanged.connect(self._on_notes)
        self._input = PromptInput(self)
        self._send = QPushButton("Ask", self)
        self._build_voice_widgets()
        row = QHBoxLayout()
        row.addWidget(self._input)
        self._add_talk(row)
        row.addWidget(self._send)
        self._layout.addWidget(self._log)
        self._build_question_card()
        if self._notes is not None:
            self._layout.addWidget(self._notes)
        self._add_speak_toggle()
        self._layout.addLayout(row)
        self._send.clicked.connect(self._submit)
        self._input.submitted.connect(self._submit)
        self._connect_voice()
        self._pending: QuestionBridge | None = None

    def _build_voice_status(self) -> None:
        """Add the voice status label only in voice mode.

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

        Returns
        -------
        None
            The toggle is added when present.
        """
        if self._speak_toggle is not None:
            self._layout.addWidget(self._speak_toggle)

    def _connect_voice(self) -> None:
        """Connect voice signals only in voice mode.

        Returns
        -------
        None
            The recognition signal is connected when enabled.
        """
        if self._voice_on:
            self.heard.connect(self._on_heard)

    def _build_question_card(self) -> None:
        """Build the inline agent-question panel.

        Returns
        -------
        None
            The hidden card is added to the layout.
        """
        self._question_card = QWidget(self)
        self._question_card.setObjectName("QuestionCard")
        box = QVBoxLayout(self._question_card)
        box.setContentsMargins(6, 6, 6, 6)
        self._question_label = QLabel("", self._question_card)
        self._question_label.setWordWrap(True)
        self._question_options = QHBoxLayout()
        self._question_input = QLineEdit(self._question_card)
        self._question_send = QPushButton("Answer", self._question_card)
        box.addWidget(self._question_label)
        box.addLayout(self._question_options)
        box.addLayout(self._question_row())
        self._question_card.hide()
        self._layout.addWidget(self._question_card)
        self._question_send.clicked.connect(self._answer_typed)
        self._question_input.returnPressed.connect(self._answer_typed)

    def _question_row(self) -> QHBoxLayout:
        """Build the free-text answer row.

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

        Returns
        -------
        None
            Recording starts or an error is shown.
        """
        if self._voice is None:
            self._voice_status.setText("voice unavailable")
            return
        try:
            self._voice.stop_speaking()
            self._voice.start_recording()
        except Exception as exc:
            self._voice_status.setText(f"mic error: {exc}")
            return
        self._voice_status.setText("listening...")

    def _stop_talk(self) -> None:
        """Stop capture and transcribe on a background thread.

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

        Returns
        -------
        None
            The prompt is queued for the worker.
        """
        prompt = prompt or self._input.toPlainText()
        prompt = prompt.strip()
        if not prompt:
            return
        if self._pending is not None:
            self._input.clear()
            self._answer_question(prompt)
            return
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
        user = label == "you"
        tool = label == "tool"
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self._log.document().isEmpty():
            cursor.insertBlock()
        start = cursor.position()
        doc = QTextDocument()
        doc.setMarkdown(text)
        cursor.insertFragment(QTextDocumentFragment(doc))
        end = cursor.position()
        self._apply_bubble(start, end, user, tool)
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
        fmt = QTextBlockFormat()
        fmt.setBackground(QColor(self._bubble_color(user, tool)))
        if tool:
            fmt.setAlignment(Qt.AlignLeft)
            fmt.setRightMargin(self._bubble_margin())
        else:
            fmt.setAlignment(Qt.AlignRight if user else Qt.AlignLeft)
            if user:
                fmt.setLeftMargin(self._bubble_margin())
            else:
                fmt.setRightMargin(self._bubble_margin())
        block = self._log.document().findBlock(start)
        first = QTextBlockFormat(fmt)
        first.setTopMargin(6)
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
        from .settings import Settings

        self._settings = settings or Settings()
        self._store = store
        self._root = root
        self._voice_on = voice_enabled()
        self._theme = ui_mode()
        self._record: SessionRecord | None = None
        self._command_panel = ChatPanel(
            self._make_agent(),
            show_tools=self._settings.get("show_tools"),
            settings=self._settings,
            voice_on=self._voice_on,
            theme=self._theme,
        )
        self._command_panel.posted.connect(self._on_posted)
        ideas_context = self._make_ideas_context
        self._ideas_panel = ChatPanel(
            self._make_agent(),
            title="Ideas",
            context=ideas_context,
            show_notes_toggle=True,
            show_tools=self._settings.get("show_tools"),
            settings=self._settings,
            voice_on=self._voice_on,
            theme=self._theme,
        )
        self._ideas_panel.posted.connect(self._on_posted)
        self._ideas_card = self._card(self._ideas_panel)
        self._ideas_card.hide()
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._build_header())
        layout.addLayout(self._build_toggle_bar())
        body = QSplitter(Qt.Horizontal, central)
        body.setHandleWidth(6)
        body.addWidget(self._build_sidebar())
        main = QSplitter(Qt.Horizontal, central)
        main.setHandleWidth(6)
        main.addWidget(self._card(self._command_panel))
        main.addWidget(self._ideas_card)
        body.addWidget(main)
        layout.addWidget(body)
        self.setCentralWidget(central)
        self.setWindowTitle("Minimal Harness")
        self.resize(1440, 640)
        self._refresh_sidebar()
        self._activate(self._store.list()[0])

    def _make_agent(self) -> Agent:
        """Build an agent for one panel.

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
        import json

        lines = []
        for line in path.read_text().splitlines()[-8:]:
            try:
                body = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = body.get("role")
            content = body.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                lines.append(role + ": " + content)
        return "\n".join(lines)

    def _build_sidebar(self) -> QWidget:
        """Build the sessions and builds sidebar.

        Returns
        -------
        QWidget
            Sidebar with two sections and new buttons.
        """
        sidebar = QWidget(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        box = QVBoxLayout(sidebar)
        box.addWidget(QLabel("<b>Sessions</b>", sidebar))
        self._session_list = QListWidget(sidebar)
        self._session_list.itemClicked.connect(self._select)
        self._session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._session_list.customContextMenuRequested.connect(
            self._menu_session
        )
        box.addWidget(self._session_list)
        session_button = QPushButton("+ New Session", sidebar)
        session_button.clicked.connect(self._new_session)
        box.addWidget(session_button)
        box.addSpacing(12)
        box.addWidget(QLabel("<b>Builds</b>", sidebar))
        self._build_list = QListWidget(sidebar)
        self._build_list.itemClicked.connect(self._select)
        self._build_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._build_list.customContextMenuRequested.connect(self._menu_build)
        box.addWidget(self._build_list)
        build_button = QPushButton("+ New Build", sidebar)
        build_button.clicked.connect(self._new_build)
        box.addWidget(build_button)
        return sidebar

    def _refresh_sidebar(self) -> None:
        """Repopulate the session and build lists.

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
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        chosen = menu.exec(listing.mapToGlobal(pos))
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
        import shutil

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

        Returns
        -------
        None
            A new session becomes active.
        """
        self._activate(self._store.create())

    def _new_build(self) -> None:
        """Create and activate a new build.

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
        target = (
            self._session_list
            if record.kind == "session"
            else self._build_list
        )
        for index in range(target.count()):
            item = target.item(index)
            if item.data(Qt.UserRole) == record.session_id:
                target.setCurrentItem(item)
                return

    def _touch_active(self) -> None:
        """Bump the active session timestamp.

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

        Returns
        -------
        None
            The session list reflects the update.
        """
        self._touch_active()

    def _build_toggle_bar(self) -> QHBoxLayout:
        """Build the settings and ideas toggle row.

        Returns
        -------
        QHBoxLayout
            Bar with checkboxes and the ideas button.
        """
        bar = QHBoxLayout()
        self._workspace_label = QLabel("", self)
        self._workspace_label.setObjectName("workspaceLabel")
        bar.addWidget(self._workspace_label)
        change = QPushButton("Change Folder", self)
        change.clicked.connect(self._choose_workspace)
        bar.addWidget(change)
        bar.addStretch(1)
        self._show_commands = QCheckBox("Show commands", self)
        self._show_commands.setChecked(self._settings.get("show_commands"))
        self._show_commands.toggled.connect(self._on_show_commands)
        bar.addWidget(self._show_commands)
        self._show_tools = QCheckBox("Show tool activity", self)
        self._show_tools.setChecked(self._settings.get("show_tools"))
        self._show_tools.toggled.connect(self._on_show_tools)
        bar.addWidget(self._show_tools)
        self._toggle = QPushButton("Open Ideas", self)
        self._toggle.clicked.connect(self.toggle_ideas)
        bar.addWidget(self._toggle)
        self._update_workspace_label()
        return bar

    def _update_workspace_label(self) -> None:
        """Show the active projects folder.

        Returns
        -------
        None
            The label text and tooltip are updated.
        """
        self._workspace_label.setText("Projects: " + str(self._root))
        self._workspace_label.setToolTip(str(self._root))

    def _choose_workspace(self) -> None:
        """Ask for a new projects folder and apply it.

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
        choice = QMessageBox.information(
            self,
            "Close",
            "Save this session?",
            buttons=QMessageBox.Save
            | QMessageBox.Discard
            | QMessageBox.Cancel,
            defaultButton=QMessageBox.Save,
        )
        if choice == QMessageBox.Discard:
            self._remove(self._record)
        elif choice != QMessageBox.Save:
            event.ignore()
            return
        self._command_panel.stop()
        self._ideas_panel.stop()
        event.accept()


def main() -> None:
    """Launch the desktop application.

    Returns
    -------
    None
        The application runs until the window closes.
    """
    load_env()
    app = QApplication(sys.argv)
    _apply_theme(app)
    if ui_mode() == "hal":
        _apply_hal_identity(app)
    store = SessionStore(Path("runs/sessions"))
    if not any(store.root.iterdir()):
        store.create(kind="session")
    from .settings import Settings

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
    from .hal import hal_icon, set_macos_dock_icon

    icon = hal_icon()
    app.setApplicationName("Minimal Harness")
    app.setApplicationDisplayName("Minimal Harness")
    app.setWindowIcon(icon)
    set_macos_dock_icon(icon)
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
        from AppKit import NSApplication
        from Foundation import NSProcessInfo
    except Exception:
        return
    NSProcessInfo.processInfo().setProcessName_(name)
    menu = NSApplication.sharedApplication().mainMenu()
    if menu is not None and menu.numberOfItems() > 0:
        menu.itemAtIndex_(0).setTitle_(name)


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
        from .hal import HalWindow

        return HalWindow(store, root, settings)
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
