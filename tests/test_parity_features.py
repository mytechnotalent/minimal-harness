"""Tests for parity-oriented runtime features."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.evaluator import AppEvaluator
from meta_harness.provider import ProviderCatalog
from meta_harness.session import Session


class ParityFeatureTests(unittest.TestCase):
    """Verify persistence, scoring, and provider contracts."""

    def test_session_branch_and_compact(self) -> None:
        """Branch a session and compact its retained messages.

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

        Returns
        -------
        None
            Assertions pass when all checks succeed.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<html></html>")
            (root / "styles.css").write_text("body {}")
            (root / "app.js").write_text("console.log('ok');")
            result = AppEvaluator().evaluate(root)
        self.assertEqual(result["score"], 1.0)

    def test_free_model_filter(self) -> None:
        """Filter provider records by zero pricing.

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
