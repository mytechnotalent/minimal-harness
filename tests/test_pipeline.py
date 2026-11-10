"""Offline tests for adversarial search control flow."""

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from functools import partial
from pathlib import Path

from meta_harness._json_util import json_text
from meta_harness.models import Candidate
from meta_harness.models import SearchConfig
from meta_harness.pipeline import SearchPipeline


def cycle_proposer(
    seed: str, history: list[Candidate], calls: dict[str, int]
) -> list[Candidate]:
    """Return one candidate for the current iteration.

    Parameters
    ----------
    seed : str
        Initial task description.
    history : list[Candidate]
        Prior candidates.
    calls : dict[str, int]
        Mutable proposer call counter.

    Returns
    -------
    list[Candidate]
        One deterministic candidate.
    """
    calls["count"] += 1
    return [Candidate(f"c{calls['count']}", "test", "valid proposal")]


def blocked_proposer(seed: str, history: list[Candidate]) -> list[Candidate]:
    """Return one candidate for review.

    Parameters
    ----------
    seed : str
        Initial task description.
    history : list[Candidate]
        Prior candidates.

    Returns
    -------
    list[Candidate]
        One candidate.
    """
    return [Candidate("c1", "test", "proposal")]


REFERENCE_SOLUTION_PATH = (
    Path(__file__).resolve().parent.parent
    / "benchmarks"
    / "starter"
    / "reference_solution.py"
)


def reference_solution_proposer(
    seed: str, history: list[Candidate]
) -> list[Candidate]:
    """Return one candidate carrying the starter reference solution.

    Parameters
    ----------
    seed : str
        Initial task description.
    history : list[Candidate]
        Prior candidates.

    Returns
    -------
    list[Candidate]
        One candidate whose proposal is valid Python.
    """
    code = REFERENCE_SOLUTION_PATH.read_text(encoding="utf-8")
    return [Candidate("candidate-1", "test", code)]


def counting_reference(
    seed: str, history: list[Candidate], calls: dict[str, int]
) -> list[Candidate]:
    """Count proposer calls while returning the reference solution.

    Parameters
    ----------
    seed : str
        Initial task description.
    history : list[Candidate]
        Prior candidates.
    calls : dict[str, int]
        Mutable proposer call counter.

    Returns
    -------
    list[Candidate]
        One reference-solution candidate.
    """
    calls["count"] += 1
    return reference_solution_proposer(seed, history)


class _StagedProposer:
    """Emit a flawed candidate first, then a good one."""

    def __init__(self, good: str, flawed: str) -> None:
        """Store both candidate sources.

        Parameters
        ----------
        good : str
            Correct solution code.

        flawed : str
            Code that passes gate 1 but fails validation.

        Returns
        -------
        None
            The proposer is ready.
        """
        self._good = good
        self._flawed = flawed

    def __call__(self, seed, history):
        """Emit one candidate per call.

        Parameters
        ----------
        seed : str
            Initial task description.

        history : list[Candidate]
            Prior records.

        Returns
        -------
        list[Candidate]
            One candidate for the iteration.
        """
        code = self._flawed if not history else self._good
        return [Candidate(f"candidate-{len(history) + 1}", "test", code)]


def staged_proposer(good: str, flawed: str):
    """Return a proposer that emits a flawed then a good candidate.

    Parameters
    ----------
    good : str
        Correct solution code.

    flawed : str
        Code that passes gate 1 but fails validation.

    Returns
    -------
    collections.abc.Callable
        Proposer callable.
    """
    return _StagedProposer(good, flawed)


def blocked_review(
    candidate: Candidate, history: list[Candidate]
) -> Candidate:
    """Mark a candidate as blocked by review.

    Parameters
    ----------
    candidate : Candidate
        Candidate under review.
    history : list[Candidate]
        Prior candidates.

    Returns
    -------
    Candidate
        Candidate with a failed review.
    """
    return Candidate(
        candidate.candidate_id,
        candidate.source,
        candidate.proposal,
        review={"passed": False},
    )


