"""Tests for adversarial tests, independence, and draft ensembling."""

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from meta_harness import agent as agent_module
from meta_harness.agent import Agent
from meta_harness.models import Candidate
from meta_harness.models import SearchConfig
from meta_harness.pipeline import SearchPipeline
from meta_harness.pipeline import _pareto_survivors
from scripts import ab_pi

_GOOD = "def double(x):\n    return x * 2\n"
_PASSING_TEST = """import unittest

from solution import double


class ReviewTests(unittest.TestCase):
    def test_triple(self) -> None:
        self.assertEqual(double(3), 6)
"""
_FAILING_TEST = """import unittest

from solution import double


class ReviewTests(unittest.TestCase):
    def test_triple(self) -> None:
        self.assertEqual(double(3), 7)
"""
_TASK_TEST = """import unittest

from solution import double


class DoubleTests(unittest.TestCase):
    def test_double(self) -> None:
        self.assertEqual(double(2), 4)
"""


def _manifest(root: Path) -> str:
    """Write a passing one-task manifest.

    Parameters
    ----------
    root : pathlib.Path
        Temporary directory.

    Returns
    -------
    str
        Manifest path.
    """
    (root / "test_double.py").write_text(_TASK_TEST, encoding="utf-8")
    return _write_manifest(root, "double", "test_double.py")


def _failing_manifest(root: Path) -> str:
    """Write a failing one-task manifest.

    Parameters
    ----------
    root : pathlib.Path
        Temporary directory.

    Returns
    -------
    str
        Manifest path.
    """
    source = _TASK_TEST.replace("), 4)", "), 99)")
    (root / "test_fail.py").write_text(source, encoding="utf-8")
    return _write_manifest(root, "failing_double", "test_fail.py")


def _write_manifest(root: Path, task_id: str, test_name: str) -> str:
    """Write a manifest referencing one test file.

    Parameters
    ----------
    root : pathlib.Path
        Temporary directory.

    task_id : str
        Task identifier.

    test_name : str
        Test filename relative to the manifest.

    Returns
    -------
    str
        Manifest path.
    """
    entry = {"id": task_id, "function": "double", "test": test_name}
    path = root / f"{task_id}.json"
    path.write_text(json.dumps([entry]), encoding="utf-8")
    return str(path)


def _pipeline(directory, final=False, observer=None):
    """Build a manifest-backed pipeline for tests.

    Parameters
    ----------
    directory : str
        Workspace directory.

    final : bool
        Whether the final gate uses a failing manifest.

    observer : callable or None
        Event observer.

    Returns
    -------
    SearchPipeline
        Configured pipeline.
    """
    root = Path(directory)
    search = _manifest(root)
    final_path = _failing_manifest(root) if final else search
    fields = _fields(search)
    fields["final_task_manifest"] = final_path
    return _search_pipeline(fields, directory, observer)


def _fields(search: str) -> dict:
    """Return base search configuration fields.

    Parameters
    ----------
    search : str
        Search manifest path.

    Returns
    -------
    dict
        Base configuration fields.
    """
    return {
        "task_manifest": search,
        "use_web_search": False,
        "use_docker": False,
    }


def _search_pipeline(fields, directory, observer):
    """Build a pipeline from configuration fields.

    Parameters
    ----------
    fields : dict
        Configuration fields.

    directory : str
        Workspace directory.

    observer : callable or None
        Event observer.

    Returns
    -------
    SearchPipeline
        Configured pipeline.
    """
    client = Mock()
    config = SearchConfig(**fields)
    return SearchPipeline(
        config, client=client, workspace=directory, observer=observer
    )


def _reviewed(code, test_source):
    """Build a reviewed candidate carrying one reviewer test.

    Parameters
    ----------
    code : str
        Candidate solution source.

    test_source : str
        Reviewer-generated unittest source.

    Returns
    -------
    Candidate
        Reviewed candidate.
    """
    review = {"passed": True, "blockers": [], "tests": [test_source]}
    return Candidate("c1", "test", code, review=review)


def _gated(pipeline, code):
    """Review and gate one candidate without reviewer tests.

    Parameters
    ----------
    pipeline : SearchPipeline
        Configured pipeline.

    code : str
        Candidate solution source.

    Returns
    -------
    Candidate
        Candidate after gate 1.
    """
    review = {"passed": True, "blockers": [], "tests": []}
    candidate = Candidate("c1", "test", code, review=review)
    return pipeline._dynamic_test(candidate, 1)


def _scored(candidate_id, score, elapsed):
    """Build a gated candidate with a score and elapsed time.

    Parameters
    ----------
    candidate_id : str
        Candidate identifier.

    score : float
        Candidate score.

    elapsed : float
        Gate elapsed seconds.

    Returns
    -------
    Candidate
        Candidate with gate data.
    """
    result = {"passed": True, "score": score, "elapsed": elapsed}
    return Candidate(candidate_id, "test", "p", score, {}, result)


