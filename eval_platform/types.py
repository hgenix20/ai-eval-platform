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
        return asdict(self)


class Expect(BaseModel):
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
    name: str
    passed: bool
    grades: tuple[Grade, ...]
    trajectory: Trajectory | None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class SuiteResult:
    suite: str
    target: str
    started_at: str
    finished_at: str
    cases: tuple[CaseResult, ...]
    metrics: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
    return {
        "cases_total": float(len(cases)),
        "cases_passed": float(sum(c.passed for c in scored)),
        "cases_skipped": float(len(cases) - len(scored)),
        "pass_rate": (sum(c.passed for c in scored) / len(scored)) if scored else 0.0,
        "usd_per_run_p50": _percentile(costs, 0.5),
        "wall_ms_p50": _percentile(walls, 0.5),
        "wall_ms_p95": _percentile(walls, 0.95),
    }
