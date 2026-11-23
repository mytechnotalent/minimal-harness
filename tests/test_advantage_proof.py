"""Enforce the recorded adversarial advantage proofs."""

import unittest

from scripts.prove_advantage import run_proof


class AdvantageProofTests(unittest.TestCase):
    """Verify the mechanism-level advantage proofs still hold."""

    def test_gate_two_beats_baseline(self) -> None:
        """Gate 2 selects a higher held-out score than the baseline.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        report = run_proof(repeats=1)
        self.assertGreater(
            report["gate2"]["adversarial_held_out"],
            report["gate2"]["baseline_held_out"],
        )

    def test_reviewer_tests_block_flawed_candidate(self) -> None:
        """Executable reviewer tests block what prose review passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        review = run_proof(repeats=1)["reviewer_tests"]
        self.assertTrue(review["prose_gate1_passed"])
        self.assertFalse(review["test_gate1_passed"])

    def test_proof_is_deterministic(self) -> None:
        """Repeated runs produce identical outcomes.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertTrue(run_proof(repeats=3)["deterministic"])


if __name__ == "__main__":
    unittest.main()