class CapturingClient:
    """Capture the proposer payload and return one candidate."""

    def __init__(self) -> None:
        """Initialize the capture buffer.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.user = ""

    def complete(self, system: str, user: str, temperature: float = 0.2):
        """Capture the payload and return one candidate.

        Parameters
        ----------
        system : str
            System instruction.

        user : str
            User payload.

        temperature : float
            Sampling temperature.

        Returns
        -------
        str
            JSON list with one candidate source.
        """
        self.user = user
        return '["def double(x):\\n    return x * 2"]'


class MalformedClient:
    """Return plain prose for every agent request."""

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return malformed output for fallback tests.

        Parameters
        ----------
        system : str
            Agent instruction.
        user : str
            Agent payload.
        temperature : float
            Unused sampling temperature.

        Returns
        -------
        str
            Plain prose that is not JSON.
        """
        return "plain model prose"


class PipelineTests(unittest.TestCase):
    """Verify cycling and review gates without external services."""

    class FakeClient:
        """Return valid agent responses without network access."""

        def complete(
            self, system: str, user: str, temperature: float = 0.2
        ) -> str:
            """Return a deterministic response.

            Parameters
            ----------
            system : str
                Agent instruction.
            user : str
                Agent payload.
            temperature : float
                Unused sampling temperature.

            Returns
            -------
            str
                JSON review response.
            """
            return '{"passed": true, "blockers": [], "tests": []}'

    def test_pipeline_cycles_until_target_with_local_proposer(self) -> None:
        """Continue through the budget when target remains unmet.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when cycling is correct.
        """
        calls = {"count": 0}
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_cycle(directory, calls)
        self.assertEqual(calls["count"], 3)
        self.assertFalse(result.stopped_on_target)
        self.assertTrue(result.stop_reason.startswith("iteration budget"))

    def _run_cycle(self, directory: str, calls: dict[str, int]):
        """Run a three-iteration local search.

        Parameters
        ----------
        directory : str
            Temporary artifact directory.
        calls : dict[str, int]
            Mutable proposer call counter.

        Returns
        -------
        SearchResult
            Completed local search result.
        """
        config = self._cycle_config()
        proposer = partial(cycle_proposer, calls=calls)
        return SearchPipeline(
            config, client=self.FakeClient(), workspace=Path(directory)
        ).run("seed", proposer)

    def _cycle_config(self) -> SearchConfig:
        """Build the offline cycling configuration.

        Parameters
        ----------
        None

        Returns
        -------
        SearchConfig
            Three-iteration test configuration.
        """
        return SearchConfig(
            iterations=3,
            proposers_per_iteration=1,
            target_score=2.0,
            use_docker=False,
        )

    def test_task_manifest_scores_python_proposal(self) -> None:
        """Score a Python-code proposal against the starter manifest.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when the manifest scorer is invoked.
        """
        manifest_path = self._starter_manifest_path()
        result = self._run_with_manifest(manifest_path)
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.score, 1.0)
        self.assertTrue(result.winner.dynamic_test.get("final_passed"))

    def test_missing_gate_fails_closed(self) -> None:
        """A Docker run without a gate command cannot score.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        config = _docker_config()
        pipeline = SearchPipeline(config, client=self.FakeClient())
        result = pipeline.run("seed", blocked_proposer)
        self.assertIsNone(result.winner)
        self.assertIn(
            "no gate configured",
            result.history[0].dynamic_test["error"],
        )

    def test_gate_command_is_used(self) -> None:
        """The configured gate command is sent to Docker.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        config = _gate_config("python check.py")
        pipeline = SearchPipeline(config, client=self.FakeClient())
        calls: list[list[str]] = []
        pipeline.gate.run = _RecordingGate(calls)
        result = self._run_one_gate(pipeline)
        self.assertTrue(result["passed"])
        self.assertEqual(calls[0], ["sh", "-c", "python check.py"])

    def _run_one_gate(self, pipeline):
        """Run the gate on one reviewed candidate.

        Parameters
        ----------
        pipeline : SearchPipeline
            Pipeline under test.

        Returns
        -------
        dict
            Gate result.
        """
        candidate = Candidate("c1", "test", "proposal")
        reviewed = pipeline._with_review(candidate, {"passed": True})
        return pipeline._run_gate(reviewed, 1)

    def test_local_gate_runs_configured_command(self) -> None:
        """The opt-in local gate produces a scored winner.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        command = f'"{sys.executable}" -c "print(1)"'
        config = _local_gate_config(command)
        result = self._run_seed(config)
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.score, 1.0)
        self.assertFalse(result.winner.dynamic_test["isolated"])

    def test_final_manifest_is_held_out(self) -> None:
        """Gate two scores against the configured held-out manifest.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._held_out_manifest(Path(directory))
            result = self._run_held_out_search(manifest)
        self.assertIsNone(result.winner)
        self.assertFalse(result.history[0].dynamic_test["final_passed"])
        self.assertTrue(result.history[0].dynamic_test["independent"])

    def _held_out_manifest(self, root: Path) -> str:
        """Write a failing held-out task manifest.

        Parameters
        ----------
        root : pathlib.Path
            Temporary manifest root.

        Returns
        -------
        str
            Manifest path.
        """
        (root / "test_fail.py").write_text(_FAILING_TEST, encoding="utf-8")
        manifest = json.dumps([_FAILING_ENTRY])
        path = root / "manifest.json"
        path.write_text(manifest, encoding="utf-8")
        return str(path)

    def _run_held_out_search(self, manifest: str):
        """Run one search with a separate held-out manifest.

        Parameters
        ----------
        manifest : str
            Held-out manifest path.

        Returns
        -------
        SearchResult
            Completed search result.
        """
        config = _search_config(
            proposers_per_iteration=1,
            target_score=1.0,
            task_manifest=self._starter_manifest_path(),
            final_task_manifest=manifest,
        )
        return self._run_seed(config)

    def test_stops_early_on_target(self) -> None:
        """The loop stops after the target score is reached.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        calls = {"count": 0}
        manifest = self._starter_manifest_path()
        result = self._run_seed(
            _search_config(iterations=3, task_manifest=manifest),
            partial(counting_reference, calls=calls),
        )
        self.assertEqual(calls["count"], 1)
        self.assertTrue(result.stopped_on_target)

    def test_proposer_context_includes_search_tasks(self) -> None:
        """The proposer sees search prompts but not held-out tasks.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        user = self._propose_context(CapturingClient())
        self.assertIn("fizz_buzz", user)
        self.assertNotIn("Held-out check", user)

    def _propose_context(self, client):
        """Run one proposal call and return the captured payload.

        Parameters
        ----------
        client : CapturingClient
            Client capturing the proposer payload.

        Returns
        -------
        str
            Captured proposer payload.
        """
        config = _search_config(
            task_manifest=self._starter_manifest_path(),
            held_out_manifest=self._heldout_manifest_path(),
        )
        SearchPipeline(config, client=client)._propose("seed", [])
        return client.user

    def test_held_out_score_recorded_without_selecting(self) -> None:
        """Held-out scoring happens after the winner is chosen.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        result = self._run_seed(_held_out_config())
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.held_out_score, 1.0)

    def test_gate_two_rejects_search_only_winner(self) -> None:
        """Gate two replaces a gate-one winner that fails validation.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        hard = self._hard_dir()
        good = (hard / "reference_solution.py").read_text(encoding="utf-8")
        flawed = (hard / "flawed_solution.py").read_text(encoding="utf-8")
        proposer = staged_proposer(good, flawed)
        baseline = self._run_hard(hard, True, proposer)
        adversarial = self._run_hard(hard, False, proposer)
        self.assertLess(baseline.held_out_score, 1.0)
        self.assertEqual(adversarial.held_out_score, 1.0)

    def _run_hard(self, hard: Path, baseline: bool, proposer):
        """Run the hard benchmark with a staged proposer.

        Parameters
        ----------
        hard : pathlib.Path
            Hard benchmark root.
        baseline : bool
            Whether to run the baseline.
        proposer : collections.abc.Callable
            Proposer callable.

        Returns
        -------
        SearchResult
            Completed search result.
        """
        config = _hard_config(hard, baseline)
        return _run_in_temp(config, self.FakeClient(), proposer)

    def _hard_dir(self) -> Path:
        """Return the hard benchmark root.

        Parameters
        ----------
        None

        Returns
        -------
        pathlib.Path
            Hard benchmark directory.
        """
        here = Path(__file__).resolve().parent
        return here.parent / "benchmarks" / "hard"

    def test_validation_manifest_scores_gate_two(self) -> None:
        """Gate two scores the validation split independently.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        result = self._run_seed(_validation_config())
        self.assertIsNotNone(result.winner)
        self.assertTrue(result.history[0].dynamic_test["independent"])

    def _validation_manifest_path(self) -> str:
        """Return the validation benchmark manifest path.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Absolute path to the validation manifest.
        """
        here = Path(__file__).resolve().parent
        return str(here.parent / "benchmarks" / "validation" / "manifest.json")

    def _heldout_manifest_path(self) -> str:
        """Return the held-out benchmark manifest path.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Absolute path to the held-out manifest.
        """
        here = Path(__file__).resolve().parent
        return str(here.parent / "benchmarks" / "heldout" / "manifest.json")

    def _starter_manifest_path(self) -> str:
        """Return the starter benchmark manifest path.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Absolute path to the starter manifest.
        """
        here = Path(__file__).resolve().parent
        return str(here.parent / "benchmarks" / "starter" / "manifest.json")

    def _run_with_manifest(self, manifest_path: str):
        """Run one iteration with a fixed Python-code proposer.

        Parameters
        ----------
        manifest_path : str
            Path to the task manifest.

        Returns
        -------
        SearchResult
            Completed search result.
        """
        config = _search_config(
            proposers_per_iteration=1,
            target_score=1.0,
            task_manifest=manifest_path,
        )
        return self._run_seed(config)

    def _run_seed(self, config, proposer=None):
        """Run the pipeline, defaulting to the reference proposer.

        Parameters
        ----------
        config : SearchConfig
            Search configuration.

        proposer : collections.abc.Callable or None
            Optional proposer override.

        Returns
        -------
        SearchResult
            Completed search result.
        """
        chosen = proposer or reference_solution_proposer
        pipeline = SearchPipeline(config, client=self.FakeClient())
        return pipeline.run("seed", chosen)

    def test_blocked_review_does_not_score_candidate(self) -> None:
        """Exclude candidates blocked by adversarial review.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when blocked candidates cannot win.
        """
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_blocked(directory)
        self.assertIsNone(result.winner)
        self.assertEqual(
            result.history[0].dynamic_test["error"],
            "adversarial review blocked candidate",
        )

    def test_trajectory_records_every_stage_call(self) -> None:
        """Write one trajectory entry per proposer, reviewer, adjudicator call.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when every stage call is recorded.
        """
        with tempfile.TemporaryDirectory() as directory:
            self._run_full_search_in(directory)
            stages = self._trajectory_stages(Path(directory))
        self.assertEqual(stages.count("proposer"), 1)
        self.assertEqual(stages.count("reviewer"), 1)
        self.assertEqual(stages.count("adjudicator"), 1)

    def _run_full_search_in(self, directory: str) -> None:
        """Run one full search into a persistent workspace directory.

        Parameters
        ----------
        directory : str
            Workspace directory.

        Returns
        -------
        None
            Search runs to completion.
        """
        client = SequenceClient()
        config = SearchConfig(iterations=1, target_score=0.0, use_docker=False)
        SearchPipeline(
            config,
            client=client,
            workspace=directory,
            web_search=FakeWebSearch(),
        ).run("seed")

    def _trajectory_stages(self, workspace: Path) -> list[str]:
        """Return the stage tag of every trajectory entry.

        Parameters
        ----------
        workspace : pathlib.Path
            Workspace directory.

        Returns
        -------
        list[str]
            Stage tags in the order they were written.
        """
        path = workspace / "iteration-1" / "trajectory.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line)["stage"] for line in lines if line.strip()]

    def test_model_json_parser_accepts_fenced_proposals(self) -> None:
        """Accept explanatory text around fenced proposal JSON.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when proposal JSON is recovered.
        """
        pipeline = SearchPipeline(
            SearchConfig(use_web_search=False), client=self.FakeClient()
        )
        raw = 'Here you go:\n```json\n["fix"]\n```'
        proposals = pipeline._proposal_items([], json_text(raw))
        self.assertEqual(proposals[0].proposal, "fix")

    def test_non_json_agent_output_has_safe_stage_fallbacks(self) -> None:
        """Keep malformed agent responses inside the pipeline.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when malformed output is handled safely.
        """
        proposals, review, selection = self._malformed_stages()
        self.assertEqual(proposals[0].proposal, "plain model prose")
        self.assertFalse(review.review["passed"])
        self.assertEqual(selection.candidate_id, proposals[0].candidate_id)

    def _malformed_stages(self):
        """Run proposer, review, and adjudication with malformed output.

        Parameters
        ----------
        None

        Returns
        -------
        tuple
            Candidate proposals, review, and selection.
        """
        pipeline = SearchPipeline(
            SearchConfig(use_web_search=False), client=MalformedClient()
        )
        proposals = pipeline._propose("seed", [])
        review = pipeline._review(proposals[0], [])
        return proposals, review, pipeline._adjudicate([review], [])

    def test_full_agent_stage_sequence_runs(self) -> None:
        """Exercise proposer, review, adjudication, and both gates.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when every agent stage is called.
        """
        client, result = self._run_full_search()
        self.assertEqual(client.roles, ["proposer", "reviewer", "adjudicator"])
        self.assertTrue(result.stopped_on_target)
        self.assertEqual(result.history[0].dynamic_test["final_passed"], True)

    def test_winner_score_survives_final_gate(self) -> None:
        """Preserve the first-gate score through the final gate.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when the winner keeps its numeric score.
        """
        _, result = self._run_full_search()
        winner = result.winner
        self.assertIsNotNone(winner)
        self.assertIsNotNone(winner.score)

    def test_baseline_skips_reviewer_and_adjudicator(self) -> None:
        """Baseline mode runs proposer and one gate only.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = SequenceClient()
        config = SearchConfig(iterations=1, use_docker=False, baseline=True)
        result = SearchPipeline(
            config, client=client, web_search=FakeWebSearch()
        ).run("seed")
        self.assertEqual(client.roles, ["proposer"])
        self.assertIsNotNone(result.winner)
        self.assertTrue(result.winner.dynamic_test["final_passed"])

    def test_adjudicator_skipped_when_review_blocks_all(self) -> None:
        """Skip adjudication when no candidate survives the review gate.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Assertions pass when only proposer and reviewer are called.
        """
        client, result = self._run_blocked_sequence()
        self.assertNotIn("adjudicator", client.roles)
        self.assertIsNone(result.winner)

    def _run_blocked_sequence(self):
        """Run one iteration with review forced to block.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[SequenceClient, SearchResult]
            Client call record and result.
        """
        client = SequenceClient()
        config = SearchConfig(iterations=1, use_docker=False)
        pipeline = SearchPipeline(
            config, client=client, web_search=FakeWebSearch()
        )
        pipeline._review = blocked_review
        return client, pipeline.run("seed")

    def _run_full_search(self):
        """Run the complete mocked agent pipeline.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[SequenceClient, SearchResult]
            Client call record and search result.
        """
        client = SequenceClient()
        config = SearchConfig(iterations=1, target_score=0.0, use_docker=False)
        search = SearchPipeline(
            config, client=client, web_search=FakeWebSearch()
        )
        return client, search.run("seed")

    def _run_blocked(self, directory: str):
        """Run one search with a forced blocked review.

        Parameters
        ----------
        directory : str
            Temporary artifact directory.

        Returns
        -------
        SearchResult
            Completed blocked search result.
        """
        pipeline = SearchPipeline(
            SearchConfig(iterations=1, use_docker=False),
            client=self.FakeClient(),
            workspace=directory,
        )
        pipeline._review = blocked_review
        return pipeline.run("seed", blocked_proposer)


