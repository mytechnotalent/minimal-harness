"""Cross-platform speech capture and playback for the desktop shell.

Heavy audio and machine-learning libraries are imported lazily so the
module can be imported, inspected, and unit tested without them.
"""

import asyncio
import os
import queue
import tempfile
import threading
from pathlib import Path
from typing import Any

_DEPENDENCIES = (
    "numpy",
    "sounddevice",
    "faster_whisper",
    "edge_tts",
    "miniaudio",
)


class VoiceUnavailable(RuntimeError):
    """Raised when voice dependencies or models are unavailable."""


def _hf_token() -> str | None:
    """Return a Hugging Face token from the environment.

    Returns
    -------
    str or None
        Configured token, if any.
    """
    for name in ("HARNESS_HF_TOKEN", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        value = os.getenv(name)
        if value:
            return value
    return None


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment flag.

    Parameters
    ----------
    name : str
        Variable name.
    default : bool
        Value when the variable is unset.

    Returns
    -------
    bool
        Parsed flag value.
    """
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def missing_dependencies() -> list[str]:
    """Return optional voice modules that cannot be imported.

    Returns
    -------
    list[str]
        Import names that are missing from the environment.
    """
    return [name for name in _DEPENDENCIES if not _installed(name)]


def _installed(name: str) -> bool:
    """Return whether a module can be imported.

    Parameters
    ----------
    name : str
        Import name.

    Returns
    -------
    bool
        Whether the import succeeds.
    """
    try:
        __import__(name)
    except Exception:
        return False
    return True


class Recorder:
    """Capture mono float32 audio from the default microphone."""

    rate = 16000

    def __init__(self) -> None:
        """Prepare a stopped recorder.

        Returns
        -------
        None
            The recorder holds no active stream.
        """
        self._stream: Any = None
        self._frames: list = []
        self._lock = threading.Lock()

    def start(self) -> None:
        """Open the microphone and begin buffering frames.

        Returns
        -------
        None
            The stream starts delivering audio callbacks.
        """
        import sounddevice as sd

        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self.rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(
        self, indata: Any, frames: int, time_info: Any, status: Any
    ) -> None:
        """Buffer one block of captured microphone samples.

        Parameters
        ----------
        indata : numpy.ndarray
            Captured audio block.
        frames : int
            Number of frames in the block.
        time_info : Any
            PortAudio timing information.
        status : Any
            PortAudio stream status flags.

        Returns
        -------
        None
            The block is copied into the buffer.
        """
        with self._lock:
            self._frames.append(indata.copy())

    def stop(self) -> Any:
        """Stop capturing and return the recorded samples.

        Returns
        -------
        numpy.ndarray
            Mono float32 samples at ``rate`` hertz.
        """
        self._close_stream()
        return self._join(self._take_frames())

    def _close_stream(self) -> None:
        """Stop and close the active input stream.

        Returns
        -------
        None
            The stream is released.
        """
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()

    def _take_frames(self) -> list:
        """Clear and return buffered audio blocks.

        Returns
        -------
        list
            Buffered audio blocks.
        """
        with self._lock:
            frames, self._frames = self._frames, []
        return frames

    @staticmethod
    def _join(frames: list) -> Any:
        """Concatenate buffered blocks into one sample array.

        Parameters
        ----------
        frames : list
            Buffered audio blocks.

        Returns
        -------
        numpy.ndarray
            Flat mono sample array.
        """
        import numpy as np

        if not frames:
            return np.zeros(0, dtype="float32")
        return np.concatenate(frames, axis=0).reshape(-1)


class Transcriber:
    """Transcribe recorded audio with a local faster-whisper model."""

    def __init__(self, model_size: str | None = None) -> None:
        """Store the model choice without loading it yet.

        Parameters
        ----------
        model_size : str or None
            Whisper model name, or ``HARNESS_WHISPER_MODEL``.

        Returns
        -------
        None
            The model loads on first use.
        """
        self.model_size = model_size or os.getenv(
            "HARNESS_WHISPER_MODEL", "base.en"
        )
        self.token = _hf_token()
        self.local_only = _env_flag(
            "HARNESS_WHISPER_LOCAL_ONLY", not bool(self.token)
        )
        self.cache_dir = os.getenv("HARNESS_WHISPER_CACHE")
        self._model: Any = None

    def transcribe(self, audio: Any) -> str:
        """Transcribe one mono float32 sample array.

        Parameters
        ----------
        audio : numpy.ndarray
            Mono float32 samples at 16 kHz.

        Returns
        -------
        str
            Recognized text, or an empty string.
        """
        segments, _ = self._load().transcribe(
            audio, language="en", vad_filter=True
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _load(self) -> Any:
        """Load and cache the faster-whisper model.

        Returns
        -------
        faster_whisper.WhisperModel
            Cached model instance.
        """
        if self._model is None:
            from faster_whisper import WhisperModel

            try:
                self._model = WhisperModel(self.model_size, **self._options())
            except Exception as exc:
                raise VoiceUnavailable(self._hint(exc)) from exc
        return self._model

    def _options(self) -> dict[str, Any]:
        """Return authenticated, offline-aware model options.

        Returns
        -------
        dict[str, Any]
            Keyword arguments for ``WhisperModel``.
        """
        return {
            "device": "cpu",
            "compute_type": "int8",
            "download_root": self.cache_dir,
            "local_files_only": self.local_only,
            "use_auth_token": self.token,
        }

    def _hint(self, exc: Exception) -> str:
        """Build a readable model-loading error.

        Parameters
        ----------
        exc : Exception
            Original loading failure.

        Returns
        -------
        str
            Error text with a remediation hint.
        """
        if self.local_only:
            return (
                f"{exc}. Whisper model '{self.model_size}' is not cached; "
                "set HARNESS_HF_TOKEN to download it with authentication."
            )
        return str(exc)


class Speaker:
    """Speak text with an online neural voice and local playback."""

    def __init__(self, voice: str | None = None) -> None:
        """Configure the voice and a background speech queue.

        Parameters
        ----------
        voice : str or None
            edge-tts voice name, or ``HARNESS_VOICE``.

        Returns
        -------
        None
            The worker starts on the first utterance.
        """
        self.voice = voice or os.getenv("HARNESS_VOICE", "en-US-AriaNeural")
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    def speak(self, text: str) -> None:
        """Queue text for background speech.

        Parameters
        ----------
        text : str
            Plain text to speak.

        Returns
        -------
        None
            The text is queued when nonempty.
        """
        if text.strip():
            self._start_worker()
            self._queue.put(text.strip())

    def stop(self) -> None:
        """Stop pending and active speech.

        Returns
        -------
        None
            The queue is drained and playback halts.
        """
        self._drain()
        self._halt()

    def _start_worker(self) -> None:
        """Start the speech worker thread when it is not running.

        Returns
        -------
        None
            A daemon worker is running.
        """
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def _work(self) -> None:
        """Process queued utterances forever.

        Returns
        -------
        None
            The daemon worker blocks awaiting speech.
        """
        while True:
            self._guard_say(self._queue.get())

    def _guard_say(self, text: str) -> None:
        """Speak one utterance without killing the worker.

        Parameters
        ----------
        text : str
            Plain text to speak.

        Returns
        -------
        None
            Failures are swallowed for the next utterance.
        """
        try:
            self._say(text)
        except Exception:
            return

    def _say(self, text: str) -> None:
        """Synthesize and play one utterance.

        Parameters
        ----------
        text : str
            Plain text to speak.

        Returns
        -------
        None
            Playback runs to completion or failure.
        """
        if not text:
            return
        path = self._synthesize(text)
        try:
            self._play(path)
        finally:
            path.unlink(missing_ok=True)

    def _synthesize(self, text: str) -> Path:
        """Render text to a temporary MP3 file.

        Parameters
        ----------
        text : str
            Plain text to speak.

        Returns
        -------
        pathlib.Path
            Temporary MP3 path.
        """
        path = self._temp_path()
        try:
            self._render(text, path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path

    @staticmethod
    def _temp_path() -> Path:
        """Create a temporary MP3 path.

        Returns
        -------
        pathlib.Path
            Writable temporary file path.
        """
        handle = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        handle.close()
        return Path(handle.name)

    def _render(self, text: str, path: Path) -> None:
        """Render text into a temporary MP3 file.

        Parameters
        ----------
        text : str
            Plain text to speak.
        path : pathlib.Path
            Output file path.

        Returns
        -------
        None
            The file is written.
        """
        asyncio.run(_save_speech(text, self.voice, path))

    def _play(self, path: Path) -> None:
        """Decode and play an MP3 file on the default speaker.

        Parameters
        ----------
        path : pathlib.Path
            MP3 file to play.

        Returns
        -------
        None
            Playback blocks until the file finishes.
        """
        import sounddevice as sd

        samples, rate = _decode_mp3(path)
        sd.play(samples, rate)
        sd.wait()

    def _drain(self) -> None:
        """Discard all queued utterances.

        Returns
        -------
        None
            The queue is empty.
        """
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            return

    def _halt(self) -> None:
        """Stop the audio device if it is available.

        Returns
        -------
        None
            Active playback is cancelled.
        """
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            return


async def _save_speech(text: str, voice: str, path: Path) -> None:
    """Render text to an MP3 file with edge-tts.

    Parameters
    ----------
    text : str
        Plain text to speak.
    voice : str
        edge-tts voice name.
    path : pathlib.Path
        Output file path.

    Returns
    -------
    None
        The MP3 file is written.
    """
    import edge_tts

    await edge_tts.Communicate(text, voice).save(str(path))


def _decode_mp3(path: Path) -> tuple[Any, int]:
    """Decode an MP3 file into signed 16-bit samples.

    Parameters
    ----------
    path : pathlib.Path
        MP3 file to decode.

    Returns
    -------
    tuple[numpy.ndarray, int]
        Sample array and sample rate.
    """
    import miniaudio
    import numpy as np

    decoded = miniaudio.decode_file(str(path))
    samples = np.array(decoded.samples, dtype=np.int16)
    if decoded.nchannels > 1:
        samples = samples.reshape(-1, decoded.nchannels)
    return samples, decoded.sample_rate


class VoiceEngine:
    """Coordinate recording, transcription, and speech output."""

    def __init__(self, model_size: str | None = None) -> None:
        """Create the capture, transcription, and speech components.

        Parameters
        ----------
        model_size : str or None
            Whisper model name, or ``HARNESS_WHISPER_MODEL``.

        Returns
        -------
        None
            The engine is ready to use.
        """
        self.recorder = Recorder()
        self.transcriber = Transcriber(model_size)
        self.speaker = Speaker()
        self._recording = False

    @property
    def recording(self) -> bool:
        """Return whether the microphone is currently recording.

        Returns
        -------
        bool
            Current recording state.
        """
        return self._recording

    def start_recording(self) -> None:
        """Begin capturing microphone audio.

        Returns
        -------
        None
            Recording starts.
        """
        self.recorder.start()
        self._recording = True

    def stop_recording(self) -> str:
        """Stop capturing and transcribe the utterance.

        Returns
        -------
        str
            Recognized text, or an empty string when too short.
        """
        audio = self.recorder.stop()
        self._recording = False
        if len(audio) < self.recorder.rate // 2:
            return ""
        return self.transcriber.transcribe(audio)

    def speak(self, text: str) -> None:
        """Queue text for speech.

        Parameters
        ----------
        text : str
            Plain text to speak.

        Returns
        -------
        None
            Speech is queued.
        """
        self.speaker.speak(text)

    def stop_speaking(self) -> None:
        """Stop active and pending speech.

        Returns
        -------
        None
            Speech output is cancelled.
        """
        self.speaker.stop()
