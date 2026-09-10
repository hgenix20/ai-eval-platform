# AI Eval Platform

An evaluation and reliability platform for AI systems. It carries a validated
catalog of the benchmarks that still discriminate in 2026, its own suites for
the behaviors no public benchmark measures, and a regression gate that fails a
pull request on accuracy, safety, cost, or latency. Public benchmarks run
through Inspect AI, while the built suites run through this package's own
trajectory runner, so they cost nothing and run on every push.

## Status

Phase 1 (core). The offline suite passes 12 of 12 cases against the agent
platform in process, p50 3.671 ms and p95 5.294 ms wall time, $0.00 spent
(`results/offline_core/latest.json`, run 2026-09-09). `evalplat gate` reports
PASS. The catalog holds 77 entries. Rungs 1 and 2 of the ladder run in CI.

The first public-benchmark number is pending. IFEval needs an
`ANTHROPIC_API_KEY` and no live run has happened yet, so the gate's
`public_ifeval` row reads `not_measured` and the ledger has no lines. The
command that produces it is in [docs/results.md](docs/results.md).

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
construction.

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

| rung | what runs | cost | when | Phase 1 |
|---|---|---|---|---|
| 1. static | catalog, case, and gate-config validation; ruff, pyright, bandit, pytest | free | every push | live |
| 2. offline deterministic | built suites against scripted providers and the agent platform in process | free | every push | live |
| 3. judge-graded, sampled | first `pr_sample` cases per suite on a PR, the full set on merge | cached | on a PR | Phase 3 |
| 4. public benchmarks | catalog entries through Inspect AI against a live model, under a per-run cap | budgeted | nightly or manual | Phase 2 |

Rungs 1 and 2 can fail a pull request today. `.github/workflows/ci.yml` runs
both, uploads `out/` as an artifact, and posts the gate table as a PR comment.
On merge to main it also re-measures the baselines from that run and commits
them, so a pull request's cost and latency rows compare against numbers taken
on a CI runner rather than on the laptop the first ones came from.

## Layout

```
catalog/entries/*.yaml       one benchmark per file, keyed by URL
suites/offline_core/*.yaml   the twelve built cases
gate.yaml                    thresholds, one row per metric
baselines/*.json             the committed numbers the gate compares against
results/*/latest.json        the published run per suite
eval_platform/types.py       Step, Trajectory, Case, Expect, Grade, CaseResult, SuiteResult
eval_platform/budget.py      Budget, BudgetExceeded, Ledger
eval_platform/catalog/       pydantic schema and the loader
eval_platform/targets/       scripted, agent-platform local, agent-platform HTTP, conversion
eval_platform/suites/        case loader, trajectory runner, Inspect public runner
eval_platform/graders/       deterministic expectation grading
eval_platform/gate/          config, comparison, JUnit, markdown
eval_platform/reports/       static HTML
eval_platform/cli.py         evalplat catalog | run | gate | report
tests/                       one module per source module
```

Four targets exist: `ScriptedTarget` for deterministic replies, the agent
platform in process, the agent platform over HTTP, and Inspect's own model
providers (`anthropic/`, `openai-api/`) for model-level benchmarks.

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
[docs/results.md](docs/results.md).

## Decisions

- [ADR-0001](docs/adr/0001-inspect-ai-substrate.md): Inspect AI is the
  substrate for public benchmarks.
- [ADR-0002](docs/adr/0002-own-regression-gate.md): the regression gate is our
  own code.
- [ADR-0003](docs/adr/0003-catalog-keyed-by-url.md): the catalog's registry key
  is the primary URL.
- [ADR-0004](docs/adr/0004-cost-and-latency-are-gate-metrics.md): cost and
  latency fail a build, the same as accuracy.

Design spec: `docs/superpowers/specs/2026-09-07-ai-eval-platform-design.md`.

## Roadmap

- **Phase 2, gap suites.** Five suites of at least 10 cases each (trajectory,
  faults, cost and latency, memory, prompt injection) run against the agent
  platform, with recovery rate, attack success rate, and step efficiency
  published alongside red-team findings. The OpenTelemetry spans per sample and
  per grader call from spec section 4.9 arrive here as well; Phase 1 emits
  none.
- **Phase 3, judges.** Judge graders with a cache keyed on model version, a
  calibration set of at least 50 labeled items, per-judge kappa from
  `evalplat calibrate`, a swap-stability check against a second judge model,
  and the groundedness suite on the EDGAR golden set.
- **Phase 4, online.** Production sampling, a drift report, a dashboard
  section, and a promote-to-case flow, verified against a live compose stack of
  the agent platform.
