"""Minimal HAL-style voice interface with a red eye and push-to-talk."""

import math
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtCore import QRectF
from PySide6.QtCore import QThread
from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtGui import QIcon
from PySide6.QtGui import QPainter
from PySide6.QtGui import QPen
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QRadialGradient
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget

from meta_harness.agent import Agent
from meta_harness.session import Session
from meta_harness.voice import VoiceEngine
from meta_harness.voice import missing_dependencies
from meta_harness.voice_text import match_option
from meta_harness.voice_text import speech_text

from .store import SessionStore
from .worker import AgentWorker
from .worker import QuestionBridge

_STATE_COLORS = {
    "idle": QColor(255, 40, 40),
    "listening": QColor(255, 0, 0),
    "thinking": QColor(255, 140, 0),
    "speaking": QColor(255, 60, 90),
    "answer": QColor(255, 200, 60),
    "error": QColor(255, 255, 255),
}

HAL_STYLE = """
QMainWindow, #HalRoot {
    background-color: #000000;
}
#HalButton {
    background-color: #140000;
    border: 2px solid #ff2222;
    border-radius: 66px;
}
#HalButton:hover {
    background-color: #2a0000;
}
#HalButton:pressed {
    background-color: #ff2222;
}
#HalButton:disabled {
    border-color: #421111;
}
"""


