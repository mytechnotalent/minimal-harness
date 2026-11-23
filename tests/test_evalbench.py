"""Offline tests for the comparative evaluation suite."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meta_harness.evalbench.adapters import bfcl_cases
from meta_harness.evalbench.adapters import gaia_cases
from meta_harness.evalbench.adapters import inspect_export
from meta_harness.evalbench.adapters import inspect_summary
from meta_harness.evalbench.baseline import BaselineRunner
from meta_harness.evalbench.cases import Case
from meta_harness.evalbench.cases import dump_cases
from meta_harness.evalbench.cases import load_cases
from meta_harness.evalbench.cases import score_case
from meta_harness.evalbench.cases import validate_record
from meta_harness.evalbench.harness_run import HarnessRunner
from meta_harness.evalbench.report import compare
from meta_harness.evalbench.report import json_report
from meta_harness.evalbench.report import markdown_report
from meta_harness.evalbench.report import repeat_stats
from meta_harness.evalbench.report import summary
from meta_harness.evalbench.report import wilson
from meta_harness.tools import ToolRegistry
from scripts.bfcl_official import build_model_result
from scripts.bfcl_official import serialize_calls
from scripts.eval_compare import parse_args
from scripts.eval_compare import run_evaluation

REVIEW_OFF = {
    "HARNESS_ANSWER_REVIEW": "0",
    "HARNESS_ANSWER_LEDGER": "off",
    "HARNESS_ANSWER_INVARIANTS": "off",
    "HARNESS_REQUIREMENT_CHECK": "off",
    "HARNESS_ANSWER_TESTS": "0",
    "HARNESS_AUTO_VERIFY": "0",
}

BFCL_ENTRY = {
    "id": "f1",
    "question": [[{"role": "user", "content": "Get the weather"}]],
    "function": [
        {
            "name": "get_weather",
            "description": "weather",
            "parameters": {
                "type": "dict",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ],
}

BFCL_ANSWERS = [
    {"id": "f1", "ground_truth": [{"get_weather": {"city": ["SF"]}}]},
]

GAIA_ENTRY = {
    "task_id": "g1",
    "Question": "What is 2+2?",
    "Final answer": "4",
}

INSPECT_LOG = {
    "eval": {
        "model": {"name": "beam"},
        "results": {
            "samples": [
                {"scores": {"accuracy": {"value": "C"}}},
                {"scores": {"accuracy": {"value": "I"}}},
            ]
        },
    }
}


def _case(expected, scorer="contains", tools=None, kind="qa", tolerance=1e-6):
    """Build a compact test case.

    Parameters
    ----------
    expected : Any
        Expected value.
    scorer : str
        Scorer name.
    tools : list or None
        Allowed tool names.
    kind : str
        Case kind.
    tolerance : float
        Numeric tolerance.

    Returns
    -------
    Case
        Test case.
    """
    case = Case("c", kind, "q", expected=expected, scorer=scorer, tools=tools)
    case.tolerance = tolerance
    return case


def _call(name, **arguments):
    """Build one expected tool-call record.

    Parameters
    ----------
    name : str
        Tool name.
    arguments : dict
        Expected argument subset.

    Returns
    -------
    dict
        Call record.
    """
    return {"name": name, "arguments": arguments}


def _run_record(case_id="c", score=True, answer="a", prompt="p", **fields):
    """Build one run record for report tests.

    Parameters
    ----------
    case_id : str
        Case identifier.
    score : bool
        Pass outcome.
    answer : str
        Answer text.
    prompt : str
        Prompt text.
    fields : dict
        Extra record fields.

    Returns
    -------
    dict
        Run record.
    """
    record = {"case_id": case_id, "score": score, "answer": answer}
    record["prompt"] = prompt
    record.update(fields)
    return record


def _baseline_record(case, client, directory):
    """Run one case through the baseline runner.

    Parameters
    ----------
    case : Case
        Benchmark case.
    client : Any
        Model client.
    directory : str
        Workspace root.

    Returns
    -------
    dict
        Scored run record.
    """
    runner = BaselineRunner(client, root=directory)
    return runner.run_case(case)


def _harness_record(case, client, directory):
    """Run one case through the harness runner.

    Parameters
    ----------
    case : Case
        Benchmark case.
    client : Any
        Model client.
    directory : str
        Workspace root.

    Returns
    -------
    dict
        Scored run record.
    """
    runner = HarnessRunner(client, root=directory)
    return runner.run_case(case)


class FakeClient:
    """Deterministic offline model client."""

    def __init__(self, answer: str = "final answer") -> None:
        """Store the fixed answer and zeroed usage.

        Parameters
        ----------
        answer : str
            Fixed answer text.

        Returns
        -------
        None
            The client is ready.
        """
        self.answer = answer
        self.model = "fake-model"
        self.provider = "fake"
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0
        self.model_seconds = 0.0

    def chat(self, messages, tools):
        """Return a final text response.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.
        tools : list[dict]
            Tool schemas.

        Returns
        -------
        dict
            Chat response body.
        """
        self.call_count += 1
        self.completion_tokens += 2
        message = {"role": "assistant", "content": self.answer}
        return {"choices": [{"message": message}]}

    def complete(self, system, user, temperature=0.2):
        """Return the fixed answer as plain text.

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
            Fixed answer.
        """
        self.call_count += 1
        return self.answer


class TextOnlyClient:
    """Expose only complete, no chat."""

    def __init__(self, answer: str = "text answer") -> None:
        """Store the fixed answer and zeroed usage.

        Parameters
        ----------
        answer : str
            Fixed answer text.

        Returns
        -------
        None
            The client is ready.
        """
        self.answer = answer
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0
        self.model_seconds = 0.0

    def complete(self, system, user, temperature=0.2):
        """Return the fixed answer as plain text.

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
            Fixed answer.
        """
        self.call_count += 1
        return self.answer


class ToolLoopClient:
    """Return one list tool call, then a final answer."""

    def __init__(self) -> None:
        """Store the turn counter and zeroed usage.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The client is ready.
        """
        self.calls = 0
        self.model = "fake-model"
        self.provider = "fake"
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0
        self.model_seconds = 0.0

    def chat(self, messages, tools):
        """Return a tool call first and text second.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.
        tools : list[dict]
            Tool schemas.

        Returns
        -------
        dict
            Chat response body.
        """
        self.calls += 1
        self.call_count += 1
        if self.calls == 1:
            return self._tool_call()
        return self._final()

    def _tool_call(self) -> dict:
        """Return one list tool call.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Response containing one tool call.
        """
        call = {"id": "1", "function": {"name": "list", "arguments": "{}"}}
        message = {"role": "assistant", "content": "", "tool_calls": [call]}
        return {"choices": [{"message": message}]}

    def _final(self) -> dict:
        """Return the final text response.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Response containing final text.
        """
        message = {"role": "assistant", "content": "listed result"}
        return {"choices": [{"message": message}]}


class ExternalToolClient:
    """Return one external tool call, then a final answer."""

    def __init__(self) -> None:
        """Store the turn counter and zeroed usage.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The client is ready.
        """
        self.calls = 0
        self.model = "fake-model"
        self.provider = "fake"
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0
        self.model_seconds = 0.0

    def chat(self, messages, tools):
        """Return an external tool call first and text second.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages.
        tools : list[dict]
            Tool schemas.

        Returns
        -------
        dict
            Chat response body.
        """
        self.calls += 1
        self.call_count += 1
        if self.calls == 1:
            return self._tool_call()
        return self._final()

    def _tool_call(self) -> dict:
        """Return one get_weather tool call.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Response containing one external tool call.
        """
        function = {"name": "get_weather", "arguments": '{"city": "SF"}'}
        call = {"id": "1", "function": function}
        message = {"role": "assistant", "content": "", "tool_calls": [call]}
        return {"choices": [{"message": message}]}

    def _final(self) -> dict:
        """Return the final text response.

        Parameters
        ----------
        None

        Returns
        -------
        dict
            Response containing final text.
        """
        message = {"role": "assistant", "content": "done"}
        return {"choices": [{"message": message}]}


class CaseFileTests(unittest.TestCase):
    """Verify case loading, validation, and deterministic scoring."""

    def test_load_cases_roundtrip(self) -> None:
        """Dump and reload cases from a JSONL file.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Reloaded cases match the originals.
        """
        cases = [Case("a", "reasoning", "hello"), Case("b", "qa", "why?")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            dump_cases(path, cases)
            loaded = load_cases(path)
        self.assertEqual([case.id for case in loaded], ["a", "b"])
        self.assertEqual(loaded[0].scorer, "contains")

    def test_load_cases_rejects_invalid_record(self) -> None:
        """A record with an unknown kind raises ValueError.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The error message names the record position.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            path.write_text('{"id": "x", "kind": "weird"}\n', encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                load_cases(path)
        self.assertIn("record 1", str(caught.exception))

    def test_validate_record_flags_problems(self) -> None:
        """Validation reports missing fields and bad types.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The problem list covers each defect.
        """
        problems = validate_record({"kind": "reasoning"})
        self.assertIn("id is required", problems)
        self.assertIn("prompt is required", problems)

    def test_score_contains(self) -> None:
        """Fragment containment scoring is case-insensitive.

        Parameters
        ----------
        None

        Returns
        -------
        None
            All fragments must be present.
        """
        case = _case(["jupiter", "solar"])
        self.assertTrue(score_case(case, "Jupiter is in the Solar System"))
        self.assertFalse(score_case(case, "Jupiter only"))

    def test_score_exact_normalizes(self) -> None:
        """Exact scoring ignores case and whitespace.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Normalized equality drives the score.
        """
        case = _case("PING-7", scorer="exact")
        self.assertTrue(score_case(case, "  ping-7  "))
        self.assertFalse(score_case(case, "PING-8"))

    def test_score_regex(self) -> None:
        """Regex scoring searches the whole answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A matching answer passes.
        """
        case = _case(r"\b\d+\.\d+\b", scorer="regex")
        self.assertTrue(score_case(case, "value is 3.14"))
        self.assertFalse(score_case(case, "no decimals"))

    def test_score_numeric_tolerance(self) -> None:
        """Numeric scoring honors the tolerance.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Near numbers pass, far numbers fail.
        """
        case = _case(16.0, scorer="numeric", tolerance=0.5)
        self.assertTrue(score_case(case, "The speed is 16.1 km/h"))
        self.assertFalse(score_case(case, "The speed is 42 km/h"))

    def test_score_tool_call_subset(self) -> None:
        """Tool-call scoring matches name and argument subsets.

        Parameters
        ----------
        None

        Returns
        -------
        None
            A matching executed call passes.
        """
        case = _case([_call("bash", command="echo hi")], scorer="tool_call")
        executed = [_call("bash", command="echo hi", timeout=30)]
        self.assertTrue(score_case(case, "", executed))
        self.assertFalse(score_case(case, "", [_call("read")]))

    def test_score_tool_call_count_parity(self) -> None:
        """Tool-call scoring requires the expected call count.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Extra executed calls fail the case.
        """
        case = _case([_call("list")], scorer="tool_call")
        extra = [_call("list"), _call("list")]
        self.assertFalse(score_case(case, "", extra))


class AdapterTests(unittest.TestCase):
    """Verify external benchmark format converters."""

    def test_bfcl_mapping(self) -> None:
        """A BFCL entry maps to a tool-execution case.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Prompt, tools, and expected calls are extracted.
        """
        case = bfcl_cases([BFCL_ENTRY], BFCL_ANSWERS)[0]
        self.assertEqual(case.id, "f1")
        self.assertEqual(case.kind, "tool")
        self.assertEqual(case.prompt, "Get the weather")
        self.assertEqual(case.tools, ["get_weather"])
        self.assertEqual(case.scorer, "tool_call")
        self.assertEqual(case.expected[0]["arguments"], {"city": "SF"})

    def test_bfcl_schema_normalization(self) -> None:
        """BFCL parameter types convert to JSON Schema.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The schema is OpenAI-compatible.
        """
        case = bfcl_cases([BFCL_ENTRY], BFCL_ANSWERS)[0]
        schema = case.schemas[0]
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "get_weather")
        self.assertEqual(schema["function"]["parameters"]["type"], "object")

    def test_gaia_mapping(self) -> None:
        """A GAIA entry maps to an exact-scored QA case.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Question and final answer are extracted.
        """
        case = gaia_cases([GAIA_ENTRY])[0]
        self.assertEqual(case.id, "g1")
        self.assertEqual(case.expected, "4")
        self.assertEqual(case.scorer, "exact")

    def test_inspect_summary(self) -> None:
        """Inspect log summaries count passing samples.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Accuracy and model are extracted.
        """
        result = inspect_summary(INSPECT_LOG)
        self.assertEqual(result["samples"], 2)
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["model"], "beam")

    def test_inspect_export_shape(self) -> None:
        """Inspect export combines both configurations.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The EvalLog has two sample groups.
        """
        baseline = [_run_record("c1", True)]
        harness = [_run_record("c2", False)]
        log = inspect_export("smoke", "fake", baseline, harness)
        sample = log["eval"]["results"]["samples"][0]
        self.assertEqual(log["version"], 2)
        self.assertEqual(len(log["eval"]["results"]["samples"]), 2)
        self.assertEqual(sample["scores"]["accuracy"]["value"], "C")


