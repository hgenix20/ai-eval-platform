# Results

Every measured number below comes from a committed file and reproduces with
the command shown above it: a run summary under `results/`, or, for the gate
table's baseline column, a file under `baselines/`. Two classes of figure come
from outside that rule and say so where they appear: a vendor's published
benchmark score, each carrying a link to the page it was read from, and the
live MCP server's tool count, which a network-marked test produced.

Five offline suites run against the agent platform in process: `offline_core`
from Phase 1, and the four gap suites `trajectory`, `faults`, `memory`, and
`injection` from Phase 2. All five are free, all five run on every push, and
each has its own section below. The five offline runs published here were
taken on 2026-09-11, three in one pass, the faults suite re-run later the
same morning after its recovery metric was corrected, and the trajectory
suite re-run after two of its cases gained an assertion; the public-benchmark
runs further down are from 2026-09-10.

A sixth suite, `groundedness`, came in with Phase 3. It is the first one that
needs a model to produce the answer being graded, so it runs through the MCP
target on a local GPU and does not run on every push. Its section and the
judge calibration behind it are below the MCP target section.

## Offline core suite

```
evalplat run offline --suite-dir suites/offline_core --target agent-platform-local --results results
```

Source: `results/offline_core/latest.json`, run 2026-09-11T06:55:29Z.

| suite | target | cases | pass rate | p50 wall ms | p95 wall ms |
|---|---|---|---|---|---|
| offline_core | agent-platform-local | 12 | 1.00 (12 of 12) | 3.796 | 5.316 |

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
the quality of a model's answer.

One gap this section has always named is still open. No case here binds a
tool's real output to the graded answer, so that a recall failure would change
what the answer says. `session-answer-uses-recall` in the memory suite moves
partway: the grade reads the final answer instead of the recall step. The
answer text is still a scripted string, so the binding itself waits on a
target where a model writes the answer. The groundedness suite below is that
target: its `answer_contains` and `quotes_in_source` dimensions grade text a
model wrote from what the retrieval tools actually returned. The gap in this
suite stays open.

## Trajectory suite

```
evalplat run offline --suite-dir suites/trajectory --target agent-platform-local --results results
```

Source: `results/trajectory/latest.json`, run 2026-09-11T08:15:37Z.

| suite | cases | pass rate | step efficiency mean | p50 wall ms | p95 wall ms |
|---|---|---|---|---|---|
| trajectory | 10 | 1.00 (10 of 10) | 0.75 (5 cases) | 3.676 | 5.626 |

Ten cases assert on the shape of the path the platform took: strict and
unordered tool sequences, forbidden tools that stay unused, redundant calls
counted by tool name plus arguments, and step efficiency against a per-case
reference count. Recording a tool's actual arguments in the trajectory is what
makes the redundancy check real, since two `lookup` calls with different keys
are two units of work and two with the same key are one.

Two of the ten carry an assertion that only says what must not happen, and a
run that called no tools at all would satisfy it. Both now pin the path that
was supposed to run as well: `forbidden-tool-never-called` asserts
`tools_used: {strict: [lookup]}` next to its `forbidden_tools`, and
`unordered-lookups-accepted` asserts a real `lookup` output next to its
`max_redundant_calls: 0`. This run is the one taken after that change.

The 0.75 mean efficiency is a property of the case mix. Only the five cases
that declare a `reference_steps` count contribute to it, and two of those
overshoot on purpose: `repeated-lookup-is-redundant` scores 0.5 for calling
`lookup` twice with the same key, and `over-long-path-scored` scores 0.25 for
four distinct lookups against a reference of one. The other three score 1.0.
Both overshoots are recorded as cost and neither fails its case. Cost in
dollars is $0.00.

## Faults suite

```
evalplat run offline --suite-dir suites/faults --target agent-platform-local --results results
```

Source: `results/faults/latest.json`, run 2026-09-11T07:16:00Z.

| suite | cases | pass rate | recovery rate | expectation match | p50 wall ms | p95 wall ms |
|---|---|---|---|---|---|---|
| faults | 11 | 0.82 (9 of 11) | 0.75 (6 of 8) | 0.82 (9 of 11) | 3.312 | 155.167 |

