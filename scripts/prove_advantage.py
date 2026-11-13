"""Prove the adversarial loop's selection advantages on fixed benchmarks."""

import json
import tempfile
from pathlib import Path

from meta_harness.models import SearchConfig
from meta_harness.pipeline import SearchPipeline

ROOT = Path(__file__).resolve().parent.parent
HARD = ROOT / "benchmarks" / "hard"
REFERENCE = (HARD / "reference_solution.py").read_text(encoding="utf-8")
FLAWED = (HARD / "flawed_solution.py").read_text(encoding="utf-8")
SEARCH = str(HARD / "search" / "manifest.json")
VALIDATION = str(HARD / "validation" / "manifest.json")
HELDOUT = str(HARD / "heldout" / "manifest.json")

_MS_TEST = """import unittest
from solution import parse_duration


class T(unittest.TestCase):
    def test_ms(self) -> None:
        self.assertEqual(parse_duration("500ms"), 500)
"""

_PROPOSER_RESPONSES = (
    json.dumps([FLAWED, REFERENCE]),
    json.dumps([REFERENCE]),
)
_REVIEWER_RESPONSES = (
    '{"passed": true, "blockers": [], "tests": []}',
    '{"passed": true, "blockers": [], "tests": []}',
    '{"passed": true, "blockers": [], "tests": []}',
)
_ADJUDICATOR_RESPONSES = (
    '{"selected_candidate_id": "candidate-1", "rationale": "scripted"}',
    '{"selected_candidate_id": "candidate-3", "rationale": "scripted"}',
)
_PROPOSE_FLAWED = (json.dumps([FLAWED]),)
_PROSE_REVIEWER = ('{"passed": true, "tests": []}',)
_TEST_REVIEWER = (json.dumps({"passed": True, "tests": [_MS_TEST]}),)


class _Scripted:
    """Return stage responses by call order."""

    def __init__(self, proposer, reviewer, adjudicator) -> None:
        """Store per-stage response sequences.

        Parameters
        ----------
        proposer : tuple
            Proposer responses in order.

        reviewer : tuple
            Reviewer responses in order.

        adjudicator : tuple
            Adjudicator responses in order.

        Returns
        -------
        None
            The client is ready.
        """
        self._responses = {
            "proposer": proposer,
            "reviewer": reviewer,
            "adjudicator": adjudicator,
        }
        self._calls = {"proposer": 0, "reviewer": 0, "adjudicator": 0}

    def complete(self, system, user, temperature=0.2):
        """Return the next scripted response for a stage.

        Parameters
        ----------
        system : str
            System prompt.

        user : str
            User payload.

        temperature : float
            Sampling temperature.

        Returns
        -------
        str
            Scripted response.
        """
        stage = _stage(system)
        index = self._calls[stage]
        self._calls[stage] += 1
        return self._responses[stage][index]


def _stage(system: str) -> str:
    """Return the stage name embedded in a system prompt.

    Parameters
    ----------
    system : str
        System prompt.

    Returns
    -------
    str
        Stage name.
    """
    lowered = system.lower()
    for stage in ("proposer", "reviewer", "adjudicator"):
        if stage in lowered:
            return stage
    raise ValueError("unknown stage")


def _config(**overrides) -> SearchConfig:
    """Build a search configuration for a proof scenario.

    Parameters
    ----------
    overrides : dict
        Configuration field overrides.

    Returns
    -------
    SearchConfig
        Search configuration.
    """
    fields = {
        "iterations": 1,
        "use_docker": False,
        "use_web_search": False,
        "target_score": 1.0,
    }
    fields.update(overrides)
    return SearchConfig(**fields)


def _run(config, client) -> object:
    """Run one scripted search and return its result.

    Parameters
    ----------
    config : SearchConfig
        Search configuration.

    client : _Scripted
        Scripted model client.

    Returns
    -------
    SearchResult
        Completed search result.
    """
    with tempfile.TemporaryDirectory() as workspace:
        pipeline = SearchPipeline(config, client=client, workspace=workspace)
        return pipeline.run("solve the hard benchmark")


def _baseline_config() -> SearchConfig:
    """Build the gate-1-only baseline configuration.

    Parameters
    ----------
    None

    Returns
    -------
    SearchConfig
        Baseline configuration.
    """
    return _config(
        proposers_per_iteration=1,
        task_manifest=SEARCH,
        final_task_manifest=VALIDATION,
        held_out_manifest=HELDOUT,
        baseline=True,
    )


