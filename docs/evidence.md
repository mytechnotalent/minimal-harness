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

Five tasks vendored from real projects, with the projects' own tests as the
hidden oracle (not authored here):

| Task | Source | License | Tests |
| --- | --- | --- | --- |
| itsdangerous_signer | pallets/itsdangerous | BSD-3-Clause | 17 |
| iniconfig_parser | pytest-dev/iniconfig | MIT | 90 |
| packaging_utils | pypa/packaging | Apache-2.0 OR BSD-2-Clause | 79 |
| itsdangerous_serializer | pallets/itsdangerous | BSD-3-Clause | 41 |
| packaging_markers | pypa/packaging | Apache-2.0 OR BSD-2-Clause | 2500 |

Every task fails with the stubbed source and passes with its reference file;
`tests/test_independent_corpus.py` enforces this in CI. This is still a small
sample; phase 1 targets 20-50 tasks.

## Independent corpus v1 results (beam-free)

| Task | This harness | Pi | Our time | Pi |
| --- | --- | --- | --- | --- |
| itsdangerous_signer | 0/1 | 0/1 | 139-191s | 600s timeout |
| iniconfig_parser | 0/1 | 0/1 | 246s | 600s timeout |
| packaging_utils | 0/1 | 0/1 | 274s | 900s timeout |

All three tasks fail for both agents. The harness finishes; Pi times out. This
is a latency and completion signal, not a capability win. The free model is
the limiting factor on real-project tasks.

## Independent corpus with deepseek-v4.1-flash

Clean stubs, default harness settings (answer-time verification off), 1200s,
1 run per task:

| Task | Harness | Pi | Our time | Pi |
| --- | --- | --- | --- | --- |
| itsdangerous_signer | 1/1 | 1/1 | 146s | 55s |
| iniconfig_parser | 0/1 | 1/1 | 276s | 88s |
| packaging_utils | 0/1 | 1/1 | 272s | 47s |

Pi passes all three and is 2-6x faster. The harness passes one. A previous
deepseek run produced a different split (itsdangerous miss, iniconfig and
packaging pass), so single-run variance is large; these numbers are not
stable estimates.

During an earlier run an agent modified the vendored template, contaminating
later runs. Stubs are restored, and `ab_pi.run_guarded` now snapshots and
restores any template that changes during evaluation.

Conclusion: on real repository tasks at this model, Pi is currently equal or
better on capability and clearly better on latency. The offline adversarial
search remains this project's only proven differentiator.

## Model access update

`deepseek-v4.1-flash` is now enabled and works. It is the default model in
`.env.example`. Stronger models remain blocked:

- `big-pickle`: unavailable on the OpenCode Go inference endpoint.
- `claude-fable-5`: listed on the Zen endpoint, but the key returns HTTP 403
  `permission_error` with "Model access is disabled".

## Latency diagnosis (deepseek-v4.1-flash)

Five repeats on itsdangerous, default settings: harness 0.80 (4/5) versus Pi
1.00 (5/5); 239s versus 79s average per task.

Instrumented single runs:

| Run | Calls | Prompt tokens | Model seconds | Wall | Hidden test |
| --- | --- | --- | --- | --- | --- |
| A | 26 | 275k | not recorded | 219s | pass |
| B | 13 | 137k | 181.2 | 184s | fail |

Model time is about 98% of wall time; tool execution and the test runner are
negligible. Per-call latency is roughly 12-14 seconds. Turn count varies
between 13 and 26, and that variance drives both latency and outcome. The
answer-review call is one of those calls; the coding-standards prompt inflates
prompt size but the provider latency is per call, not per token.

Conclusion: the latency gap is a turn-count and provider-latency problem, not
a tooling problem. Reducing turns trades quality against speed, and the
current evidence does not show our extra turns buying reliable quality.

## Lean mode results (deepseek-v4.1-flash)

`--lean` uses a short repo-editing prompt, hides web tools, skips the
text-only answer review after file edits, and asks for few turns.

| Task | Repeats | Harness | Pi | Harness time | Pi time |
| --- | --- | --- | --- | --- | --- |
| itsdangerous_signer | 5 | 0.80 | 1.00 | 116s mean | 155s mean |
| iniconfig_parser | 3 | 0.67 | 1.00 | 177s median | 126s median |
| packaging_utils | 3 | 0.67 | 1.00 | 186s median | 113s median |

Lean mode cuts latency roughly in half versus the default harness on the
first task (239s to 116s) and is sometimes faster than Pi, but it is not
consistently faster and it is less accurate. The remaining gap is agent
workflow quality and turn count, not tooling. This is an opt-in config, not
a claimed default win.

## Beam-free hardening campaign (5 tasks, 5 repeats)