class SequenceClient:
    """Provide deterministic responses for each agent role."""

    def __init__(self) -> None:
        """Initialize the recorded role list.

        Parameters
        ----------
        None

        Returns
        -------
        None
            This initializer mutates the client instance.
        """
        self.roles = []

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return a role-specific JSON response.

        Parameters
        ----------
        system : str
            Agent instruction.
        user : str
            Agent payload.
        temperature : float
            Unused sampling temperature.

        Returns
        -------
        str
            Deterministic JSON response.
        """
        role = self._role(system)
        self.roles.append(role)
        return self._response(role)

    def _role(self, system: str) -> str:
        """Classify an agent instruction.

        Parameters
        ----------
        system : str
            Agent instruction.

        Returns
        -------
        str
            Proposer, reviewer, or adjudicator role.
        """
        if "proposer" in system:
            return "proposer"
        if "reviewer" in system:
            return "reviewer"
        return "adjudicator"

    def _response(self, role: str) -> str:
        """Build a response for an agent role.

        Parameters
        ----------
        role : str
            Agent role.

        Returns
        -------
        str
            Role-specific JSON.
        """
        if role == "proposer":
            return '["candidate proposal"]'
        if role == "reviewer":
            return '{"passed": true, "blockers": [], "tests": []}'
        return '{"selected_candidate_id": "candidate-1", "rationale": "pass"}'


class FakeWebSearch:
    """Provide deterministic web results for integration tests."""

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Return one deterministic web result.

        Parameters
        ----------
        query : str
            Search query.
        limit : int
            Maximum result count.

        Returns
        -------
        list[dict[str, str]]
            One fake result.
        """
        return [{"title": "Example", "url": "https://example.com"}][:limit]


