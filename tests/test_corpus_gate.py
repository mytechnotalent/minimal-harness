"""Tests for the corpus A/B gate."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.corpus_gate import FAIR_PI_COMMAND
from scripts.corpus_gate import _write_report
from scripts.corpus_gate import gate_passed


class CorpusGateTests(unittest.TestCase):
    """Verify gate thresholds and report output."""

    def test_gate_requires_pass_rate(self) -> None:
        """A run below the absolute threshold fails.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(gate_passed(0.60, 0.48, 0.52, 0.0))
        self.assertFalse(gate_passed(0.50, 0.48, 0.52, 0.0))

    def test_gate_requires_gain(self) -> None:
        """A run below the required gain over Pi fails.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(gate_passed(0.65, 0.48, 0.52, 0.10))
        self.assertFalse(gate_passed(0.55, 0.48, 0.52, 0.10))

    def test_fair_pi_command_uses_no_shell(self) -> None:
        """The default baseline disables Pi's shell tools.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertIn("--tools read,write,edit", FAIR_PI_COMMAND)

    def test_report_is_written(self) -> None:
        """The gate writes its report as JSON.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate.json"
            _write_report(str(path), {"harness": 0.6, "pi": 0.48})
            report = json.loads(path.read_text())
        self.assertEqual(report["harness"], 0.6)
