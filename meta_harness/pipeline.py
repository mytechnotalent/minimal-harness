"""Orchestrate proposal, review, testing, adjudication, and cycling."""

import json
from pathlib import Path
from typing import Callable

from .docker_gate import DockerGate
from .models import Candidate, SearchConfig, SearchResult
from .openrouter import OpenRouterClient
from .web_search import WebSearchClient

Proposer = Callable[[str, list[Candidate]], list[Candidate]]


class SearchPipeline:
    """Run the Minimal Harness candidate search loop."""

    def __init__(
        self,
        config: SearchConfig,
        client: OpenRouterClient | None = None,
        workspace: Path | str = "runs",
        web_search: WebSearchClient | None = None,
    ) -> None:
        """Initialize the search pipeline.

        Parameters
        ----------
        config : SearchConfig
            Search and gate settings.
        client : OpenRouterClient or None
            Optional agent client.
        workspace : pathlib.Path or str
            Artifact directory.

        Returns
        -------
        None
            This initializer mutates the pipeline instance.
        """
        self.config = config
        self.client = client or OpenRouterClient()
        self.workspace = Path(workspace)
        self.gate = DockerGate(config.docker_image)
        self.web_search = web_search or WebSearchClient()

    def run(self, seed: str, proposer: Proposer | None = None) -> SearchResult:
        """Cycle candidates until target or budget exhaustion.

        Parameters
        ----------
        seed : str
            Initial task description.
        proposer : Proposer or None
            Optional offline proposer.

        Returns
        -------
        SearchResult
            Search history, winner, and stop reason.
        """
        history, winner = self._search(seed, proposer)
        reached = self._target_reached(winner)
        reason = "target score reached" if reached else self._stop_reason()
        return SearchResult(winner, tuple(history), reached, reason)

    def _search(
        self, seed: str, proposer: Proposer | None
    ) -> tuple[list[Candidate], Candidate | None]:
        """Run the configured iteration budget.

        Parameters
        ----------
        seed : str
            Initial task description.
        proposer : Proposer or None
            Optional offline proposer.

        Returns
        -------
        tuple[list[Candidate], Candidate or None]
            History and best candidate.
        """
        history, winner = [], None
        self.workspace.mkdir(parents=True, exist_ok=True)
        for iteration in range(1, self.config.iterations + 1):
            history, winner = self._iteration(
                seed, history, winner, proposer, iteration
            )
        return history, winner

    def _iteration(
        self,
        seed: str,
        history: list[Candidate],
        winner: Candidate | None,
        proposer: Proposer | None,
        iteration: int,
    ) -> tuple[list[Candidate], Candidate | None]:
        """Run one proposal-to-final-gate iteration.

        Parameters
        ----------
        seed : str
            Initial task description.
        history : list[Candidate]
            Prior records.
        winner : Candidate or None
            Current best candidate.
        proposer : Proposer or None
            Optional offline proposer.
        iteration : int
            Current iteration number.

        Returns
        -------
        tuple[list[Candidate], Candidate or None]
            Updated history and winner.
        """
        candidates = self._proposals(seed, history, proposer)
        evaluated = self._evaluate_all(candidates, history, iteration)
        if not evaluated:
            return history, winner
        selected = self._adjudicate(evaluated, history)
        final = self._final_dynamic_test(selected, iteration)
        return self._record(evaluated, final, history, winner, iteration)

    def _evaluate_all(
        self,
        candidates: list[Candidate],
        history: list[Candidate],
        iteration: int,
    ) -> list[Candidate]:
        """Evaluate every candidate in an iteration.

        Parameters
        ----------
        candidates : list[Candidate]
            Candidates to evaluate.
        history : list[Candidate]
            Prior records.
        iteration : int
            Current iteration number.

        Returns
        -------
        list[Candidate]
            Evaluated candidates.
        """
        return [
            self._evaluate(item, history, iteration) for item in candidates
        ]

    def _proposals(
        self, seed: str, history: list[Candidate], proposer: Proposer | None
    ) -> list[Candidate]:
        """Obtain limited proposals for an iteration.

        Parameters
        ----------
        seed : str
            Initial task description.
        history : list[Candidate]
            Prior records.
        proposer : Proposer or None
            Optional offline proposer.

        Returns
        -------
        list[Candidate]
            Candidates to evaluate.
        """
        source = (
            proposer(seed, history)
            if proposer
            else self._propose(seed, history)
        )
        return source[: self.config.proposers_per_iteration]

    def _evaluate(
        self, candidate: Candidate, history: list[Candidate], iteration: int
    ) -> Candidate:
        """Review and first-test one candidate.

        Parameters
        ----------
        candidate : Candidate
            Candidate under evaluation.
        history : list[Candidate]
            Prior records.
        iteration : int
            Current iteration number.

        Returns
        -------
        Candidate
            Reviewed and first-tested candidate.
        """
        return self._dynamic_test(self._review(candidate, history), iteration)

    def _propose(self, seed: str, history: list[Candidate]) -> list[Candidate]:
        """Ask OpenRouter for candidate proposals.

        Parameters
        ----------
        seed : str
            Initial task description.
        history : list[Candidate]
            Prior records.

        Returns
        -------
        list[Candidate]
            Parsed proposals.
        """
        context = self._json(
            {"seed": seed, "history": history, "web": self._web(seed)}
        )
        raw = self.client.complete(
            "You are a proposer. Return a JSON array of proposals.", context
        )
        return self._proposal_items(history, raw)

    def _web(self, seed: str) -> list[dict[str, str]]:
        """Collect optional web context for the proposer.

        Parameters
        ----------
        seed : str
            Search query derived from the seed task.

        Returns
        -------
        list[dict[str, str]]
            Search results, or an empty list when disabled or unavailable.
        """
        if not self.config.use_web_search:
            return []
        return self.web_search.search(seed)

    def _proposal_items(
        self, history: list[Candidate], raw: str
    ) -> list[Candidate]:
        """Convert a proposal response into candidates.

        Parameters
        ----------
        history : list[Candidate]
            Prior records.
        raw : str
            JSON proposal array.

        Returns
        -------
        list[Candidate]
            Parsed candidates.
        """
        values = self._proposal_values(raw)
        return [
            Candidate(
                f"candidate-{len(history) + i + 1}", "openrouter", str(item)
            )
            for i, item in enumerate(values)
        ]

    def _proposal_values(self, raw: str) -> list:
        """Convert model output into proposal values.

        Parameters
        ----------
        raw : str
            Model response.

        Returns
        -------
        list
            Parsed proposals or one raw-text proposal.
        """
        try:
            value = self._json_value(raw)
        except ValueError:
            return [raw.strip()]
        return value if isinstance(value, list) else [value]

    def _review(
        self, candidate: Candidate, history: list[Candidate]
    ) -> Candidate:
        """Ask an adversarial reviewer to inspect a candidate.

        Parameters
        ----------
        candidate : Candidate
            Candidate under review.
        history : list[Candidate]
            Prior records.

        Returns
        -------
        Candidate
            Candidate with review data.
        """
        return self._with_review(
            candidate, self._review_data(candidate, history)
        )

    def _review_data(
        self, candidate: Candidate, history: list[Candidate]
    ) -> dict:
        """Request and decode review data.

        Parameters
        ----------
        candidate : Candidate
            Candidate under review.
        history : list[Candidate]
            Prior records.

        Returns
        -------
        dict
            Decoded review object.
        """
        context = self._json({"candidate": candidate, "history": history})
        raw = self.client.complete(
            "You are an adversarial reviewer. Return JSON.", context
        )
        return self._review_value(raw)

    def _review_value(self, raw: str) -> dict:
        """Decode review output with a blocking fallback.

        Parameters
        ----------
        raw : str
            Model response.

        Returns
        -------
        dict
            Review result.
        """
        try:
            value = self._json_value(raw)
        except ValueError:
            return {"passed": False, "blockers": ["invalid JSON"], "tests": []}
        return value if isinstance(value, dict) else {"passed": False}

    def _dynamic_test(self, candidate: Candidate, iteration: int) -> Candidate:
        """Run the first dynamic gate.

        Parameters
        ----------
        candidate : Candidate
            Candidate with review data.
        iteration : int
            Current iteration number.

        Returns
        -------
        Candidate
            Candidate with score and gate data.
        """
        result = self._test_result(candidate, iteration)
        return self._with_test(
            candidate, result, self._score(candidate, result)
        )

    def _score(self, candidate: Candidate, result: dict) -> float | None:
        """Choose an existing or gate-provided score.

        Parameters
        ----------
        candidate : Candidate
            Candidate with an optional score.
        result : dict
            Dynamic gate result.

        Returns
        -------
        float or None
            Selected score.
        """
        return (
            candidate.score
            if candidate.score is not None
            else result.get("score")
        )

    def _test_result(self, candidate: Candidate, iteration: int) -> dict:
        """Choose the first-gate result source.

        Parameters
        ----------
        candidate : Candidate
            Candidate with review data.
        iteration : int
            Current iteration.

        Returns
        -------
        dict
            First-gate result.
        """
        if not candidate.review.get("passed", False):
            return self._blocked_result()
        return self._run_gate(candidate, iteration)

    def _run_gate(self, candidate: Candidate, iteration: int) -> dict:
        """Run or simulate the first dynamic gate.

        Parameters
        ----------
        candidate : Candidate
            Candidate to test.
        iteration : int
            Current iteration number.

        Returns
        -------
        dict
            First-gate result.
        """
        if not self.config.use_docker:
            return {
                "passed": True,
                "score": 0.0,
                "error": "Docker disabled; no score assigned",
            }
        return self._run_candidate_gate(candidate, iteration)

    def _run_candidate_gate(
        self, candidate: Candidate, iteration: int
    ) -> dict:
        """Run the first gate for a candidate.

        Parameters
        ----------
        candidate : Candidate
            Candidate to test.
        iteration : int
            Current iteration number.

        Returns
        -------
        dict
            First-gate result.
        """
        directory = self._candidate_dir(candidate, iteration)
        (directory / "proposal.txt").write_text(candidate.proposal)
        return self.gate.run(
            directory, ["sh", "-c", "test -s /candidate/proposal.txt"]
        )

    def _adjudicate(
        self, candidates: list[Candidate], history: list[Candidate]
    ) -> Candidate:
        """Ask the adjudicator to select a survivor.

        Parameters
        ----------
        candidates : list[Candidate]
            First-gate results.
        history : list[Candidate]
            Prior records.

        Returns
        -------
        Candidate
            Selected candidate.
        """
        raw = self.client.complete(
            "You are the adjudicator. Return JSON.",
            self._json({"candidates": candidates, "history": history}),
        )
        return self._select(candidates, self._selection_id(raw))

    def _selection_id(self, raw: str) -> str | None:
        """Extract a selection from adjudicator output.

        Parameters
        ----------
        raw : str
            Model response.

        Returns
        -------
        str or None
            Selected candidate identifier.
        """
        return self._selection_value(raw)

    def _selection_value(self, raw: str) -> str | None:
        """Decode a selection or return no selection.

        Parameters
        ----------
        raw : str
            Model response.

        Returns
        -------
        str or None
            Candidate identifier.
        """
        try:
            value = self._json_value(raw)
        except ValueError:
            return None
        return self._candidate_id(value)

    def _candidate_id(self, value: object) -> str | None:
        """Read a selected candidate identifier from decoded JSON.

        Parameters
        ----------
        value : object
            Decoded adjudicator response.

        Returns
        -------
        str or None
            Selected candidate identifier.
        """
        return (
            value.get("selected_candidate_id")
            if isinstance(value, dict)
            else None
        )

    def _json_text(self, raw: str) -> str:
        """Extract a JSON proposal array from model output.

        Parameters
        ----------
        raw : str
            Model response containing JSON.

        Returns
        -------
        str
            Normalized JSON array text.
        """
        value = self._json_value(raw)
        if not isinstance(value, list):
            raise ValueError("proposer response must be a JSON array")
        return json.dumps(value)

    def _json_value(self, raw: str):
        """Decode JSON embedded in model output.

        Parameters
        ----------
        raw : str
            Model response containing JSON.

        Returns
        -------
        object
            Decoded JSON value.
        """
        text = raw.strip().replace("```json", "").replace("```", "")
        return self._scan_json(text)

    def _scan_json(self, text: str):
        """Scan text for the first valid JSON value.

        Parameters
        ----------
        text : str
            Cleaned model response.

        Returns
        -------
        object
            Decoded JSON value.
        """
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character not in "[{":
                continue
            value = self._decode_at(decoder, text, index)
            if value is not None:
                return value
        raise ValueError("model response did not contain valid JSON")

    def _decode_at(self, decoder: json.JSONDecoder, text: str, index: int):
        """Try to decode JSON beginning at one text position.

        Parameters
        ----------
        decoder : json.JSONDecoder
            Decoder used for the attempt.
        text : str
            Response text.
        index : int
            Candidate starting position.

        Returns
        -------
        object or None
            Decoded value, or None when decoding fails.
        """
        try:
            return decoder.raw_decode(text[index:])[0]
        except json.JSONDecodeError:
            return None

    def _select(
        self, candidates: list[Candidate], selected: str | None
    ) -> Candidate:
        """Select a valid candidate or highest score.

        Parameters
        ----------
        candidates : list[Candidate]
            First-gate results.
        selected : str or None
            Requested candidate identifier.

        Returns
        -------
        Candidate
            Selected candidate.
        """
        valid = self._valid_selection(candidates, selected)
        return (
            valid[0]
            if valid
            else max(candidates, key=lambda item: item.score or 0.0)
        )

    def _valid_selection(
        self, candidates: list[Candidate], selected: str | None
    ) -> list[Candidate]:
        """Find the passing selected candidate.

        Parameters
        ----------
        candidates : list[Candidate]
            First-gate results.
        selected : str or None
            Requested identifier.

        Returns
        -------
        list[Candidate]
            Matching passing candidates.
        """
        return [
            item
            for item in candidates
            if item.candidate_id == selected
            and item.dynamic_test.get("passed")
        ]

    def _final_dynamic_test(
        self, candidate: Candidate, iteration: int
    ) -> Candidate:
        """Run the final dynamic gate.

        Parameters
        ----------
        candidate : Candidate
            Adjudicated candidate.
        iteration : int
            Current iteration number.

        Returns
        -------
        Candidate
            Candidate with final-gate data.
        """
        result = (
            {"final_passed": False}
            if not candidate.dynamic_test.get("passed")
            else self._final_gate(candidate, iteration)
        )
        return self._with_test(candidate, {**candidate.dynamic_test, **result})

    def _final_gate(self, candidate: Candidate, iteration: int) -> dict:
        """Run or simulate the final dynamic gate.

        Parameters
        ----------
        candidate : Candidate
            Candidate to test.
        iteration : int
            Current iteration number.

        Returns
        -------
        dict
            Final-gate result.
        """
        if not self.config.use_docker:
            return {
                "final_passed": True,
                "error": "Docker disabled; final gate simulated",
            }
        return self._final_docker_gate(candidate, iteration)

    def _final_docker_gate(self, candidate: Candidate, iteration: int) -> dict:
        """Run the final Docker gate.

        Parameters
        ----------
        candidate : Candidate
            Candidate to test.
        iteration : int
            Current iteration number.

        Returns
        -------
        dict
            Final-gate result.
        """
        result = self.gate.run(
            self._candidate_dir(candidate, iteration),
            ["sh", "-c", "test -s /candidate/proposal.txt"],
        )
        return {**result, "final_passed": result.get("passed", False)}

    def _record(
        self,
        evaluated: list[Candidate],
        final: Candidate,
        history: list[Candidate],
        winner: Candidate | None,
        iteration: int,
    ) -> tuple[list[Candidate], Candidate | None]:
        """Record results and update the winner.

        Parameters
        ----------
        evaluated : list[Candidate]
            First-gate results.
        final : Candidate
            Final-gate result.
        history : list[Candidate]
            Mutable history.
        winner : Candidate or None
            Current winner.
        iteration : int
            Current iteration number.

        Returns
        -------
        tuple[list[Candidate], Candidate or None]
            Updated history and winner.
        """
        for item in evaluated:
            completed = (
                final if item.candidate_id == final.candidate_id else item
            )
            history.append(completed)
            self._write_artifact(iteration, completed)
        return history, self._best(winner, final)

    def _best(
        self, winner: Candidate | None, candidate: Candidate
    ) -> Candidate | None:
        """Keep the highest-scoring final-passed candidate.

        Parameters
        ----------
        winner : Candidate or None
            Current winner.
        candidate : Candidate
            Candidate to compare.

        Returns
        -------
        Candidate or None
            Updated winner.
        """
        if not candidate.dynamic_test.get("final_passed"):
            return winner
        return (
            candidate
            if winner is None
            or (candidate.score or 0.0) > (winner.score or 0.0)
            else winner
        )

    def _candidate_dir(self, candidate: Candidate, iteration: int) -> Path:
        """Create a candidate artifact directory.

        Parameters
        ----------
        candidate : Candidate
            Candidate being evaluated.
        iteration : int
            Current iteration number.

        Returns
        -------
        pathlib.Path
            Candidate directory.
        """
        directory = (
            self.workspace / f"iteration-{iteration}" / candidate.candidate_id
        )
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _write_artifact(self, iteration: int, candidate: Candidate) -> None:
        """Persist one candidate artifact.

        Parameters
        ----------
        iteration : int
            Current iteration number.
        candidate : Candidate
            Candidate record.

        Returns
        -------
        None
            Artifact is written to disk.
        """
        path = self._candidate_dir(candidate, iteration) / "candidate.json"
        path.write_text(json.dumps(candidate.__dict__, indent=2, default=str))

    def _target_reached(self, winner: Candidate | None) -> bool:
        """Check whether the target is reached.

        Parameters
        ----------
        winner : Candidate or None
            Current winner.

        Returns
        -------
        bool
            Whether the target is reached.
        """
        return (
            winner is not None
            and (winner.score or 0.0) >= self.config.target_score
        )

    def _stop_reason(self) -> str:
        """Describe budget exhaustion.

        Returns
        -------
        str
            Human-readable stop reason.
        """
        suffix = (
            " (Docker gate disabled)" if not self.config.use_docker else ""
        )
        return f"iteration budget exhausted{suffix}"

    def _json(self, value: dict) -> str:
        """Serialize agent context.

        Parameters
        ----------
        value : dict
            Context to serialize.

        Returns
        -------
        str
            JSON serialization.
        """
        return json.dumps(value, default=lambda item: item.__dict__)

    def _with_review(self, candidate: Candidate, review: dict) -> Candidate:
        """Attach review data.

        Parameters
        ----------
        candidate : Candidate
            Candidate under review.
        review : dict
            Parsed review object.

        Returns
        -------
        Candidate
            Updated candidate.
        """
        return Candidate(
            candidate.candidate_id,
            candidate.source,
            candidate.proposal,
            review=review,
        )

    def _with_test(
        self, candidate: Candidate, result: dict, score: float | None = None
    ) -> Candidate:
        """Attach dynamic-test data.

        Parameters
        ----------
        candidate : Candidate
            Candidate under testing.
        result : dict
            Test result.
        score : float or None
            Candidate score.

        Returns
        -------
        Candidate
            Updated candidate.
        """
        return Candidate(
            candidate.candidate_id,
            candidate.source,
            candidate.proposal,
            score,
            candidate.review,
            result,
        )

    def _blocked_result(self) -> dict:
        """Build a review-block result.

        Returns
        -------
        dict
            Failed result with zero score.
        """
        return {
            "passed": False,
            "score": 0.0,
            "error": "adversarial review blocked candidate",
        }
