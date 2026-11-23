"""Offline tests for the Anthropic Messages provider."""

import os
import unittest
from unittest.mock import patch

from meta_harness.openrouter import OpenRouterClient
from meta_harness.openrouter import OpenRouterError
from meta_harness.openrouter import _anthropic_turns

ANTHROPIC_ENV = {
    "HARNESS_PROVIDER": "anthropic",
    "ANTHROPIC_API_KEY": "test-key",
    "ANTHROPIC_MODEL": "claude-test",
}


class AnthropicProviderTests(unittest.TestCase):
    """Verify Anthropic provider configuration and translation."""

    def test_provider_resolution(self) -> None:
        """The anthropic provider configures keys, headers, and URL.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, ANTHROPIC_ENV):
            client = OpenRouterClient()
        self.assertEqual(client.provider, "anthropic")
        self.assertEqual(client.model, "claude-test")
        self.assertEqual(client._headers()["x-api-key"], "test-key")
        self.assertIn("anthropic-version", client._headers())
        self.assertTrue(client._url().endswith("/v1/messages"))

    def test_missing_key_is_reported(self) -> None:
        """Anthropic requires ANTHROPIC_API_KEY.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The error names the missing variable.
        """
        with patch.dict(os.environ, {"HARNESS_PROVIDER": "anthropic"}):
            client = OpenRouterClient()
        client.api_key = None
        with self.assertRaises(OpenRouterError):
            client.complete("system", "user")

    def test_complete_returns_text_and_usage(self) -> None:
        """A text completion maps Anthropic usage counters.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Text and token counts match the canned response.
        """
        with patch.dict(os.environ, ANTHROPIC_ENV):
            client = OpenRouterClient()
            with patch.object(client, "_send", return_value=_text_body()):
                text = client.complete("system", "user")
        self.assertEqual(text, "hello there")
        self.assertEqual(client.prompt_tokens, 7)
        self.assertEqual(client.completion_tokens, 3)

    def test_chat_maps_tool_calls(self) -> None:
        """A tool-use response maps to OpenAI-shaped tool calls.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The mapped call carries name and JSON arguments.
        """
        with patch.dict(os.environ, ANTHROPIC_ENV):
            client = OpenRouterClient()
            with patch.object(client, "_send", return_value=_tool_body()):
                body = client.chat([], [])
        message = body["choices"][0]["message"]
        call = message["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "get_weather")
        self.assertIn('"city": "SF"', call["function"]["arguments"])

    def test_turns_translation(self) -> None:
        """OpenAI messages translate to Anthropic turns and system.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Tool use and tool results become content blocks.
        """
        system, turns = _anthropic_turns(_conversation())
        self.assertEqual(system, "be brief")
        self.assertEqual(turns[0]["role"], "user")
        self.assertEqual(turns[1]["content"][0]["type"], "tool_use")
        self.assertEqual(turns[2]["content"][0]["type"], "tool_result")


def _text_body() -> dict:
    """Return a canned Anthropic text response.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Text response with usage.
    """
    return {
        "content": [{"type": "text", "text": "hello there"}],
        "usage": {"input_tokens": 7, "output_tokens": 3},
    }


def _tool_body() -> dict:
    """Return a canned Anthropic tool-use response.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Tool-use response with usage.
    """
    block = {
        "type": "tool_use",
        "id": "call-1",
        "name": "get_weather",
        "input": {"city": "SF"},
    }
    usage = {"input_tokens": 5, "output_tokens": 4}
    return {"content": [block], "usage": usage}


def _assistant_tool_call() -> dict:
    """Return an OpenAI-shaped assistant tool-call message.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Assistant message with one tool call.
    """
    call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "get_weather", "arguments": '{"city": "SF"}'},
    }
    return {"role": "assistant", "content": "", "tool_calls": [call]}


def _conversation() -> list:
    """Return a mixed OpenAI-shaped conversation.

    Parameters
    ----------
    None

    Returns
    -------
    list
        System, user, tool-call, and tool-result messages.
    """
    return [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "weather in SF"},
        _assistant_tool_call(),
        _tool_result(),
    ]


def _tool_result() -> dict:
    """Return an OpenAI-shaped tool result message.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Tool message with a result.
    """
    return {"role": "tool", "tool_call_id": "call-1", "content": "sunny"}


if __name__ == "__main__":
    unittest.main()
