"""Tests for harness configuration search."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import search_harness

_REPORTS = (
    {"name": "fast", "score": 0.5, "seconds": 1.0},
    {"name": "best", "score": 1.0, "seconds": 2.0},
    {"name": "slow", "score": 1.0, "seconds": 3.0},
)


def _manifest(root: Path) -> str:
    """Write a one-task manifest.

    Parameters
    ----------
    root : pathlib.Path
        Temporary directory.

    Returns
    -------
    str
        Manifest path.
    """
    path = root / "manifest.json"
    payload = [{"id": "x", "test": "t.py"}]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _rows(scores):
    """Build scripted task rows.

    Parameters
    ----------
    scores : list of float
        Pass flags in call order.

    Returns
    -------
    list of dict
        Scripted rows.
    """
    return [{"id": "x", "passed": value, "seconds": 1.0} for value in scores]


def _patched(scores):
    """Build a patched task-score context.

    Parameters
    ----------
    scores : list of float
        Scripted pass flags.

    Returns
    -------
    unittest.mock._patch
        Patch context manager.
    """
    return patch.object(
        search_harness, "_task_score", side_effect=_rows(scores)
    )


def _report(configs, scores, repeats=2):
    """Run a scripted search.

    Parameters
    ----------
    configs : list
        Configuration records.

    scores : list of float
        Scripted pass flags.

    repeats : int
        Runs per task.

    Returns
    -------
    dict
        Search report.
    """
    with tempfile.TemporaryDirectory() as directory:
        manifest = _manifest(Path(directory))
        stub = _patched(scores)
        with stub:
            return search_harness.search(
                manifest, configs, ["h"], 5, repeats=repeats
            )


class ArchiveTests(unittest.TestCase):
    """Verify Pareto ranking."""

    def test_marks_front(self) -> None:
        """Dominated configs are excluded from the front.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        archived = search_harness._archive(list(_REPORTS))
        marked = [
            item["name"] for item in archived["configs"] if item["pareto"]
        ]
        self.assertEqual(sorted(marked), ["best", "fast"])


class SearchTests(unittest.TestCase):
    """Verify config evaluation and averaging."""

    def test_averages_runs(self) -> None:
        """Repeated runs are averaged per config.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        report = _report(
            [{"name": "on"}, {"name": "off"}], [1.0, 1.0, 1.0, 0.0]
        )
        top = report["configs"][0]
        self.assertEqual(top["name"], "on")
        self.assertEqual(top["score"], 1.0)
        self.assertEqual(report["configs"][1]["score"], 0.5)

    def test_rejects_non_list_configs(self) -> None:
        """Invalid config files raise ValueError.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configs.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                search_harness.load_configs(str(path))


if __name__ == "__main__":
    unittest.main()