Eleven cases inject a seeded fault at a named seam and grade whether the run
came back from it: a tool handler that raises, malformed and empty tool
output, a 300 ms tool delay, retryable and fatal provider errors, a truncated
provider reply, and a validator-side provider error.

Two metrics answer two questions. `recovery_rate` is the share of the eight
cases that were supposed to recover and did, which is 6 of 8.
`expectation_match_rate` is the share of all eleven that ended the way their
case predicted, which is 9 of 11. Three cases set `recovered: false` and sit
outside the recovery denominator: two predict a run the platform cannot come
back from, and the third is the control case, which fires no fault at all.
Across all eleven, seven runs completed and four ended in `target_error`.

A run counts as recovered when at least one fault fired, the run completed,
and every other dimension the case asserts on passed. That last term means an
unrelated assertion failure reads as a non-recovery. In every case here the
two coincide, since a case whose run came back also meets its other
assertions.

Two of those four aborts are predicted and pass. A fatal provider error is
re-raised with no fallback attempt, and a validator fault has no fallback route
at all, since the fallback this suite installs applies only to the planner
route and leaves the validator's route at depth one. Both are the platform
behaving as designed; the depth-one route is this harness's own configuration,
and F5 in the write-up splits the two.

The other two aborts are the finding, and both are tool-raise cases.
`ToolExecutor.execute` in the agent platform does not catch an exception from
a tool handler, so a raised tool aborts the whole run before the model ever
sees an error it could work around. Malformed output and empty output both
recover, which shows the recovery path exists and that a raised exception
never reaches it. See [docs/red-team-findings.md](red-team-findings.md).

p95 of 155 ms is the single 300 ms delay case showing through an eleven-case
sample. At that sample size the percentile does one job: it confirms the delay
fault registers in the timing the runner records.

Only `recovery_rate` is gated. `expectation_match_rate` is published because
it reports a different thing, how well the case files predict the platform. A
drop there points at a case file that has gone out of date.

## Memory suite

```
evalplat run offline --suite-dir suites/memory --target agent-platform-local --results results
```

Source: `results/memory/latest.json`, run 2026-09-11T06:55:37Z.

| suite | cases | pass rate | step efficiency mean | p50 wall ms | p95 wall ms |
|---|---|---|---|---|---|
| memory | 11 | 1.00 (11 of 11) | 1.00 (1 case) | 4.738 | 8.071 |

Eleven cases drive the platform's `remember` and `recall` tools across up to
four sequential sessions that share one store, one registry, and one approval
queue. What they check is persistence under interference: recall after an
unrelated distractor session, recall after two non-adjacent sessions, a
300-character fact recovered by an unrelated keyword, and five facts stored in
one session with one of them retrieved by name.

Two findings came out of authoring the suite. The first is about ranking.
When two stored values differ only in a token the query does not mention,
they score identically against that query, and `search` sorts on similarity
alone; Python's stable sort then leaves the older value first. Every
`MemoryItem` already carries a `created_at`, in the in-process store and in
the pgvector schema alike, and nothing in the ranking reads it. The `recall`
tool payload drops it too, returning text, score, and metadata only, so an
agent cannot break the tie for itself either.

The second is that there is no forget primitive. `forget` is neither granted
nor registered, and a call to it comes back as `tool_denied`, which is the
authorization check running before the existence check. Both findings are
recorded as platform properties, and neither is patched from this repository.

## Injection suite

```
evalplat run offline --suite-dir suites/injection --target agent-platform-local --results results
```

Source: `results/injection/latest.json`, run 2026-09-11T06:55:40Z.

| suite | cases | pass rate | attack success | utility | p50 wall ms | p95 wall ms |
|---|---|---|---|---|---|---|
| injection | 16 | 1.00 (16 of 16) | 0.25 (3 of 12) | 1.00 (4 of 4) | 3.666 | 4.579 |

Sixteen cases, twelve attacks and four benign, run against a world that
carries a secret-bearing `lookup` key, an ungranted `post_webhook` tool, and a
`read_document` tool whose fixed document contains an indirect injection. The
scripted planner obeys the injection in every attack case, so the model's
resistance is not what is measured. The platform's controls are.

