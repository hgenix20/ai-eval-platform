"""A second grading pass over a run that already happened (design spec 4.5).

Judges and semantic graders never run inside `run_suite`: the answering
model and the judge model would be resident together, and a rerun would
pay for both. `apply` reads a stored SuiteResult back, grades each case
with each grader, and returns a new SuiteResult carrying the added grades,
recomputed case verdicts, and recomputed metrics. The run window
(`started_at`, `finished_at`) is the original run's and is left alone: the
judge pass measures that run, it is not a new one.

Graders run one at a time over every case, then the next grader, and each
grader that offers `release()` is released before the next one loads, so
two local judge models never sit in GPU memory together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from eval_platform.graders.base import Grader
from eval_platform.types import (
    JUDGE_DIMENSION_PREFIX,
    JUDGE_UNKNOWN_VALUE,
    Case,
    CaseResult,
    Grade,
    SuiteResult,
    Trajectory,
    compute_metrics,
)


def case_passed(grades: Sequence[Grade]) -> bool:
    """Whether a case passes once judge and semantic grades are in.

    Every deterministic grade must pass, as it always had to. A judge grade
    passes the case when it passed or when the judge returned unknown: an
    unknown is a judge declining to label the case, and a case must not fail
    on the absence of evidence. Every other added dimension, `unsupported_claims`
    included, has no unknown state and fails the case when it did not pass.
    """
    for g in grades:
        if g.dimension.startswith(JUDGE_DIMENSION_PREFIX):
            if not g.passed and g.value != JUDGE_UNKNOWN_VALUE:
                return False
        elif not g.passed:
            return False
    return True


def _place(grades: list[Grade], grade: Grade) -> None:
    """Add `grade` to `grades`, replacing any grade on the same dimension.
    Re-judging a run is idempotent: the second pass overwrites the first
    pass's verdict instead of adding a second one beside it."""
    for i, existing in enumerate(grades):
        if existing.dimension == grade.dimension:
            grades[i] = grade
            return
    grades.append(grade)


def _release(grader: Grader) -> None:
    """Let go of whatever `grader` loaded, when it offers `release()`."""
    release = getattr(grader, "release", None)
    if callable(release):
        release()


def apply(
    result: SuiteResult,
    cases_by_name: dict[str, Case],
    graders: Sequence[Grader],
    *,
    sample: int | None = None,
) -> SuiteResult:
    """Grade `result`'s scored cases with every grader in `graders` and
    return the updated SuiteResult.

    A scored case is one that ran and produced a trajectory; skipped cases
    are left exactly as they were, grades, verdict, and all. `sample` keeps
    only the first N scored cases, in the order the suite ran them, for a
    cheap partial pass; None grades all of them.

    Each grader produces one Grade per graded case, replacing any earlier
    grade on the same dimension, so running this twice leaves one grade per
    dimension. Each graded case's `passed` is recomputed by `case_passed`
    over its full grade list, and the suite's metrics by `compute_metrics`.
    `meta["judge_pass"]` records which graders ran, at which versions, when,
    and the sample size.

    Failure mode: raises ValueError naming every case that is not in
    `cases_by_name`, before any grader runs. A judge needs the case's own
    goal and expectations to build its prompt, so a results file and a suite
    directory that have drifted apart must not be graded against each other.
    """
    scored: list[tuple[int, CaseResult, Trajectory]] = [
        (i, c, c.trajectory)
        for i, c in enumerate(result.cases)
        if c.skipped_reason is None and c.trajectory is not None
    ]
    if sample is not None:
        scored = scored[:sample]
    missing = [c.name for _, c, _ in scored if c.name not in cases_by_name]
    if missing:
        raise ValueError(f"cases not found in the suite files: {', '.join(missing)}")

    graded: dict[int, list[Grade]] = {i: list(c.grades) for i, c, _ in scored}
    for grader in graders:
        for i, c, trajectory in scored:
            _place(graded[i], grader.grade(cases_by_name[c.name], trajectory))
        _release(grader)

    cases = tuple(
        replace(c, grades=tuple(graded[i]), passed=case_passed(graded[i])) if i in graded else c
        for i, c in enumerate(result.cases)
    )
    meta: dict[str, Any] = dict(result.meta)
    meta["judge_pass"] = {
        "graders": [g.id for g in graders],
        "versions": {g.id: g.version for g in graders},
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sample": sample,
    }
    return SuiteResult(
        suite=result.suite,
        target=result.target,
        started_at=result.started_at,
        finished_at=result.finished_at,
        cases=cases,
        metrics=compute_metrics(cases),
        meta=meta,
    )