if __name__ == "__main__":
    unittest.main()


_FAILING_TEST = (
    "import unittest\n"
    "from solution import double\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_wrong(self):\n"
    "        self.assertEqual(double(2), 99)\n"
)
_FAILING_ENTRY = {
    "id": "heldout",
    "function": "double",
    "test": "test_fail.py",
}


class _RecordingGate:
    """Record gate commands and report success."""

    def __init__(self, calls: list) -> None:
        """Store the command record list.

        Parameters
        ----------
        calls : list
            List receiving commands.

        Returns
        -------
        None
            The gate is ready.
        """
        self.calls = calls

    def __call__(self, directory, command):
        """Record the command and report success.

        Parameters
        ----------
        directory : pathlib.Path
            Candidate directory.

        command : list[str]
            Docker command arguments.

        Returns
        -------
        dict
            Passing gate result.
        """
        self.calls.append(command)
        return {"passed": True, "score": 1.0}


def _search_config(**overrides) -> SearchConfig:
    """Build a no-Docker search configuration.

    Parameters
    ----------
    overrides : dict
        Configuration field overrides.

    Returns
    -------
    SearchConfig
        Search configuration.
    """
    fields = {"iterations": 1, "use_docker": False, "use_web_search": False}
    fields.update(overrides)
    return SearchConfig(**fields)


