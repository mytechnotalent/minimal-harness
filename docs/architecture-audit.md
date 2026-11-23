# Architecture Audit: External Evaluation Readiness

Audited November 22, 2026 against the seven questions of Phase 1. Every
statement points at source so it stays checkable.

## 1. How requests enter the system

Three entry points:

- CLI: `meta_harness/cli.py` dispatches `agent` mode (single-task answer
  mode) and `optimize` mode (the adversarial search loop in
  `meta_harness/pipeline.py`).
- GUI: `gui/app.py` wraps the same agent and pipeline objects.
- Programmatic: `meta_harness/agent.py` exposes `Agent.run(prompt) -> str`,
  and `meta_harness/pipeline.py` exposes `SearchPipeline.run(...)`. Both are
  importable without the CLI, which is what the benchmark adapters use.

## 2. How the harness communicates with the underlying model

`OpenRouterClient` (`meta_harness/openrouter.py`) is an OpenAI-compatible
chat client. It supports three providers selected by `HARNESS_PROVIDER`:

- `opencode` (OpenCode Go inference endpoint),
- `local` (any OpenAI-compatible local server: Ollama, LM Studio, vLLM),
- `openrouter` (OpenRouter API).

Two call shapes:

- `complete(system, user, temperature) -> str` - one text completion.
- `chat(messages, tools) -> dict` - a full chat completion that may return
  tool calls.

The client records cumulative usage (`call_count`, `prompt_tokens`,
`completion_tokens`, `cost`, `model_seconds`), which the eval runners
snapshot before and after each case.

## 3. Additional processing and validation layers

The harness adds these layers on top of the raw model, all in
`meta_harness/agent.py` unless noted:

- Adversarial answer review (`_review_final`, prompt
  `answer_reviewer.md`) - a reviewer pass over every final answer.
- Ledger verification (`verify_ledger.md`) - recomputes numeric totals in
  Python and checks stated distributions.
- Invariant checks (`technical_reviewer.md` + `meta_harness/invariants.py`)
  for database, retry, security, and operations claims.
- Requirement tracking (`requirements_reviewer.md`) for multi-turn spec
  work.
- Adversarial drafts (`HARNESS_ADVERSARIAL_DRAFTS`): N drafts, one chosen
  by `adversarial.md`.
- Answer-time tests (`repo_reviewer.md`): the reviewer emits executable
  `unittest` sources that run in the workspace, with one bounded repair turn
  on failure (`HARNESS_ANSWER_TESTS`).
- Deliverables verification (`meta_harness/deliverables.py`): requested and
  named files, passing-test claims, completion status.
- Bounded tool loop with sandboxed bash (`meta_harness/bash_sandbox.py`).
- The adversarial search loop (`meta_harness/pipeline.py`): propose, review,
  gate 1, adjudicate, gate 2, with Docker gates
  (`meta_harness/docker_gate.py`) when configured.

Each layer is individually switchable through environment variables, which
is what makes the baseline-vs-harness comparison well defined.

## 4. Tool and function calling

Supported. `Agent` advertises OpenAI-compatible tool schemas
(`ToolRegistry.schema`, `meta_harness/tools.py`) and executes model-invoked
calls through `ToolRegistry.execute(name, arguments)`. Tools include read,
write, edit, patch, list, glob, grep, bash, web_search, browser tools, and
project evaluation. BFCL-style function-calling evaluation is therefore
directly expressible: both baseline and harness runners use the same
registry, restricted to the benchmark's function set.

## 5. External API or programmatic interface

There is no HTTP server and none is required: external evaluation software
drives the harness through the Python API or the CLI. The eval package
(`meta_harness/evalbench/`) is the benchmark-facing interface:

- `BaselineRunner` - raw model plus tools, minimal loop, no harness layers.
- `HarnessRunner` - the same model and tools through the full `Agent` stack.
- `scripts/eval_compare.py` - reproducible CLI that records config, raw
  per-case records, and the comparison report.

For Inspect AI, `adapters.py` can export results as a minimal EvalLog;
official Inspect integration remains a run-through-Inspect option documented
in `docs/independent-evaluation.md`.

## 6. Logging of decisions, outputs, errors, and times

- `Session` (`meta_harness/session.py`) persists full message transcripts as
  JSONL.
- `HARNESS_TRACE_LOG` appends one JSONL record per tool call (task id,
  execution id, timestamps, redacted arguments, status, short result,
  retry link, cited flag).
- The reviewer receives the tool trace plus changed-file context, so claims
  are checked against what actually ran.
- The eval runners record per-case wall time, error text, answer, tool
  calls, score, and usage deltas into `baseline.jsonl` and `harness.jsonl`.

## 7. Evaluating the underlying model independently

Yes, three ways:

- `OpenRouterClient.complete(...)` for plain text baselines.
- `OpenRouterClient.chat(...)` plus `ToolRegistry` for tool baselines with
  no harness validation.
- The agentless compare path already exists in `scripts/ab_pi.py`, which
  runs two harnesses head to head.

## Compatibility requirements (prioritized)

1. Keep `ChatModel` (`meta_harness/chat_model.py`) as the interchange
   protocol: any provider wrapper with `complete`, `usage_summary`, and the
   usage counters can drive both the pipeline and the eval runners.
2. Standardize benchmark import on JSON/JSONL case files so BFCL, GAIA, and
   custom suites share one runner (done in `evalbench/cases.py`).
3. Preserve deterministic scorers independent of any model judge, so an
   independent party can re-score raw answers without re-running the model.
4. Record environment flags with every run so configurations are
   reproducible bit for bit.
5. Keep held-out results out of search-time stages (unchanged: held-out
   evaluation stays in a separate pass).
