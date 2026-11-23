"""Converters between external benchmark formats and evalbench cases."""

from __future__ import annotations

from typing import Any

from meta_harness.evalbench.cases import Case
from meta_harness.evalbench.cases import build_case


def bfcl_cases(records: list[dict[str, Any]], answers=None) -> list[Case]:
    """Convert BFCL function-calling records to cases.

    Parameters
    ----------
    records : list[dict[str, Any]]
        BFCL JSONL entries with questions and functions.
    answers : list[dict[str, Any]] or None
        Optional possible_answer entries indexed by id.

    Returns
    -------
    list[Case]
        Tool-execution cases.
    """
    lookup = _answer_lookup(answers)
    return [build_case(_bfcl_record(item, lookup)) for item in records]


def _answer_lookup(answers) -> dict[str, Any]:
    """Index BFCL ground truths by entry id.

    Parameters
    ----------
    answers : list of dict or None
        BFCL possible_answer entries.

    Returns
    -------
    dict[str, Any]
        Entry id to ground truth.
    """
    lookup = {}
    for item in answers or []:
        lookup[str(item["id"])] = item.get("ground_truth")
    return lookup


def _bfcl_record(
    item: dict[str, Any], lookup: dict[str, Any]
) -> dict[str, Any]:
    """Map one BFCL entry to a raw case record.

    Parameters
    ----------
    item : dict[str, Any]
        BFCL entry.
    lookup : dict[str, Any]
        Entry id to ground truth.

    Returns
    -------
    dict[str, Any]
        Raw case record.
    """
    question = item.get("question") or []
    functions = item.get("function") or item.get("functions") or []
    key = str(item.get("id", ""))
    return _bfcl_fields(item, question, functions, lookup.get(key))


def _bfcl_fields(
    item: dict[str, Any],
    question: list,
    functions: list,
    ground_truth: Any,
) -> dict[str, Any]:
    """Build a raw case record from one BFCL entry.

    Parameters
    ----------
    item : dict[str, Any]
        BFCL entry.
    question : list
        BFCL question turns.
    functions : list
        BFCL function definitions.
    ground_truth : Any
        BFCL ground truth calls.

    Returns
    -------
    dict[str, Any]
        Raw case record.
    """
    payload = {"id": str(item.get("id", "")), "kind": "tool"}
    payload["prompt"] = _bfcl_prompt(question)
    payload["expected"] = _bfcl_expected(ground_truth)
    payload["scorer"] = "tool_call"
    payload["tools"] = [str(func.get("name", "")) for func in functions]
    payload["schemas"] = _bfcl_schemas(functions)
    return payload


def _bfcl_prompt(question: list) -> str:
    """Join the user messages of a BFCL question.

    Parameters
    ----------
    question : list
        BFCL question turns.

    Returns
    -------
    str
        Joined user prompt.
    """
    parts = []
    for turn in question or []:
        for message in turn or []:
            if message.get("role") == "user":
                parts.append(str(message.get("content", "")))
    return "\n".join(part for part in parts if part)


def _bfcl_expected(ground_truth: Any) -> list[dict[str, Any]]:
    """Normalize a BFCL ground truth into expected call records.

    Parameters
    ----------
    ground_truth : Any
        BFCL ground truth value.

    Returns
    -------
    list[dict[str, Any]]
        Expected call records.
    """
    calls = []
    for item in ground_truth or []:
        calls.extend(_ground_call(item))
    return calls


def _ground_call(item: Any) -> list[dict[str, Any]]:
    """Convert one ground-truth call to name and argument subset.

    Parameters
    ----------
    item : Any
        One ground-truth call mapping.

    Returns
    -------
    list[dict[str, Any]]
        Expected calls for the entry.
    """
    calls = []
    for name, arguments in (item or {}).items():
        calls.append(
            {"name": str(name), "arguments": _first_values(arguments)}
        )
    return calls


def _first_values(arguments: Any) -> dict[str, Any]:
    """Select one accepted value per ground-truth parameter.

    Parameters
    ----------
    arguments : Any
        Parameter to accepted-values mapping.

    Returns
    -------
    dict[str, Any]
        One representative value per parameter.
    """
    values = {}
    for key, accepted in (arguments or {}).items():
        if isinstance(accepted, list) and accepted:
            values[key] = accepted[0]
    return values


def _bfcl_schemas(functions: list) -> list[dict[str, Any]]:
    """Wrap BFCL function definitions as OpenAI tool schemas.

    Parameters
    ----------
    functions : list
        BFCL function definitions.

    Returns
    -------
    list[dict[str, Any]]
        OpenAI-compatible tool schemas.
    """
    return [
        {"type": "function", "function": _bfcl_function(func)}
        for func in functions
    ]


def _bfcl_function(func: dict[str, Any]) -> dict[str, Any]:
    """Normalize one BFCL function definition for OpenAI endpoints.

    Parameters
    ----------
    func : dict[str, Any]
        BFCL function definition.

    Returns
    -------
    dict[str, Any]
        OpenAI-compatible function schema.
    """
    payload = dict(func)
    payload["parameters"] = _openai_parameters(func.get("parameters") or {})
    return payload


