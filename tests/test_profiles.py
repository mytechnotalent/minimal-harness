"""Tests for per-model runtime profiles."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from meta_harness.cli import _configure_client
from meta_harness.profiles import effective_turns
from meta_harness.profiles import profile_for


class ProfileTests(unittest.TestCase):
    """Verify model profile selection and client configuration."""

    def test_known_model_profile(self) -> None:
        """Beam-free gets a shorter turn budget and more retries.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        profile = profile_for("beam-free")
        self.assertEqual(profile.max_turns, 12)
        self.assertEqual(profile.retries, 4)

    def test_provider_prefix_is_ignored(self) -> None:
        """A provider prefix does not hide the model profile.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(profile_for("opencode/beam-free").max_turns, 12)

    def test_unknown_model_uses_default(self) -> None:
        """Unknown models keep the default turn budget.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(profile_for("unknown").max_turns, 24)

    def test_explicit_turns_override_profile(self) -> None:
        """A command-line turn value wins over the profile.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(effective_turns("beam-free", 7), 7)
        self.assertEqual(effective_turns("beam-free", None), 12)

    def test_client_uses_profile_timeout(self) -> None:
        """The client inherits the profile timeout and retries.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = SimpleNamespace(model="beam-free", timeout=0, max_retries=0)
        with patch.dict(os.environ, {}, clear=True):
            configured = _configure_client(client)
        self.assertEqual(configured.timeout, 180)
        self.assertEqual(configured.max_retries, 4)