def _final(candidate):
    """Mark a candidate as final-gate passed.

    Parameters
    ----------
    candidate : Candidate
        Candidate with gate data.

    Returns
    -------
    Candidate
        Candidate with ``final_passed`` set.
    """
    result = {**candidate.dynamic_test, "final_passed": True}
    return replace(candidate, dynamic_test=result)


class ReviewTestGateTests(unittest.TestCase):
    """Verify reviewer-generated tests are executed by gate 1."""

    def test_reviewer_test_failure_blocks_gate(self) -> None:
        """A failing reviewer test makes gate 1 fail.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            pipeline = _pipeline(directory)
            tested = pipeline._dynamic_test(_reviewed(_GOOD, _FAILING_TEST), 1)
        self.assertFalse(tested.dynamic_test["review_tests_passed"])
        self.assertFalse(tested.dynamic_test["passed"])
        self.assertEqual(tested.gate1["review_tests"], 1)

    def test_reviewer_test_success_keeps_gate(self) -> None:
        """A passing reviewer test keeps gate 1 passing.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            pipeline = _pipeline(directory)
            tested = pipeline._dynamic_test(_reviewed(_GOOD, _PASSING_TEST), 1)
        self.assertTrue(tested.dynamic_test["review_tests_passed"])
        self.assertTrue(tested.dynamic_test["passed"])


class IndependentGateTests(unittest.TestCase):
    """Verify gate 2 records independent evidence."""

    def test_gate_two_records_independence(self) -> None:
        """Gate 2 records consistency and differential data.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            pipeline = _pipeline(directory)
            candidate = _gated(pipeline, _GOOD)
            winner = _gated(pipeline, _GOOD)
            final = pipeline._final_dynamic_test(candidate, 1, winner)
        self._assert_independence(final)

    def _assert_independence(self, final) -> None:
        """Verify gate 2 evidence fields.

        Parameters
        ----------
        final : Candidate
            Candidate after gate 2.

        Returns
        -------
        None
        """
        self.assertTrue(final.gate2["consistent"])
        self.assertEqual(final.gate2["runs"], 2)
        self.assertEqual(final.gate2["incumbent_score"], 1.0)
        self.assertTrue(final.gate2["beats_incumbent"])
        self.assertTrue(final.dynamic_test["final_passed"])

    def test_disagreement_event_is_emitted(self) -> None:
        """A gate-1 pass with a gate-2 failure emits an event.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            events = []
            pipeline = _pipeline(directory, final=True, observer=events.append)
            final = pipeline._final_dynamic_test(_gated(pipeline, _GOOD), 1)
        names = [event["event"] for event in events]
        self.assertTrue(final.gate2["disagreement"])
        self.assertIn("gate_disagreement", names)