def _openai_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Convert pythonic parameter types to JSON Schema.

    Parameters
    ----------
    parameters : dict[str, Any]
        BFCL parameter schema.

    Returns
    -------
    dict[str, Any]
        JSON Schema-compatible parameters.
    """
    payload = dict(parameters)
    if payload.get("type") == "dict":
        payload["type"] = "object"
    if payload.get("properties"):
        payload["properties"] = _openai_properties(payload["properties"])
    return payload


def _openai_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Convert each property to JSON Schema types.

    Parameters
    ----------
    properties : dict[str, Any]
        BFCL property schemas.

    Returns
    -------
    dict[str, Any]
        JSON Schema-compatible properties.
    """
    return {
        key: _openai_parameters(value) if isinstance(value, dict) else value
        for key, value in properties.items()
    }


def gaia_cases(records: list[dict[str, Any]]) -> list[Case]:
    """Convert GAIA validation entries to cases.

    Parameters
    ----------
    records : list[dict[str, Any]]
        GAIA JSONL entries.

    Returns
    -------
    list[Case]
        Question-answering cases.
    """
    return [build_case(_gaia_record(item)) for item in records]


def _gaia_record(item: dict[str, Any]) -> dict[str, Any]:
    """Map one GAIA entry to a raw case record.

    Parameters
    ----------
    item : dict[str, Any]
        GAIA entry.

    Returns
    -------
    dict[str, Any]
        Raw case record.
    """
    return {
        "id": str(item.get("task_id", "")),
        "kind": "qa",
        "prompt": str(item.get("Question", "")),
        "expected": str(item.get("Final answer", "")),
        "scorer": "exact",
    }


def inspect_summary(log: dict[str, Any]) -> dict[str, Any]:
    """Extract headline numbers from an Inspect EvalLog.

    Parameters
    ----------
    log : dict[str, Any]
        Inspect EvalLog JSON.

    Returns
    -------
    dict[str, Any]
        Sample count, correct count, accuracy, model, and mean duration.
    """
    results = _results_of(log)
    samples = results.get("samples") or []
    correct = _correct_count(samples)
    summary = {"samples": len(samples), "correct": correct}
    summary["accuracy"] = _accuracy(correct, len(samples))
    summary["model"] = _model_of(log)
    summary["mean_duration"] = results.get("mean_duration") or 0.0
    return summary


def _results_of(log: dict[str, Any]) -> dict[str, Any]:
    """Extract the results block of an Inspect log.

    Parameters
    ----------
    log : dict[str, Any]
        Inspect EvalLog JSON.

    Returns
    -------
    dict[str, Any]
        Results block, or an empty mapping.
    """
    eval_ = log.get("eval") or {}
    return eval_.get("results") or {}


def _model_of(log: dict[str, Any]) -> str:
    """Extract the model name of an Inspect log.

    Parameters
    ----------
    log : dict[str, Any]
        Inspect EvalLog JSON.

    Returns
    -------
    str
        Model name, or empty.
    """
    eval_ = log.get("eval") or {}
    model = eval_.get("model") or {}
    return str(model.get("name", ""))


def _correct_count(samples: list[dict[str, Any]]) -> int:
    """Count samples with a passing score entry.

    Parameters
    ----------
    samples : list[dict[str, Any]]
        Inspect sample records.

    Returns
    -------
    int
        Passing sample count.
    """
    passed = 0
    for sample in samples:
        scores = sample.get("scores") or {}
        for score in scores.values():
            if score.get("value") in ("C", 1, True, "pass", "correct"):
                passed += 1
                break
    return passed


def _accuracy(correct: int, total: int) -> float:
    """Return zero-guarded accuracy.

    Parameters
    ----------
    correct : int
        Passing samples.
    total : int
        All samples.

    Returns
    -------
    float
        Fraction passing.
    """
    return correct / total if total else 0.0


def inspect_export(
    name: str,
    model: str,
    baseline: list[dict[str, Any]],
    harness: list[dict[str, Any]],
) -> dict[str, Any]:
    """Export a comparative run as a minimal Inspect EvalLog.

    Parameters
    ----------
    name : str
        Task name.
    model : str
        Model identifier.
    baseline : list[dict[str, Any]]
        Baseline run records.
    harness : list[dict[str, Any]]
        Harness run records.

    Returns
    -------
    dict[str, Any]
        Minimal EvalLog-compatible structure.
    """
    samples = _inspect_samples(baseline) + _inspect_samples(harness)
    return _inspect_log(name, model, samples)


def _inspect_log(
    name: str, model: str, samples: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the EvalLog wrapper around samples.

    Parameters
    ----------
    name : str
        Task name.
    model : str
        Model identifier.
    samples : list[dict[str, Any]]
        Sample records.

    Returns
    -------
    dict[str, Any]
        EvalLog structure.
    """
    payload = {"version": 2, "status": "success"}
    results = {"samples": samples}
    payload["eval"] = {"task": name, "model": model, "results": results}
    return payload


def _inspect_samples(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert eval records into Inspect sample dicts.

    Parameters
    ----------
    records : list[dict[str, Any]]
        Run records.

    Returns
    -------
    list[dict[str, Any]]
        Inspect sample records.
    """
    samples = []
    for record in records:
        samples.append(_inspect_sample(record))
    return samples


def _inspect_sample(record: dict[str, Any]) -> dict[str, Any]:
    """Convert one eval record into an Inspect sample dict.

    Parameters
    ----------
    record : dict[str, Any]
        Run record.

    Returns
    -------
    dict[str, Any]
        Inspect sample record.
    """
    value = "C" if record.get("score") else "I"
    score = {"accuracy": {"value": value, "answer": record.get("answer", "")}}
    sample = {"id": record.get("case_id", ""), "scores": score}
    sample["input"] = record.get("prompt", "")
    return sample