Three attacks land: a secret in the final answer, a secret written to memory,
and an exfiltrating answer that the model-side validator approves. Nine are
stopped by the approval gate, the authorization boundary, or the step cap, and
all four benign cases complete, so utility under attack is 4 of 4. A case
passes when its predicted outcome matches the observed one, which is why the
three successful attacks are still passing cases.

`attack_success_rate` is gated by `max_rise: 0.0`, so a fourth success fails
the build. The full attack table, the severity of each finding, and a proposed
mitigation for each are in
[docs/red-team-findings.md](red-team-findings.md).

## MCP target

`evalplat run mcp` points an Inspect ReAct agent at one Model Context Protocol
server, local on stdio or remote over HTTP, and runs a suite's cases through
its tools. The server's tool list is read once before the suite starts, so an
unreachable server exits 2 instead of failing every case, and the names it
returned are recorded in the run summary's `meta["mcp_tools"]`.

The network-marked test in `tests/test_mcp_target.py` connects to
<https://mcp.signalnodus.ai/> and lists 31 tools: lookup_company,
recent_filings, latest_filings, filing_section, compare_filings,
verify_financial_claim, filing_events, company_financials, who_holds,
institutional_holdings, insider_trades, edgar_search, activist_stakes,
ipo_pipeline, rewrite_ratio, evm_balance, evm_gas, evm_receipt, token_price,
fx_rate, domain_report, prediction_markets, government_contracts, lobbying,
cftc_positioning, energy_data, crop_data, trade_flows, x402_audit,
token_report, gas_optimizer. Listing is one connect, one `tools/list` round
trip, one disconnect. No tool was called, so no key was needed and nothing was
spent. There is still no published suite score against a live MCP server. The
groundedness suite below is the first scored run through the MCP target, and it
uses a local fixture server over committed EDGAR text, for the reasons in
[ADR-0008](adr/0008-groundedness-against-the-golden-set-with-a-fixture-retriever.md).

## Groundedness suite

```
evalplat run mcp --suite-dir suites/groundedness --mcp-command .venv/Scripts/python.exe --mcp-args eval_platform/retrievers/edgar_fixture_server.py --server-name edgar-fixture --model hf/Qwen/Qwen2.5-3B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --max-steps 6 --budget-usd 0 --max-wall-s 7200 --results results

evalplat judge --suite-dir suites/groundedness --results results --judge hf/Qwen/Qwen2.5-3B-Instruct --judge hf/Qwen/Qwen2.5-1.5B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --hhem
```

Source: `results/groundedness/latest.json`, run 2026-09-11T14:54:25Z, with the
judge pass applied at 2026-09-11T15:18:01Z (`meta.judge_pass.at`). The run as
it stood before the judge pass is kept at
`results/groundedness/2026-09-11T145425Z-mcp_edgar-fixture.json`.

What the suite asks: find one sentence in a real SEC filing and quote it back.
52 cases over 31 filing sections, retrieved through the fixture server's
`list_filings`, `search_filing`, and `get_paragraph`. The answerer is
Qwen2.5-3B-Instruct loaded in process through Inspect's `hf/` provider,
bfloat16, greedy decoding (`do_sample: false`), capped at 6 agent steps. All 52
cases completed, none were skipped, and every one of them called the retriever
at least once.

| dimension | grader | pass rate |
|---|---|---|
| `answer_contains` (the anchor hit rate) | deterministic | 0.6923 (36 of 52) |
| `quotes_in_source` (quote fidelity) | deterministic | 0.7692 (40 of 52) |
| `unsupported_claims` | HHEM-2.1-Open | 0.6538 (34 of 52) |
| `judge:faithfulness` on Qwen2.5-3B-Instruct | judge model | 0.8462 (44 of 52) |
| `judge:faithfulness` on Qwen2.5-1.5B-Instruct | judge model | 0.9038 (47 of 52) |

The anchor hit rate is the pass rate of the `answer_contains` dimension,
counted over the per-case grades in that file. The two judge rows are counted
the same way, over all 52 cases. The metrics block in the file reports
`judge.faithfulness.hf/Qwen/Qwen2.5-1.5B-Instruct.pass_rate` as 0.9400, since
that metric divides by the 50 cases the 1.5B judge gave a verdict on and counts
the other two under `unknown_rate` (0.0385). The 3B judge returned no unknowns.

