"""Tests for OpenRouter request resilience."""

import io
import os
import tempfile
import threading
import unittest
from pathlib import Path
import urllib.error
from unittest.mock import patch

from meta_harness.openrouter import OpenRouterClient
from meta_harness.openrouter import OpenRouterError
from meta_harness.openrouter import _sanitize_messages


def _http_error(code: int, body: bytes = b"") -> urllib.error.HTTPError:
    """Build an HTTP error with an optional body.

    Parameters
    ----------
    code : int
        HTTP status code.
    body : bytes
        Response body.

    Returns
    -------
    urllib.error.HTTPError
        Error response.
    """
    return urllib.error.HTTPError("https://x", code, "x", {}, io.BytesIO(body))


class OpenRouterTests(unittest.TestCase):
    """Verify credential and transient-error handling."""

    def test_missing_key_is_reported(self) -> None:
        """Reject completion when no key is configured.

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

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

        Parameters
        ----------
        None

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
        """Retry a socket timeout and return the later response.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = OpenRouterClient()
        request = client._build_request("system", "user", 0.0)
        result, sleeper = _retry_with(client, request, TimeoutError("slow"))
        self.assertEqual(result, {"ok": True})
        sleeper.assert_called_once()

    def test_chat_records_usage(self) -> None:
        """Chat responses add their tokens to the usage counters.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = OpenRouterClient()
        client.api_key = "test"
        with patch.object(client, "_send", return_value=_usage_body()):
            client.chat([], [])
        self._assert_usage(client)

    def _assert_usage(self, client) -> None:
        """Verify usage counters from a canned response.

        Parameters
        ----------
        client : OpenRouterClient
            Client with recorded usage.

        Returns
        -------
        None
            Assertions document the counters.
        """
        self.assertEqual(client.call_count, 1)
        self.assertEqual(client.prompt_tokens, 10)
        self.assertEqual(client.completion_tokens, 2)
        self.assertEqual(client.cached_tokens, 4)
        self.assertAlmostEqual(client.cost, 0.0005)
        self.assertIn("cost=$0.000500", client.usage_summary())

    def test_chat_omits_empty_tools(self) -> None:
        """An empty tools list is omitted for strict providers.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = OpenRouterClient()
        client.api_key = "test"
        body = {"choices": [{"message": {"content": "ok"}}]}
        with patch.object(client, "_build_payload_request") as build:
            with patch.object(client, "_send", return_value=body):
                client.chat([{"role": "user", "content": "hi"}], [])
        payload = build.call_args.args[0]
        self.assertNotIn("tools", payload)

    def test_sanitize_drops_provider_fields(self) -> None:
        """Provider-only fields and stale system messages are removed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        messages = _provider_messages()
        clean = _sanitize_messages(messages)
        roles = [message["role"] for message in clean]
        self.assertEqual(roles, ["system", "assistant", "user"])
        self.assertNotIn("reasoning_content", clean[1])

    def test_sanitize_drops_orphan_tool_results(self) -> None:
        """A tool result without a pending call is removed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        messages = [
            {"role": "tool", "tool_call_id": "missing", "content": "x"},
            {"role": "user", "content": "hi"},
        ]
        clean = _sanitize_messages(messages)
        self.assertEqual([message["role"] for message in clean], ["user"])

    def test_retryable_status_codes(self) -> None:
        """Transient status codes retry while bad requests do not.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = OpenRouterClient()
        for code in (408, 409, 425, 429, 500):
            error = urllib.error.HTTPError(
                "https://x", code, "x", {}, io.BytesIO()
            )
            self.assertTrue(client._retryable(error))
        error = urllib.error.HTTPError("https://x", 400, "x", {}, io.BytesIO())
        self.assertFalse(client._retryable(error))

    def test_http_error_includes_body(self) -> None:
        """Provider error details are preserved in the client error.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        error = _http_error(400, b'{"error":"tools empty"}')
        message = str(OpenRouterClient()._request_error(error))
        self.assertIn("tools empty", message)

    def test_record_usage_writes_log(self) -> None:
        """HARNESS_USAGE_LOG records usage as JSON lines.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = OpenRouterClient()
        body = {"usage": {"prompt_tokens": 3, "completion_tokens": 1}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            with patch.dict(os.environ, {"HARNESS_USAGE_LOG": str(path)}):
                client._record_usage(body)
            text = path.read_text()
        self.assertIn('"prompt_tokens": 3', text)

    def test_model_timeout_is_configurable(self) -> None:
        """The model timeout can be raised from the environment.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, {"HARNESS_MODEL_TIMEOUT": "240"}):
            self.assertEqual(OpenRouterClient().timeout, 240)

    def test_send_runs_off_the_main_thread(self) -> None:
        """A worker thread can send without installing a signal handler.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when the threaded send returns its body.
        """
        client = OpenRouterClient()
        request = client._build_request("system", "user", 0.0)
        outcome = _threaded_send(client, request)
        self.assertEqual(outcome.get("value"), {"ok": True})


if __name__ == "__main__":
    unittest.main()


def _retry_with(client, request, first):
    """Retry a request with one failure then success.

    Parameters
    ----------
    client : OpenRouterClient
        Client under test.

    request : urllib.request.Request
        Request to retry.

    first : Exception
        Exception raised by the first attempt.

    Returns
    -------
    tuple
        Retry result and the sleep mock.
    """
    with patch.object(client, "_open", side_effect=[first, {"ok": True}]):
        with patch("meta_harness.openrouter.time.sleep") as sleeper:
            return client._retry_open(request), sleeper


def _usage_body() -> dict:
    """Build a canned response carrying usage details.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        OpenAI-compatible response body.
    """
    return {
        "choices": [{"message": {"content": "ok"}}],
        "usage": _usage_counters(),
    }


def _usage_counters() -> dict:
    """Build the usage counters for a canned response.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Token and cost counters.
    """
    return {
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "prompt_tokens_details": {"cached_tokens": 4},
        "cost": 0.0005,
    }


def _provider_messages() -> list[dict]:
    """Build messages containing provider-only and stale entries.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Mixed conversation messages.
    """
    return [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": None, "reasoning_content": "x"},
        {"role": "system", "content": "stale"},
        {"role": "user", "content": "hi"},
    ]


def _threaded_send(client, request) -> dict:
    """Send a request from a worker thread and capture the outcome.

    Parameters
    ----------
    client : OpenRouterClient
        Client under test.

    request : urllib.request.Request
        Request to send.

    Returns
    -------
    dict
        Mapping with the returned body under ``value``.
    """
    outcome: dict = {}
    with patch.object(client, "_open", return_value={"ok": True}):
        worker = threading.Thread(
            target=lambda: outcome.update(value=client._send(request))
        )
        worker.start()
        worker.join()
    return outcome


if __name__ == "__main__":
    unittest.main()
