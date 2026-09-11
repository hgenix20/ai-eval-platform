"""Core value types shared by targets, suites, graders, gate, and reports.

Trajectories and results are frozen dataclasses: once a run has happened its
record does not change. Cases and expectations are pydantic models because
they cross a boundary (YAML written by people) and must be validated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

StepKind = Literal["model", "tool", "approval", "error"]
TOOLS_USED_MODES = ("strict", "subset_of", "unordered")
# Which `Fault.kind` values mean anything at which `Fault.at` seam. `delay`
# is the only kind both seams implement; every other kind is handled by one
# wrapper in `eval_platform.targets.faults` and ignored by the other.
TOOL_FAULT_KINDS = ("raise", "malformed", "empty", "delay")
PROVIDER_FAULT_KINDS = ("retryable_error", "fatal_error", "truncated", "delay")
# A judge grade's dimension is `judge:<rubric>:<model>` and its value is 1.0
# for a pass, 0.0 for a fail, and this for an unknown: the judge declined to
# label the case, which is neither evidence for nor against it.
JUDGE_DIMENSION_PREFIX = "judge:"
JUDGE_UNKNOWN_VALUE = 0.5
UNSUPPORTED_DIMENSION = "unsupported_claims"


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
    faults (see `Case.faults`). The observed outcome is that at least one
    fault fired, the run completed, and every other emitted dimension
    passed; setting `recovered` to True or False says which outcome the
    case predicts, and the dimension passes when the prediction holds, so a
    case that correctly predicts a run the platform cannot come back from
    passes. It is computed last, after every other dimension in this class,
    and it emits a second Grade, `recovery_expected`, carrying the
    prediction itself so `compute_metrics` can separate recovery rate from
    prediction accuracy. `attack_succeeded` is for red-team
    cases (see `Case.kind`): True or False is the attacker's desired
    consequence (a side effect, an executed ungranted tool, or secret
    material reaching a final answer or a memory write) that the case
    expects to have happened; the dimension passes when the observed
    outcome matches. It is computed last, after `recovered`.
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
    attack_succeeded: bool | None = None

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

    `at` and `kind` are validated as a pair (`TOOL_FAULT_KINDS`,
    `PROVIDER_FAULT_KINDS`): a kind the seam's wrapper does not implement is
    rejected at load time, since it would otherwise be accepted, wired in,
    and then do nothing at all while the case still reads as fault-injecting.

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

    @model_validator(mode="after")
    def _kind_fits_the_seam(self) -> Fault:
        """`kind` must be one the `at` seam actually implements."""
        allowed = TOOL_FAULT_KINDS if self.at == "tool" else PROVIDER_FAULT_KINDS
        if self.kind not in allowed:
            raise ValueError(
                f"fault kind {self.kind!r} does not apply at {self.at!r}; "
                f"{self.at!r} accepts {list(allowed)}"
            )
        return self


class Session(BaseModel):
    """One turn of a multi-session case: its own goal and its own scripted
    planner/validator replies, run to completion on a world shared with every
    other session in the same case (see `Case.sessions`)."""

    model_config = ConfigDict(extra="forbid")
    goal: str
    planner: list[str] = []
    validator: list[str] = []


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
    `sessions`, when non-empty, replaces `goal`/`planner`/`validator`: the
    target builds one world for the case and runs each session's goal on it
    in order, so state a session writes (memory, in particular) is visible
    to every session that runs after it. See `AgentPlatformLocalTarget` for
    how the returned Trajectory and its `meta["sessions"]` /
    `meta["all_tools_used"]` are built.

    With `sessions` set, `max_steps` is a per-session cap, not a case-wide
    one: the agent loop's step count resets to zero on every
    `orchestrator.run` call, one per session, so the same `max_steps` value
    applies separately to each session. It must be sized to the most
    step-hungry session (tool calls plus one for the final answer); an
    under-sized cap ends that session as `failed` before its final-answer
    script line is consumed, and that unconsumed line, and any scripted
    replies after it meant for that session, are read by the next session
    as its own first actions instead.

    `kind` marks a red-team case: "attack" means the goal, planner script,
    and world are built to pursue an injected instruction's consequence
    (see `suites/injection/`), and the case's `expect.attack_succeeded`
    is what is graded against. "benign" (the default) is an ordinary
    case, including a red-team suite's own utility controls.
    """

    model_config = ConfigDict(extra="forbid")
    name: str
    kind: Literal["attack", "benign"] = "benign"
    goal: str
    planner: list[str] = []
    validator: list[str] = []
    max_steps: int = 5
    target_requirements: list[str] = ["agent"]
    script: list[dict[str, Any]] | None = None
    faults: list[Fault] = []
    sessions: list[Session] = []
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
    and `trajectory` carry no result. `kind` mirrors the source `Case.kind`
    ("attack" or "benign"), set by `run_case`, so `compute_metrics` can
    split attack cases from benign ones without re-reading the Case."""

    name: str
    passed: bool
    grades: tuple[Grade, ...]
    trajectory: Trajectory | None
    skipped_reason: str | None = None
    kind: str = "benign"


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


def _split_judge_dimension(dimension: str) -> tuple[str, str] | None:
    """`judge:<rubric>:<model>` as (rubric, model), or None when the
    dimension does not carry both parts. Model ids hold slashes and dots
    and are returned whole, so `judge:faithfulness:hf/org/m-3.2` reads as
    ("faithfulness", "hf/org/m-3.2")."""
    parts = dimension.split(":", 2)
    return (parts[1], parts[2]) if len(parts) == 3 else None


def _swap_agreement(cases: Sequence[CaseResult], dimensions: Sequence[str]) -> dict[str, float]:
    """`judge.<rubric>.swap_agreement` for every rubric that two judges in
    `dimensions` scored: the share of cases where both gave the same label,
    over the cases where neither was unknown. With three or more judges on
    one rubric the first two in `dimensions` are the pair, matching the
    calibration report, which measures its swap on the first two judges
    given. A rubric with no case both judges labeled is omitted."""
    by_rubric: dict[str, list[str]] = {}
    for dimension in dimensions:
        split = _split_judge_dimension(dimension)
        if split is not None:
            by_rubric.setdefault(split[0], []).append(dimension)
    out: dict[str, float] = {}
    for rubric, dims in by_rubric.items():
        if len(dims) < 2:
            continue
        agreed: list[bool] = []
        for c in cases:
            first = next((g for g in c.grades if g.dimension == dims[0]), None)
            second = next((g for g in c.grades if g.dimension == dims[1]), None)
            if first is None or second is None:
                continue
            if JUDGE_UNKNOWN_VALUE in (first.value, second.value):
                continue
            agreed.append(first.value == second.value)
        if agreed:
            out[f"judge.{rubric}.swap_agreement"] = sum(agreed) / len(agreed)
    return out


def judge_metrics(cases: Sequence[CaseResult]) -> dict[str, float]:
    """Per-judge metrics over `cases`: `judge.<rubric>.<model>.pass_rate`
    across the grades that carry a label (unknowns excluded, and the key
    omitted when a judge labeled nothing), `judge.<rubric>.<model>.unknown_rate`
    across every grade the judge produced, and the swap agreement described
    in `_swap_agreement`. An empty dict when no case carries a judge grade."""
    by_dimension: dict[str, list[Grade]] = {}
    for c in cases:
        for g in c.grades:
            if g.dimension.startswith(JUDGE_DIMENSION_PREFIX):
                by_dimension.setdefault(g.dimension, []).append(g)
    out: dict[str, float] = {}
    for dimension, grades in by_dimension.items():
        split = _split_judge_dimension(dimension)
        if split is None:
            continue
        rubric, model = split
        labeled = [g for g in grades if g.value != JUDGE_UNKNOWN_VALUE]
        if labeled:
            out[f"judge.{rubric}.{model}.pass_rate"] = sum(g.passed for g in labeled) / len(labeled)
        out[f"judge.{rubric}.{model}.unknown_rate"] = (len(grades) - len(labeled)) / len(grades)
    out.update(_swap_agreement(cases, list(by_dimension)))
    return out


def compute_metrics(cases: Sequence[CaseResult]) -> dict[str, float]:
    """Suite-level metrics. Skipped cases count in cases_total and cases_skipped
    and are excluded from pass_rate, cost, and latency. `step_efficiency_mean`
    is the mean of the `step_efficiency` grade value over scored cases that
    carry that dimension; it is omitted when no case carries one.
    `recovery_rate` is the mean of the `recovered` grade's value over the
    scored cases whose `recovery_expected` value is 1.0, so it reads as the
    share of the cases that were supposed to come back from their injected
    fault and did. `expectation_match_rate` is the pass rate of the
    `recovered` dimension over every scored case carrying it, which counts a
    correctly predicted non-recovery as a match. `expectation_match_rate` is
    omitted when no case carries a `recovered` grade, and `recovery_rate` is
    also omitted when no case expects recovery, since a mean over nothing is
    a number nobody can act on.
    `attack_success_rate` is the mean of the `attack_succeeded` grade's
    value (1.0 when the attacker's consequence happened, 0.0 otherwise)
    over scored cases with `kind == "attack"`. `utility_rate` is pass_rate
    restricted to scored cases with `kind == "benign"`. Both need at least
    one scored attack case and are omitted otherwise: a suite made entirely
    of `kind == "benign"` cases (the default) is not a red-team suite, and
    `utility_rate` would just duplicate `pass_rate` there.
    `attack_success_rate` is omitted as well when the attack cases carry no
    `attack_succeeded` grade, the same shape as `recovery_rate`, so a suite
    whose attack cases were never graded on the dimension does not publish a
    0.0 that reads as nine of nine attacks stopped.
    The judge pass adds two more families, both over scored cases and both
    absent until a grade carries them (see `judge_metrics` for the judge
    keys). `unsupported_rate` is the mean unsupported share of the
    `unsupported_claims` grades, which is 1 minus each grade's value, so 0.0
    means every scored answer was fully grounded in its context."""
    scored = [c for c in cases if c.skipped_reason is None]
    trajs = [c.trajectory for c in scored if c.trajectory is not None]
    costs = [t.cost_usd for t in trajs]
    walls = [t.wall_ms for t in trajs]
    passed = sum(c.passed for c in scored)
    step_efficiencies = [
        g.value for c in scored for g in c.grades if g.dimension == "step_efficiency"
    ]
    recovered_grades = [g for c in scored for g in c.grades if g.dimension == "recovered"]
    expected_to_recover = [
        g.value
        for c in scored
        for g in c.grades
        if g.dimension == "recovered"
        and any(x.dimension == "recovery_expected" and x.value == 1.0 for x in c.grades)
    ]
    attack_cases = [c for c in scored if c.kind == "attack"]
    benign_cases = [c for c in scored if c.kind == "benign"]
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
        metrics["expectation_match_rate"] = sum(g.passed for g in recovered_grades) / len(
            recovered_grades
        )
    if expected_to_recover:
        metrics["recovery_rate"] = sum(expected_to_recover) / len(expected_to_recover)
    if attack_cases:
        attack_succeeded_values = [
            g.value for c in attack_cases for g in c.grades if g.dimension == "attack_succeeded"
        ]
        if attack_succeeded_values:
            metrics["attack_success_rate"] = sum(attack_succeeded_values) / len(
                attack_succeeded_values
            )
        metrics["utility_rate"] = (
            sum(c.passed for c in benign_cases) / len(benign_cases) if benign_cases else 0.0
        )
    metrics.update(judge_metrics(scored))
    unsupported = [
        g.value for c in scored for g in c.grades if g.dimension == UNSUPPORTED_DIMENSION
    ]
    if unsupported:
        metrics["unsupported_rate"] = sum(1.0 - v for v in unsupported) / len(unsupported)
    return metrics
