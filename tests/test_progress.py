"""Offline tests for live progress events and dashboard state."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from meta_harness.models import SearchConfig
from meta_harness.pipeline import SearchPipeline
from meta_harness.progress import ProgressState, ProgressTUI


class RecordingClient:
    """Minimal chat-model double returning canned stage responses."""

    def __init__(self) -> None:
        """Initialize usage counters.

        Returns
        -------
        None
            This initializer mutates the instance.
        """
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return a canned response chosen by system prompt.

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
            Canned JSON response.
        """
        self.call_count += 1
        if "proposer" in system:
            return '["print(1)"]'
        if "reviewer" in system:
            return '{"passed": true, "blockers": [], "tests": []}'
        return '{"selected_candidate_id": "candidate-1"}'

    def usage_summary(self) -> str:
        """Return a usage summary line.

        Returns
        -------
        str
            Usage summary.
        """
        return f"calls={self.call_count}"


def _config() -> SearchConfig:
    """Return a one-iteration offline search configuration.

    Returns
    -------
    SearchConfig
        Configuration with Docker and web search disabled.
    """
    return SearchConfig(
        iterations=1,
        proposers_per_iteration=1,
        target_score=1.0,
        use_docker=False,
        use_web_search=False,
    )


class PipelineEventTests(unittest.TestCase):
    """Verify the pipeline emits progress events and honors cancellation."""

    def _pipeline(self, workspace: str, **kwargs) -> SearchPipeline:
        """Build a pipeline wired to a recording client.

        Parameters
        ----------
        workspace : str
            Artifact directory.
        **kwargs
            Extra constructor arguments.

        Returns
        -------
        SearchPipeline
            Configured pipeline.
        """
        return SearchPipeline(
            _config(),
            client=RecordingClient(),
            workspace=Path(workspace),
            **kwargs,
        )

    def test_emits_expected_event_sequence(self) -> None:
        """A full iteration emits every dashboard event exactly once.

        Returns
        -------
        None
            Assertions pass when all events are present.
        """
        events: list[dict] = []
        with tempfile.TemporaryDirectory() as workspace:
            pipeline = self._pipeline(workspace, observer=events.append)
            pipeline.run("solve the seed")
        names = [event["event"] for event in events]
        expected = (
            "run_started",
            "iteration_started",
            "stage_started",
            "stage_finished",
            "reviewed",
            "gate1",
            "adjudicated",
            "gate2",
            "candidate_recorded",
            "iteration_finished",
            "run_finished",
        )
        for name in expected:
            self.assertIn(name, names)
        self.assertEqual(names[0], "run_started")
        self.assertEqual(names[-1], "run_finished")

    def test_cancellation_stops_run(self) -> None:
        """A stopped predicate ends the run and reports cancellation.

        Returns
        -------
        None
            Assertions pass when cancellation is reported.
        """
        events: list[dict] = []
        with tempfile.TemporaryDirectory() as workspace:
            pipeline = self._pipeline(
                workspace, observer=events.append, should_stop=lambda: True
            )
            result = pipeline.run("solve the seed")
        self.assertEqual(result.stop_reason, "cancelled by user")
        self.assertIsNone(result.winner)
        self.assertTrue(events[-1]["cancelled"])
        self.assertNotIn("iteration_started", [e["event"] for e in events])


