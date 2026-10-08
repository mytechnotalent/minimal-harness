"""Tests for OpenRouter request resilience."""

import io
import threading
import unittest
import urllib.error
from unittest.mock import patch

from meta_harness.openrouter import OpenRouterClient, OpenRouterError


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