class BaselineTests(unittest.TestCase):
    """Verify the raw-model baseline runner."""

    def test_complete_fallback_without_chat(self) -> None:
        """Clients without chat fall back to complete.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The answer is scored from the completion.
        """
        case = Case("t1", "qa", "hello", expected=["text answer"])
        with tempfile.TemporaryDirectory() as directory:
            record = _baseline_record(case, TextOnlyClient(), directory)
        self.assertTrue(record["score"])
        self.assertEqual(record["answer"], "text answer")
        self.assertEqual(record["call_count"], 1.0)

    def test_tool_loop_executes_and_scores(self) -> None:
        """The minimal loop executes tool calls and scores them.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The executed call and final text are recorded.
        """
        case = _case([_call("list")], scorer="tool_call", tools=["list"])
        case.kind = "tool"
        with tempfile.TemporaryDirectory() as directory:
            record = _baseline_record(case, ToolLoopClient(), directory)
        self.assertTrue(record["score"])
        self.assertEqual(record["answer"], "listed result")
        self.assertEqual(record["tool_calls"][0]["name"], "list")


class ExternalSchemaTests(unittest.TestCase):
    """Verify external benchmark function schemas."""

    def test_external_function_returns_stub_result(self) -> None:
        """External benchmark functions execute to a stub success.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No error is raised for an external schema name.
        """
        spec = {"type": "function", "function": {"name": "get_weather"}}
        registry = ToolRegistry(".", extra_schemas=[spec])
        result = registry.execute("get_weather", {"city": "SF"})
        self.assertIn('"ok"', result)

    def test_baseline_external_function_scored(self) -> None:
        """Baseline advertises and scores an external function.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The executed external call matches the ground truth.
        """
        spec = {"name": "get_weather", "parameters": {"type": "object"}}
        case = _case([_call("get_weather", city="SF")], scorer="tool_call")
        case.schemas = [{"type": "function", "function": spec}]
        with tempfile.TemporaryDirectory() as directory:
            record = _baseline_record(case, ExternalToolClient(), directory)
        self.assertTrue(record["score"])
        self.assertEqual(record["tool_calls"][0]["name"], "get_weather")

    def test_harness_external_function_scored(self) -> None:
        """The agent advertises and records an external function.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The harness record scores the executed call.
        """
        spec = {"name": "get_weather", "parameters": {"type": "object"}}
        case = _case([_call("get_weather", city="SF")], scorer="tool_call")
        case.schemas = [{"type": "function", "function": spec}]
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, REVIEW_OFF):
                record = _harness_record(case, ExternalToolClient(), directory)
        self.assertTrue(record["score"])
        self.assertEqual(record["tool_calls"][0]["name"], "get_weather")


