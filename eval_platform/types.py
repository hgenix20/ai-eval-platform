"""Core value types shared by targets, suites, graders, gate, and reports.

Trajectories and results are frozen dataclasses: once a run has happened its
record does not change. Cases and expectations are pydantic models because
they cross a boundary (YAML written by people) and must be validated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

StepKind = Literal["model", "tool", "approval", "error"]
TOOLS_USED_MODES = ("strict", "subset_of", "unordered")


@dataclass(frozen=True)
class Step:
    kind: StepKind
    name: str
    input: Any
    output: Any
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class Trajectory:
    target: str
    goal: str
    steps: tuple[Step, ...]
    status: str
    answer: str | None
    side_effects: tuple[dict[str, Any], ...]
    cost_usd: float
    wall_ms: float
    meta: dict[str, Any] = field(default_factory=dict)

    def tools_used(self) -> list[str]:
        """Names of "tool" steps, in the order they occurred."""
        return [s.name for s in self.steps if s.kind == "tool"]

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict form of this trajectory: nested dataclasses become dicts and
        tuples become lists (dataclasses.asdict), so the result is JSON-serializable."""
        return asdict(self)


class Expect(BaseModel):
    """A case's pass/fail assertions, checked against the run's Trajectory.

    Each field is an independent, optional assertion; unset fields are not
    checked. `status` and `answer_contains` compare against the trajectory's
    `status` and `answer`. `side_effects` is the expected count of recorded
    side effects. `history_types` is the expected sequence of step kinds.
    `max_steps_used` is the maximum number of steps the run may have taken.
    `tools_used` asserts on `Trajectory.tools_used()` and must carry exactly
    one of three modes: `{"strict": [...]}` (must equal exactly, in order),
    `{"subset_of": [...]}` (every tool used must be in this list), or
    `{"unordered": [...]}` (must use exactly these tools, any order).
    """

    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    answer_contains: str | None = None
    side_effects: int | None = None
    history_types: list[str] | None = None
    max_steps_used: int | None = None
    tools_used: dict[str, list[str]] | None = None

    @field_validator("tools_used")
    @classmethod
    def _one_known_mode(cls, v: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        """tools_used must carry exactly one recognized mode key, or None."""
        if v is None:
            return v
        if len(v) != 1 or next(iter(v)) not in TOOLS_USED_MODES:
            raise ValueError(f"tools_used must have exactly one of {TOOLS_USED_MODES}")
        return v


class Case(BaseModel):
    """One test case: a goal to pursue plus the expectations to grade it against.

    `planner` and `validator` are scripted model replies, consumed in order by
    the agent platform's fake providers, so a case can force a specific path
    through the agent loop without calling a real model. `target_requirements`
    gates which targets the case may run on: it runs only on a target whose
    declared capabilities include every entry in this list. `script` is the
    step list a `ScriptedTarget` replays instead of running an agent; it is
    only used when the target is scripted. `max_steps` caps the agent loop,
    the maximum number of steps a target may take before it is forced to stop.
    """

    model_config = ConfigDict(extra="forbid")
    name: str
    goal: str
    planner: list[str] = []
    validator: list[str] = []
    max_steps: int = 5
    target_requirements: list[str] = ["agent"]
    script: list[dict[str, Any]] | None = None
    expect: Expect


@dataclass(frozen=True)
class Grade:
    """One dimension's score for a case: a named metric, its value in [0, 1],
    whether that value clears the dimension's pass threshold, and why."""

    dimension: str
    value: float
    passed: bool
    explanation: str

    def __post_init__(self) -> None:
        """Grade values are a normalized score; anything outside [0, 1] is a caller bug."""
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"grade value {self.value} outside [0, 1]")


@dataclass(frozen=True)
class CaseResult:
    """The outcome of running one Case: its grades and the trajectory they were
    computed from, or, when `skipped_reason` is set, that the case was not
    scored at all (no matching target, missing dependency, etc.) and `grades`
    and `trajectory` carry no result."""

    name: str
    passed: bool
    grades: tuple[Grade, ...]
    trajectory: Trajectory | None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class SuiteResult:
    """The outcome of running a full suite against one target: every case's
    result, the run window, aggregate metrics (see compute_metrics), and any
    extra metadata."""

    suite: str
    target: str
    started_at: str
    finished_at: str
    cases: tuple[CaseResult, ...]
    metrics: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict form of this result: nested dataclasses become dicts and
        tuples become lists (dataclasses.asdict), so the result is JSON-serializable."""
        return asdict(self)


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank-with-interpolation percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def compute_metrics(cases: Sequence[CaseResult]) -> dict[str, float]:
    """Suite-level metrics. Skipped cases count in cases_total and cases_skipped
    and are excluded from pass_rate, cost, and latency."""
    scored = [c for c in cases if c.skipped_reason is None]
    trajs = [c.trajectory for c in scored if c.trajectory is not None]
    costs = [t.cost_usd for t in trajs]
    walls = [t.wall_ms for t in trajs]
    passed = sum(c.passed for c in scored)
    return {
        "cases_total": float(len(cases)),
        "cases_passed": float(passed),
        "cases_skipped": float(len(cases) - len(scored)),
        "pass_rate": (passed / len(scored)) if scored else 0.0,
        "usd_per_run_p50": _percentile(costs, 0.5),
        "wall_ms_p50": _percentile(walls, 0.5),
        "wall_ms_p95": _percentile(walls, 0.95),
    }