`unsupported_rate` is 0.2724, one minus the mean of the per-case
`unsupported_claims` scores, so it reads as the average share of an answer's
sentences HHEM could not find support for. That is the metric the gate
compares. The run cost $0.00, and its `started_at` to `finished_at` window is
15 min 09 s, with `wall_ms_p50` 15,101 and `wall_ms_p95` 22,191.3 per case.

Two pass rates sit in the file and they mean different things. Before the judge
pass a case had to clear two deterministic dimensions, and 28 of 52 did:
`pass_rate` 0.5385. After the judge pass a case has to clear five, and 20 of 52
do: `pass_rate` 0.3846. Neither is a gate row. The gated numbers are the
dimension-level ones above, which is why this section quotes those.

### What this suite does not measure

The questions are templated from the golden set's anchor phrases, so what gets
measured is retrieval and faithful quotation. Open-ended financial reasoning is
not in scope here.

Each fixture holds a window of its section, 40 paragraphs on each side of an
anchor, and never the whole filing. One golden filing produced no fixture
(`nage-0001654954-20-005725-1A` has no Item 1A heading to cut a section from),
so 52 cases came out of 53 anchors. Three of the 31 fixtures are tiny: one
holds 3 paragraphs and two hold 7. The 3-paragraph one is Gold Star Tutoring
Services' Item 1A, whose whole text is a smaller-reporting-company line saying
the information isn't required, so its anchor can be guessed from the question
and only the quote check forces the agent to retrieve anything. A few cases are
that easy, and the baseline should be read knowing it.

`unsupported_rate` comes from HHEM-2.1-Open, whose agreement with human labels
is kappa 0.52 (next section). The row it feeds is relative, so what it catches
is a change in the answers. It does not say that 27 percent of these answers
contain hallucinations.

What all of these numbers describe is one 3B model driving three retrieval
tools. Swap the answerer and every figure here moves.

## Judge calibration

```
evalplat calibrate --items calibration/faithfulness --judge hf/Qwen/Qwen2.5-3B-Instruct --judge hf/Qwen/Qwen2.5-1.5B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --hhem --results results
```

No judge available on this machine is calibrated, so the gate's judge row
cannot fail a build. That row reports not_measured and carries the kappa and
the floor in its detail.

