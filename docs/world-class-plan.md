# Plan: from strong prototype to world-class framework

This is the execution plan for making Minimal Harness the reference framework
for autonomous, evidence-driven improvement of coding agents and the projects
they maintain. It is written to be falsifiable: every claim has a measurement,
a baseline, and an exit gate.

## Mission

Build the framework that proposes changes to a harness, writes executable
tests for them, adversarially verifies the result, and ships only what survives
held-out evaluation - reproducibly, safely, and with public evidence.

The unique asset is not the tool loop. It is the adversarial loop:
propose -> review with executable tests -> gate 1 -> adjudicate -> independent
gate 2 -> ratchet. Pi and other harnesses are static; this one improves and
proves it.

## What "best in the world" means (falsifiable)

No claim ships unless all five hold:

1. **Held-out self-improvement**: at least +10 points over the seed harness on
   an independent corpus, at a fixed model, budget, and timeout, with a 95%
   confidence interval across at least 5 seeds.
2. **Head-to-head**: at least +10 points pass rate, or at least 30% lower cost
   at equal pass rate, against a named baseline (Aider, OpenHands, Claude
   Code, or Pi), over at least 5 repeats per task.
3. **Reliability**: at least 99% crash-free sessions; p50 overhead at most 15%
   versus the named baseline.
4. **Reproducibility**: the same environment hash and seed produce the same
   score; an independent party can rerun the protocol and get the same result.
5. **Safety**: zero sandbox escapes and zero held-out leaks in the red-team
   suite.

If a criterion fails, the result is reported as a failure.

## Current state (November 2026)

Proven (deterministic, test-enforced by `tests/test_advantage_proof.py`):

- Gate 2 beats gate-1-only selection: held-out 0.857 -> 1.000.
- Executable reviewer tests block a candidate that prose review passes.

Measured (small samples):

- Single-file corpus versus Pi: 0.952 versus 0.952, a tie at the ceiling.
- Multi-file corpus with answer-time reviewer tests: 4/4 versus 2/4; without
  the feature: 3/4 versus 3/4. One paired run per configuration.
- Focused repeat on the two hard tasks: 2/2 versus 1/2 with tests on; 1/2
  versus 1/2 with tests off.

Known gaps:

- Corpus is small and self-authored.
- Sample sizes are too small for confidence intervals.
- Pi failures were mostly 600-second timeouts.
- No frontier model and no established harness comparison.
- Answer-mode tools run on the host; no rootless sandbox by default.
- Single default provider, no packaging or extension ecosystem.

## Workstreams

### A. Evaluation spine

- Independent corpus of 20-50 repository tasks, sourced from real issues and
  existing test suites where possible. Hidden tests are authored or reviewed
  by someone other than the proposer.
- Deterministic oracles with flake detection, environment hashes, per-task
  cost, and leakage scanning.
- Statistics: 5+ repeats, confidence intervals, pre-registered hypotheses.

Exit gate: the corpus discriminates between a reference and a flawed solution
on every task, and reproduces bit-for-bit in CI.

### B. Search engine

- Search over harness configurations, not only solution files: system prompts,
  tool subsets, context and compaction policies, stop rules, model routing.
- Operators: component mutation, crossover, keep-winner-mutate-one-knob.
- Pareto archive over score, cost, and latency; budgeted search; resume after
  interruption.

Exit gate: at least +10 points held-out over the seed at fixed budget, 5 seeds,
with a non-dominated archive.

### C. Test synthesis

- Reviewer emits executable tests that gate 1 runs (done).
- Add property-based, metamorphic, and mutation-based checks; score test
  suites by fault detection and false-positive rate.
- Calibrate the reviewer against gate-2 outcomes: precision and recall of
  blocking.

Exit gate: reviewer-generated tests detect at least 50% of seeded defects that
the task tests miss, with under 5% false positives on correct solutions.

### D. Runtime and safety

- Rootless sandbox by default for answer-mode tools; no network; dropped
  capabilities; PID and memory limits; pinned image digest.
