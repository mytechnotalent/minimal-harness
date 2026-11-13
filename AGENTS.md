# AGENTS.md

Guidance for humans and coding agents contributing to Minimal Harness.

## Project shape

Minimal Harness is a Python control plane inspired by *Meta-Harness:
End-to-End Optimization of Model Harnesses* (arXiv:2603.28052v1). It runs an
adversarial candidate-search loop: **propose → review → gate 1 → adjudicate →
gate 2 → log → repeat**. See [docs/adversarial-loop.md](docs/adversarial-loop.md).

## Layout

- `meta_harness/pipeline.py` — the adversarial search loop.
- `meta_harness/prompts/` — stage prompts loaded at runtime.
- `meta_harness/agent.py` — bounded tool loop for answer mode.
- `meta_harness/tools.py` — read / write / edit / bash / web / browser tools.
- `meta_harness/docker_gate.py` — constrained Docker execution.
- `meta_harness/openrouter.py` — model provider client.
- `meta_harness/session.py` — JSONL trajectory persistence.
- `meta_harness/tui.py` — full-screen curses TUI.
- `meta_harness/progress.py` — live `--optimize` progress dashboard.
- `scripts/ab_pi.py` — headless A/B comparison against Pi.
- `scripts/prove_advantage.py` — deterministic gate-2 and reviewer proofs.
- `scripts/search_harness.py` — harness configuration search and Pareto archive.
- `benchmarks/headtohead/` — single-file seed corpus for the A/B runner.
- `benchmarks/repo/` — multi-file agentic corpus with hidden tests.
- `benchmarks/independent/` — vendored real-project tasks with project tests
  (excluded from formatting and audit).
- `tests/` — offline unit tests.
- `runs/` — per-run candidate artifacts (generated).

## Style rules (strict)

See `.opencode/skill/embedded-python-standard/SKILL.md`. Summary:

- PEP 8 enforced by `pycodestyle` at `--max-line-length=79`; Black and
  Flake8 stay clean (`line-length = 79`).
- Module docstring on every `.py` file, and a docstring on every class,
  function, and method.
- Every function/method docstring has a `Parameters` section and a `Returns`
  section (write `None` when nothing is returned), in NumPy style.
- Function bodies are **≤ 8 executable lines** and contain **no blank lines**.
- No en dash (U+2013) or em dash (U+2014) anywhere; use the hyphen-minus.
- Imports are grouped standard library, third party, local, one name per line.
- Break longer bodies into private helpers.

## Verifying a change

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" flake8 pycodestyle
black meta_harness tests gui benchmarks scripts setup_app.py
black --check meta_harness tests gui benchmarks scripts setup_app.py
flake8 meta_harness tests gui benchmarks scripts setup_app.py
python .opencode/skill/embedded-python-standard/audit_python_standard.py
python -m compileall -q meta_harness tests gui scripts
python -m unittest discover -s tests -v
```

The audit must exit 0. Any output from it is a failure to fix.

All of the above must pass before opening a PR.

## Prompts

Adversarial-stage prompts live in `meta_harness/prompts/*.md`. Load with
`from meta_harness.prompts import load` and `load("proposer")`. Keep the
one-liner headers in place — the `SequenceClient` test classifies stages by
scanning for `proposer` and `reviewer` in the system string.

`agent.md` is the interactive agent's system prompt. It instructs the agent
to ask one question at a time (via the `ask` tool) instead of assuming. The
`ask` tool is only advertised when an interactive questioner is wired up.
Every final Q&A answer is reviewed by `answer_reviewer.md`; disable it with
`HARNESS_ANSWER_REVIEW=0`. `HARNESS_ADVERSARIAL_DRAFTS=N` generates N drafts
and picks one with `adversarial.md`. `reviewer.md` also emits executable
`unittest` sources that Gate 1 runs; keep them standard-library only and
deterministic. `HARNESS_ANSWER_TESTS=1` enables test-time verification with
`repo_reviewer.md`, which writes workspace tests and triggers one repair turn
on failure.

## Held-out data

The proposer, reviewer, adjudicator, and any search-time summary must **never**
see held-out task results. Held-out evaluation belongs in a separate pass
after search completes.

## Docker gate

Gates fail closed. A run must provide `--task-manifest`, `--gate-command`,
`--final-task-manifest`, or `--final-gate-command`; otherwise no candidate can
win. `--gate-threshold` defaults to `1.0`, so a manifest gate rejects any
candidate that misses a task. The container runs with `--network none`, one
CPU, 512 MiB, read-only rootfs, read-only mount, and `--rm`; production use
should add rootless mode, dropped capabilities, seccomp/AppArmor, PID limits,
and an external isolation boundary. On macOS, Colima is supported; its default
home-directory share requires the workspace to live under the home directory.

## PR checklist

- [ ] Style rules satisfied (Black, Flake8, pycodestyle 79, audit clean).
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] Every new function, module, command, or behavior has an offline unit test.
- [ ] No held-out data leaks into a search-time stage.
- [ ] README or `docs/` updated when user-facing behavior changes.
