# AI Eval Platform

An evaluation and reliability platform for AI systems. It carries a validated
catalog of the benchmarks that still discriminate in 2026, its own suites for
the behaviors no public benchmark measures, and a regression gate that fails a
pull request on accuracy, safety, cost, or latency. Public benchmarks run
through Inspect AI, while the built suites run through this package's own
trajectory runner, so they cost nothing and run on every push.

## Status

Phase 3 (judges) is done, and its first finding is a negative one: no judge
this machine can run is calibrated, so the gate's judge row reports
not_measured and cannot fail a build. Against 120 human-labeled RAGTruth items,
Qwen2.5-3B-Instruct scores kappa 0.08 and Qwen2.5-1.5B-Instruct 0.02, both near
chance; HHEM-2.1-Open reaches 0.52 against a floor of 0.70. HHEM's number still
gates and the two judges' numbers do not: at 0.52 it feeds a relative row,
`groundedness` at `max_rise: 0.02`, because the classifier is fixed and its
snapshot is pinned, so a rise on the same cases means the answers changed. The
floors stayed where they were, and the measured judge pass rates stay on the
page deciding nothing
([ADR-0007](docs/adr/0007-uncalibrated-judges-cannot-block.md)).

The groundedness suite ran anyway, since most of what it measures needs no
judge. 52 cases ask Qwen2.5-3B-Instruct to find a sentence in a real SEC filing
and quote it back, through three MCP retrieval tools over committed EDGAR text
([ADR-0008](docs/adr/0008-groundedness-against-the-golden-set-with-a-fixture-retriever.md)).
The anchor hit rate is 0.69, quote fidelity 0.77, and HHEM's unsupported rate
0.27, at $0.00 and 22.2 s p95 per case. `evalplat gate` reports PASS across
seventeen rows.

Phase 2's five offline suites run against the agent platform in process for
$0.00, all measured 2026-09-11: `offline_core` 12 of 12, `trajectory` 10 of 10
at 0.75 mean step efficiency over its five scored paths, `faults` recovery 6 of
the 8 cases meant to recover, `memory` 11 of 11, and `injection` attack success
3 of 12 at utility 4 of 4. The catalog holds 77 entries. Rungs 1, 2, and 3 of
the ladder run in CI.

The two unrecovered fault cases and the three landed attacks are findings
about the platform under test, written up with severities and proposed
mitigations in [docs/red-team-findings.md](docs/red-team-findings.md). This
repository measures that platform and does not patch it
([ADR-0006](docs/adr/0006-fault-and-injection-suites-measure-the-platform-not-the-model.md)).

The first public-benchmark numbers are in. Google's IFEval ran in full, all 541
prompts, against two open instruct models on a local GPU. Qwen2.5-3B-Instruct
scored 59.3 percent prompt-strict against a published 58.2, and
Qwen2.5-1.5B-Instruct scored 41.0 against a published 42.5. Both gaps are
smaller than the 2.1-point standard error on the measurement, which is how the
platform's own accuracy gets checked
([ADR-0005](docs/adr/0005-published-scores-as-the-accuracy-check.md)). The two
runs cost $0.00, and `results/ledger.jsonl` puts program spend at $0.00 across
all three of the day's run attempts. Commands, settings, and sources are in
[docs/results.md](docs/results.md).

## Bring-up

