# Third-Party Reproduction Kit

Everything a third party needs to reproduce the measured results without
re-running the model, plus the commands to re-run it entirely.

## Reproduce without model access (offline re-scoring)

The recorded answers, tool calls, and configurations are committed under
`runs/eval/`. A third party can recompute every local score offline:

```bash
python scripts/bfcl_official.py --run-dir runs/eval/bfcl20-deepseek-fixed \
    --out runs/bfcl-official
```

This requires the official evaluator in a separate virtual environment:

```bash
python3.12 -m venv .bfcl-venv
.bfcl-venv/bin/pip install bfcl-eval
.bfcl-venv/bin/python scripts/bfcl_official.py \
    --run-dir runs/eval/bfcl20-deepseek-fixed --out runs/bfcl-official
```

The script converts recorded tool calls into the official checker's Python
call format and runs the official `bfcl-eval` scorer over the simple-python
category. Expected output for the deepseek run: `{"baseline": 0.9,
"harness": 0.9}`.

Local (approximate) scores can be recomputed the same way with the run's
recorded data and `meta_harness.evalbench.cases.score_case`.

## Reproduce live runs

Prerequisites: an OpenCode Go API key exported as `OPENCODE_API_KEY`, and
Pi 0.73.1 with a custom provider entry in `~/.pi/agent/models.json` that
adds the `x-opencode-session` header (see the head-to-head section of
`README.md`).

```bash
source .venv/bin/activate
set -a; source .env; set +a
OPENCODE_MODEL=deepseek-v4.1-flash \
python scripts/eval_compare.py \
    --cases benchmarks/eval/cases/bfcl_simple_python_20.jsonl \
    --repeats 1 --out runs/eval/bfcl20-deepseek

OPENCODE_MODEL=deepseek-v4.1-flash HARNESS_ANSWER_REVIEW=0 \
python scripts/ab_pi.py \
    --manifest benchmarks/headtohead/manifest.json \
    --harness-cmd "python -m meta_harness.cli --no-web" \
    --pi-cmd "pi --provider opencode-go-manual --model deepseek-v4.1-flash --print --mode text" \
    --repeats 3 --out runs/ab-pi-deepseek-reviewoff-r3.json
```

Each run writes `config.json` (model, provider, captured `HARNESS_*`
flags) so the exact configuration is recorded. Because free-tier model
serving drifts over time, re-runs may not match these numbers bit for bit;
compare within-run pairs, never across hours.

## Verification checklist

- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] The audit passes: `python .opencode/skill/python-standard/audit_python_standard.py`.
- [ ] Offline re-scoring reproduces the recorded official BFCL numbers.
- [ ] A fresh live run writes `config.json` and matching report files.

## What is not included

Official leaderboard submissions are the submitting party's responsibility
and must follow each benchmark's submission rules. This kit enables
reproduction; it does not perform third-party validation by itself.
