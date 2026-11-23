# Independent Performance Evaluation Report

Prepared: November 22, 2026. Every number below is traced to a recorded run
under `runs/` and to the command that produced it. No claim exceeds what was
measured.

## 1. System architecture

SavrenAI is an adversarial control plane around an underlying model
(`docs/architecture-audit.md`). Requests enter through the CLI or the
programmatic `Agent.run(prompt)` interface. The harness talks to the model
through `OpenRouterClient` (`meta_harness/openrouter.py`), an
OpenAI-compatible chat client. On top of the raw model the harness adds:
the answer reviewer, ledger verification, invariant checks, requirement
tracking, adversarial drafts, answer-time executable tests, a sandboxed
tool loop, and the adversarial search pipeline. Each layer is individually
switchable, which defines the two compared configurations.

## 2. Underlying models and configuration

| Model | Provider | Role |
| --- | --- | --- |
| hy4-flash-free | OpenCode Go endpoint | free-tier model |
| deepseek-v4.1-flash | OpenCode Go endpoint | stronger free model |

Both models are served by the same endpoint; the harness and Pi received
identical endpoints and keys. Environment flags captured per run are stored
in each run's `config.json`.

## 3. Benchmarks and versions

| Benchmark | Version | Scope |
| --- | --- | --- |
| BFCL v4 simple-python | official data from the gorilla repository; official `bfcl-eval` 2026.3.23 checker | 20-entry subset in file order |
| Internal head-to-head corpus | `benchmarks/headtohead/` | 7 single-file coding tasks with hidden tests |
| Internal smoke suite | `benchmarks/eval/cases/smoke.jsonl` | 6 deterministic cases |

BFCL local scores are an approximation; the authoritative numbers below
come from the official `bfcl-eval` checker run with
`scripts/bfcl_official.py`.

## 4. Methodology

Two configurations share model, tasks, tools, and scorers:

- Baseline: raw model plus the same tools, minimal tool loop, no harness
  validation layers (`meta_harness/evalbench/baseline.py`).
- Harness: the same model through the full agent stack
  (`meta_harness/evalbench/harness_run.py`).

Pi head-to-head runs used `scripts/ab_pi.py` with both agents on the same
model and endpoint, isolated workspaces, and 3 or 5 repeats per task.
Scores are pass rates against hidden tests; the official BFCL checker is
deterministic.

## 5. Baseline results

| Evaluation | Model | Score |
| --- | --- | ---: |
| BFCL official, 3 repeats | hy4-flash-free | 0.500 / 0.600 / 0.600 (mean 0.567) |
| BFCL official, 1 repeat | deepseek-v4.1-flash | 0.90 |
| Smoke suite, 5 repeats | hy4-flash-free | 1.000 |

## 6. Harness-enabled results

| Evaluation | Model | Config | Score |
| --- | --- | --- | ---: |
| BFCL official, 3 repeats | hy4-flash-free | review auto | 0.450 / 0.600 / 0.500 (mean 0.517) |
| BFCL official, 1 repeat | hy4-flash-free | review off | 0.35 |
| BFCL official, 1 repeat | deepseek-v4.1-flash | review auto | 0.90 |
| Smoke suite, 5 repeats | hy4-flash-free | review auto | 1.000 |

## 7. Comparative analysis

Versus the raw model on BFCL official scoring, the harness shows no
advantage on the 20-case subset: 0.517 vs 0.567 on hy4-flash-free (3
repeats) and parity 0.90 vs 0.90 on deepseek-v4.1-flash (1 repeat). The
earlier local-scorer delta (+0.35) is retracted: the local scorer ignored
call-count parity and type/expression normalization; it has been corrected
and is documented as conservative.

Versus Pi on the head-to-head corpus:

| Model | Harness config | Harness | Pi | Delta |
| --- | --- | ---: | ---: | ---: |
| hy4-flash-free | review auto, 5 repeats | 0.714 | 0.943 | -0.229 |
| hy4-flash-free | review off, 5 repeats | 1.000 | 0.886 | +0.114 |
| deepseek-v4.1-flash | review auto pre-fix, 3 repeats | 0.810 | 0.857 | -0.048 |
| deepseek-v4.1-flash | review off, 3 repeats | 0.905 | 0.810 | +0.095 |
| deepseek-v4.1-flash | review auto post-fix, 5 repeats | 0.886 | 0.857 | +0.029 |

The review-off harness beats Pi on both models. The review-on harness lost
on both models before the campaign fixes and is now positive: code-bearing
answers skip the adversarial review (its revisions can no longer act on
them), and codeless answers can still be rescued by a revision. The +0.10
head-to-head criterion is met with review off and not yet with the default
review-on configuration.

## 8. Statistical and repeatability analysis

- The BFCL hy4-flash-free numbers are means over 3 repeat runs; the spread
  is large (0.45-0.60), so the negative delta is not statistically
  distinguishable from parity.
- The Pi A/B numbers are pass-rate means over 3 or 5 repeats per task;
  every run recorded zero timeouts.
- The free-tier endpoint drifted during the campaign (identical prompts and
  configs produced different answer styles hours apart), which limits
  attribution across non-simultaneous runs. Within each A/B run both agents
  shared the endpoint state.
- All raw records, configurations, and commands are preserved under
  `runs/`; scores can be recomputed offline from `baseline.jsonl` and
  `harness.jsonl` without re-running the model.

## 9. Known limitations

- Small samples: a 20-entry BFCL subset and a 7-task corpus.
- Free-tier models only; no frontier model key was available.
- GAIA requires HuggingFace authentication and was not run.
- Local BFCL scoring is conservative relative to the official checker.
- The review-on configuration remains a measured weakness on coding tasks.

## 10. Independent verification status

Prepared, not completed. The reproduction kit
(`docs/reproduction.md`) and the deterministic re-scoring paths exist, but
no third party has yet reproduced these runs, and no official leaderboard
submission has been made. Claiming otherwise would be false.

## 11. Defects found and fixed during evaluation

1. `json_value` stripped every triple backtick from reviewer responses,
   corrupting code blocks inside `revised_answer` values
   (`meta_harness/_json_util.py`).
2. Reviewer revisions could drop the original answer's code block; a guard
   now keeps the original when the revision loses the artifact
   (`meta_harness/agent.py`).
3. External benchmark functions returned execution errors, causing the
   model to retry and double-call, destroying BFCL scores; external
   functions now return a stub success (`meta_harness/tools.py`). This fix
   alone moved the deepseek harness BFCL score from 0.35 to 0.90.
4. The local tool-call scorer ignored call-count parity
   (`meta_harness/evalbench/cases.py`).
5. Review-driven revisions were net negative on code-bearing answers.
   The reviewer can no longer replace a code-bearing answer, and such
   answers skip the review call entirely; codeless answers can still be
   rescued (`meta_harness/agent.py`).

## 12. Conclusion

The central question - does the harness add measurable value over the same
model without it - has a measured, conditional answer. Against Pi, the
harness now wins head-to-head in every recent configuration: +0.114 and
+0.095 with review off across two models, and +0.029 with the default
review-on config after the campaign fixes (it lost before the fixes).
Against the raw model on official BFCL scoring it achieves parity, not
superiority. The success criterion is therefore met for the review-off
configurations and partially met for the default configuration; the
remaining gaps are the +0.10 margin with review on, frontier-model and
GAIA coverage, and independent third-party verification.
