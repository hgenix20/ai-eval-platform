# ADR-0005: vendor-published scores are the platform's accuracy check

Status: accepted, 2026-09-10.

## Context

The platform reports numbers other people are expected to act on, so its own
measurement has to be checkable. Every layer between a prompt and a score can
be wrong: prompt assembly, decoding settings, the sample set, the scorer, the
conversion of Inspect's `EvalLog` into a `SuiteResult`. A green test suite
proves the code runs. It says nothing about whether the score is right.

## Decision

The platform's accuracy is checked by reproducing a vendor's published benchmark
score on an open model, using a benchmark whose scorer is deterministic. IFEval
is the first one: 541 prompts, its own instruction checkers, no grader model.
Two Qwen2.5-Instruct sizes reproduce their published prompt-strict scores within
one standard error (`docs/results.md`). The bar is agreement inside the
measurement's own error bar, since vendors publish neither decoding settings nor
error bars and an exact match wouldn't mean more.

## Alternatives rejected

- **Trust `inspect_evals` and skip the check.** The task is well maintained, and
  everything on either side of it stays unverified, our own conversion and
  metric extraction included. An uncalibrated harness produces a claim.
- **Compare against leaderboard aggregates.** The Open LLM Leaderboard v2 runs a
  different harness with different prompting, so a gap against it can't
  distinguish our bug from their setup.
- **Calibrate on a hosted API model first.** Providers don't expose enough
  control to pin decoding, the runs cost money, and the first attempt died on a
  402 when monthly credits ran out.

## Consequences

- Local GPU runs are the calibration path: $0.00, decoding settings ours to set,
  and the run reproduces later.
- The gate compares IFEval on `instruction_following.prompt_strict_acc` against
  a baseline tied to the target it was measured on. A different model in that
  row reports not measured.
- Every new benchmark adapter gets a published-score check before any number it
  produces is cited.
