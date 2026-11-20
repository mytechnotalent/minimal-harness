"""Tests for local voice transcription serialization."""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from meta_harness.voice import Transcriber


class FakeSegment:
    """Provide one fake transcription segment."""

    text = " hello "


class FakeModel:
    """Record the peak number of concurrent transcriptions."""

    def __init__(self) -> None:
        """Initialize the counters.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Counters are ready.
        """
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def transcribe(self, audio, language=None, vad_filter=False):
        """Run one slow fake transcription.

        Parameters
        ----------
        audio : object
            Ignored audio samples.
        language : str or None
            Ignored language.
        vad_filter : bool
            Ignored voice-activity flag.

        Returns
        -------
        tuple
            Fake segments and info.
        """
        self._enter()
        time.sleep(0.05)
        self._leave()
        return [FakeSegment()], None

    def _enter(self) -> None:
        """Record an active call.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The active count and peak are updated.
        """
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)

    def _leave(self) -> None:
        """Record a finished call.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The active count is decremented.
        """
        with self._lock:
            self._active -= 1


class TranscriberLockTests(unittest.TestCase):
    """Verify only one transcription runs at a time."""

    def test_transcribe_calls_are_serialized(self) -> None:
        """Concurrent calls never overlap inside the model.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when the peak concurrency is one.
        """
        transcriber = Transcriber()
        model = FakeModel()
        transcriber._model = model
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(transcriber.transcribe, [[0.0]] * 4))
        self.assertEqual(model.peak, 1)
