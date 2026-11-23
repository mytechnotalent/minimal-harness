"""Offline tests for voice text helpers and UI mode selection."""

import os
import unittest
from unittest.mock import patch

from meta_harness.app_mode import ui_mode
from meta_harness.app_mode import voice_enabled
from meta_harness.voice import Speaker
from meta_harness.voice import Transcriber
from meta_harness.voice_text import match_option
from meta_harness.voice_text import speech_text


class SpeechTextTests(unittest.TestCase):
    """Verify markdown is reduced to speakable text."""

    def test_strips_code_fences(self) -> None:
        """Fenced code is replaced rather than read aloud.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(
            speech_text("Use `x` here:\n```py\nprint(1)\n```"),
            "Use x here: Code block omitted.",
        )

    def test_strips_markdown_markup(self) -> None:
        """Headers and emphasis markers are removed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(speech_text("## Title\n\n**bold**"), "Title bold")


class MatchOptionTests(unittest.TestCase):
    """Verify spoken replies resolve to suggested options."""

    def test_exact_match(self) -> None:
        """An exact spoken option wins.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(match_option("Yes", ["Yes", "No"]), "Yes")

    def test_digit_match(self) -> None:
        """A digit selects the numbered option.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(match_option("2", ["Yes", "No"]), "No")

    def test_number_word_match(self) -> None:
        """A spoken number word selects the numbered option.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(match_option("two", ["Yes", "No"]), "No")

    def test_free_text_falls_through(self) -> None:
        """Unmatched speech is returned verbatim.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        said = "maybe later"
        self.assertEqual(match_option(said, ["Yes", "No"]), said)

    def test_empty_speech(self) -> None:
        """Silence resolves to the no-answer sentinel.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(match_option("   ", ["Yes"]), "no answer")


class SpeakerVoiceTests(unittest.TestCase):
    """Verify the default speech voice."""

    def test_default_voice_is_female(self) -> None:
        """The built-in default is a female en-US voice.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Speaker().voice, "en-US-AriaNeural")

    def test_voice_override(self) -> None:
        """An explicit voice name wins over the default.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                Speaker("en-GB-SoniaNeural").voice, "en-GB-SoniaNeural"
            )


class TranscriberConfigTests(unittest.TestCase):
    """Verify Whisper downloads are authenticated or offline."""

    def test_no_token_forces_local_only(self) -> None:
        """Without a token no Hub request is allowed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {}, clear=True):
            transcriber = Transcriber("base.en")
            self.assertIsNone(transcriber.token)
            self.assertTrue(transcriber.local_only)

    def test_token_enables_authenticated_download(self) -> None:
        """A token allows authenticated Hub downloads.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {"HARNESS_HF_TOKEN": "hf_x"}
        with patch.dict(os.environ, env, clear=True):
            transcriber = Transcriber("base.en")
            self.assertEqual(transcriber.token, "hf_x")
            self.assertFalse(transcriber.local_only)

    def test_explicit_local_only_wins(self) -> None:
        """The offline flag overrides token-based downloads.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {
            "HARNESS_HF_TOKEN": "hf_x",
            "HARNESS_WHISPER_LOCAL_ONLY": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(Transcriber("base.en").local_only)


class UiModeTests(unittest.TestCase):
    """Verify the cyber mode is opt-in."""

    def test_defaults_to_classic(self) -> None:
        """No setting keeps the classic interface.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ui_mode(), "classic")
            self.assertFalse(voice_enabled())

    def test_cyber_opt_in(self) -> None:
        """The cyber setting enables voice mode.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {"HARNESS_UI_MODE": "cyber"}):
            self.assertEqual(ui_mode(), "cyber")
            self.assertTrue(voice_enabled())

    def test_hal_opt_in(self) -> None:
        """The HAL setting enables the minimal voice mode.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {"HARNESS_UI_MODE": "hal"}):
            self.assertEqual(ui_mode(), "hal")
            self.assertTrue(voice_enabled())

    def test_unknown_value_stays_classic(self) -> None:
        """Unknown values fall back to the classic interface.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {"HARNESS_UI_MODE": "spaceship"}):
            self.assertEqual(ui_mode(), "classic")


if __name__ == "__main__":
    unittest.main()
