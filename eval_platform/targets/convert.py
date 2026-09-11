"""Agent platform run dict -> Trajectory. Shared by the in-process and HTTP
targets so both produce identical step shapes."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from eval_platform.types import Step, Trajectory

_ERROR_TYPES = {"protocol_error", "tool_denied", "tool_unknown", "validator_feedback"}
# Which key on a history entry carries its human-readable detail, by error type.
_ERROR_DETAIL_KEYS = {
    "protocol_error": "detail",
    "validator_feedback": "reason",
    "tool_denied": "tool",
    "tool_unknown": "tool",
}


def run_dict_to_trajectory(
    run: dict[str, Any],
    *,
    target: str,
    goal: str,
    wall_ms: float,
    cost_usd: float,
    side_effects: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> Trajectory:
    """Convert one agent-platform run record into a `Trajectory`.

    `run["history"]` entries are mapped by their `type`: `tool_result` becomes
    a `Step(kind="tool")`, `proposed_answer` becomes `Step(kind="model",
    name="proposed_answer")`, and `protocol_error` / `tool_denied` /
    `tool_unknown` / `validator_feedback` each become `Step(kind="error",
    name=<type>)` with `error` read from the key that type actually carries
    (`detail` for `protocol_error`, `reason` for `validator_feedback`, `tool`
    for `tool_denied` and `tool_unknown`), falling back to the type name if
    that key is missing. Any other type is kept as a `Step(kind="model")` so
    no history entry is dropped. `run["outcome"]` supplies `status` (missing,
    `None`, or empty all become `"failed"`) and `answer`. `side_effects` is
    supplied by the caller, not read from `run`, since the agent platform
    reports them separately from the history.

    `tool_calls` is the ordered list of `{"tool": name, "arguments": args}`
    entries recorded as handlers actually ran (see `build_world`). Each
    history entry's `tool_result` history carries only `tool` and `output`,
    not the arguments that produced it, so `Step.input` is filled by
    matching the i-th `tool_result` for a given tool name to the i-th
    recorded call for that same name, in order. A gated tool that parked
    waiting for approval never reached its handler, so it has no recorded
    call; any `tool_result` left without a matching call keeps `input=None`.

    Sets `meta["steps_used"]` and `meta["history_types"]` (the ordered list
    of raw history type strings) because graders key off both.
    """
    calls_by_tool: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for call in tool_calls or []:
        calls_by_tool[call["tool"]].append(call["arguments"])

    steps: list[Step] = []
    for h in run.get("history", []):
        kind = h.get("type", "")
        if kind == "tool_result":
            queue = calls_by_tool.get(h["tool"])
            tool_input = queue.popleft() if queue else None
            steps.append(
                Step(kind="tool", name=h["tool"], input=tool_input, output=h.get("output"))
            )
        elif kind == "proposed_answer":
            steps.append(
                Step(kind="model", name="proposed_answer", input=None, output=h.get("answer"))
            )
        elif kind in _ERROR_TYPES:
            detail = h.get(_ERROR_DETAIL_KEYS[kind], kind)
            steps.append(Step(kind="error", name=kind, input=None, output=None, error=str(detail)))
        else:
            steps.append(Step(kind="model", name=kind or "unknown", input=None, output=h))
    outcome = run.get("outcome") or {}
    return Trajectory(
        target=target,
        goal=goal,
        steps=tuple(steps),
        status=outcome.get("status") or "failed",
        answer=outcome.get("answer"),
        side_effects=tuple(side_effects or []),
        cost_usd=cost_usd,
        wall_ms=wall_ms,
        meta={
            "steps_used": run.get("steps_used", 0),
            "history_types": [h.get("type") for h in run.get("history", [])],
        },
    )