class ParetoAndRatchetTests(unittest.TestCase):
    """Verify Pareto filtering and incumbent ratcheting."""

    def test_pareto_drops_dominated_candidates(self) -> None:
        """A slower equal-score candidate is dominated.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        candidates = [
            _scored("fast", 1.0, 1.0),
            _scored("slow", 1.0, 2.0),
            _scored("low", 0.5, 0.5),
        ]
        survivors = _pareto_survivors(candidates)
        ids = [item.candidate_id for item in survivors]
        self.assertEqual(ids, ["fast", "low"])

    def test_ratchet_rejects_weaker_candidate(self) -> None:
        """A lower-scoring candidate never replaces the incumbent.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            pipeline = _pipeline(directory)
            winner = _final(_scored("best", 1.0, 1.0))
            weaker = _final(_scored("weak", 0.5, 0.1))
            self.assertIs(pipeline._best(winner, weaker), winner)

    def test_ratchet_accepts_cheaper_candidate(self) -> None:
        """An equal-score faster candidate replaces the incumbent.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            pipeline = _pipeline(directory)
            winner = _final(_scored("best", 1.0, 2.0))
            faster = _final(_scored("fast", 1.0, 1.0))
            self.assertIs(pipeline._best(winner, faster), faster)


class AdversarialDraftTests(unittest.TestCase):
    """Verify test-time draft ensembling."""

    def test_drafts_are_adjudicated(self) -> None:
        """Two drafts are produced and the adjudicator picks one.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = _DraftClient()
        agent = Agent(root=".", client=client, max_turns=1)
        with patch.dict(os.environ, _draft_env("2")):
            answer = agent.run("solve it")
        self.assertEqual(answer, "draft 2")
        self.assertEqual(client.chat_calls, 2)
        self.assertEqual(client.complete_calls, 1)

    def test_single_draft_when_disabled(self) -> None:
        """Adversarial mode is off unless configured.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = _DraftClient()
        agent = Agent(root=".", client=client, max_turns=1)
        with patch.dict(os.environ, _draft_env("0")):
            answer = agent.run("solve it")
        self.assertEqual(answer, "draft 1")
        self.assertEqual(client.chat_calls, 1)


class _DraftClient:
    """Return scripted drafts and one adjudicator choice."""

    def __init__(self) -> None:
        """Initialize call counters.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Counters are zeroed.
        """
        self.chat_calls = 0
        self.complete_calls = 0

    def chat(self, messages, tools):
        """Return the next scripted draft.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.

        tools : list[dict]
            Tool schemas.

        Returns
        -------
        dict
            Chat-completion response.
        """
        self.chat_calls += 1
        text = f"draft {self.chat_calls}"
        message = {"role": "assistant", "content": text}
        return {"choices": [{"message": message}]}

    def complete(self, system, user, temperature=0.2):
        """Return an adjudicator selection for the second draft.

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
            JSON selecting index 1.
        """
        self.complete_calls += 1
        return '{"selected_index": 1, "rationale": "second"}'


def _draft_env(drafts: str) -> dict:
    """Build an environment enabling draft ensembles.

    Parameters
    ----------
    drafts : str
        Draft count setting.

    Returns
    -------
    dict
        Environment overrides.
    """
    return {
        "HARNESS_ADVERSARIAL_DRAFTS": drafts,
        "HARNESS_ANSWER_REVIEW": "0",
    }


_REPEAT_ROWS = (
    {
        "id": "x",
        "harness": 1.0,
        "pi": 0.0,
        "harness_s": 1.0,
        "pi_s": 2.0,
        "harness_status": "ok",
        "pi_status": "ok",
    },
    {
        "id": "x",
        "harness": 0.0,
        "pi": 1.0,
        "harness_s": 3.0,
        "pi_s": 4.0,
        "harness_status": "timeout",
        "pi_status": "ok",
    },
)


def _repeat_report(directory):
    """Run a repeated comparison with scripted rows.

    Parameters
    ----------
    directory : pathlib.Path
        Temporary directory.

    Returns
    -------
    dict
        Comparison report.
    """
    manifest = _write_manifest(directory, "x", "t.py")
    with patch.object(ab_pi, "_task_row", side_effect=list(_REPEAT_ROWS)):
        return ab_pi.compare(manifest, ["a"], ["b"], 5, repeats=2)


def _compare_ab(directory):
    """Run the A/B comparison with patched collaborators.

    Parameters
    ----------
    directory : pathlib.Path
        Temporary directory.

    Returns
    -------
    tuple
        Runner mock and comparison report.
    """
    manifest = _write_manifest(directory, "double", "test_double.py")
    with patch.object(
        ab_pi, "_run_status", return_value=("", 0.0, "ok")
    ) as runner:
        with patch.object(ab_pi, "score_answer", side_effect=[1.0, 0.0]):
            report = ab_pi.compare(manifest, ["ours"], ["pi"], 5)
    return runner, report


class AnswerTestRepairTests(unittest.TestCase):
    """Verify reviewer tests can trigger one workspace repair."""

    def test_workspace_tests_trigger_repair(self) -> None:
        """A failing reviewer test causes one repair turn.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = _RepairClient()
        with tempfile.TemporaryDirectory() as directory:
            answer = _run_repair(
                directory, client, [(False, "boom"), (True, "")]
            )
        self.assertEqual(answer, "repaired answer")
        self.assertEqual(client.chat_calls, 2)
        self.assertEqual(client.complete_calls, 1)

    def test_failed_repair_restores_workspace(self) -> None:
        """A repair that still fails restores the snapshot.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = _RepairClient()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(agent_module, "_restore_workspace") as restore:
                answer = _run_repair(
                    directory, client, [(False, "boom"), (False, "worse")]
                )
        self.assertEqual(answer, "first answer")
        restore.assert_called_once()

    def test_restore_workspace_replaces_contents(self) -> None:
        """Restoring replaces the workspace files.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            root, snap = _snapshot_pair(Path(directory))
            agent_module._restore_workspace(root, snap)
            restored = (root / "a.py").read_text(encoding="utf-8")
        self.assertEqual(restored, "old")

    def test_passing_tests_skip_repair(self) -> None:
        """Passing reviewer tests leave the answer untouched.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = _RepairClient()
        with tempfile.TemporaryDirectory() as directory:
            answer = _run_repair(directory, client, [(True, "")])
        self.assertEqual(answer, "first answer")
        self.assertEqual(client.chat_calls, 1)

    def test_workspace_tests_disabled_by_default(self) -> None:
        """Answer-time tests are off unless configured.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        client = _RepairClient()
        with tempfile.TemporaryDirectory() as directory:
            agent = Agent(root=directory, client=client, max_turns=1)
            with patch.dict(os.environ, _answer_env("0")):
                answer = agent.run("fix it")
        self.assertEqual(answer, "first answer")
        self.assertEqual(client.complete_calls, 0)

    def test_test_sources_filters_values(self) -> None:
        """Only non-empty string tests survive decoding.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(
            agent_module._test_sources('{"tests": ["a", "", 3]}'), ["a"]
        )
        self.assertEqual(agent_module._test_sources("not json"), [])


class _RepairClient:
    """Return scripted answers and one reviewer test."""

    def __init__(self) -> None:
        """Initialize call counters.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Counters are zeroed.
        """
        self.chat_calls = 0
        self.complete_calls = 0

    def chat(self, messages, tools):
        """Return the next scripted answer.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.

        tools : list[dict]
            Tool schemas.

        Returns
        -------
        dict
            Chat-completion response.
        """
        self.chat_calls += 1
        text = "first answer" if self.chat_calls == 1 else "repaired answer"
        return {
            "choices": [{"message": {"role": "assistant", "content": text}}]
        }

    def complete(self, system, user, temperature=0.2):
        """Return one reviewer test source.

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
            JSON with one unittest source.
        """
        self.complete_calls += 1
        return '{"tests": ["import unittest"]}'


def _answer_env(value: str) -> dict:
    """Build an environment for answer-time tests.

    Parameters
    ----------
    value : str
        ``HARNESS_ANSWER_TESTS`` setting.

    Returns
    -------
    dict
        Environment overrides.
    """
    return {
        "HARNESS_ANSWER_TESTS": value,
        "HARNESS_ANSWER_REVIEW": "0",
        "HARNESS_ADVERSARIAL_DRAFTS": "0",
    }


def _run_repair(directory, client, results=None):
    """Run an agent with scripted workspace test results.

    Parameters
    ----------
    directory : str
        Workspace directory.

    client : _RepairClient
        Scripted chat-model double.

    results : list or None
        Side effects for ``run_workspace_tests``.

    Returns
    -------
    str
        Final agent answer.
    """
    agent = Agent(root=directory, client=client, max_turns=1)
    effects = results if results is not None else [(True, "")]
    with patch.object(
        agent_module, "run_workspace_tests", side_effect=effects
    ):
        with patch.dict(os.environ, _answer_env("1")):
            return agent.run("fix it")


def _snapshot_pair(directory):
    """Build a workspace and snapshot with different contents.

    Parameters
    ----------
    directory : pathlib.Path
        Temporary directory.

    Returns
    -------
    tuple
        Workspace root and snapshot directory.
    """
    root = directory / "root"
    snap = directory / "snap"
    root.mkdir()
    snap.mkdir()
    (root / "a.py").write_text("new", encoding="utf-8")
    (snap / "a.py").write_text("old", encoding="utf-8")
    return root, snap


class AbRunnerTests(unittest.TestCase):
    """Verify the Pi A/B runner schema and scoring."""

    def test_extracts_fenced_code(self) -> None:
        """Fenced Python blocks are preferred.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        answer = "text\n```python\nx = 1\n```\nmore"
        self.assertEqual(ab_pi.extract_code(answer), "x = 1")

    def test_joins_multiple_code_blocks(self) -> None:
        """Multiple fenced blocks are concatenated.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        answer = "```python\nx = 1\n```\ntext\n```python\ny = 2\n```"
        self.assertEqual(ab_pi.extract_code(answer), "x = 1\n\ny = 2")

    def test_repeats_average_runs(self) -> None:
        """Repeated runs are averaged per task.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            report = _repeat_report(Path(directory))
        row = report["tasks"][0]
        self.assertEqual(row["harness"], 0.5)
        self.assertEqual(row["harness_timeouts"], 1)

    def test_report_averages_tasks(self) -> None:
        """The report averages per-task rates.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        rows = [
            {"id": "a", "harness": 1.0, "pi": 0.0},
            {"id": "b", "harness": 0.0, "pi": 1.0},
        ]
        report = ab_pi._report(rows)
        self.assertEqual(report["harness"], 0.5)
        self.assertEqual(report["delta"], 0.0)

    def test_compare_calls_both_commands(self) -> None:
        """Both agent commands run for each task.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with tempfile.TemporaryDirectory() as directory:
            runner, report = _compare_ab(Path(directory))
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(report["harness"], 1.0)
        self.assertEqual(report["delta"], 1.0)


if __name__ == "__main__":
    unittest.main()
