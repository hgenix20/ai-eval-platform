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

The twelve cases cover approval gating, denied tools, memory write and recall,
protocol-error recovery, validator rejection and retry, and the step cap. Each
one asserts on a trajectory, not on a string of model output.

The gate compares this run against `baselines/offline_core.json`,
`baselines/offline_core_cost.json`, and `baselines/offline_core_latency.json`:

| suite | metric | baseline | current | threshold | verdict |
|---|---|---|---|---|---|
| offline_core | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass |
| offline_core_cost | usd_per_run_p50 | 0.0000 | 0.0000 | max_increase_pct=10.0 | pass |
| offline_core_latency | wall_ms_p95 | 5.3186 | 5.2940 | max_increase_pct=50.0 | pass |
| public_ifeval | accuracy | n/a | n/a | min=0.7, max_drop=0.03 | not_measured |

Overall verdict: PASS. Reproduce it with `evalplat gate --markdown out/gate.md`.

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
`catalog/entries/ifeval.yaml`. Its path through the platform is verified end to
end in `tests/test_public.py` against Inspect's mock model, which exercises the
same conversion code a priced model goes through.

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