def _adversarial_config() -> SearchConfig:
    """Build the full adversarial configuration.

    Parameters
    ----------
    None

    Returns
    -------
    SearchConfig
        Adversarial configuration.
    """
    return _config(
        iterations=2,
        proposers_per_iteration=2,
        task_manifest=SEARCH,
        final_task_manifest=VALIDATION,
        held_out_manifest=HELDOUT,
    )


def _review_config() -> SearchConfig:
    """Build a gate-1-only reviewer-test configuration.

    Parameters
    ----------
    None

    Returns
    -------
    SearchConfig
        Reviewer configuration.
    """
    return _config(proposers_per_iteration=1, task_manifest=SEARCH)


def _baseline_client() -> _Scripted:
    """Build a client that proposes only the flawed candidate.

    Parameters
    ----------
    None

    Returns
    -------
    _Scripted
        Scripted client.
    """
    return _Scripted(_PROPOSE_FLAWED, (), ())


def _adversarial_client() -> _Scripted:
    """Build a client that proposes flawed then good candidates.

    Parameters
    ----------
    None

    Returns
    -------
    _Scripted
        Scripted client.
    """
    return _Scripted(
        _PROPOSER_RESPONSES, _REVIEWER_RESPONSES, _ADJUDICATOR_RESPONSES
    )


def _gate2_proof() -> dict:
    """Compare baseline and adversarial held-out selection.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Baseline and adversarial held-out scores.
    """
    baseline = _run(_baseline_config(), _baseline_client())
    adversarial = _run(_adversarial_config(), _adversarial_client())
    return {
        "baseline_held_out": baseline.held_out_score,
        "adversarial_held_out": adversarial.held_out_score,
    }


def _review_client(tests) -> _Scripted:
    """Build a client whose reviewer emits optional tests.

    Parameters
    ----------
    tests : tuple
        Reviewer test sources.

    Returns
    -------
    _Scripted
        Scripted client.
    """
    reviewer = (json.dumps({"passed": True, "tests": list(tests)}),)
    adjudicator = ('{"selected_candidate_id": "candidate-1"}',)
    return _Scripted(_PROPOSE_FLAWED, reviewer, adjudicator)


def _reviewer_proof() -> dict:
    """Compare prose review and executable reviewer tests.

    Parameters
    ----------
    None

    Returns
    -------
    dict
        Gate 1 outcomes for both reviewer styles.
    """
    prose = _run(_review_config(), _review_client(()))
    tests = _run(_review_config(), _review_client((_MS_TEST,)))
    return {
        "prose_gate1_passed": _gate1(prose),
        "test_gate1_passed": _gate1(tests),
    }


def _gate1(result) -> bool:
    """Return the first candidate's gate-1 outcome.

    Parameters
    ----------
    result : SearchResult
        Completed search result.

    Returns
    -------
    bool
        Whether gate 1 passed.
    """
    return bool(result.history[0].dynamic_test.get("passed"))


def run_proof(repeats: int = 3) -> dict:
    """Run the advantage scenarios and return the report.

    Parameters
    ----------
    repeats : int
        Number of repetitions used to confirm determinism.

    Returns
    -------
    dict
        Scenario outcomes and determinism flag.
    """
    gate = [_gate2_proof() for _ in range(repeats)]
    review = [_reviewer_proof() for _ in range(repeats)]
    report = {"gate2": gate[0], "reviewer_tests": review[0]}
    report["repeats"] = repeats
    report["deterministic"] = _stable(gate, review, repeats)
    return report


def _stable(gate, review, repeats) -> bool:
    """Report whether repeated runs are identical.

    Parameters
    ----------
    gate : list[dict]
        Gate 2 proof runs.

    review : list[dict]
        Reviewer proof runs.

    repeats : int
        Expected run count.

    Returns
    -------
    bool
        Whether every run matches the first.
    """
    return (
        len(gate) == repeats
        and gate.count(gate[0]) == repeats
        and review.count(review[0]) == repeats
    )


def _proved(report: dict) -> bool:
    """Report whether every expected advantage appears.

    Parameters
    ----------
    report : dict
        Proof report.

    Returns
    -------
    bool
        Whether gate 2 and reviewer tests both show an advantage.
    """
    gate = report["gate2"]
    review = report["reviewer_tests"]
    return (
        gate["adversarial_held_out"] > gate["baseline_held_out"]
        and review["prose_gate1_passed"]
        and not review["test_gate1_passed"]
        and report["deterministic"]
    )


def main() -> int:
    """Print the proof report.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Zero when the expected advantages are observed.
    """
    report = run_proof()
    print(json.dumps(report, indent=2))
    return 0 if _proved(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
