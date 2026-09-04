"""Offline tests for adversarial search control flow."""

import tempfile
import unittest
from functools import partial
from pathlib import Path

from meta_harness.models import Candidate, SearchConfig
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

    def test_blocked_review_does_not_score_candidate(self) -> None:
        """Exclude candidates blocked by adversarial review.

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

    def test_model_json_parser_accepts_fenced_proposals(self) -> None:
        """Accept explanatory text around fenced proposal JSON.

        Returns
        -------
        None
            Assertions pass when proposal JSON is recovered.
        """
        pipeline = SearchPipeline(
            SearchConfig(use_web_search=False), client=self.FakeClient()
        )
        raw = 'Here you go:\n```json\n["fix"]\n```'
        proposals = pipeline._proposal_items([], pipeline._json_text(raw))
        self.assertEqual(proposals[0].proposal, "fix")

    def test_non_json_agent_output_has_safe_stage_fallbacks(self) -> None:
        """Keep malformed agent responses inside the pipeline.

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

        Returns
        -------
        None
            Assertions pass when every agent stage is called.
        """
        client, result = self._run_full_search()
        self.assertEqual(client.roles, ["proposer", "reviewer", "adjudicator"])
        self.assertTrue(result.stopped_on_target)
        self.assertEqual(result.history[0].dynamic_test["final_passed"], True)

    def _run_full_search(self):
        """Run the complete mocked agent pipeline.

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
