"""Public benchmarks run through Inspect AI. The platform does not
reimplement any benchmark: it hands the catalog entry's task to
inspect_ai.eval and converts the EvalLog into the same SuiteResult shape the
built suites produce, so the gate and report treat both alike."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import inspect_ai
from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog

from eval_platform.budget import Budget
from eval_platform.catalog import CatalogEntry
from eval_platform.types import CaseResult, Grade, SuiteResult


def _passed(value: Any) -> bool:
    """A score value counts as a pass when it is match()'s "C", or a truthy
    numeric/boolean 1. Anything else (e.g. "I", 0, False, other scorer
    vocabularies) counts as a fail."""
    return value in ("C", 1, 1.0, True)


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
    Inspect recorded usage for. Returns zeros when the log carries no stats
    (e.g. a run that failed before any sample completed)."""
    usage = log.stats.model_usage if log.stats else {}
    tin = sum(u.input_tokens for u in usage.values())
    tout = sum(u.output_tokens for u in usage.values())
    usd = sum(float(u.total_cost or 0.0) for u in usage.values())
    return tin, tout, usd


def eval_log_to_suite_result(log: EvalLog, *, suite: str, target: str) -> SuiteResult:
    """Convert an Inspect EvalLog into this platform's SuiteResult shape.

    Contract: one CaseResult per EvalSample in `log.samples`, in order. A
    case passes when every scorer's value on that sample counts as a pass
    (see `_passed`); a sample with no scores at all does not pass. Grades
    carry one entry per scorer, named by the scorer's key in `sample.scores`.
    `metrics["accuracy"]` is the suite's headline number (see `_headline`);
    `usd` is 0.0 when Inspect recorded no cost. Missing `log.results` or
    `log.stats` (an incomplete or errored run) degrades to sample counts
    from `log.samples` and zeroed usage rather than raising.
    """
    cases: list[CaseResult] = []
    for s in log.samples or []:
        scores = s.scores or {}
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
    started = log.stats.started_at if log.stats else datetime.now(UTC).isoformat()
    finished = log.stats.completed_at if log.stats else started
    return SuiteResult(
        suite=suite,
        target=target,
        started_at=started,
        finished_at=finished,
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
    `external`/`builtin`/`none` runner kinds, and a missing ref). Charges
    `budget` with the run's actual dollar cost after Inspect returns; a
    prior overrun raises BudgetExceeded from `budget.check()` before the run
    starts, and the post-run charge can itself raise BudgetExceeded if the
    run's actual cost pushes spend over the ceiling.
    """
    if not entry.runnable or entry.runner.kind != "inspect_evals" or not entry.runner.ref:
        raise ValueError(
            f"catalog entry {entry.id} is not runnable through Inspect "
            f"(kind={entry.runner.kind}, license={entry.license.status})"
        )
    budget.check()
    [log] = inspect_eval(
        entry.runner.ref,
        model=model,
        limit=limit,
        log_dir=str(log_dir),
        display="none",
        cost_limit=budget.remaining_usd() or None,
        task_args=task_args or {},
    )
    result = eval_log_to_suite_result(
        log, suite=f"public_{entry.id.replace('-', '_')}", target=model
    )
    budget.charge(result.metrics["usd"])
    return result