After adding `grep`, `glob`, `list`, `repo_map`, `patch`, fuzzy edits, a
no-edit nudge that restricts tools to edit/write/patch, shell-path
confinement, bounded repair turns, and a beam-free model profile, the
independent corpus was rerun at 600 seconds per task.

| Task | Pass | Runs | Mean seconds | Mean calls |
| --- | --- | --- | --- | --- |
| itsdangerous_signer | 0 | 5 | 26.8 | 12.8 |
| iniconfig_parser | 0 | 5 | 30.9 | 12.8 |
| packaging_utils | 0 | 5 | 21.5 | 12.8 |
| itsdangerous_serializer | 0 | 5 | 21.0 | 12.8 |
| packaging_markers | 0 | 5 | 12.4 | 12.8 |

All 25 runs fail. Failure classes: 24 `tests_fail`, 1 `no_edit`, zero
timeouts, zero provider errors. Twenty-four of 25 runs edited a file, so the
nudge fixed the exploration failure; the remaining gap is incomplete
implementation by `beam-free`, not tool access or latency.

A five-run comparison at 24 turns also scored 0/5 and was slower (mean about
50 seconds), so the 12-turn profile is not the limiting factor. A diagnostic
24-turn run of itsdangerous_signer reached 15 of 17 hidden assertions, which
shows the harness can produce most of the implementation but cannot close the
last edge cases at this model.

Do not claim a capability win from these runs. The harness improvements raise
edit rate and reduce wasted exploration; the model is the ceiling.

## DeepSeek 4.1 Flash campaign (5 tasks, 5 repeats)

Same harness, same profile, after model access was enabled.

| Task | Pass | Runs | Mean seconds | Mean calls |
| --- | --- | --- | --- | --- |
| itsdangerous_signer | 3 | 5 | 86.3 | 14.2 |
| packaging_utils | 2 | 5 | 174.6 | 21.6 |
| itsdangerous_serializer | 2 | 5 | 154.5 | 21.8 |
| iniconfig_parser | 0 | 5 | 186.5 | 22.2 |
| packaging_markers | 0 | 5 | 205.9 | 21.8 |

Overall: **7/25 pass (28%)**, mean 161.5 seconds, 20.3 calls, about 200k
prompt and 12.3k completion tokens per run. Every failure is `tests_fail`;
there are zero timeouts, provider errors, or no-edit runs. The harness
mechanics work; the remaining gap is implementation quality on these real
projects.

For comparison, beam-free scored 0/25 under the same harness (22.5 seconds
mean, 12.8 calls). Pi's earlier single-run sample passed 3/3 on a three-task
subset at 47-118 seconds, so Pi remains faster and likely stronger. A 5x5 Pi
comparison is still required before any head-to-head claim.

## Head-to-head: DeepSeek 4.1 Flash, 5 tasks x 5 repeats

Pi was run against the same manifest with the same model id
(`deepseek-v4.1-flash`) through a custom OpenCode Go provider that supplies
the required `x-opencode-session` header. Both agents ran five repeats per
task at a 900-second timeout.

| Task | Harness | Pi |
| --- | --- | --- |
| itsdangerous_signer | 3/5 | 5/5 |
| iniconfig_parser | 0/5 | 5/5 |
| packaging_utils | 2/5 | 5/5 |
| itsdangerous_serializer | 2/5 | 5/5 |
| packaging_markers | 0/5 | 5/5 |
| **Overall** | **7/25 (28%)** | **25/25 (100%)** |

Mean wall time: harness 161.5 seconds, Pi 204.7 seconds. The harness is about
27% faster but passes 3.6x fewer tasks. At this model, Pi is clearly the
stronger agent; the harness has no capability win on this corpus.

Failure review showed two harness-specific causes worth fixing: the model
sometimes asked for clarification although the CLI advertises no `ask` tool,
and some edits introduced Python syntax errors. The harness now tells the
model to proceed when `ask` is unavailable and rejects Python writes, edits,
or patches that do not compile.

A focused five-repeat rerun after those fixes scored 1/5 on iniconfig_parser
(up from 0/5) and 0/5 on packaging_markers. The fixes remove two failure
modes but do not close the capability gap.

Reproduce Pi with the same model through a custom provider in
`~/.pi/agent/models.json`:

```json
{
  "providers": {
    "opencode-go-manual": {
      "baseUrl": "https://opencode.ai/inference/go/openai/v1",
      "api": "openai-completions",
      "apiKey": "OPENCODE_API_KEY",
      "headers": {"x-opencode-session": "pi-benchmark-session"},
      "models": [{"id": "deepseek-v4.1-flash"}]
    }
  }
}
```

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