def _docker_config() -> SearchConfig:
    """Build a Docker configuration without a gate command.

    Parameters
    ----------
    None

    Returns
    -------
    SearchConfig
        One-iteration Docker configuration.
    """
    return SearchConfig(iterations=1, use_docker=True, use_web_search=False)


def _gate_config(command: str) -> SearchConfig:
    """Build a Docker configuration with a gate command.

    Parameters
    ----------
    command : str
        Gate shell command.

    Returns
    -------
    SearchConfig
        One-iteration Docker configuration.
    """
    return SearchConfig(
        iterations=1,
        use_docker=True,
        use_web_search=False,
        gate_command=command,
    )


def _local_gate_config(command: str) -> SearchConfig:
    """Build a configuration enabling the local gate.

    Parameters
    ----------
    command : str
        Gate shell command.

    Returns
    -------
    SearchConfig
        Local-gate configuration.
    """
    base = _gate_config(command)
    return replace(
        base,
        proposers_per_iteration=1,
        target_score=1.0,
        allow_local_gate=True,
    )


def _hard_config(hard: Path, baseline: bool) -> SearchConfig:
    """Build the hard-benchmark search configuration.

    Parameters
    ----------
    hard : pathlib.Path
        Hard benchmark root.

    baseline : bool
        Whether to run the baseline.

    Returns
    -------
    SearchConfig
        Hard-benchmark configuration.
    """
    base = {
        "iterations": 2,
        "proposers_per_iteration": 1,
        "target_score": 1.0,
    }
    base.update(_hard_manifests(hard))
    base["baseline"] = baseline
    return _search_config(**base)


