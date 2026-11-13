# Evidence

This page records what is proven, what is measured, and what is not yet
proven. Reproduce every number with the commands shown.

## 1. Gate 2 beats gate-1-only selection (proven, deterministic)

`scripts/prove_advantage.py` runs the hard benchmark with a scripted
proposer, reviewer, and adjudicator. The baseline selects the highest
gate-1 score. The adversarial loop rejects a candidate that passes the search
split but fails the validation split, then selects the correct candidate on
the next iteration.

```
python scripts/prove_advantage.py
```

Observed over 3 repeats:

| Selection | Held-out pass rate |
| --- | --- |
| Baseline (gate 1 only) | 0.857 |
| Adversarial (gate 2) | 1.000 |

Deterministic: all repeats produced identical results. Enforced by
`tests/test_advantage_proof.py`.

## 2. Executable reviewer tests beat prose review (proven, deterministic)

The same script uses a flawed candidate that passes the search split. With a
prose-only reviewer it passes gate 1. With a reviewer that emits an executable
unittest (`parse_duration("500ms") == 500`) it fails gate 1.

| Reviewer style | Gate 1 outcome |
| --- | --- |
| Prose only | pass |
| Executable tests | fail |

Enforced by `tests/test_advantage_proof.py`.

## 3. Head-to-head against Pi

Both agents used the same model (`beam-free` through the OpenCode Go
endpoint) and the same tasks. Agents ran in isolated temporary workspaces.

Single-file corpus (`benchmarks/headtohead/`, 7 tasks, 3 runs each):

| Agent | Mean pass rate |
| --- | --- |
| This harness | 0.952 |
| Pi | 0.952 |

Multi-file corpus (`benchmarks/repo/`, 4 tasks with hidden tests):

| Config | This harness | Pi |
| --- | --- | --- |
| Reviewer tests off, full corpus | 3/4 | 3/4 |
| Reviewer tests on, full corpus | 4/4 | 2/4 |
| Reviewer tests off, logreport+verlib | 1/2 | 1/2 |
| Reviewer tests on, logreport+verlib | 2/2 | 1/2 |

Reproduce with `scripts/ab_pi.py`; see the README for the exact command.

## What is not proven

- **World-best.** No independent benchmark, external replication, or
  leaderboard comparison exists. This harness has not been compared with
  Claude Code, Aider, OpenHands, or SWE-bench-style evaluation.
- **Statistical significance.** The multi-file result above is one paired run
  per configuration (plus one focused repeat). Pi's failures were mostly
  600-second timeouts, not wrong code.
- **Corpus independence.** The hidden tests were written for this repository.
  They are held out from the agent but not from the authors.
- **Search-time self-improvement at scale.** The offline loop's gain is proven
  on the deterministic hard benchmark, not yet on a large independent corpus.
- **Cost-normalized superiority.** Average latency is reported, but no
  frontier-model, per-dollar comparison exists.

## Frozen protocol (phase 0)

Every comparable run uses these settings:

- Model: `beam-free` through the OpenCode Go OpenAI-compatible endpoint.
- Pi: 1.5.2, `--provider opencode --model beam-free --print --mode text`
  with sessions, context files, extensions, skills, templates, and MCP off.
- Harness: `python -m meta_harness.cli --no-web`.
- Timeout: 600 seconds per agent and task, recorded separately as a timeout
  failure.
- Repeats: 5 per task and configuration; report mean, spread, and timeout
  counts.
- Isolation: every agent runs in a fresh temporary copy of the task
  workspace; hidden tests are injected only after the run.
- Single-file tasks: each agent is asked for one Python block and the code is
  extracted; workspace tasks: the agent edits files in place.

Results from different settings are never mixed.

## Independent corpus v1

Three tasks vendored from real projects, with the projects' own tests as the
hidden oracle (not authored here):

| Task | Source | License | Tests |
| --- | --- | --- | --- |
| itsdangerous_signer | pallets/itsdangerous | BSD-3-Clause | 17 |
| iniconfig_parser | pytest-dev/iniconfig | MIT | 90 |
| packaging_utils | pypa/packaging | Apache-2.0 OR BSD-2-Clause | 79 |

Every task fails with the stubbed source and passes with its reference file;
`tests/test_independent_corpus.py` enforces this in CI. This is still a small
sample; phase 1 targets 20-50 tasks.

## Config search engine

`scripts/search_harness.py` evaluates a configuration grid on a manifest and
returns a Pareto archive over pass rate and elapsed time. Configs vary
environment variables and CLI arguments (verification on/off, draft count,
turn budget). Unit tests cover ranking, averaging, and invalid configs. The
independent-corpus campaign has not yet been run at scale.

## Phase 0 pilot log (honest)

- A 2-repeat pilot at a 300-second timeout was invalid: the harness verification
  loop timed out three times. The frozen protocol uses 600 seconds.
- A 2-repeat logreport pilot at 600 seconds produced 0/2 for this harness and
  2/2 for Pi. Diagnosis: the repair turn could replace a correct workspace with
  a worse one when reviewer tests were wrong. The agent now snapshots the
  workspace before repair and restores it when the tests still fail.
- After that fix, two verification-on samples and one verification-off sample
  all passed. This is a reliability improvement, not a superiority result.
- The pilot flipped the sign of the earlier +50 result. No superiority claim is
  made until the 5-repeat campaign completes.

## Next proof milestones

1. Five or more repeats per configuration with confidence intervals.
2. Twenty to fifty independent repository tasks.
3. Compare against at least one established harness and one frontier model.
4. Reproduce the search-time held-out gain on the independent corpus.
5. External replication of `scripts/prove_advantage.py` and the A/B runs.
