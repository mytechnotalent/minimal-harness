"""Tests for parity-oriented runtime features."""

import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from meta_harness.evaluator import AppEvaluator
from meta_harness.provider import ProviderCatalog
from meta_harness.session import Session


class ParityFeatureTests(unittest.TestCase):
    """Verify persistence, scoring, and provider contracts."""

    def test_session_branch_and_compact(self) -> None:
        """Branch a session and compact its retained messages.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when session controls work.
        """
        with tempfile.TemporaryDirectory() as directory:
            source = Session(Path(directory) / "source.jsonl")
            source.append({"role": "user", "content": "one"})
            source.append({"role": "assistant", "content": "two"})
            child = source.branch(Path(directory) / "child.jsonl")
            discarded = child.compact(1)
        self.assertEqual(len(discarded), 1)
        self.assertEqual(child.messages[0]["content"], "two")

    def test_app_evaluator_scores_valid_files(self) -> None:
        """Score a valid static web application deterministically.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when all checks succeed.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_app(root)
            result = _evaluate(root)
        self.assertEqual(result["score"], 1.0)

    def test_app_evaluator_skips_missing_node(self) -> None:
        """Missing Node does not fail an otherwise valid app.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_app(root)
            result = _evaluate(root, FileNotFoundError)
        self.assertEqual(result["score"], 1.0)
        self.assertNotIn("javascript_syntax", result["checks"])

    def test_free_model_filter(self) -> None:
        """Filter provider records by zero pricing.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when only free models remain.
        """
        catalog = ProviderCatalog()
        records = [
            {"id": "free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "paid", "pricing": {"prompt": "1", "completion": "0"}},
        ]
        with patch.object(catalog, "list_models", return_value=records):
            models = catalog.free_models()
        self.assertEqual([model["id"] for model in models], ["free"])


if __name__ == "__main__":
    unittest.main()


def _write_app(root: Path) -> None:
    """Write a minimal valid static application.

    Parameters
    ----------
    root : pathlib.Path
        Application directory.

    Returns
    -------
    None
        Three files are written.
    """
    (root / "index.html").write_text("<html></html>")
    (root / "styles.css").write_text("body {}")
    (root / "app.js").write_text("console.log('ok');")


def _evaluate(root: Path, error=None) -> dict:
    """Evaluate an application with Node stubbed.

    Parameters
    ----------
    root : pathlib.Path
        Application directory.

    error : Exception or None
        Optional error raised by the Node stub.

    Returns
    -------
    dict
        Evaluator result mapping.
    """
    if error is None:
        stub = CompletedProcess(["node"], 0)
        with patch.object(AppEvaluator, "_node_process", return_value=stub):
            return AppEvaluator().evaluate(root)
    with patch.object(AppEvaluator, "_node_process", side_effect=error):
        return AppEvaluator().evaluate(root)


if __name__ == "__main__":
    unittest.main()