def _manifest_path(name: str) -> str:
    """Return a benchmark manifest path.

    Parameters
    ----------
    name : str
        Benchmark split directory name.

    Returns
    -------
    str
        Absolute manifest path.
    """
    here = Path(__file__).resolve().parent
    return str(here.parent / "benchmarks" / name / "manifest.json")


def _held_out_config() -> SearchConfig:
    """Build a starter/held-out configuration.

    Parameters
    ----------
    None

    Returns
    -------
    SearchConfig
        Configuration with the held-out manifest attached.
    """
    return _search_config(
        proposers_per_iteration=1,
        target_score=1.0,
        task_manifest=_manifest_path("starter"),
        held_out_manifest=_manifest_path("heldout"),
    )


def _validation_config() -> SearchConfig:
    """Build a starter/validation configuration.

    Parameters
    ----------
    None

    Returns
    -------
    SearchConfig
        Configuration with the validation manifest attached.
    """
    return _search_config(
        proposers_per_iteration=1,
        target_score=1.0,
        task_manifest=_manifest_path("starter"),
        final_task_manifest=_manifest_path("validation"),
    )


def _hard_manifests(hard: Path) -> dict:
    """Build the hard-benchmark manifest fields.

    Parameters
    ----------
    hard : pathlib.Path
        Hard benchmark root.

    Returns
    -------
    dict
        Manifest path fields.
    """
    return {
        "task_manifest": str(hard / "search" / "manifest.json"),
        "final_task_manifest": str(hard / "validation" / "manifest.json"),
        "held_out_manifest": str(hard / "heldout" / "manifest.json"),
    }


def _run_in_temp(config, client, proposer):
    """Run a search in a temporary workspace.

    Parameters
    ----------
    config : SearchConfig
        Search configuration.

    client : object
        Chat-model double.

    proposer : collections.abc.Callable
        Proposer callable.

    Returns
    -------
    SearchResult
        Completed search result.
    """
    with tempfile.TemporaryDirectory() as directory:
        pipeline = SearchPipeline(config, client=client, workspace=directory)
        return pipeline.run("seed", proposer)


if __name__ == "__main__":
    unittest.main()