class HarnessTests(unittest.TestCase):
    """Verify the harness-enabled runner through the agent stack."""

    def test_agent_run_scores_answer(self) -> None:
        """The agent produces and scores a final answer.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The harness record passes the case.
        """
        case = Case("h1", "qa", "hello", expected=["final answer"])
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, REVIEW_OFF):
                record = _harness_record(case, FakeClient(), directory)
        self.assertTrue(record["score"])
        self.assertEqual(record["answer"], "final answer")
        self.assertGreaterEqual(record["call_count"], 1.0)

    def test_agent_tool_case_scores_call(self) -> None:
        """The agent executes tool calls through the registry.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The tool-call scorer sees the executed call.
        """
        case = _case([_call("list")], scorer="tool_call", tools=["list"])
        case.kind = "tool"
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, REVIEW_OFF):
                record = _harness_record(case, ToolLoopClient(), directory)
        self.assertTrue(record["score"])
        self.assertEqual(record["answer"], "listed result")
        self.assertEqual(record["tool_calls"][0]["name"], "list")


class OfficialBfclTests(unittest.TestCase):
    """Verify the official BFCL result serialization."""

    def test_serialize_calls(self) -> None:
        """Recorded calls serialize to Python call syntax.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Names and arguments render correctly.
        """
        calls = [_call("get_weather", city="SF")]
        text = serialize_calls(calls)
        self.assertEqual(text, "get_weather(city='SF')")

    def test_build_model_result(self) -> None:
        """Run records convert to official-format entries.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Entries carry id and result text.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            record = _run_record(case_id="c1", score=True)
            record["tool_calls"] = [_call("list")]
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            entries = build_model_result(path)
        self.assertEqual(entries[0]["id"], "c1")
        self.assertEqual(entries[0]["result"], "list()")


class ReportTests(unittest.TestCase):
    """Verify comparative analysis and report emission."""

    def test_summary_math(self) -> None:
        """Summaries compute accuracy and token totals.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Headline numbers match the records.
        """
        records = [_run_record(score=True, prompt_tokens=3, elapsed=1.0)]
        records.append(_run_record(score=False, prompt_tokens=5, elapsed=2.0))
        result = summary(records)
        self.assertEqual(result["cases"], 2)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["prompt_tokens"], 8.0)

    def test_compare_deltas(self) -> None:
        """Comparisons compute accuracy and overhead deltas.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Harness improvement is quantified.
        """
        baseline = [_run_record("a", False), _run_record("b", True)]
        harness = [_run_record("a", True), _run_record("b", True)]
        result = compare(baseline, harness)
        self.assertEqual(result["deltas"]["absolute"], 0.5)
        self.assertEqual(result["deltas"]["relative_percent"], 100.0)
        self.assertEqual(result["rows"][0]["outcome"], "harness_only")

    def test_wilson_bounds(self) -> None:
        """Wilson bounds are inside the unit interval.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The bound shrinks with sample size.
        """
        self.assertEqual(wilson(0.0, 0), 0.0)
        lower = wilson(5.0, 10)
        self.assertGreater(lower, 0.2)
        self.assertLess(lower, 0.5)
        self.assertGreater(wilson(10.0, 10), 0.5)

    def test_repeat_stats_pooling(self) -> None:
        """Repeat statistics pool per-case fractions.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The pooled mean matches the fractions.
        """
        first = [_run_record("a", True), _run_record("b", True)]
        second = [_run_record("a", False), _run_record("b", True)]
        result = repeat_stats([first, second])
        self.assertEqual(result["runs"], 2)
        self.assertEqual(result["cases"], 2)
        self.assertEqual(result["mean"], 0.75)

    def test_report_rendering(self) -> None:
        """Markdown and JSON reports contain the numbers.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Both formats render without error.
        """
        baseline = [_run_record("a", True)]
        harness = [_run_record("a", True)]
        result = compare(baseline, harness)
        markdown = markdown_report(result, {"model": "fake"})
        payload = json.loads(json_report(result, {"model": "fake"}))
        self.assertIn("Baseline accuracy", markdown)
        self.assertIn("## Summary", markdown)
        self.assertEqual(payload["notes"]["model"], "fake")


class CliTests(unittest.TestCase):
    """Verify the evaluation CLI end to end with a fake client."""

    def test_run_evaluation_writes_reports(self) -> None:
        """A full run writes config, records, and comparison files.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The comparison reports a perfect score.
        """
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, REVIEW_OFF):
                payload = self._run_in(directory)
        self.assertEqual(payload["harness"]["accuracy"], 1.0)

    def _run_in(self, directory: str) -> dict:
        """Drive one evaluation in a temporary directory.

        Parameters
        ----------
        directory : str
            Temporary directory path.

        Returns
        -------
        dict
            The comparison payload.
        """
        cases_path = Path(directory) / "cases.jsonl"
        case = Case("c1", "reasoning", "hello", expected=["final answer"])
        dump_cases(cases_path, [case])
        args = parse_args(["--cases", str(cases_path), "--out", directory])
        self.assertEqual(run_evaluation(args, client=FakeClient()), 0)
        payload = json.loads((Path(directory) / "comparison.json").read_text())
        self.assertEqual(payload["baseline"]["accuracy"], 1.0)
        return payload


if __name__ == "__main__":
    unittest.main()
