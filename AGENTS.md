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
- `tests/` — offline unit tests.
- `runs/` — per-run candidate artifacts (generated).

## Style rules (strict)

See `.github/skills/minimal-harness-python-formatting/SKILL.md`. Summary:

- PEP 8, Black (`line-length = 79`), Flake8 clean.
- Module docstring on every `.py` file.
- Every function has a full NumPy-style docstring.
- Function bodies are **≤ 8 executable lines** and contain **no blank lines**.
- Break longer bodies into private helpers.

## Verifying a change

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" flake8
black meta_harness tests
black --check meta_harness tests
flake8 meta_harness tests
python -m compileall -q meta_harness tests
python -m unittest discover -s tests -v
```

All of the above must pass before opening a PR.

## Prompts

Adversarial-stage prompts live in `meta_harness/prompts/*.md`. Load with
`from meta_harness.prompts import load` and `load("proposer")`. Keep the
one-liner headers in place — the `SequenceClient` test classifies stages by
scanning for `proposer` and `reviewer` in the system string.

## Held-out data

The proposer, reviewer, adjudicator, and any search-time summary must **never**
see held-out task results. Held-out evaluation belongs in a separate pass
after search completes.

## Docker gate

The default gate command is a placeholder. Replace it with a real domain
evaluator before comparing harnesses across runs. The container runs with
`--network none`, one CPU, 512 MiB, read-only rootfs, read-only mount, and
`--rm`; production use should add rootless mode, dropped capabilities,
seccomp/AppArmor, PID limits, and an external isolation boundary.

## PR checklist

- [ ] Style rules satisfied (Black, Flake8, 8-line, no-blank).
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] New behavior has an offline test.
- [ ] No held-out data leaks into a search-time stage.
- [ ] README or `docs/` updated when user-facing behavior changes.
