"""Offline tests for provider selection and endpoint resolution."""

import os
import unittest
from unittest.mock import patch

from meta_harness.openrouter import OpenRouterClient
from meta_harness.openrouter import OpenRouterError

OPENCODE_URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"


class ProviderConfigTests(unittest.TestCase):
    """Verify OpenRouter, OpenCode Go, and local configuration."""

    def test_defaults_to_openrouter(self) -> None:
        """No provider setting keeps OpenRouter defaults.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "k"}, clear=True):
            client = OpenRouterClient()
            self.assertEqual(client.provider, "openrouter")
            self.assertEqual(client.api_key, "k")
            self.assertEqual(
                client._url(),
                "https://openrouter.ai/api/v1/chat/completions",
            )

    def test_opencode_go_defaults(self) -> None:
        """The opencode provider uses the Go endpoint and model.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = _client_with(_opencode_env())
        self._assert_opencode(client)

    def _assert_opencode(self, client) -> None:
        """Verify the Go provider, key, model, and URL.

        Parameters
        ----------
        client : OpenRouterClient
            Configured client.

        Returns
        -------
        None
            Assertions document the configuration.
        """
        self.assertEqual(client.provider, "opencode")
        self.assertEqual(client.api_key, "go-key")
        self.assertEqual(client.model, "deepseek-v4.1-flash")
        self.assertEqual(client._url(), OPENCODE_URL)

    def test_opencode_base_url_is_completed(self) -> None:
        """A base URL ending in /v1 gains the chat path.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {
            "HARNESS_PROVIDER": "opencode",
            "OPENCODE_BASE_URL": "https://opencode.ai/zen/go/v1",
        }
        self.assertEqual(
            _url_with(env), "https://opencode.ai/zen/go/v1/chat/completions"
        )

    def test_opencode_key_fallback(self) -> None:
        """The alternate Go key variable is accepted.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {
            "HARNESS_PROVIDER": "opencode",
            "OPENCODE_GO_API_KEY": "alt-key",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(OpenRouterClient().api_key, "alt-key")

    def test_opencode_session_header(self) -> None:
        """OpenCode Go requires a stable session header.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {
            "HARNESS_PROVIDER": "opencode",
            "OPENCODE_API_KEY": "go-key",
        }
        client = _client_with(env)
        headers = client._headers()
        self.assertEqual(headers["x-opencode-session"], client.session_id)
        self.assertIn("User-Agent", headers)

    def test_local_defaults(self) -> None:
        """Local models use Ollama defaults and a dummy key.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {"HARNESS_PROVIDER": "local", "LOCAL_MODEL": "qwen2.5-coder:7b"}
        client = _client_with(env)
        self._assert_local(client, "qwen2.5-coder:7b")

    def _assert_local(self, client, model: str) -> None:
        """Verify the local provider defaults.

        Parameters
        ----------
        client : OpenRouterClient
            Configured client.

        model : str
            Expected local model name.

        Returns
        -------
        None
            Assertions document the configuration.
        """
        self.assertEqual(client.provider, "local")
        self.assertEqual(client.model, model)
        self.assertEqual(client.api_key, "local")
        self.assertEqual(
            client._url(), "http://localhost:11434/v1/chat/completions"
        )
        self.assertIn("Authorization", client._headers())

    def test_local_base_url_without_path_is_completed(self) -> None:
        """A bare local base URL gains /v1/chat/completions.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {
            "HARNESS_PROVIDER": "ollama",
            "LOCAL_BASE_URL": "http://localhost:11434",
        }
        self.assertEqual(
            _url_with(env), "http://localhost:11434/v1/chat/completions"
        )

    def test_local_v1_base_url_is_completed(self) -> None:
        """A local /v1 base URL gains only the chat path.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {
            "HARNESS_PROVIDER": "lmstudio",
            "LOCAL_BASE_URL": "http://localhost:1234/v1",
        }
        self.assertEqual(
            _url_with(env), "http://localhost:1234/v1/chat/completions"
        )

    def test_local_custom_key_and_model_fallback(self) -> None:
        """The local key is configurable and HARNESS_MODEL is a fallback.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        env = {
            "HARNESS_PROVIDER": "vllm",
            "LOCAL_API_KEY": "secret",
            "HARNESS_MODEL": "local-coder",
        }
        client = _client_with(env)
        self.assertEqual(client.api_key, "secret")
        self.assertEqual(client.model, "local-coder")

    def test_missing_opencode_key_message(self) -> None:
        """A missing Go key names the correct variable.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(
            os.environ, {"HARNESS_PROVIDER": "opencode"}, clear=True
        ):
            with self.assertRaises(OpenRouterError) as caught:
                OpenRouterClient().complete("system", "user")
            self.assertIn("OPENCODE_API_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()


def _opencode_env() -> dict:
    """Build a minimal OpenCode Go environment.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Provider, key, and model settings.
    """
    return {
        "HARNESS_PROVIDER": "opencode",
        "OPENCODE_API_KEY": "go-key",
        "OPENCODE_MODEL": "deepseek-v4.1-flash",
    }


def _client_with(env: dict):
    """Build a client under one environment.

    Parameters
    ----------
    env : dict
        Environment overrides.

    Returns
    -------
    OpenRouterClient
        Configured client.
    """
    with patch.dict(os.environ, env, clear=True):
        return OpenRouterClient()


def _url_with(env: dict) -> str:
    """Return the resolved URL for one environment.

    Parameters
    ----------
    env : dict
        Environment overrides.

    Returns
    -------
    str
        Resolved chat-completions URL.
    """
    with patch.dict(os.environ, env, clear=True):
        return OpenRouterClient()._url()
