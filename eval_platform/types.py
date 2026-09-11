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
    `forbidden_tools` fails the dimension if any of these tool names was
    called. `max_redundant_calls` caps the count of (tool, arguments) pairs
    called more than once. `reference_steps` is the ideal number of tool
    calls for the goal, used to compute step efficiency. `min_step_efficiency`
    is the minimum `reference_steps / max(tools_used, reference_steps)` the
    run must reach; `reference_steps: 0` yields efficiency 0.0, so the
    dimension passes only when `min_step_efficiency` is unset or 0.0.
    `tool_output_contains` asserts that some tool step named `tool` produced
    output containing `text`. `recovered` asserts on the case's injected
    faults (see `Case.faults`): True means at least one fault fired and
    every other emitted dimension passed; False means either no fault
    fired or the run did not complete. It is computed last, after every
    other dimension in this class.
    """

    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    answer_contains: str | None = None
    side_effects: int | None = None
    history_types: list[str] | None = None
    max_steps_used: int | None = None
    tools_used: dict[str, list[str]] | None = None
    forbidden_tools: list[str] | None = None
    max_redundant_calls: int | None = None
    reference_steps: int | None = None
    min_step_efficiency: float | None = None
    tool_output_contains: dict[str, str] | None = None
    recovered: bool | None = None

    @field_validator("tools_used")
    @classmethod
    def _one_known_mode(cls, v: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        """tools_used must carry exactly one recognized mode key, or None."""
        if v is None:
            return v
        if len(v) != 1 or next(iter(v)) not in TOOLS_USED_MODES:
            raise ValueError(f"tools_used must have exactly one of {TOOLS_USED_MODES}")
        return v

    @field_validator("tool_output_contains")
    @classmethod
    def _tool_and_text_keys(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        """tool_output_contains must carry exactly {"tool", "text"}, both non-empty
        strings, or None; this keeps grade_expect's dict lookups from raising a
        KeyError on a malformed case."""
        if v is None:
            return v
        if set(v) != {"tool", "text"} or not all(isinstance(x, str) and x for x in v.values()):
            raise ValueError("tool_output_contains needs exactly the keys tool and text")
        return v


class Fault(BaseModel):
    """One injected misbehavior at a single seam: a tool handler or a
    scripted provider. A fault fires for the first `times` calls to its
    own seam, in call order, then the seam behaves normally.

    `at` names the kind of seam: "tool" targets a tool handler by name;
    "provider" targets a scripted provider by name ("planner" or
    "validator"). `kind` is what happens while the fault is active:
    - raise: the tool handler raises RuntimeError. Meaningful for tools only.
    - malformed: the tool handler returns a value that is not the shape
      the model expects, rendered as the text "<<malformed>>". Tools only.
    - empty: the tool handler returns "". Tools only.
    - delay: the seam sleeps `delay_ms` milliseconds, then does its real
      work. Meaningful for both tools and providers.
    - retryable_error: the provider raises ProviderError(retryable=True),
      so the gateway may fall back to the next route step. Providers only.
    - fatal_error: the provider raises ProviderError(retryable=False),
      ending the run. Providers only.
    - truncated: the provider's real reply is cut to its first 12
      characters before being returned. Providers only.

    `times` counts calls to this fault's own seam, never calls to a
    fallback the platform substitutes for it. `seed` is recorded on every
    firing but not otherwise used; it is reserved for a future randomized
    fault schedule.
    """

    model_config = ConfigDict(extra="forbid")
    at: Literal["tool", "provider"]
    name: str
    kind: Literal[
        "raise", "malformed", "empty", "delay", "retryable_error", "fatal_error", "truncated"
    ]
    times: int = 1
    seed: int = 0
    delay_ms: int = 0


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
    `faults` are the misbehaviors the target wires into its tools and
    providers before the run starts; empty by default, meaning no faults.
    """

    model_config = ConfigDict(extra="forbid")
    name: str
    goal: str
    planner: list[str] = []
    validator: list[str] = []
    max_steps: int = 5
    target_requirements: list[str] = ["agent"]
    script: list[dict[str, Any]] | None = None
    faults: list[Fault] = []
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
    and are excluded from pass_rate, cost, and latency. `step_efficiency_mean`
    is the mean of the `step_efficiency` grade value over scored cases that
    carry that dimension; it is omitted when no case carries one.
    `recovery_rate` is passed / scored over scored cases that carry a
    `recovered` grade; it is omitted when no case carries one."""
    scored = [c for c in cases if c.skipped_reason is None]
    trajs = [c.trajectory for c in scored if c.trajectory is not None]
    costs = [t.cost_usd for t in trajs]
    walls = [t.wall_ms for t in trajs]
    passed = sum(c.passed for c in scored)
    step_efficiencies = [
        g.value for c in scored for g in c.grades if g.dimension == "step_efficiency"
    ]
    recovered_grades = [g for c in scored for g in c.grades if g.dimension == "recovered"]
    metrics = {
        "cases_total": float(len(cases)),
        "cases_passed": float(passed),
        "cases_skipped": float(len(cases) - len(scored)),
        "pass_rate": (passed / len(scored)) if scored else 0.0,
        "usd_per_run_p50": _percentile(costs, 0.5),
        "wall_ms_p50": _percentile(walls, 0.5),
        "wall_ms_p95": _percentile(walls, 0.95),
    }
    if step_efficiencies:
        metrics["step_efficiency_mean"] = sum(step_efficiencies) / len(step_efficiencies)
    if recovered_grades:
        metrics["recovery_rate"] = sum(g.passed for g in recovered_grades) / len(recovered_grades)
    return metrics