- Approval flows for installs and destructive actions; protected paths; secret
  redaction.
- Provider parity (Anthropic, OpenAI, local), retries, streaming.
- Packaging and a compatibility surface for external integrations.

Exit gate: red-team suite has zero escapes; crash-free rate at least 99%;
p50 overhead at most 15%.

### E. Evidence and governance

- `docs/evidence.md` is the single source of truth for claims.
- Every experiment publishes command, commit, model pin, timeout, raw JSON,
  and confidence intervals.
- External replication before any "best" claim.
- Release notes never overstate results.

Exit gate: one independent party reproduces the headline result.

## Phases and exit gates

| Phase | Duration | Deliverables | Exit gate |
| --- | --- | --- | --- |
| 0. Protocol and repeats | 1 week | `--repeats`, pre-registered protocol, CI statistics | 5 repeats run on the hard corpus; intervals reported |
| 1. Independent corpus | 2-3 weeks | 20-50 tasks with independent tests | corpus discriminates; no leakage |
| 2. Baselines and models | 3-4 weeks | Pi, Aider, OpenHands, frontier model runs | paired results with intervals and cost |
| 3. Config search | 4-6 weeks | harness-config search and Pareto archive | +10 points held-out, 5 seeds |
| 4. Test synthesis | 4 weeks | property/metamorphic/mutation checks; calibrated reviewer | detection and false-positive gates |
| 5. Runtime and safety | 3-4 weeks | rootless sandbox, approvals, providers, packaging | red-team and reliability gates |
| 6. Replication and release | ongoing | public evidence, external rerun, releases | independent reproduction |

## Experimental protocol

- Pin model, temperature, timeout, prompt, tools, and workspace template.
- Run agents in isolated temporary workspaces; score with hidden tests.
- At least 5 repeats per task and configuration; report mean and 95%
  confidence interval, never a single run.
- Pre-register the hypothesis and the stopping rule.
- Publish raw JSON, commit hash, model pin, and environment hash.
- No held-out identifiers reach the proposer, reviewer, adjudicator, or any
  search-time artifact.

## Metrics

| Metric | Target |
| --- | --- |
| Held-out pass rate (independent corpus) | at least +10 points over seed |
| Head-to-head pass rate | at least +10 points, or 30% lower cost at equal rate |
| Cost per solved task | measured and reported for every run |
| p50 latency overhead | at most 15% |
| Crash-free sessions | at least 99% |
| Reviewer test detection | at least 50% of seeded defects |
| Reviewer false positives | at most 5% |
| Sandbox escapes | zero |

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Overfitting to self-authored tests | independent corpus and independent test authors |
| Single-run claims | repeats, intervals, pre-registration |
| Timeout-driven wins | report timeouts separately; raise limits; rerun |
| Reviewer false negatives/positives | calibrate against outcomes; bounded repair |
| Benchmark contamination | private holdout, leakage scanner, rotating tasks |
| Model drift | pin model and record provider version |
| Host execution of generated tests | rootless sandbox, no network, resource limits |
| Overstating results | evidence page and release checklist |

## Budget and timeline

- Engineering: roughly 4-6 months of focused work for one experienced engineer.
- Compute: the current free model is adequate for the protocol; frontier-model
  runs need a metered budget and should be batched.
- Critical path: independent corpus (phase 1) and config search (phase 3).

## Next 10 days (phase 0)

1. Add `--repeats N` to `scripts/ab_pi.py`; average per task; report spread
   and per-run values.
2. Run 5 repeats on `benchmarks/repo/` with reviewer tests off and on, same
   model and timeout; publish intervals in `docs/evidence.md`.
3. Freeze the protocol in `docs/evidence.md` so later results are comparable.
4. Record timeouts as failures with a separate timeout count.
5. Start phase 1: draft the independent corpus specification and the task
   intake checklist.

Acceptance for phase 0: the repo-corpus result has a confidence interval, the
protocol is frozen, and the CI runs the proof plus the full test suite.