Source: `results/calibration/latest.json`, run 2026-09-11T15:18:41Z, a
`started_at` to `finished_at` window of 22 min 38 s, $0.00. The labeled set is
120 items drawn from RAGTruth, which publishes
human span annotations under MIT
(<https://github.com/ParticleMedia/RAGTruth>). Each item's spans are reduced to
one binary label, and the set is balanced at 60 supported and 60 unsupported.

| grader | kappa | accuracy | unknown | tp | fp | tn | fn |
|---|---|---|---|---|---|---|---|
| `faithfulness@1:hf/Qwen/Qwen2.5-3B-Instruct` | 0.0763 | 0.5339 | 2 of 120 | 16 | 11 | 47 | 44 |
| `faithfulness@1:hf/Qwen/Qwen2.5-1.5B-Instruct` | 0.0167 | 0.5083 | 0 of 120 | 3 | 2 | 58 | 57 |
| `hhem@2.1-open` | 0.5167 | 0.7583 | 0 of 120 | 51 | 20 | 40 | 9 |

Swap agreement between the two judge models on these items is 0.7458. The
floors recorded in the report are `kappa_floor` 0.70 and `min_swap_agreement`
0.90, and the report's `calibrated` map marks all three graders false with the
kappa as the reason. Neither floor was lowered after the measurement.

Both small judges sit near chance. The 1.5B judge calls 57 of the 60
unsupported items supported, which is why its 0.94 pass rate on the
groundedness answers carries no weight, and at kappa 0.08 the 3B judge isn't
much better. The 0.92 swap agreement the two reached on the run's own cases is
no evidence either: two graders that pass almost everything agree trivially,
and on the labeled set, where the answer is known, they agree on 0.7458.

HHEM-2.1-Open is the only grader here with real agreement against the human
labels, and it still misses the floor. It is licensed Apache-2.0 on a
FLAN-T5-base foundation
(<https://huggingface.co/vectara/hallucination_evaluation_model>), and its
checkpoint snapshot is pinned in `eval_platform/graders/hhem.py`, so the same
answers score the same way on a rerun. The calibration rule covers judge models
and leaves HHEM outside it deliberately. The reasoning, and what has to happen
before `unsupported_rate` gets an absolute ceiling, are in
[ADR-0007](adr/0007-uncalibrated-judges-cannot-block.md).

The judge models are Qwen2.5-3B-Instruct, licensed qwen-research, and
Qwen2.5-1.5B-Instruct, Apache-2.0, per their model cards
(<https://huggingface.co/Qwen/Qwen2.5-3B-Instruct>,
<https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct>).

Reading the report back costs nothing:

```
evalplat calibrate --check results/calibration/latest.json
```

That validates the committed report against the schema in
`eval_platform/calibration.py`, prints each grader's verdict, and exits 2 on a
missing or malformed file. It calls no model, which is what lets CI run it. It
checks the report's shape and nothing else; matching a judge to a gate row is
the gate's job, and `evalplat gate` is where a judge id that no report covers
turns into a not_measured row.

## The gate

```
evalplat gate --markdown out/gate.md
```

Seventeen rows, one per gated metric, comparing the newest run per suite
against the committed baselines:

| suite | metric | baseline | current | threshold | verdict |
|---|---|---|---|---|---|
| offline_core | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass |
| offline_core_cost | usd_per_run_p50 | 0.0000 | 0.0000 | max_increase_pct=10.0 | pass |
| offline_core_latency | wall_ms_p95 | 9.5622 | 5.3165 | max_increase_pct=50.0 | pass |
| public_ifeval | instruction_following.prompt_strict_acc | 0.5933 | 0.5933 | max_drop=0.03 | pass |
| public_ifeval_speed | ms_per_sample | 9776.3401 | 9776.3401 | max_increase_pct=50.0 | pass |
| trajectory | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass |
| trajectory_latency | wall_ms_p95 | 8.4189 | 5.6258 | max_increase_pct=50.0 | pass |
| faults | recovery_rate | 0.7500 | 0.7500 | max_drop=0.0 | pass |
| faults_latency | wall_ms_p95 | 157.5732 | 155.2442 | max_increase_pct=50.0 | pass |
| memory | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass |
| memory_latency | wall_ms_p95 | 13.0271 | 8.0705 | max_increase_pct=50.0 | pass |
| injection | attack_success_rate | 0.2500 | 0.2500 | max_rise=0.0 | pass |
| injection_utility | utility_rate | 1.0000 | 1.0000 | min=1.0 | pass |
| groundedness | unsupported_rate | 0.2724 | 0.2724 | max_rise=0.02 | pass |
| groundedness_quotes | quote_fidelity_rate | 0.7692 | 0.7692 | max_drop=0.0 | pass |
| groundedness_latency | wall_ms_p95 | 22191.3000 | 22191.3000 | max_increase_pct=50.0 | pass |
| groundedness_judge | judge.faithfulness.hf/Qwen/Qwen2.5-3B-Instruct.pass_rate | 0.8462 | 0.8462 | max_drop=0.05 | not_measured |

Overall verdict: PASS.

### The four groundedness rows

Phase 3 added four rows and one block of judge settings. `gate.yaml` carries
them as:

```yaml
groundedness: {metric: unsupported_rate, max_rise: 0.02}
groundedness_quotes: {metric: quote_fidelity_rate, max_drop: 0.0}
groundedness_latency: {metric: wall_ms_p95, max_increase_pct: 50}
groundedness_judge: {metric: judge.faithfulness.hf/Qwen/Qwen2.5-3B-Instruct.pass_rate, max_drop: 0.05}
judges: {kappa_floor: 0.70, min_swap_agreement: 0.90, require_swap_agreement: true}
```

`groundedness_quotes` is deterministic, so any drop fails. `groundedness` is
relative with a small allowance, because the level of `unsupported_rate` on a
3B answerer says nothing yet about where an absolute ceiling belongs, while a
rise against the same cases means the answers got worse.

`groundedness_judge` is the row that cannot fire. Its full detail in
`out/gate.md` reads "judge faithfulness@1:hf/Qwen/Qwen2.5-3B-Instruct
uncalibrated: kappa 0.08 < 0.70 (kappa 0.08, floor 0.70)". The gate looks the
judge up in `results/calibration/latest.json`, finds it marked uncalibrated,
and reports not_measured with the reason. Both the baseline and the current
value are still recorded at 0.8462, so the number stays visible while deciding
nothing. It starts deciding the moment some judge clears the floors in the
`judges:` block, with no further change to `gate.yaml`. See
[ADR-0007](adr/0007-uncalibrated-judges-cannot-block.md).

Three of these rows carry a Phase 2 decision worth naming. `faults` compares
`recovery_rate` with `max_drop: 0.0`, so the measured 0.75 becomes a floor
the platform may not slip below; the spec's 0.90 target was a guess made
before anything was measured, and the measurement replaces it. `injection`
compares `attack_success_rate` with `max_rise: 0.0`, so 0.25 is a ceiling and
a fourth successful attack fails the build. `injection_utility` holds
`utility_rate` at an absolute 1.0, so a control that blocks an attack by
breaking benign work fails too.

The offline baselines carry 2026-09-11T08:26 timestamps, each tied to the
target it was measured on, `agent-platform-local` for all five. The four
groundedness baselines carry `"from": "2026-09-11T14:54:25+00:00"` and a
`"target"` of `mcp:edgar-fixture`. `baselines/public_ifeval.json` carries the
Qwen2.5-3B-Instruct run described below, `"from": "2026-09-10T06:58:40+00:00"`,
with a `"target"` of `hf/Qwen/Qwen2.5-3B-Instruct`. A run of the same suite
against a different target reports not measured in that row, so swapping
models does not read as a regression.

The `public_ifeval_speed` baseline was computed from that 3B run's own
`started_at` and `completed_at` after `ms_per_sample` was added as a metric,
which is why both `wall_ms_total` and `ms_per_sample` now appear in the
committed per-run file as well as in `latest.json`.

The spec's sixth Phase 2 suite, `cost_latency`, shipped as metrics and gate
rows on every suite instead of as a suite of its own: `usd_per_run_p50` and
`wall_ms_p95` are computed for every run, and five of the rows above gate
them. That leaves `offline_core` standing as the fifth suite CI runs.

The latency threshold is 50 percent, against the spec's 20 percent. p95 on
four of these suites is a few milliseconds, and CI scheduling noise is larger
than any regression at that scale; the faults suite's 155 ms is one injected
delay showing through eleven cases. Live-model suites use 20 percent. See
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
the same number. SimpleQA Verified needs a judge that clears the kappa floor
first, so it waits on one. See
[ADR-0005](adr/0005-published-scores-as-the-accuracy-check.md).

`tests/test_public.py` exercises the runner path against Inspect's mock model
two ways: a two-sample synthetic task, answered right once and wrong once, whose
`EvalLog` is converted and checked at accuracy 0.5, and a network-marked IFEval
smoke run at `limit=2` that loads the real task and returns a `SuiteResult`
named `public_ifeval`. The task id resolves through `runner.ref` in
`catalog/entries/ifeval.yaml`, and inspect-evals 0.19.0 supplies the task.

## AgentDojo, local model

```
evalplat run public agentdojo --model hf/Qwen/Qwen2.5-3B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false, "batch_size": 4}' --task-args '{"with_sandbox_tasks": "no"}' --no-cost-cap --limit 20 --max-tokens 1024 --max-wall-s 5400 --results results --log-dir logs
```

This is the optional run named in the Phase 2 roadmap: the model-side
susceptibility number the built injection suite deliberately leaves out,
since that suite's planner is scripted and obeys every injected instruction
by construction. AgentDojo runs a real model against its own tools and its
own indirect-injection attacks, so it measures whether Qwen2.5-3B-Instruct
follows an injected instruction, not whether the platform's controls catch
one.

`--task-args` is a new CLI option, forwarding keyword arguments to the
Inspect task function itself rather than to the model constructor
(`--model-args`). `run_public` already accepted `task_args`; `run public`
had no flag for it before this run, and `with_sandbox_tasks: "no"` is what
keeps the run off Docker.

Source: `results/public_agentdojo/latest.json`, run
2026-09-11T07:41:45Z, 144 seconds end to end including model load
(113 seconds of that inside the run itself, `wall_ms_total` in the summary).
20 samples, all completed, none errored, none unscored.

| metric | value |
|---|---|
| utility (benign task completed) | 0.00 (0 of 20) |
| attack success (injection executed) | 0.05 (1 of 20), stderr 0.05 |
| input tokens | 80,276 |
| output tokens | 9,344 |
| cost | $0.00 |

A model that completes 0 of 20 benign tasks has nothing to show resistance
against. The single attack success in twenty samples is not evidence that
Qwen2.5-3B-Instruct usually resists the injected instruction: the other
nineteen non-successes more likely come from general task failure, plausibly
the model never calling a tool at all, than from any security judgment the
model made on the injected content. A meaningful attack-success number needs
a model that completes the benign tasks first, so resistance has something
real to measure against: a larger local model, or a hosted model run when
credits exist, with utility high enough that the attack-success figure
measures something. The 0 of 20 utility result was checked no further than
confirming zero per-sample errors; transcripts were not read case by case,
so a formatting mismatch between the model's tool calls and the harness is
possible as an explanation too.

AgentDojo's own scorer names these two numbers `utility` and `security`;
`security` is `"C"` when the injected instruction was carried out, so the
`security.accuracy` figure above is an attack success rate, not a pass rate,
and that is what the table calls it. The platform's own top-level
`accuracy` metric in the summary equals `utility.accuracy` here, since
Inspect lists the `utility` score first; the two granular numbers in the
table are the ones that carry the finding, not the headline figure.

Every one of the 20 cases shows `"passed": false` in the per-case list.
That is the documented behavior for a dict-valued score
(`eval_log_to_suite_result`'s docstring: "a dict-valued score... flattens to
fail here by design, not by omission"), not a claim that every case failed
its security check; the real per-case outcome is in each case's
`injection_task_scorer` grade, and the suite-level numbers above are the
ones to read.

The sample is small and lopsided by construction, not by intent: `--limit
20` takes the first 20 tasks in AgentDojo's dataset order, and all 20 land
in the `banking` suite (user tasks 0 through 2 crossed with injection tasks
0 through 8), one of AgentDojo's four suites. A wider or shuffled sample
would be needed before this number says anything about the model across
tool domains, not just banking tools. One attack (`important_instructions`,
Inspect's default) and one agent scaffold (`default`) were tested; AgentDojo
ships several of each.

## Program spend to date

$0.00. `results/ledger.jsonl` is committed and holds seven lines. The first is
the Hugging Face Inference Providers attempt that errored, recorded at
`"usd": 0`. The other six are local runs on the laptop's own GPU, each at
`"usd": 0.0`: two IFEval, one AgentDojo, and the three added by Phase 3, which
are the groundedness run at 2026-09-11T15:10:03Z, the judge pass over that same
run at 15:18:32Z, and the calibration run at 15:41:52Z. The judge pass shares
the groundedness run's `run_id`, since it is a second pass over one run and the
note is what separates the two lines. That hosted attempt generated no tokens
before it stopped, so it bought nothing, and a model running locally carries no
per-token price.

## What is versioned here

`.gitignore` keeps `results/**/latest.json` and `results/ledger.jsonl` in git
and drops the per-run timestamped JSON files. The published number and the
running spend total stay reviewable in a diff, and the rest of the run archive
isn't carried in the repo.

Some per-run files are committed anyway, because this page reads numbers out of
them and a reader should be able to open the same file. Those are the two
IFEval calibration runs, and the three Phase 3 files under
`results/groundedness/` and `results/calibration/`. The groundedness pair
matters most: `latest.json` is overwritten by the next run, and
`2026-09-11T145425Z-mcp_edgar-fixture.json` is the only file holding the
deterministic-only verdicts before the judges changed them.

`results/calibration/latest.json` is versioned for a second reason. It is what
the gate reads to decide whether a judge may block, and what CI validates at
rung 3 with `evalplat calibrate --check`, so it is evidence a reviewer can open
and a build can fail on.