def hal_icon(size: int = 256) -> QIcon:
    """Draw the red-eye window and dock icon.

    Parameters
    ----------
    size : int
        Square icon size in pixels.

    Returns
    -------
    QIcon
        Rendered eye icon.
    """
    pixmap = _icon_pixmap(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    center = QPointF(size / 2, size / 2)
    base = _STATE_COLORS["idle"]
    _icon_eye(painter, center, size, base)
    painter.end()
    return QIcon(pixmap)


def _icon_pixmap(size: int) -> QPixmap:
    """Create a transparent square pixmap.

    Parameters
    ----------
    size : int
        Square side length in pixels.

    Returns
    -------
    QPixmap
        Transparent pixmap.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    return pixmap


def _icon_eye(painter, center, size, base) -> None:
    """Paint the icon halo and iris.

    Parameters
    ----------
    painter : QPainter
        Active painter.

    center : QPointF
        Eye center.

    size : float
        Icon size.

    base : QColor
        State color.

    Returns
    -------
    None
        The eye is painted.
    """
    _icon_glow(painter, center, size, base)
    _icon_iris(painter, center, size, base)


def _log_error(message: str) -> None:
    """Append an error to the HAL diagnostic log.

    Parameters
    ----------
    message : str
        Error text.

    Returns
    -------
    None
        The log is appended.
    """
    path = Path(os.getenv("HARNESS_HAL_LOG", "runs/hal-error.log"))
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def _icon_glow(
    painter: QPainter, center: QPointF, size: float, base: QColor
) -> None:
    """Paint the icon halo.

    Parameters
    ----------
    painter : QPainter
        Active painter.
    center : QPointF
        Icon center.
    size : float
        Icon size.
    base : QColor
        Eye color.

    Returns
    -------
    None
        The halo is painted.
    """
    radius = size * 0.48
    gradient = QRadialGradient(center, radius)
    _icon_glow_stops(gradient, base)
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(center, radius, radius)


def _icon_glow_stops(gradient: QRadialGradient, base: QColor) -> None:
    """Set the halo gradient stops.

    Parameters
    ----------
    gradient : QRadialGradient
        Halo gradient.
    base : QColor
        Eye color.

    Returns
    -------
    None
        Stops are configured.
    """
    glow = QColor(base)
    glow.setAlpha(90)
    gradient.setColorAt(0.0, glow)
    fade = QColor(base)
    fade.setAlpha(0)
    gradient.setColorAt(1.0, fade)


def _icon_iris(
    painter: QPainter, center: QPointF, size: float, base: QColor
) -> None:
    """Paint the icon lens and pupil.

    Parameters
    ----------
    painter : QPainter
        Active painter.
    center : QPointF
        Icon center.
    size : float
        Icon size.
    base : QColor
        Eye color.

    Returns
    -------
    None
        The lens is painted.
    """
    radius = size * 0.30
    gradient = QRadialGradient(center, radius)
    _icon_lens_stops(gradient, base)
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor(40, 0, 0), max(size * 0.01, 1.0)))
    painter.drawEllipse(center, radius, radius)
    _icon_pupil(painter, center, radius)


def _icon_lens_stops(gradient: QRadialGradient, base: QColor) -> None:
    """Set the lens gradient stops.

    Parameters
    ----------
    gradient : QRadialGradient
        Lens gradient.
    base : QColor
        Eye color.

    Returns
    -------
    None
        Stops are configured.
    """
    gradient.setColorAt(0.0, QColor(base).lighter(150))
    gradient.setColorAt(0.55, QColor(base))
    gradient.setColorAt(1.0, QColor(base).darker(240))


def _icon_pupil(painter: QPainter, center: QPointF, radius: float) -> None:
    """Paint the icon pupil and highlight.

    Parameters
    ----------
    painter : QPainter
        Active painter.
    center : QPointF
        Icon center.
    radius : float
        Lens radius.

    Returns
    -------
    None
        The pupil is painted.
    """
    pupil = radius * 0.42
    painter.setBrush(QColor(5, 0, 0))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(center, pupil, pupil)
    point = QPointF(center.x() - radius * 0.28, center.y() - radius * 0.30)
    painter.setBrush(QColor(255, 220, 220, 190))
    painter.drawEllipse(point, radius * 0.12, radius * 0.12)


class HalEye(QWidget):
    """Paint an animated red lens."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Prepare the eye animation.

        Parameters
        ----------
        parent : QWidget or None
            Optional parent widget.

        Returns
        -------
        None
            The animation timer starts.
        """
        super().__init__(parent)
        self._state = "idle"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.setMinimumSize(260, 260)

    def set_state(self, state: str) -> None:
        """Change the eye color state.

        Parameters
        ----------
        state : str
            One of the named eye states.

        Returns
        -------
        None
            The next repaint uses the new color.
        """
        self._state = state
        self.update()

    def _tick(self) -> None:
        """Advance the pulse animation.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The eye is repainted.
        """
        self._phase += 0.12
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        """Draw the glowing lens.

        Parameters
        ----------
        event : QPaintEvent
            Paint event.

        Returns
        -------
        None
            The widget is painted.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        size = min(self.width(), self.height())
        base = _STATE_COLORS.get(self._state, _STATE_COLORS["idle"])
        self._paint_glow(painter, center, size, base)
        self._paint_iris(painter, center, size, base)
        painter.end()

    def _paint_glow(
        self, painter: QPainter, center: QPointF, size: float, base: QColor
    ) -> None:
        """Paint the outer halo.

        Parameters
        ----------
        painter : QPainter
            Active painter.
        center : QPointF
            Eye center.
        size : float
            Widget size.
        base : QColor
            State color.

        Returns
        -------
        None
            The glow is painted.
        """
        pulse = 1.0 + 0.05 * math.sin(self._phase)
        radius = size * 0.42 * pulse
        painter.setBrush(_glow_gradient(center, radius, base))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)

    def _paint_iris(
        self, painter: QPainter, center: QPointF, size: float, base: QColor
    ) -> None:
        """Paint the lens, pupil, and highlight.

        Parameters
        ----------
        painter : QPainter
            Active painter.
        center : QPointF
            Eye center.
        size : float
            Widget size.
        base : QColor
            State color.

        Returns
        -------
        None
            The lens is painted.
        """
        radius = size * 0.22
        painter.setBrush(_iris_gradient(center, radius, base))
        painter.setPen(QPen(QColor(40, 0, 0), max(size * 0.008, 1.0)))
        painter.drawEllipse(center, radius, radius)
        self._paint_pupil(painter, center, radius)

    def _paint_pupil(
        self, painter: QPainter, center: QPointF, radius: float
    ) -> None:
        """Paint the pupil and specular highlight.

        Parameters
        ----------
        painter : QPainter
            Active painter.
        center : QPointF
            Eye center.
        radius : float
            Lens radius.

        Returns
        -------
        None
            The pupil is painted.
        """
        pupil = radius * 0.42
        painter.setBrush(QColor(5, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, pupil, pupil)
        point = QPointF(center.x() - radius * 0.28, center.y() - radius * 0.30)
        painter.setBrush(QColor(255, 220, 220, 190))
        painter.drawEllipse(point, radius * 0.12, radius * 0.12)


class HalButton(QPushButton):
    """Large round push-to-talk button with a drawn microphone."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the round button.

        Parameters
        ----------
        parent : QWidget or None
            Optional parent widget.

        Returns
        -------
        None
            The button is ready.
        """
        super().__init__("", parent)
        self.setObjectName("HalButton")
        self.setFixedSize(132, 132)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Draw the button background and microphone glyph.

        Parameters
        ----------
        event : QPaintEvent
            Paint event.

        Returns
        -------
        None
            The button is painted.
        """
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(255, 60, 60) if self.isEnabled() else QColor(92, 34, 34)
        painter.setPen(QPen(color, 5, Qt.SolidLine, Qt.RoundCap))
        center = QPointF(self.width() / 2, self.height() / 2)
        self._paint_mic(painter, center)
        painter.end()

    def _paint_mic(self, painter: QPainter, center: QPointF) -> None:
        """Paint a minimal microphone symbol.

        Parameters
        ----------
        painter : QPainter
            Active painter.
        center : QPointF
            Button center.

        Returns
        -------
        None
            The glyph is painted.
        """
        capsule = QRectF(center.x() - 9, center.y() - 28, 18, 36)
        painter.drawRoundedRect(capsule, 9, 9)
        arc = QRectF(center.x() - 20, center.y() - 12, 40, 36)
        painter.drawArc(arc, 180 * 16, 180 * 16)
        _paint_stem(painter, center)


class HalWindow(QMainWindow):
    """Eye-only voice interface with no text and a fixed size."""

    heard = Signal(str)

    def __init__(self, store: SessionStore, root: Path, settings=None) -> None:
        """Create the HAL window and its worker.

        Parameters
        ----------
        store : SessionStore
            Session backend (unused by this minimal window).
        root : pathlib.Path
            Project workspace root.
        settings : Settings or None
            Persisted interface settings.

        Returns
        -------
        None
            The window is ready to show.
        """
        super().__init__()
        self._store = store
        self._root = root
        self._settings = settings
        self._pending: QuestionBridge | None = None
        self._busy = False
        self._voice = _voice_engine()
        self._start_components()

    def _start_components(self) -> None:
        """Build the agent, worker thread, and window layout.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Components start running.
        """
        self._agent = _hal_agent(self._root)
        self._worker = AgentWorker(self._agent)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._connect_worker()
        self._build_ui()
        self._thread.start()

    def _connect_worker(self) -> None:
        """Connect worker signals to HAL handlers.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Signals are connected.
        """
        self._worker.started.connect(self._on_started)
        self._worker.answered.connect(self._on_answered)
        self._worker.asked.connect(self._on_asked)
        self._worker.error.connect(self._on_error)
        self.heard.connect(self._on_heard)

    def _build_ui(self) -> None:
        """Compose only the eye and the talk button.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Widgets are arranged in place.
        """
        central = _hal_central(self)
        self._eye = HalEye(central)
        self._button = HalButton(central)
        self._button.pressed.connect(self._start_talk)
        self._button.released.connect(self._stop_talk)
        _hal_layout(central, self._eye, self._button)
        self.setCentralWidget(central)
        self._style_window()

    def _style_window(self) -> None:
        """Apply the HAL stylesheet, icon, and fixed size.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Window chrome is configured.
        """
        self.setStyleSheet(HAL_STYLE)
        self.setWindowTitle("Minimal Harness")
        self.setWindowIcon(hal_icon())
        self.setFixedSize(520, 720)
        self._voice_setup()

    def _voice_setup(self) -> None:
        """Disable the button when voice dependencies are missing.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The eye reflects unavailability.
        """
        if self._voice is not None:
            return
        self._button.setEnabled(False)
        self._eye.set_state("error")
        self._button.setToolTip("pip install -e '.[voice]'")

    def _start_talk(self) -> None:
        """Begin push-to-talk capture.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Recording starts when possible.
        """
        if self._voice is None or self._busy:
            return
        if not self._begin_recording():
            return
        self._set_state("listening")

    def _begin_recording(self) -> bool:
        """Start recording, reporting any failure.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            True when recording started.
        """
        try:
            self._voice.stop_speaking()
            self._voice.start_recording()
        except Exception as exc:
            _log_error(f"recording: {exc}")
            self._set_state("error")
            return False
        return True

    def _stop_talk(self) -> None:
        """Stop capture and transcribe in the background.

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
        self._set_state("thinking")
        threading.Thread(target=self._hear, daemon=True).start()

    def _hear(self) -> None:
        """Transcribe the captured audio and emit it.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Recognized text is emitted.
        """
        try:
            text = self._voice.stop_recording()
        except Exception as exc:
            _log_error(f"transcription: {exc}")
            text = ""
        self.heard.emit(text)

    def _on_heard(self, text: str) -> None:
        """Dispatch a recognized utterance.

        Parameters
        ----------
        text : str
            Recognized speech.

        Returns
        -------
        None
            The utterance answers a question or starts a turn.
        """
        if not text.strip():
            self._handle_empty_heard()
            return
        if self._pending is not None:
            self._answer_pending(text)
            return
        self._send_prompt(text)

    def _handle_empty_heard(self) -> None:
        """Release a pending question when speech was not recognized.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The eye returns to idle and the worker is released.
        """
        self._resolve_pending()
        self._set_state("idle")

    def _answer_pending(self, text: str) -> None:
        """Resolve a pending agent question with spoken input.

        Parameters
        ----------
        text : str
            Recognized speech.

        Returns
        -------
        None
            The worker resumes with the matched answer.
        """
        bridge = self._pending
        self._pending = None
        answer = match_option(text, bridge.options)
        self._set_state("thinking")
        self._worker.resolve(bridge, answer)

    def _send_prompt(self, text: str) -> None:
        """Send a prompt to the worker.

        Parameters
        ----------
        text : str
            User prompt.

        Returns
        -------
        None
            The prompt is queued.
        """
        self._busy = True
        self._button.setEnabled(False)
        self._set_state("thinking")
        self._worker.prompt_ready.emit(text)

    def _on_started(self) -> None:
        """Reflect a running turn.

        Parameters
        ----------
        None

        Returns
        -------
        None
            State is updated.
        """
        self._busy = True
        self._button.setEnabled(False)
        self._set_state("thinking")

    def _on_answered(self, answer: str) -> None:
        """Speak the assistant answer.

        Parameters
        ----------
        answer : str
            Final assistant text.

        Returns
        -------
        None
            State and speech are updated.
        """
        self._busy = False
        self._button.setEnabled(self._voice is not None)
        self._set_state("speaking")
        self._speak(answer)
        QTimer.singleShot(1200, self._idle_after_speech)

    def _speak(self, text: str) -> None:
        """Queue speech and log playback failures.

        Parameters
        ----------
        text : str
            Text to speak.

        Returns
        -------
        None
            Speech is queued or the failure is logged.
        """
        if self._voice is None:
            return
        try:
            self._voice.speak(speech_text(text))
        except Exception as exc:
            _log_error(f"speech: {exc}")

    def _idle_after_speech(self) -> None:
        """Return to idle after a short speaking period.

        Parameters
        ----------
        None

        Returns
        -------
        None
            State becomes idle when still free.
        """
        if not self._busy and self._pending is None:
            self._set_state("idle")

    def _on_asked(
        self, question: str, options: list[str], bridge: QuestionBridge
    ) -> None:
        """Speak an agent question and listen for the answer.

        Parameters
        ----------
        question : str
            Question text.
        options : list[str]
            Suggested answers.
        bridge : QuestionBridge
            Pending question bridge.

        Returns
        -------
        None
            The button is enabled for the spoken answer.
        """
        self._busy = False
        self._pending = bridge
        self._button.setEnabled(self._voice is not None)
        self._set_state("answer")
        spoken = question + " Options: " + ", ".join(options)
        self._speak(spoken)
        self._arm_ask_timeout(bridge)

    def _arm_ask_timeout(self, bridge: QuestionBridge) -> None:
        """Return to idle when a spoken answer never arrives.

        Parameters
        ----------
        bridge : QuestionBridge
            Pending question.

        Returns
        -------
        None
            A timer is scheduled.
        """
        seconds = int(os.getenv("HARNESS_ASK_TIMEOUT", "45"))
        QTimer.singleShot(seconds * 1000, lambda: self._ask_timeout(bridge))

    def _ask_timeout(self, bridge: QuestionBridge) -> None:
        """Resolve an unanswered question and return to idle.

        Parameters
        ----------
        bridge : QuestionBridge
            Question that may still be pending.

        Returns
        -------
        None
            The worker is released when the question is still active.
        """
        if self._pending is not bridge:
            return
        self._resolve_pending()
        self._set_state("idle")

    def _on_error(self, message: str) -> None:
        """Display an error state.

        Parameters
        ----------
        message : str
            Error text.

        Returns
        -------
        None
            The eye reflects the error without text.
        """
        _log_error(message)
        self._busy = False
        self._pending = None
        self._button.setEnabled(self._voice is not None)
        self._set_state("error")
        QTimer.singleShot(2000, self._idle_after_speech)

    def _set_state(self, state: str) -> None:
        """Update the eye state.

        Parameters
        ----------
        state : str
            Eye state name.

        Returns
        -------
        None
            The eye is updated.
        """
        self._eye.set_state(state)

    def stop(self) -> None:
        """Release the worker, pending question, and speech.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Background work is shut down.
        """
        self._resolve_pending()
        if self._voice is not None:
            self._voice.stop_speaking()
        self._thread.quit()
        self._thread.wait(2000)

    def _resolve_pending(self) -> None:
        """Answer any pending question with no answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The worker is released.
        """
        if self._pending is None:
            return
        bridge = self._pending
        self._pending = None
        self._worker.resolve(bridge, "no answer")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Stop background work before closing.

        Parameters
        ----------
        event : QCloseEvent
            Close notification.

        Returns
        -------
        None
            The window closes cleanly.
        """
        self.stop()
        event.accept()


def _glow_gradient(center, radius, base):
    """Build the radial halo gradient.

    Parameters
    ----------
    center : QPointF
        Eye center.

    radius : float
        Halo radius.

    base : QColor
        State color.

    Returns
    -------
    QRadialGradient
        Gradient fading from the state color to transparent.
    """
    gradient = QRadialGradient(center, radius)
    gradient.setColorAt(0.0, _alpha_color(base, 90))
    gradient.setColorAt(1.0, _alpha_color(base, 0))
    return gradient


def _alpha_color(base, alpha):
    """Return a copy of a color with a new alpha value.

    Parameters
    ----------
    base : QColor
        Source color.

    alpha : int
        Alpha channel value.

    Returns
    -------
    QColor
        Color copy with the requested alpha.
    """
    color = QColor(base)
    color.setAlpha(alpha)
    return color


def _iris_gradient(center, radius, base):
    """Build the radial iris gradient.

    Parameters
    ----------
    center : QPointF
        Eye center.

    radius : float
        Iris radius.

    base : QColor
        State color.

    Returns
    -------
    QRadialGradient
        Gradient from the lightened color to the darkened color.
    """
    gradient = QRadialGradient(center, radius)
    gradient.setColorAt(0.0, QColor(base).lighter(150))
    gradient.setColorAt(0.55, QColor(base))
    gradient.setColorAt(1.0, QColor(base).darker(240))
    return gradient


def _paint_stem(painter, center) -> None:
    """Paint the microphone stand.

    Parameters
    ----------
    painter : QPainter
        Active painter.

    center : QPointF
        Button center.

    Returns
    -------
    None
        The stand is painted.
    """
    painter.drawLine(
        QPointF(center.x(), center.y() + 24),
        QPointF(center.x(), center.y() + 34),
    )
    painter.drawLine(
        QPointF(center.x() - 11, center.y() + 34),
        QPointF(center.x() + 11, center.y() + 34),
    )


def _voice_engine():
    """Create a voice engine when dependencies are available.

    Parameters
    ----------
    None

    Returns
    -------
    VoiceEngine or None
        Engine instance, or None when voice is unavailable.
    """
    if missing_dependencies():
        return None
    return VoiceEngine()


def _hal_agent(root: Path) -> Agent:
    """Build the HAL agent with the fixed session file.

    Parameters
    ----------
    root : pathlib.Path
        Project workspace root.

    Returns
    -------
    Agent
        Configured interactive agent.
    """
    agent = Agent(root=root, session=Session(Path("runs/hal-session.jsonl")))
    agent.tools.require_project_folder = True
    agent.trim_context(8)
    return agent


def _hal_central(parent) -> QWidget:
    """Create the HAL central widget.

    Parameters
    ----------
    parent : QMainWindow
        Owning window.

    Returns
    -------
    QWidget
        Central widget named ``HalRoot``.
    """
    central = QWidget(parent)
    central.setObjectName("HalRoot")
    return central


def _hal_layout(central, eye, button) -> None:
    """Arrange the eye and talk button in the central widget.

    Parameters
    ----------
    central : QWidget
        Central widget.

    eye : HalEye
        Eye widget.

    button : HalButton
        Talk button.

    Returns
    -------
    None
        The layout is installed.
    """
    layout = QVBoxLayout(central)
    layout.setContentsMargins(40, 40, 40, 48)
    layout.setSpacing(20)
    layout.addWidget(eye, 1)
    layout.addWidget(button, 0, Qt.AlignHCenter)
