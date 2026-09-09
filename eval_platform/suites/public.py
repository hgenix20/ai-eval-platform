"""Public benchmarks run through Inspect AI. The platform does not
reimplement any benchmark: it hands the catalog entry's task to
inspect_ai.eval and converts the EvalLog into the same SuiteResult shape the
built suites produce, so the gate and report treat both alike."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import inspect_ai
from inspect_ai import eval as inspect_eval
from inspect_ai._util.error import PrerequisiteError
from inspect_ai.log import EvalLog

from eval_platform.budget import Budget, BudgetExceeded
from eval_platform.catalog import CatalogEntry
from eval_platform.types import CaseResult, Grade, SuiteResult


def _passed(value: Any) -> bool:
    """A score value counts as a pass when it is match()'s "C", or a truthy
    numeric/boolean 1. Anything else (e.g. "I", 0, False, other scorer
    vocabularies) counts as a fail. Phase 1 keeps pass/fail binary: a
    partial-credit float (e.g. 0.5) or a dict-valued score (per-dimension
    breakdowns) flattens to fail here by design, not by omission."""
    return value in ("C", 1, 1.0, True)


def _unscored(scores: dict[str, Any]) -> bool:
    """True when a sample carries no scores at all, or any scorer left a
    NaN value (Inspect's unscored sentinel, e.g. a grader that could not
    parse a judge's reply). A NaN is never `== ` anything including itself,
    so `_passed` alone would mark it a fail with no indication why; this
    catches it explicitly so the sample is skipped instead of counted as a
    failure."""
    if not scores:
        return True
    return any(isinstance(sc.value, float) and math.isnan(sc.value) for sc in scores.values())


def _headline(log: EvalLog) -> float:
    """The suite's single headline number: the first scorer's "accuracy" or
    "mean" metric if present, else that scorer's first metric. Returns 0.0
    when the log has no results or no scores at all."""
    if log.results is None or not log.results.scores:
        return 0.0
    metrics = log.results.scores[0].metrics
    for name in ("accuracy", "mean"):
        if name in metrics:
            return float(metrics[name].value)
    first = next(iter(metrics.values()), None)
    return float(first.value) if first is not None else 0.0


def _usage(log: EvalLog) -> tuple[int, int, float]:
    """Sum input tokens, output tokens, and dollar cost across every model
    Inspect recorded usage for. `log.stats` is always present (Inspect
    default-constructs it), so an empty `model_usage` dict is the only
    degenerate case, and it sums to zeros."""
    usage = log.stats.model_usage
    tin = sum(u.input_tokens for u in usage.values())
    tout = sum(u.output_tokens for u in usage.values())
    usd = sum(float(u.total_cost or 0.0) for u in usage.values())
    return tin, tout, usd


def eval_log_to_suite_result(log: EvalLog, *, suite: str, target: str) -> SuiteResult:
    """Convert an Inspect EvalLog into this platform's SuiteResult shape.

    Contract: one CaseResult per EvalSample in `log.samples`, in order. A
    sample with no scores at all, or with a NaN score from any scorer
    (Inspect's unscored sentinel), becomes a skipped case: `passed=False`,
    `grades=()`, `skipped_reason="unscored"`. Otherwise, a case passes when
    every scorer's value on that sample counts as a pass (see `_passed`);
    grades carry one entry per scorer, named by the scorer's key in
    `sample.scores`. `metrics["accuracy"]` is the suite's headline number
    (see `_headline`); `metrics["samples_unscored"]` is the count of
    skipped cases; `usd` is 0.0 when Inspect recorded no cost. Missing
    `log.results` (an incomplete or errored run) degrades `samples_total`/
    `samples_completed` to the sample count from `log.samples` rather than
    raising.
    """
    cases: list[CaseResult] = []
    for s in log.samples or []:
        scores = s.scores or {}
        if _unscored(scores):
            cases.append(
                CaseResult(
                    name=str(s.id),
                    passed=False,
                    grades=(),
                    trajectory=None,
                    skipped_reason="unscored",
                )
            )
            continue
        grades = tuple(
            Grade(
                dimension=name,
                value=1.0 if _passed(sc.value) else 0.0,
                passed=_passed(sc.value),
                explanation=str(sc.explanation or ""),
            )
            for name, sc in scores.items()
        )
        cases.append(
            CaseResult(
                name=str(s.id),
                passed=bool(grades) and all(g.passed for g in grades),
                grades=grades,
                trajectory=None,
            )
        )
    tin, tout, usd = _usage(log)
    samples_unscored = sum(1 for c in cases if c.skipped_reason == "unscored")
    return SuiteResult(
        suite=suite,
        target=target,
        started_at=log.stats.started_at,
        finished_at=log.stats.completed_at,
        cases=tuple(cases),
        metrics={
            "accuracy": _headline(log),
            "samples_total": float(log.results.total_samples if log.results else len(cases)),
            "samples_completed": float(
                log.results.completed_samples if log.results else len(cases)
            ),
            "input_tokens": float(tin),
            "output_tokens": float(tout),
            "usd": usd,
            "samples_unscored": float(samples_unscored),
        },
        meta={
            "inspect_version": inspect_ai.__version__,
            "task": log.eval.task,
            "model": log.eval.model,
            "log_location": log.location,
            "status": log.status,
        },
    )


def run_public(
    entry: CatalogEntry,
    *,
    model: str,
    limit: int | None,
    budget: Budget,
    log_dir: Path,
    task_args: dict[str, Any] | None = None,
) -> SuiteResult:
    """Run one catalog entry's public benchmark through Inspect AI and
    return it as a SuiteResult named `public_<id with - as _>`.

    Contract: raises ValueError before running anything when `entry` is not
    runnable through Inspect, i.e. `entry.runnable` is False or the runner
    kind is not `"inspect_evals"` (covers `non-commercial` license status,
    `external`/`builtin`/`none` runner kinds, and a missing ref). Running
    the `ifeval` catalog entry needs the `ifeval` extra installed
    (`pip install -e ".[ifeval]"`), since `inspect_evals`'s IFEval task
    imports that dependency at task-construction time, not at import time.

    Inspect's `cost_limit` bounds spend PER SAMPLE, not for the run as a
    whole; `--limit`, the sample count, is what actually bounds total
    spend. So for a priced model, when `limit` is a positive int the
    per-sample cap is `budget.remaining_usd() / limit`
    (`meta["cost_cap_mode"]` records `"per_sample_divided"`); when `limit`
    is None (or not a positive int) there is no sample count to divide by,
    so the cap is the full remaining budget per sample and
    `meta["cost_cap_mode"]` records `"per_sample_uncapped_count"`. That
    still caps any one sample, but not the run's total, since Inspect does
    not expose a run-level ceiling.

    Raises BudgetExceeded("usd") immediately after `budget.check()` if the
    budget is already exhausted (`remaining_usd() <= 0`): passing a zero or
    negative remaining amount as `cost_limit` would otherwise be read by
    Inspect as `0.0`, and passing None (as an exhausted-budget sentinel)
    would remove the cap entirely, so this is checked explicitly rather
    than folded into the cost_limit expression. `budget.check()` itself
    raises BudgetExceeded("wall") if the wall-clock ceiling has already
    passed. Charges `budget` with the run's actual dollar cost after
    Inspect returns; that charge can itself raise BudgetExceeded("usd") if
    the run's actual cost pushes total spend over the ceiling.

    A model whose name starts with `"mockllm/"` is free by construction: it
    generates canned output without calling any provider, so it spends
    nothing and no cap applies. Such a run gets neither `cost_limit` nor
    `model_cost_config`, and `meta["cost_cap_mode"]` records
    `"none_free_model"`. Passing either one would fail: a non-None
    `cost_limit` makes Inspect require registered cost data for every model
    in the run, and `mockllm` has no entry in Inspect's model registry at
    all, so `model_cost_config` cannot supply that data either (Inspect's
    `set_model_cost` raises ValueError for a model it does not already
    know).

    If Inspect raises PrerequisiteError over missing cost data for a priced
    model, that is re-raised as ValueError naming the model, rather than the
    raw Inspect internal error; any other exception from `inspect_eval`
    propagates unchanged.
    """
    if not entry.runnable or entry.runner.kind != "inspect_evals" or not entry.runner.ref:
        raise ValueError(
            f"catalog entry {entry.id} is not runnable through Inspect "
            f"(kind={entry.runner.kind}, license={entry.license.status})"
        )
    budget.check()
    remaining = budget.remaining_usd()
    if remaining <= 0:
        raise BudgetExceeded("usd", "no budget remaining for a public run")
    # A mockllm model spends nothing and has no entry in Inspect's model
    # registry, so neither a cost cap nor a cost table can be attached to
    # it; every other model gets a per-sample cap cut from the budget.
    cost_kwargs: dict[str, Any] = {}
    if model.startswith("mockllm/"):
        cost_cap_mode = "none_free_model"
    elif limit is not None and limit > 0:
        cost_kwargs["cost_limit"] = remaining / limit
        cost_cap_mode = "per_sample_divided"
    else:
        cost_kwargs["cost_limit"] = remaining
        cost_cap_mode = "per_sample_uncapped_count"
    try:
        [log] = inspect_eval(
            entry.runner.ref,
            model=model,
            limit=limit,
            log_dir=str(log_dir),
            display="none",
            task_args=task_args or {},
            **cost_kwargs,
        )
    except PrerequisiteError as exc:
        if "cost data" in str(exc):
            raise ValueError(
                f"model {model} has no cost data in Inspect; cannot enforce a spend cap"
            ) from exc
        raise
    result = eval_log_to_suite_result(
        log, suite=f"public_{entry.id.replace('-', '_')}", target=model
    )
    result.meta["cost_cap_mode"] = cost_cap_mode
    budget.charge(result.metrics["usd"])
    return result
