# Results

Every number below comes from a file committed under `results/` and reproduces
with the command shown above it.

## Offline suite (free, runs on every push)

```
evalplat run offline --suite-dir suites/offline_core --target agent-platform-local --results results
```

Source: `results/offline_core/latest.json`, run 2026-09-09T05:27:47Z.

| suite | target | cases | pass rate | p50 wall ms | p95 wall ms |
|---|---|---|---|---|---|
| offline_core | agent-platform-local | 12 | 1.00 (12 of 12) | 3.671 | 5.294 |

Cost is $0.00. The target is the `enterprise-agent-platform` package running
in process with scripted providers, so no tokens are bought and no network is
touched. `usd_per_run_p50` in the JSON is `0.0` for the same reason.

The twelve cases cover approval gating, denied tools, the memory tool path,
protocol-error recovery, validator rejection and retry, and the step cap. Each
one asserts on the trajectory the platform produced: which tools ran and in what
order, the final run status, the steps consumed, side effects on targets that
can observe them, and that the answer the platform accepted is the one the case
script supplied. The planner and validator lines are scripted, so what these
cases measure is the platform's control flow and its governance behavior, not
the quality of a model's answer. A case that binds a tool's real output to the
graded answer, so that a recall failure changes the answer, is Phase 2 work.

The gate compares this run against `baselines/offline_core.json`,
`baselines/offline_core_cost.json`, and `baselines/offline_core_latency.json`:

| suite | metric | baseline | current | threshold | verdict |
|---|---|---|---|---|---|
| offline_core | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass |
| offline_core_cost | usd_per_run_p50 | 0.0000 | 0.0000 | max_increase_pct=10.0 | pass |
| offline_core_latency | wall_ms_p95 | 5.3186 | 5.2940 | max_increase_pct=50.0 | pass |
| public_ifeval | accuracy | n/a | n/a | min=0.7, max_drop=0.03 | not_measured |

Overall verdict: PASS. Reproduce it with `evalplat gate --markdown out/gate.md`.

All three baselines carry `"from": "2026-09-09T05:18:02+00:00"`, an earlier run
of this same suite on this same target. The numbers published above come from
the later run in `latest.json`, timestamped 2026-09-09T05:27:47Z, which is what
the gate read as `current`.

The latency threshold is 50 percent, against the spec's 20 percent. p95 here is
about 5 ms, and CI scheduling noise is larger than any regression at that
scale. Live-model suites use 20 percent. See
[ADR-0004](adr/0004-cost-and-latency-are-gate-metrics.md).

## Public benchmark (live model, budgeted)

```
evalplat run public ifeval --model anthropic/claude-haiku-4-5-20251001 --limit 100 --budget-usd 5 --results results --log-dir logs
```

Live run pending: needs ANTHROPIC_API_KEY. The command above is the run; its
numbers are appended here when it has happened.

IFEval is the first live benchmark because its scoring is its own set of
deterministic instruction checkers. No grader model is involved, so anyone with
the same model and the same sample count gets the same number. SimpleQA
Verified follows in Phase 3, once the judge layer has a calibration set behind
it.

The runner is Inspect AI 0.3.263 against the `inspect_evals/ifeval` task from
inspect-evals 0.19.0, which is the `runner.ref` recorded in
`catalog/entries/ifeval.yaml`. `tests/test_public.py` exercises that path
against Inspect's mock model two ways: a two-sample synthetic task, answered
right once and wrong once, whose `EvalLog` is converted and checked at
accuracy 0.5, and a network-marked IFEval smoke run at `limit=2` that loads
the real task and returns a `SuiteResult` named `public_ifeval`.

Until the run happens, `gate.yaml`'s `public_ifeval` row reports
`not_measured`, which does not fail the gate. Its floor of 0.70 is a first
guess. If a real number lands below it, the floor moves and the number stays.

## Program spend to date

$0.00. No live run has happened, so `results/ledger.jsonl` does not exist yet.
The first live run creates it and appends one line per run.

## What is versioned here

`.gitignore` keeps `results/**/latest.json` and `results/ledger.jsonl` in git
and drops the per-run timestamped JSON files. The published number and the
running spend total are reviewable in a diff; the run archive is not carried in
the repo.
