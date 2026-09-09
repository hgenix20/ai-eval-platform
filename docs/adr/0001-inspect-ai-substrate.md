# ADR-0001: Inspect AI is the substrate for public benchmarks

Status: accepted, 2026-09-08. Spec section 10, decision 1.

## Context

The platform runs public benchmarks without reimplementing any of them, so it
needs a harness carrying the datasets, the scorers, and an agent loop, one
likely to still be maintained in a year. Survey:
`docs/research/2026-09-07-eval-frameworks-and-ci-gates.md`.

## Decision

Inspect AI 0.3.263 runs public benchmarks, with tasks from inspect-evals
0.19.0. A catalog entry names its task in `runner.ref` as
`inspect_evals/<task>`; `eval_platform/suites/public.py` hands that to
`inspect_ai.eval` and converts the returned `EvalLog` into the same
`SuiteResult` the built suites produce, so the gate and the report treat both
alike.

## Alternatives rejected

- **lm-evaluation-harness** (0.4.13): no agent loop, so trajectories cannot be
  evaluated, and code execution runs unsandboxed (`--confirm_run_unsafe_code`).
- **OpenAI Evals**: hosted product deprecated 2026-06-03, read-only 2026-10-31,
  shutdown 2026-11-30. OpenAI's own notice points users at promptfoo.
- **HELM**: the research records maintenance mode since 2026-06-01 and marks
  that UNVERIFIED, so treat it as a soft signal. Either way, no agent model and
  no CI path.
- **A custom runner**: rewriting dataset loaders and scorers reimplements the
  field, and every benchmark after that becomes our maintenance burden.

## Consequences

- `inspect_evals` task names are catalog data. 32 of the 77 entries carry one,
  and `tests/test_catalog_entries.py::test_every_inspect_evals_ref_resolves`
  asserts each resolves in the installed registry, so an inspect-evals upgrade
  that renames a task fails the build, ahead of any live run.
- Both packages are pinned. Upgrading them is deliberate.
