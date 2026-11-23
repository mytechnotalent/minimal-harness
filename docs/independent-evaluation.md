# Independent Evaluation Guide

How to reproduce the baseline-vs-harness comparison, wire external
benchmarks, and prepare results for independent verification.

## The comparison contract

Both configurations share the model, the tasks, the tools, and the scorers.
The only difference is the harness validation stack:

- Baseline: `BaselineRunner` (`meta_harness/evalbench/baseline.py`) runs the
  raw model through a minimal tool loop. No answer review, no ledger, no
  invariants, no requirements, no drafts, no answer-time tests, no repair.
- Harness: `HarnessRunner` (`meta_harness/evalbench/harness_run.py`) runs
  the same model through the full `Agent` stack with every layer the
  product enables by default.

Every run writes `config.json` (model, provider, case ids, repeats, and the
captured `HARNESS_*` flags), raw per-case records in `baseline.jsonl` and
`harness.jsonl`, the comparison in `comparison.json`, and `report.md`.

## Running the internal suite

```bash
source .venv/bin/activate
python scripts/eval_compare.py --cases benchmarks/eval/cases/smoke.jsonl \
    --repeats 5 --out runs/eval/smoke
```

Five repeats enable the Wilson confidence interval in `report.md` and
`comparison.json`. The internal suite is the seed for the Operational
Reliability Suite; grow it with held-out, deterministic, standard-library
scorable cases before claiming anything beyond what it measures.

## Wiring BFCL

1. Obtain the official BFCL v4 data from the Berkeley Function-Calling
   Leaderboard repository (`ShishirPatil/gorilla`, path
   `berkeley-function-call-leaderboard/bfcl_eval/data/`), under its license.
   The HuggingFace mirror `gorilla-llm/BFCL_v4` requires authentication.
2. Convert one split, pairing entries with the matching `possible_answer`
   file:

```python
import json
from meta_harness.evalbench.adapters import bfcl_cases
from meta_harness.evalbench.cases import dump_cases

records = [json.loads(line) for line in open("BFCL_v4_simple_python.json")]
answers = [json.loads(line) for line in open("possible_answer/BFCL_v4_simple_python.json")]
dump_cases("benchmarks/eval/cases/bfcl.jsonl", bfcl_cases(records, answers))
```

3. Run `scripts/eval_compare.py --cases benchmarks/eval/cases/bfcl.jsonl`.

The adapter maps BFCL questions to user prompts, converts pythonic
parameter types to JSON Schema, and advertises the benchmark's own function
schemas to both configurations. Local scoring requires the function name
plus one accepted argument value per parameter, which approximates but does
not replace BFCL's official evaluator. Submission scores must follow BFCL's
official scoring and submission rules.

A pinned 20-entry subset of the simple-python split is committed at
`benchmarks/eval/cases/bfcl_simple_python_20.jsonl` with the results recorded
in `docs/evidence.md`.

## Wiring GAIA

1. Download the GAIA validation metadata (JSONL) from the official GAIA
   repository under its license.
2. Convert and run the same way with `gaia_cases`; attached files must be
   placed in the workspace before the run (both configurations receive the
   same files).

## Inspect AI

`adapters.inspect_summary` reads headline numbers from an Inspect EvalLog,
and `adapters.inspect_export` writes a minimal EvalLog-shaped structure for
record-keeping. Official Inspect integration means running the task through
Inspect's own `eval()` with the harness as the solver; the exported log is
an approximation for internal comparison, never a claimed Inspect score.

## Measured results (November 22, 2026)

Authoritative numbers use the official `bfcl-eval` checker; full record in
`docs/evidence.md` and `docs/evaluation-report.md`.

| Evaluation | Baseline | Harness | Notes |
| --- | ---: | ---: | --- |
| BFCL v4 simple-python subset, official, 3 repeats (hy4-flash-free) | 0.567 | 0.517 | parity, not superiority |
| BFCL v4 simple-python subset, official, 1 repeat (deepseek-v4.1-flash) | 0.90 | 0.90 | parity |
| Head-to-head vs Pi, review off (hy4-flash-free, 5 repeats) | Pi 0.886 | 1.000 | +0.114 |
| Head-to-head vs Pi, review off (deepseek-v4.1-flash, 3 repeats) | Pi 0.810 | 0.905 | +0.095 |
| Head-to-head vs Pi, review on pre-fix (hy4-flash-free, 5 repeats) | Pi 0.943 | 0.714 | recorded as a failure |
| Head-to-head vs Pi, review on post-fix (deepseek-v4.1-flash, 5 repeats) | Pi 0.857 | 0.886 | +0.029 |

The review layer is model-dependent and must be named in every claim. The
local BFCL scorer is a conservative approximation; the official checker is
the source of record.

## Reproducibility for a third party

- All scoring is deterministic and standard-library only, so a third party
  can re-score the recorded answers from `baseline.jsonl` and
  `harness.jsonl` without re-running the model.
- `config.json` records the model id, provider, benchmark file, repeat
  count, and the `HARNESS_*` flags captured at run time.
- Re-running the same command with the same provider and flags must
  reproduce the same config block; model-level nondeterminism is recorded,
  not hidden, through the repeat statistics.

## Honesty rules

- Never mix held-out tasks into search-time prompts or stages.
- Never claim an official benchmark score without running the benchmark's
  official evaluator and submission process.
- Never publish a number without the exact command that produced it.
- Report harness overhead (time, tokens, cost) next to every improvement.
