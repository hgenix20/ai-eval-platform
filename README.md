# AI Eval Platform

An evaluation and reliability platform for AI systems. It carries a validated
catalog of the benchmarks that still discriminate in 2026, its own suites for
the behaviors no public benchmark measures, and a regression gate that fails a
pull request on accuracy, safety, cost, or latency. Public benchmarks run
through Inspect AI, while the built suites run through this package's own
trajectory runner, so they cost nothing and run on every push.

## Status

Phase 2 (gap suites). Five offline suites run against the agent platform in
process for $0.00, all measured 2026-09-11: `offline_core` 12 of 12,
`trajectory` 10 of 10 at 0.75 mean step efficiency over its five scored paths,
`faults` recovery 6 of the 8 cases meant to recover, `memory` 11 of 11, and
`injection` attack success 3 of 12 at utility 4 of 4. `evalplat gate` reports
PASS across thirteen rows. The catalog holds 77 entries. Rungs 1 and 2 of the
ladder run in CI.

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

## The ladder

Four rungs, in the order a pull request meets them.

| rung | what runs | cost | when | status |
|---|---|---|---|---|
| 1. static | catalog, case, and gate-config validation; ruff, pyright, bandit, pytest | free | every push | live |
| 2. offline deterministic | `offline_core`, `trajectory`, `faults`, `memory`, `injection` against scripted providers and the agent platform in process | free | every push | live |
| 3. judge-graded, sampled | first `pr_sample` cases per suite on a PR, the full set on merge | cached | on a PR | Phase 3 |
| 4. public benchmarks | catalog entries through Inspect AI against a hosted or local model, under a per-run cap | budgeted | nightly or manual | manual |

Rung 2 carries all five built suites, 60 cases, and 11 of the gate's thirteen
rows. Rungs 1 and 2 can fail a pull request today.
`.github/workflows/ci.yml` runs both, uploads `out/` as an artifact, and posts
the gate table as a PR comment. On merge to main it also re-measures the
baselines from that run and commits them, so a pull request's cost and latency
rows compare against numbers taken on the same class of machine the pull
request runs on.

A fifth target sits alongside the four in the Layout section: `run mcp` drives
a suite's cases through one MCP server's tools, local on stdio or remote over
HTTP. It reads the server's tool list once before the suite starts, so an
unreachable server exits 2 instead of failing every case. A live listing
against <https://mcp.signalnodus.ai/> returned 31 tools with nothing called;
running a scored suite through it needs a model target and waits on Phase 3.

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
gate.yaml                    thresholds, one row per metric
baselines/*.json             the committed numbers the gate compares against
results/*/latest.json        the published run per suite
eval_platform/types.py       Step, Trajectory, Case, Expect, Grade, CaseResult, SuiteResult
eval_platform/budget.py      Budget, BudgetExceeded, Ledger
eval_platform/catalog/       pydantic schema and the loader
eval_platform/targets/       scripted, agent-platform local, agent-platform HTTP, MCP, faults, conversion
eval_platform/suites/        case loader, trajectory runner, Inspect public runner
eval_platform/graders/       deterministic expectation grading
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

Design spec: `docs/superpowers/specs/2026-09-07-ai-eval-platform-design.md`.

## Roadmap

- **Phase 2, gap suites. Complete**, except one optional run. Five suites of
  at least 10 cases each are live against the agent platform, with recovery
  rate, attack success rate, step efficiency, and per-suite cost and latency
  published in [docs/results.md](docs/results.md) and the red-team write-up in
  [docs/red-team-findings.md](docs/red-team-findings.md). Spec section 4.9's
  OpenTelemetry instrumentation is wired through both runners, an `eval.suite`
  span per run and an `eval.case` span per case, no-ops until a provider is
  configured. The MCP target landed alongside it. Still open and optional: a
  20-task
  AgentDojo sample against a local model, which would add the model-side
  susceptibility number the built suites deliberately leave out.
- **Phase 3, judges. Next.** Judge graders with a cache keyed on model version, a
  calibration set of at least 50 labeled items, per-judge kappa from
  `evalplat calibrate`, a swap-stability check against a second judge model,
  and the groundedness suite on the EDGAR golden set.
- **Phase 4, online.** Production sampling, a drift report, a dashboard
  section, and a promote-to-case flow, verified against a live compose stack of
  the agent platform.
