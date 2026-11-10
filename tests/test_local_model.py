"""Offline integration test for the local OpenAI-compatible provider."""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from unittest.mock import patch

from meta_harness.openrouter import OpenRouterClient


class _Handler(BaseHTTPRequestHandler):
    """Answer local completion and tool-call requests."""

    def do_POST(self) -> None:
        """Record the request and return a local response.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        self.server.seen_path = self.path
        self.server.seen_auth = self.headers.get("Authorization")
        self.server.seen_payload = payload
        self._reply(self._message(payload))

    def _message(self, payload: dict) -> dict:
        """Build a final or tool-call message.

        Parameters
        ----------
        payload : dict
            Parsed request body.

        Returns
        -------
        dict
            Assistant message for the response.
        """
        if payload.get("tools"):
            call = {"id": "1", "function": {"name": "read", "arguments": "{}"}}
            return {"role": "assistant", "content": None, "tool_calls": [call]}
        return {"role": "assistant", "content": "local ok"}

    def _reply(self, message: dict) -> None:
        """Write one JSON response.

        Parameters
        ----------
        message : dict
            Assistant message to return.

        Returns
        -------
        None
        """
        body = json.dumps({"choices": [{"message": message}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        """Silence request logging.

        Parameters
        ----------
        fmt : str
            Log format string.

        args : tuple
            Log format arguments.

        Returns
        -------
        None
        """
        return


def _local_env(port: int) -> dict:
    """Build the local provider environment.

    Parameters
    ----------
    port : int
        Local server port.

    Returns
    -------
    dict
        Environment overrides for the local provider.
    """
    return {
        "HARNESS_PROVIDER": "local",
        "LOCAL_BASE_URL": f"http://127.0.0.1:{port}/v1",
        "LOCAL_MODEL": "local-test",
    }


class LocalModelTests(unittest.TestCase):
    """Verify local provider URL, auth, and tool-call handling."""

    def setUp(self) -> None:
        """Start a local OpenAI-compatible server.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.env = _local_env(self.server.server_address[1])
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()

    def tearDown(self) -> None:
        """Stop the local server.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.server.shutdown()
        self.server.server_close()

    def test_local_completion(self) -> None:
        """A local completion uses the local endpoint and placeholder key.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, self.env, clear=True):
            client = OpenRouterClient()
            self.assertEqual(client.provider, "local")
            self.assertEqual(client.model, "local-test")
            self.assertEqual(client.complete("system", "user"), "local ok")
        self.assertEqual(self.server.seen_path, "/v1/chat/completions")
        self.assertEqual(self.server.seen_auth, "Bearer local")

    def test_local_tool_call(self) -> None:
        """A local chat request forwards tools and returns tool calls.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.dict(os.environ, self.env, clear=True):
            client = OpenRouterClient()
            body = client.chat([{"role": "user", "content": "hi"}], [{"x": 1}])
        message = body["choices"][0]["message"]
        self.assertEqual(message["tool_calls"][0]["id"], "1")
        self.assertEqual(self.server.seen_payload["model"], "local-test")
        self.assertEqual(self.server.seen_payload["tools"], [{"x": 1}])


if __name__ == "__main__":
    unittest.main()
