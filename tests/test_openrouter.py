"""Tests for OpenRouter request resilience."""

import io
import os
import threading
import unittest
import urllib.error
from unittest.mock import patch

from meta_harness.openrouter import (
    OpenRouterClient,
    OpenRouterError,
    _sanitize_messages,
)


class OpenRouterTests(unittest.TestCase):
    """Verify credential and transient-error handling."""

    def test_missing_key_is_reported(self) -> None:
        """Reject completion when no key is configured.

        Returns
        -------
        None
            Assertions pass when missing credentials are explicit.
        """
        client = OpenRouterClient()
        client.api_key = None
        with self.assertRaises(OpenRouterError):
            client.complete("system", "user")

    def test_rate_limit_retries_then_succeeds(self) -> None:
        """Retry a rate limit and return the later response.

        Returns
        -------
        None
            Assertions pass when retry behavior is bounded.
        """
        result, sleeper = self._retry_result()
        sleeper.assert_called_once()
        self.assertEqual(result, {"ok": True})

    def _retry_result(self):
        """Run a mocked retry sequence.

        Returns
        -------
        tuple[dict, Mock]
            Response and sleep mock.
        """
        client = OpenRouterClient()
        error = urllib.error.HTTPError(
            "https://openrouter.ai", 429, "busy", {}, io.BytesIO()
        )
        request = client._build_request("system", "user", 0.0)
        with patch.object(client, "_open", side_effect=[error, {"ok": True}]):
            with patch("meta_harness.openrouter.time.sleep") as sleeper:
                return client._retry_open(request), sleeper

    def test_timeout_retries_then_succeeds(self) -> None:
        """Retry a socket timeout and return the later response."""
        client = OpenRouterClient()
        request = client._build_request("system", "user", 0.0)
        with patch.object(
            client, "_open", side_effect=[TimeoutError("slow"), {"ok": True}]
        ):
            with patch("meta_harness.openrouter.time.sleep") as sleeper:
                result = client._retry_open(request)
        self.assertEqual(result, {"ok": True})
        sleeper.assert_called_once()

    def test_chat_records_usage(self) -> None:
        """Chat responses add their tokens to the usage counters."""
        client = OpenRouterClient()
        client.api_key = "test"
        body = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 4},
                "cost": 0.0005,
            },
        }
        with patch.object(client, "_send", return_value=body):
            client.chat([], [])
        self.assertEqual(client.call_count, 1)
        self.assertEqual(client.prompt_tokens, 10)
        self.assertEqual(client.completion_tokens, 2)
        self.assertEqual(client.cached_tokens, 4)
        self.assertAlmostEqual(client.cost, 0.0005)
        self.assertIn("cost=$0.000500", client.usage_summary())

    def test_chat_omits_empty_tools(self) -> None:
        """An empty tools list is omitted for strict providers."""
        client = OpenRouterClient()
        client.api_key = "test"
        body = {"choices": [{"message": {"content": "ok"}}]}
        with patch.object(client, "_build_payload_request") as build:
            with patch.object(client, "_send", return_value=body):
                client.chat([{"role": "user", "content": "hi"}], [])
        payload = build.call_args.args[0]
        self.assertNotIn("tools", payload)

    def test_sanitize_drops_provider_fields(self) -> None:
        """Provider-only fields and stale system messages are removed."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": None, "reasoning_content": "x"},
            {"role": "system", "content": "stale"},
            {"role": "user", "content": "hi"},
        ]
        clean = _sanitize_messages(messages)
        roles = [message["role"] for message in clean]
        self.assertEqual(roles, ["system", "assistant", "user"])
        self.assertNotIn("reasoning_content", clean[1])

    def test_sanitize_drops_orphan_tool_results(self) -> None:
        """A tool result without a pending call is removed."""
        messages = [
            {"role": "tool", "tool_call_id": "missing", "content": "x"},
            {"role": "user", "content": "hi"},
        ]
        clean = _sanitize_messages(messages)
        self.assertEqual([message["role"] for message in clean], ["user"])

    def test_model_timeout_is_configurable(self) -> None:
        """The model timeout can be raised from the environment."""
        with patch.dict(os.environ, {"HARNESS_MODEL_TIMEOUT": "240"}):
            self.assertEqual(OpenRouterClient().timeout, 240)

    def test_send_runs_off_the_main_thread(self) -> None:
        """A worker thread can send without installing a signal handler.

        Returns
        -------
        None
            Assertions pass when the threaded send returns its body.
        """
        client = OpenRouterClient()
        request = client._build_request("system", "user", 0.0)
        outcome: dict = {}
        with patch.object(client, "_open", return_value={"ok": True}):
            worker = threading.Thread(
                target=lambda: outcome.update(value=client._send(request))
            )
            worker.start()
            worker.join()
        self.assertEqual(outcome.get("value"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
