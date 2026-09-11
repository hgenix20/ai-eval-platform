"""Run a list of cases against one target under a budget."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from eval_platform.budget import Budget, BudgetExceeded
from eval_platform.graders import grade_expect
from eval_platform.targets.base import AgentTarget
from eval_platform.telemetry import set_attributes, span
from eval_platform.types import Case, CaseResult, Grade, SuiteResult, compute_metrics


def _now() -> str:
    """Current UTC time as an ISO-8601 string, seconds precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def run_case(case: Case, target: AgentTarget) -> CaseResult:
    """Run one case on `target` and grade it.

    Contract: never raises. A case whose `target_requirements` are not a
    subset of `target.capabilities` is skipped (skipped_reason set,
    grades empty, trajectory None) without calling the target. Otherwise
    the target runs; any exception it raises (TargetUnavailable,
    ValueError, or anything else a target implementation might throw)
    becomes a failed CaseResult carrying a single Grade of dimension
    "run" rather than crashing the suite, because one bad target call
    must not abort every other case. A successful run is graded with
    `grade_expect` and passes only if every emitted Grade passes.

    The target call and grading run inside an "eval.case" span carrying
    `case` and `target` attributes up front, and `eval.status`,
    `eval.cost_usd`, `eval.wall_ms`, `eval.passed` set once the outcome is
    known; a target exception records `eval.status="target_error"` and
    `eval.passed=False` instead of the trajectory fields, since there is no
    trajectory to read them from.
    """
    missing = set(case.target_requirements) - set(target.capabilities)
    if missing:
        return CaseResult(
            case.name,
            False,
            (),
            None,
            skipped_reason=f"target lacks {sorted(missing)}",
            kind=case.kind,
        )
    with span("eval.case", case=case.name, target=target.name) as s:
        try:
            trajectory = target.run(case)
        except Exception as e:  # a target failure must become a failed case, never crash the suite
            set_attributes(s, **{"eval.status": "target_error", "eval.passed": False})
            return CaseResult(
                case.name, False, (Grade("run", 0.0, False, repr(e)),), None, kind=case.kind
            )
        grades = grade_expect(case, trajectory)
        passed = all(g.passed for g in grades)
        set_attributes(
            s,
            **{
                "eval.status": trajectory.status,
                "eval.cost_usd": trajectory.cost_usd,
                "eval.wall_ms": trajectory.wall_ms,
                "eval.passed": passed,
            },
        )
        return CaseResult(case.name, passed, tuple(grades), trajectory, kind=case.kind)


def run_suite(
    suite: str, cases: Sequence[Case], target: AgentTarget, *, budget: Budget
) -> SuiteResult:
    """Run every case in `cases` against `target`, stopping early on budget overrun.

    Contract: `budget.check()` runs before each case and `budget.charge()`
    runs after, on the trajectory's actual cost, for every case that
    produced a trajectory (skipped cases and target-exception failures
    have none, so nothing is charged for them). Either can raise
    BudgetExceeded, and the two are not the same event:

    - `check()` raising means the case never ran. It is recorded as
      skipped, with the exception's text as `skipped_reason`.
    - `charge()` raising means the case ran and was graded, and paying for
      it reached the ceiling. Its full result, trajectory included, is
      kept, because the spec requires partial results to survive an
      overrun (design spec 4.7).

    Either way every remaining case is recorded as skipped with reason
    "budget exceeded" (the target is never called for them) and
    `meta["budget_exceeded"]` is set True. Metrics come from
    `compute_metrics`, so skipped cases count toward
    `cases_total`/`cases_skipped` but not `pass_rate`.

    The whole loop runs inside an "eval.suite" span carrying `suite`,
    `target`, and `cases` (the count) attributes, so every "eval.case"
    span opened by `run_case` inside it is recorded as a child span.
    """
    started = _now()
    results: list[CaseResult] = []
    exceeded = False
    with span("eval.suite", suite=suite, target=target.name, cases=len(cases)):
        for case in cases:
            if exceeded:
                results.append(
                    CaseResult(
                        case.name,
                        False,
                        (),
                        None,
                        skipped_reason="budget exceeded",
                        kind=case.kind,
                    )
                )
                continue
            try:
                budget.check()
            except BudgetExceeded as e:
                # The ceiling was already reached, so this case never ran.
                exceeded = True
                results.append(
                    CaseResult(case.name, False, (), None, skipped_reason=str(e), kind=case.kind)
                )
                continue
            r = run_case(case, target)
            # Record the result before charging for it. The work is done and
            # graded by this point; the charge that trips the ceiling stops the
            # cases after this one, and must not discard this one's evidence.
            results.append(r)
            if r.trajectory is not None:
                try:
                    budget.charge(r.trajectory.cost_usd)
                except BudgetExceeded:
                    exceeded = True
    return SuiteResult(
        suite=suite,
        target=target.name,
        started_at=started,
        finished_at=_now(),
        cases=tuple(results),
        metrics=compute_metrics(results),
        meta={"budget_exceeded": exceeded, "spent_usd": budget.spent_usd},
    )
