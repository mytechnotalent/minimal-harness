"""End-to-end pipeline test backed by an in-process mock OpenRouter."""

import json
import os
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from meta_harness.models import SearchConfig
from meta_harness.openrouter import OpenRouterClient
from meta_harness.pipeline import SearchPipeline

STARTER = Path(__file__).resolve().parent.parent / "benchmarks" / "starter"
REFERENCE_CODE = (STARTER / "reference_solution.py").read_text(
    encoding="utf-8"
)
MANIFEST_PATH = str(STARTER / "manifest.json")

CANNED = {
    "proposer": json.dumps([REFERENCE_CODE]),
    "reviewer": '{"passed": true, "blockers": [], "tests": []}',
    "adjudicator": (
        '{"selected_candidate_id": "candidate-1", "rationale": "mock"}'
    ),
}


def classify(payload: dict) -> str:
    """Return the stage name for a payload's system prompt.

    Parameters
    ----------
    payload : dict
        Decoded chat-completion request body.

    Returns
    -------
    str
        Stage identifier: proposer, reviewer, or adjudicator.
    """
    messages = payload.get("messages", [])
    system = next(
        (m.get("content", "") for m in messages if m.get("role") == "system"),
        "",
    ).lower()
    if "proposer" in system:
        return "proposer"
    return "reviewer" if "reviewer" in system else "adjudicator"


def build_response(role: str) -> dict:
    """Return an OpenAI-compatible response wrapping a canned string.

    Parameters
    ----------
    role : str
        Stage identifier.

    Returns
    -------
    dict
        Response body.
    """
    return {
        "id": f"mock-{role}",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": CANNED[role]},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 42, "completion_tokens": 17},
    }


class _Handler(BaseHTTPRequestHandler):
    """HTTP handler that answers /chat with canned stage responses."""

    def do_POST(self) -> None:
        """Classify the system prompt and reply with canned JSON."""
        payload = self._read_payload()
        body = json.dumps(build_response(classify(payload))).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_payload(self) -> dict:
        """Read and decode the request body."""
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def log_message(self, fmt: str, *args) -> None:
        """Silence default access logging."""
        return


class EndToEndPipelineTests(unittest.TestCase):
    """Run SearchPipeline through the OpenRouter client against a mock."""

    def setUp(self) -> None:
        """Start the mock server and point env vars at it."""
        self._saved = {
            key: os.environ.get(key)
            for key in ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY")
        }
        self._start_server()

    def _start_server(self) -> None:
        """Bind the mock on a free port and install env vars."""
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = self.server.server_address[1]
        os.environ["OPENROUTER_BASE_URL"] = f"http://127.0.0.1:{port}/chat"
        os.environ["OPENROUTER_API_KEY"] = "mock-integration-key"
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        """Stop the mock server and restore environment variables."""
        self.server.shutdown()
        self.server.server_close()
        for key, value in self._saved.items():
            self._restore(key, value)

    def _restore(self, key: str, value: str | None) -> None:
        """Restore or unset one environment variable."""
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def test_optimize_with_manifest_reaches_full_score(self) -> None:
        """End to end: mock proposer + real manifest evaluator hits 1.0."""
        client = OpenRouterClient()
        with tempfile.TemporaryDirectory() as workspace:
            result = self._run(workspace, client)
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.score, 1.0)
        self.assertTrue(result.stopped_on_target)
        self.assertEqual(client.call_count, 3)
        self.assertEqual(client.prompt_tokens, 42 * 3)
        self.assertEqual(client.completion_tokens, 17 * 3)

    def _run(self, workspace: str, client: OpenRouterClient):
        """Run one iteration wired through the OpenRouter client.

        Parameters
        ----------
        workspace : str
            Temporary workspace path.
        client : OpenRouterClient
            Client instance sharing usage counters.

        Returns
        -------
        SearchResult
            Completed search result.
        """
        config = SearchConfig(
            iterations=1,
            proposers_per_iteration=1,
            target_score=1.0,
            use_docker=False,
            use_web_search=False,
            task_manifest=MANIFEST_PATH,
        )
        pipeline = SearchPipeline(config, client=client, workspace=workspace)
        return pipeline.run("solve the starter benchmark")


if __name__ == "__main__":
    unittest.main()
