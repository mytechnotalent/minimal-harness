"""Offline tests for provider selection and endpoint resolution."""

import os
import unittest
from unittest.mock import patch

from meta_harness.openrouter import OpenRouterClient, OpenRouterError

OPENCODE_URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"


class ProviderConfigTests(unittest.TestCase):
    """Verify OpenRouter and OpenCode Go configuration."""

    def test_defaults_to_openrouter(self) -> None:
        """No provider setting keeps OpenRouter defaults."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}, clear=True):
            client = OpenRouterClient()
            self.assertEqual(client.provider, "openrouter")
            self.assertEqual(client.api_key, "k")
            self.assertEqual(
                client._url(),
                "https://openrouter.ai/api/v1/chat/completions",
            )

    def test_opencode_go_defaults(self) -> None:
        """The opencode provider uses the Go endpoint and model."""
        env = {
            "HARNESS_PROVIDER": "opencode",
            "OPENCODE_API_KEY": "go-key",
            "OPENCODE_MODEL": "deepseek-v4.1-flash",
        }
        with patch.dict(os.environ, env, clear=True):
            client = OpenRouterClient()
            self.assertEqual(client.provider, "opencode")
            self.assertEqual(client.api_key, "go-key")
            self.assertEqual(client.model, "deepseek-v4.1-flash")
            self.assertEqual(client._url(), OPENCODE_URL)

    def test_opencode_base_url_is_completed(self) -> None:
        """A base URL ending in /v1 gains the chat path."""
        env = {
            "HARNESS_PROVIDER": "opencode",
            "OPENCODE_BASE_URL": "https://opencode.ai/zen/go/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                OpenRouterClient()._url(),
                "https://opencode.ai/zen/go/v1/chat/completions",
            )

    def test_opencode_key_fallback(self) -> None:
        """The alternate Go key variable is accepted."""
        env = {
            "HARNESS_PROVIDER": "opencode",
            "OPENCODE_GO_API_KEY": "alt-key",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(OpenRouterClient().api_key, "alt-key")

    def test_opencode_session_header(self) -> None:
        """OpenCode Go requires a stable session header."""
        env = {
            "HARNESS_PROVIDER": "opencode",
            "OPENCODE_API_KEY": "go-key",
        }
        with patch.dict(os.environ, env, clear=True):
            client = OpenRouterClient()
            headers = client._headers()
            self.assertEqual(headers["x-opencode-session"], client.session_id)
            self.assertIn("User-Agent", headers)

    def test_missing_opencode_key_message(self) -> None:
        """A missing Go key names the correct variable."""
        with patch.dict(
            os.environ, {"HARNESS_PROVIDER": "opencode"}, clear=True
        ):
            with self.assertRaises(OpenRouterError) as caught:
                OpenRouterClient().complete("system", "user")
            self.assertIn("OPENCODE_API_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
