# ADR-0004: cost and latency fail a build, the same as accuracy

Status: accepted, 2026-09-08. Spec sections 4.6 and 10, decision 6.

## Context

A change that holds accuracy flat while doubling token spend or p95 latency is a
regression, and almost nothing treats it as one. BFCL is the only benchmark
reporting cost and latency next to accuracy, and nobody gates on them
(`docs/research/2026-09-07-rag-safety-hallucination-judge.md`).

## Decision

`gate.yaml` carries a row per metric. The offline suite contributes three:
`pass_rate` with a floor, `usd_per_run_p50` at `max_increase_pct: 10`, and
`wall_ms_p95` at `max_increase_pct: 50`. A breached cost or latency row fails the
run exactly as a dropped pass rate does.

The latency threshold is 50 percent, against the spec's 20 percent. This suite's
p95 is about 5 ms (5.294 ms in `results/offline_core/latest.json`) and CI
scheduling noise runs larger than any regression worth catching there. 20 percent
stays the figure for live-model suites, whose latency is in seconds.

Live runs get a second bound. Inspect enforces `cost_limit` per sample, so the
sample count `--limit` bounds total spend; `run_public` divides the remaining
budget by that count and records the mode in `cost_cap_mode`.

## Alternatives rejected

- **Report the two without gating.** A number that fails nothing gets read once.
- **A fixed millisecond ceiling.** Needs retuning on every machine. A percentage
  against a committed baseline does not fix that by itself, since the committed
  numbers were measured on a laptop and a CI runner is slower and noisier. CI
  re-measures the baseline on merge to main, so a pull request compares against
  numbers taken on the same hardware it runs on.
- **20 percent everywhere.** At 5 ms it fails on noise; noisy gates get ignored.

## Consequences

- The cost and latency baselines move only through `gate --update-baseline`,
  which CI runs on main and on no other branch.
- The offline suite uses in-process fakes, so its cost row sits at $0.00 and
  catches only a change that starts spending money. It earns its keep in Phase 2.
