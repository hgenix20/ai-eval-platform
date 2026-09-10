# Results

Every measured number below comes from a file committed under `results/` and
reproduces with the command shown above it. The one class of number that comes
from outside is a vendor's published benchmark score, and each of those carries
a link to the page it was read from.

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
| offline_core_latency | wall_ms_p95 | 5.2940 | 5.2940 | max_increase_pct=50.0 | pass |
| public_ifeval | instruction_following.prompt_strict_acc | 0.5933 | 0.5933 | max_drop=0.03 | pass |

Overall verdict: PASS. Reproduce it with `evalplat gate --markdown out/gate.md`.

The three offline baselines carry `"from": "2026-09-09T05:27:47+00:00"`, the run
that `results/offline_core/latest.json` holds, so those rows compare a run
against itself until CI re-measures on the next merge to main.
`baselines/public_ifeval.json` carries the Qwen2.5-3B-Instruct run described
below, `"from": "2026-09-10T06:58:40+00:00"`, with a `"target"` of
`hf/Qwen/Qwen2.5-3B-Instruct`. Each baseline is tied to the target it was
measured on. A run of the same suite against a different model reports not
measured in that row, so swapping models does not read as a regression.

The latency threshold is 50 percent, against the spec's 20 percent. p95 here is
about 5 ms, and CI scheduling noise is larger than any regression at that
scale. Live-model suites use 20 percent. See
[ADR-0004](adr/0004-cost-and-latency-are-gate-metrics.md).

## Public benchmark: IFEval calibration

```
evalplat run public ifeval --model hf/Qwen/Qwen2.5-3B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false, "batch_size": 8}' --no-cost-cap --full --max-tokens 1024
```

Google's IFEval, all 541 prompts, against two open instruct models whose vendor
publishes its own IFEval scores. What's being measured here is the platform, so
the figure that matters is the distance to the published score.

| model | prompt-strict | stderr | inst-strict | prompt-loose | inst-loose | published prompt-strict | difference |
|---|---|---|---|---|---|---|---|
| Qwen/Qwen2.5-3B-Instruct | 59.3 | 2.1 | 69.1 | 62.1 | 71.3 | 58.2 | +1.1 |
| Qwen/Qwen2.5-1.5B-Instruct | 41.0 | 2.1 | 50.0 | 45.3 | 54.4 | 42.5 | -1.5 |

Percentages carry one decimal and stderr is in points, taken from the
prompt-level strict figure each run recorded. The two published scores are the
"IFeval strict-prompt" row of the tables "Qwen2.5-3B-Instruct Performance" and
"Qwen2.5-0.5B/1.5B-Instruct Performance" on the Qwen2.5 blog,
<https://qwenlm.github.io/blog/qwen2.5-llm/>.

The measured columns come from
`results/public_ifeval/2026-09-10T065840Z-hf_Qwen_Qwen2.5-3B-Instruct.json`, 88
minutes for 78,277 input and 511,309 output tokens, and
`results/public_ifeval/2026-09-10T082732Z-hf_Qwen_Qwen2.5-1.5B-Instruct.json`,
11 minutes. Both files are committed, and `results/public_ifeval/latest.json` is
the 3B run.

Both models loaded locally on an RTX 4080 Laptop GPU through Inspect's `hf/`
provider: bfloat16, batch size 8, greedy decoding (`do_sample: false`, because
transformers rejects a temperature of 0), 1024 max new tokens, no cost cap.
Every one of those settings is recorded in each run's `meta` block under
`generate`, `model_args`, and `cost_cap_mode`, next to Inspect AI 0.3.263 and
the task id `inspect_evals/ifeval`. Cost was $0.00 both times, because nothing
left the machine.

### Reading the result

The platform reproduces vendor-published prompt-strict scores within one
standard error, at two model sizes. Gaps of +1.1 and -1.5 points sit inside the
2.1-point standard error on our own measurement, so neither one is evidence that
the scoring differs.

That is as strong as the claim gets. The vendor doesn't publish its decoding
settings or its own error bars, so an exact match would be a coincidence and a
match to three decimals would be a reason for suspicion. Agreement inside the
error bar on two model sizes is what a working harness looks like.

None of this ranks these models against anything else. The Open LLM Leaderboard
v2 reports different IFEval numbers for both, because it uses a different
harness and different prompting; those figures describe that setup, and they are
not quoted here.

### Two things that went wrong first

The first attempt of the day went to Hugging Face Inference Providers and
stopped when the account's monthly credits ran out and the provider answered
402. It spent $0.00, and it exposed a defect worth more than the run: an errored
run was being promoted to `latest.json` and read as a measurement, which is now
fixed, so an errored run exits 2, keeps its per-run summary for the record, and
leaves `latest.json` untouched.

An earlier research pass had written down the 3B model's published score as
68.4. That is the MiniCPM3-4B figure, one column over in the same table. The
58.2 in the table above was read back off the primary source, verbatim, before
this page was published, and that is the standing practice for any published
number a comparison rests on. A figure copied out of a wide comparison table is
always one column away from being wrong.

### How the gate uses it

`gate.yaml` compares IFEval on `instruction_following.prompt_strict_acc` with
`max_drop: 0.03` against `baselines/public_ifeval.json`. There is no absolute
floor, since the right level depends on which model is under test and a 3B model
measuring correctly sits near 0.59. The baseline names the target it was
measured on, so a run against a different model reports not measured in that
row.

IFEval is the first public benchmark wired up because its scoring is its own set
of deterministic instruction checkers. No grader model is involved, so anyone
with the same model, the same sample count, and the same decoding settings gets
the same number. SimpleQA Verified follows in Phase 3, once the judge layer has
a calibration set behind it. See
[ADR-0005](adr/0005-published-scores-as-the-accuracy-check.md).

`tests/test_public.py` exercises the runner path against Inspect's mock model
two ways: a two-sample synthetic task, answered right once and wrong once, whose
`EvalLog` is converted and checked at accuracy 0.5, and a network-marked IFEval
smoke run at `limit=2` that loads the real task and returns a `SuiteResult`
named `public_ifeval`. The task id resolves through `runner.ref` in
`catalog/entries/ifeval.yaml`, and inspect-evals 0.19.0 supplies the task.

## Program spend to date

$0.00. `results/ledger.jsonl` is committed and holds three lines, all dated
2026-09-10. The first is the Hugging Face Inference Providers attempt that
errored, recorded at `"usd": 0`. The other two are the local Qwen runs, each at
`"usd": 0.0`. That hosted attempt generated no tokens before it stopped, so it
bought nothing, and a model on the laptop's own GPU carries no per-token price.

## What is versioned here

`.gitignore` keeps `results/**/latest.json` and `results/ledger.jsonl` in git
and drops the per-run timestamped JSON files. The two IFEval calibration runs
are a deliberate exception: their per-run files are committed, because the
numbers on this page are read out of them and a reader should be able to open
the same file. The published number and the running spend total stay reviewable
in a diff, and the rest of the run archive isn't carried in the repo.