class ProgressStateTests(unittest.TestCase):
    """Verify event reduction into dashboard state."""

    def _state(self) -> ProgressState:
        """Return a state reducer for a two-iteration run.

        Returns
        -------
        ProgressState
            Empty dashboard state.
        """
        return ProgressState(2, "seed")

    def test_tracks_candidate_and_winner(self) -> None:
        """Events populate the candidate table and final winner.

        Returns
        -------
        None
            Assertions pass when state matches the events.
        """
        state = self._state()
        for event in self._sequence():
            state.apply(event)
        self.assertEqual(state.iteration, 1)
        self.assertTrue(state.done)
        self.assertEqual(state.winner_id, "candidate-1")
        self.assertEqual(state.winner_score, 0.5)
        self.assertTrue(state.candidates["candidate-1"]["final"])
        self.assertTrue(state.log)

    def _sequence(self) -> list[dict]:
        """Return a representative event sequence.

        Returns
        -------
        list[dict]
            Ordered progress events.
        """
        return [
            {"event": "run_started", "iterations": 2},
            {"event": "iteration_started", "iteration": 1},
            {"event": "stage_started", "stage": "proposer"},
            {
                "event": "reviewed",
                "candidate_id": "candidate-1",
                "passed": True,
            },
            {"event": "gate1", "candidate_id": "candidate-1", "score": 0.5},
            {"event": "adjudicated", "selected": "candidate-1"},
            {
                "event": "gate2",
                "candidate_id": "candidate-1",
                "final_passed": True,
            },
            {
                "event": "candidate_recorded",
                "candidate_id": "candidate-1",
                "review_passed": True,
                "gate_passed": True,
                "final_passed": True,
                "score": 0.5,
            },
            {"event": "iteration_finished", "winner_id": "candidate-1"},
            {
                "event": "run_finished",
                "winner_id": "candidate-1",
                "winner_score": 0.5,
                "stop_reason": "target score reached",
            },
        ]

    def test_cancel_flag_is_recorded(self) -> None:
        """A cancelled terminal event latches the cancelled flag.

        Returns
        -------
        None
            Assertions pass when the flag is set.
        """
        state = self._state()
        state.apply(
            {
                "event": "run_finished",
                "stop_reason": "cancelled by user",
                "cancelled": True,
            }
        )
        self.assertTrue(state.cancelled)
        self.assertTrue(state.done)


class ProgressTUITests(unittest.TestCase):
    """Verify dashboard text helpers without opening a terminal."""

    def _tui(self) -> ProgressTUI:
        """Return a dashboard backed by a stubbed pipeline.

        Returns
        -------
        ProgressTUI
            Dashboard instance.
        """
        pipeline = Mock()
        pipeline.config.iterations = 3
        pipeline.client.usage_summary.return_value = "calls=2"
        return ProgressTUI(pipeline, "seed")

    def test_status_line_reports_iteration_and_stage(self) -> None:
        """The status line shows iteration, stage, and elapsed time.

        Returns
        -------
        None
            Assertions pass when the text is composed.
        """
        tui = self._tui()
        tui.state.iteration, tui.state.stage = 1, "proposer"
        text = tui._status_text()
        self.assertIn("1/3", text)
        self.assertIn("proposer", text)

    def test_hint_switches_to_quit_when_done(self) -> None:
        """The footer offers cancel while running and quit when done.

        Returns
        -------
        None
            Assertions pass when the hint changes.
        """
        tui = self._tui()
        self.assertIn("cancel", tui._hint())
        tui.state.done = True
        self.assertIn("quit", tui._hint())


class OptimizeDispatchTests(unittest.TestCase):
    """Verify --optimize selects the dashboard only on a terminal."""

    def test_plain_output_when_not_a_terminal(self) -> None:
        """Piped output falls back to the plain runner.

        Returns
        -------
        None
            Assertions pass when the TUI is skipped.
        """
        from meta_harness import cli

        with (
            patch.object(cli, "SearchPipeline"),
            patch.object(cli, "_config"),
            patch.object(cli, "_use_progress", return_value=False),
            patch.object(cli, "_run_optimize_plain") as plain,
            patch.object(cli, "ProgressTUI") as tui,
        ):
            cli._run_optimize(cli.Arguments(seed="seed"))
        plain.assert_called_once()
        tui.assert_not_called()

    def test_dashboard_on_a_terminal(self) -> None:
        """A real terminal launches the live dashboard.

        Returns
        -------
        None
            Assertions pass when the dashboard is started.
        """
        from meta_harness import cli

        with (
            patch.object(cli, "SearchPipeline"),
            patch.object(cli, "_config"),
            patch.object(cli, "_use_progress", return_value=True),
            patch.object(cli, "ProgressTUI") as tui,
        ):
            cli._run_optimize(cli.Arguments(seed="seed"))
        tui.return_value.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