Windows:

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev,agent-platform,ifeval]"
pytest -m "not network and not live"
evalplat run offline --suite-dir suites/offline_core --target agent-platform-local
evalplat gate
evalplat report
```

Linux and macOS:

```
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,agent-platform,ifeval]"
pytest -m "not network and not live"
evalplat run offline --suite-dir suites/offline_core --target agent-platform-local
evalplat gate
evalplat report
```

Activation comes first in both blocks, so `pip`, `pytest`, and `evalplat` all
resolve inside the venv and no command needs a path.

`gate` reads `gate.yaml`, the baselines in `baselines/`, and the newest run per
suite under `results/`, then exits non-zero on FAIL. `report` writes a
self-contained `out/report.html` with no external assets. Add
`--junit out/junit.xml --markdown out/gate.md` to `gate` for the CI artifacts.
A baseline is tied to the target it was measured on; comparing it against a
run on a different target reports not measured instead of a false regression.

The `agent-platform` extra installs `enterprise-agent-platform`, the system
under test. The `ifeval` extra installs what `inspect_evals`'s IFEval task
imports while it builds; without it, `evalplat run public ifeval` fails at task
construction. The `mcp` extra installs the Model Context Protocol package the
`run mcp` target needs.

### MCP servers

`run mcp` points an Inspect ReAct agent at one MCP server and runs a suite's
cases through it. The server is either a local child process on stdio or a
remote URL:

```
pip install -e ".[mcp]"
evalplat run mcp --suite-dir suites/offline_core --mcp-command python --mcp-args tests/fixtures/mcp_fixture_server.py --model openai/gpt-4o-mini
evalplat run mcp --suite-dir suites/offline_core --mcp-url https://mcp.example.com/ --mcp-authorization "$TOKEN" --model openai/gpt-4o-mini
```

The target's name is `mcp:<server name>` and its capabilities are
`{"agent", "mcp"}`, so only cases whose `target_requirements` fit run against
it. A stdio server is named after its executable plus a short hash of its
command line (`mcp:python.exe-0cdd10e1`), keeping results filenames bounded;
an HTTP server is named after its URL. `--server-name` overrides both. The
server's tool list is read once before the suite starts, so an unreachable
server exits 2 rather than failing every case, and those tool names are
recorded in the summary's `meta["mcp_tools"]`. `--max-steps` caps the agent
loop, and a case's own `max_steps` is bounded by it.

### Local models

Inspect's `hf/` provider loads a Hugging Face model in process instead of
calling a hosted API. Install a CUDA build of torch from the PyTorch index
first, then the `local` extra:

```
pip install --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0
pip install -e ".[local]"
```

`--model-args` passes constructor keyword arguments straight through to the
provider, for example (transformers rejects a temperature of 0, so greedy decoding is `do_sample: false`; `batch_size` sets how many prompts share one forward pass):

```
evalplat run public ifeval --model hf/Qwen/Qwen2.5-3B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false, "batch_size": 8}' --no-cost-cap --full --max-tokens 1024
```

### Judges

`evalplat judge` adds model-graded dimensions to a run that already exists. It
reads the suite's newest summary, grades each answer again, and writes a new
summary next to it, so the deterministic numbers and the latencies stay
comparable across a re-grade:

```
evalplat judge --suite-dir suites/groundedness --results results --judge hf/Qwen/Qwen2.5-3B-Instruct --judge hf/Qwen/Qwen2.5-1.5B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --hhem
```

A second `--judge` makes swap agreement measurable. An `hf/` judge has to be
downloaded first, since both commands read the judge's snapshot hash out of the
local Hugging Face cache to key the verdict cache: with no snapshot there, the
command names the path it looked for and exits 2. `--hhem` adds
HHEM-2.1-Open, a fixed classifier that scores each answer sentence against the
retrieved context and reports `unsupported_rate`. Verdicts are cached under
`.cache/judge/`, keyed by a hash over the case, the prompt, the judge's model
id and version, the rubric and its version, and the sampling parameters, so a
re-grade with the same judge is free and a judge upgrade misses every entry.

`evalplat calibrate` is what decides whether any of those judges may block a
build. It scores them against a labeled set and writes
`results/calibration/latest.json`:

```
evalplat calibrate --items calibration/faithfulness --judge hf/Qwen/Qwen2.5-3B-Instruct --judge hf/Qwen/Qwen2.5-1.5B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --hhem --results results
evalplat calibrate --check results/calibration/latest.json
```

A judge contributes to the gate once its Cohen's kappa against the labels
clears `judges.kappa_floor` in `gate.yaml` and it agrees with a second judge on
`judges.min_swap_agreement` of the items. Below either floor, its gate row
reports not_measured and names the kappa. `--check` validates an already
written report and prints its verdicts without calling a model, which is how
rung 3 runs on a machine with no GPU.

## The ladder

Four rungs, in the order a pull request meets them.

| rung | what runs | cost | when | status |
|---|---|---|---|---|
| 1. static | catalog, case, and gate-config validation; ruff, pyright, bandit, pytest | free | every push | live |
| 2. offline deterministic | `offline_core`, `trajectory`, `faults`, `memory`, `injection` against scripted providers and the agent platform in process | free | every push | live |
| 3. judge-graded | the committed judge-graded results and the calibration report, validated with `evalplat calibrate --check` | free | every push | live |
| 4. public benchmarks | catalog entries through Inspect AI against a hosted or local model, under a per-run cap | budgeted | nightly or manual | manual |

Rung 2 carries all five built suites, 60 cases, and 11 of the gate's seventeen
rows. Rung 3 calls no judge, because a GitHub runner has no GPU and the
account has no hosted credits. What it does instead is read the judge-graded
groundedness run and the calibration report out of the repository: `--check`
validates the report's shape and prints each grader's verdict, and the gate
step then reads the four groundedness rows from the committed run. `--check`
looks at shape alone; the gate is what matches a judge to a row, and a judge
row stays not_measured until that judge clears the kappa floor. What rung 3
validates, then, is the committed artifacts: `--check` fails when the
calibration report goes missing or stops parsing, and the gate step fails when
an edit to the committed groundedness run moves one of its rows past a
threshold. Re-measuring those numbers takes a local GPU run, which a CI runner
has no way to do. Rungs 1 and 2 stay the rungs a code change can fail on its
own.
`.github/workflows/ci.yml` runs all three, uploads `out/` as an artifact, and posts
the gate table as a PR comment. On merge to main it also re-measures the
baselines from that run and commits them, so a pull request's cost and latency
rows compare against numbers taken on the same class of machine the pull
request runs on.

A fifth target sits alongside the four in the Layout section: `run mcp` drives
a suite's cases through one MCP server's tools, local on stdio or remote over
HTTP. It reads the server's tool list once before the suite starts, so an
unreachable server exits 2 instead of failing every case. A live listing
against <https://mcp.signalnodus.ai/> returned 31 tools with nothing called.
The first scored run through that target is the groundedness suite, against a
local fixture server over committed EDGAR text; the same suite points at the
live server with `--mcp-url` and `--mcp-authorization`.

Rung 4 runs by hand so far. IFEval has gone the full 541 prompts against two
local models, and its gate row compares prompt-strict accuracy against a
baseline stamped with the model it was measured on, so a run against a
different model reports not measured. Putting that rung on a nightly schedule
is still open.

## Layout

```
catalog/entries/*.yaml       one benchmark per file, keyed by URL
suites/offline_core/*.yaml   the twelve Phase 1 cases
suites/trajectory/*.yaml     ten cases on tool order, redundancy, efficiency
suites/faults/*.yaml         eleven cases on injected tool and provider faults
suites/memory/*.yaml         eleven multi-session recall cases
suites/injection/*.yaml      sixteen cases, twelve attacks and four benign
suites/groundedness/         52 EDGAR cases, their fixtures, and the golden set
calibration/faithfulness/    120 human-labeled RAGTruth items
gate.yaml                    thresholds, one row per metric
baselines/*.json             the committed numbers the gate compares against
results/*/latest.json        the published run per suite
results/calibration/         per-judge kappa against the labeled set
eval_platform/types.py       Step, Trajectory, Case, Expect, Grade, CaseResult, SuiteResult
eval_platform/budget.py      Budget, BudgetExceeded, Ledger
eval_platform/catalog/       pydantic schema and the loader
eval_platform/targets/       scripted, agent-platform local, agent-platform HTTP, MCP, faults, conversion
eval_platform/suites/        case loader, trajectory runner, Inspect public runner
eval_platform/graders/       deterministic grading, judge rubrics and cache, HHEM
eval_platform/retrievers/    the EDGAR fixture MCP server
eval_platform/calibration.py kappa, swap agreement, the report and its schema
eval_platform/gate/          config, comparison, JUnit, markdown
eval_platform/reports/       static HTML
eval_platform/cli.py         evalplat catalog | run | gate | report
tests/                       one module per source module
```

Five targets exist: `ScriptedTarget` for deterministic replies, the agent
platform in process, the agent platform over HTTP, `MCPTarget` for a Model
Context Protocol server, and Inspect's own model providers (`anthropic/`,
`openai-api/`) for model-level benchmarks.

## Catalog

77 entries, each carrying a `verified` date and at least one source URL.
`verified` is the date that entry was last checked against the sources it
lists, and a headline score in its `notes` is what those sources reported on
that date. Reproduce the counts with `evalplat catalog list`.

By category: capability 14, coding 12, agent 11, safety 7, tool-use 7,
hallucination 6, long-context 6, retrieval 6, injection 4, judge 4.

By status: current 58, saturated 7, legacy 6, approaching-saturation 5,
held-out 1. Saturated and legacy entries stay in deliberately, so the catalog
also records what is no longer worth running.

By runner: 32 entries resolve to an `inspect_evals` task, and a test asserts
each still exists in the installed registry. 40 are external, 4 have no runner,
1 is built here. By license status: 54 verified, 15 unverified, 4 ambiguous, 4
non-commercial. The non-commercial four are listed and never executed.

## Results

The published numbers, each with the command that reproduces it:
[docs/results.md](docs/results.md). The security write-up behind the
`injection`, `faults`, and `memory` figures, with a severity and a proposed
mitigation per finding: [docs/red-team-findings.md](docs/red-team-findings.md).

## Decisions

- [ADR-0001](docs/adr/0001-inspect-ai-substrate.md): Inspect AI is the
  substrate for public benchmarks.
- [ADR-0002](docs/adr/0002-own-regression-gate.md): the regression gate is our
  own code.
- [ADR-0003](docs/adr/0003-catalog-keyed-by-url.md): the catalog's registry key
  is the primary URL.
- [ADR-0004](docs/adr/0004-cost-and-latency-are-gate-metrics.md): cost and
  latency fail a build, the same as accuracy.
- [ADR-0005](docs/adr/0005-published-scores-as-the-accuracy-check.md):
  reproducing vendor-published scores is how the platform's accuracy is
  checked.
- [ADR-0006](docs/adr/0006-fault-and-injection-suites-measure-the-platform-not-the-model.md):
  the fault and injection suites measure the platform's controls under a
  worst-case model, and findings go to the platform's own repository.
- [ADR-0007](docs/adr/0007-uncalibrated-judges-cannot-block.md): a judge that
  has not cleared the kappa and swap-agreement floors reports not_measured and
  cannot fail a build.
- [ADR-0008](docs/adr/0008-groundedness-against-the-golden-set-with-a-fixture-retriever.md):
  groundedness runs against the SignalNodus golden set through a committed
  EDGAR fixture retriever, with the live server as the optional path.

Design spec: `docs/superpowers/specs/2026-09-07-ai-eval-platform-design.md`.

## Roadmap

- **Phase 2, gap suites. Complete**, including the optional run. Five suites
  of at least 10 cases each are live against the agent platform, with
  recovery rate, attack success rate, step efficiency, and per-suite cost and
  latency published in [docs/results.md](docs/results.md) and the red-team
  write-up in [docs/red-team-findings.md](docs/red-team-findings.md). Each of
  those suite-level metrics is emitted only when a suite carries the cases it
  is computed from: `recovery_rate` needs a case that expected recovery, and
  `attack_success_rate` and `utility_rate` need at least one scored attack
  case carrying an `attack_succeeded` grade. `compute_metrics` in
  `eval_platform/types.py` is where that gating lives. The spec's sixth
  suite, `cost_latency`, shipped as metrics and gate rows on every suite,
  which is why `offline_core` is the fifth suite in CI. Spec
  section 4.9's OpenTelemetry instrumentation is wired through both runners,
  an `eval.suite` span per run and an `eval.case` span per case, no-ops
  until a provider is configured. The grader-call spans arrived with Phase 3:
  a judge verdict runs inside an `eval.grader` span carrying `eval.judge`,
  `eval.case`, `eval.cache_hit`, and the label it settled on. The
  MCP target landed alongside it. The
  optional 20-task AgentDojo sample against a local model also ran, adding
  the model-side susceptibility number the built suites deliberately leave
  out: see "AgentDojo, local model" in
  [docs/results.md](docs/results.md).
- **Phase 3, judges. Complete.** Judge graders with a cache keyed on model
  version, 120 labeled calibration items from RAGTruth, per-judge kappa from
  `evalplat calibrate`, a swap-stability check against a second judge model,
  and the groundedness suite on the EDGAR golden set, all measured on a local
  GPU for $0.00. The calibration rule then did the job it exists for: at kappa
  0.08, 0.02, and 0.52 against a floor of 0.70, nothing this machine can run
  earned a vote in the gate, and the judge row reports not_measured. Moving to
  a hosted judge takes four things: the `--judge` value and its key, a
  calibration run for that judge, the metric name on the `groundedness_judge`
  row in `gate.yaml`, and a baseline for the row under the new metric. Nothing
  else in the pipeline changes. What is still open is a judge that clears the
  floor, and an
  absolute ceiling on `unsupported_rate` once the level has been measured on a
  second answerer. Numbers in [docs/results.md](docs/results.md).
- **Phase 4, online. Next.** Production sampling, a drift report, a dashboard
  section, and a promote-to-case flow, verified against a live compose stack of
  the agent platform.
