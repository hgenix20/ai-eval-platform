"""The grader contract every grader kind satisfies (design spec 4.5)."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from eval_platform.types import Case, Grade, Trajectory

GraderKind = Literal["deterministic", "semantic", "judge"]


class Grader(Protocol):
    """A grader turns one (case, trajectory) pair into one Grade.

    `kind` says what the grade costs and how much to trust it: a
    deterministic grader never calls a model; a semantic grader runs a
    local classifier or embedder; a judge grader calls a pinned model
    with a rubric. `version` changes whenever the grader's output could
    change for the same input (a rubric edit, a new model snapshot), and
    is part of every judge cache key.
    """

    id: str
    kind: GraderKind
    version: str

    def grade(self, case: Case, trajectory: Trajectory) -> Grade: ...


@runtime_checkable
class Releasable(Protocol):
    """A grader that holds something expensive and can let go of it.

    `release()` drops whatever the grader loaded (a model handle, the GPU
    memory behind it) and leaves the grader usable: a later `grade()` call
    loads again. It is the contract `judge_pass.apply` checks for between
    graders, so two local judges never sit in memory together. Graders that
    load nothing do not implement it, and `apply` passes over them.

    Runtime-checkable, so `isinstance(grader, Releasable)` is the test; it
    confirms the attribute is there, not its signature.
    """

    def release(self) -> None: ...
