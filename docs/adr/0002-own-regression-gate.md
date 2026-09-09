# ADR-0002: the regression gate is our own code

Status: accepted, 2026-09-08. Spec section 10, decision 2.

## Context

Inspect AI runs evaluations and writes logs. It has no notion of a threshold,
no `--fail-on`, no JUnit output, and no GitHub Action, so something has to turn
a run into a build verdict. Framework comparison:
`docs/research/2026-09-07-eval-frameworks-and-ci-gates.md`.

## Decision

The gate is a module in this package. `eval_platform/gate/config.py` validates
`gate.yaml`, `compare.py` reads a committed baseline against the current
`SuiteResult` and decides per row, `junit.py` and `markdown.py` render the
verdict, and `evalplat gate` exits non-zero on FAIL. About 300 lines, short
enough to read end to end before trusting a build verdict to it.

## Alternatives rejected

- **promptfoo** (0.122.2) has the best off-the-shelf gate in the survey:
  `promptfoo-action@v1`, exit code 100 on failure, a pass-rate threshold
  variable, JUnit XML, PR comments, caching, about 35 assertion types. Three
  reasons against. A Node runtime inside a Python platform makes CI carry two
  toolchains. Its custom assertions run unsandboxed. And the comparison
  arithmetic is the part worth owning. promptfoo stays a documented alternative.
- **A pass-rate check in a shell script.** No baseline store, so it catches a
  suite going to zero and nothing subtler.

## Consequences

- Thresholds live in `gate.yaml` and baselines in `baselines/*.json`, both in
  git, so moving a threshold or accepting a new number is a reviewable diff.
- The interfaces to CI are JUnit XML for the test-summary UI and a markdown
  table posted as a pull-request comment. `.github/workflows/ci.yml` writes
  both to `out/` and uploads them.
- A suite with no result yet reports `not_measured` and does not fail the
  build, which is how `public_ifeval` behaves until a live run exists.
